"""Canonical trading-round model and its single resolution authority.

The resolver deliberately works on OHLC, not on UI state.  In a candle that
crosses more than one barrier, SL has priority over TP for the *same side*.
Across the two sides, a TP1 winner is selected deterministically: BUY first
when both physical TP1 barriers occur in the same OHLC candle.  This is an
explicit conservative tie-breaker; a candle has no tick ordering information.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List


OPEN = "OPEN"
RESOLVED = "RESOLVED"


def _side(direction: str, entry: float, risk_distance: float, entry_index: int,
          levels: Iterable[float], streamer: bool = False) -> Dict[str, Any]:
    sign = 1 if direction == "BUY" else -1
    return {
        "dir": direction,
        "tipo": direction,
        "entry": entry,
        "entry_index": entry_index,
        "sl": entry - sign * risk_distance,
        "tp1_price": entry + sign * risk_distance,
        "levels": [
            {"rr": float(rr), "tp": entry + sign * risk_distance * float(rr),
             "users": [], "streamer": streamer, "resolved": False}
            for rr in sorted(set(levels))
        ],
        "max_rr": float(max(levels, default=1.0)),
        "resolved": False,
        "close_reason": None,
        "flash": None,
        "be_armed": False,
    }


def create_round(round_id: int, entry: float, risk_distance: float, entry_index: int,
                 bot_rr: int = 0) -> Dict[str, Any]:
    """Create one round.  ``groups`` is a read-only compatibility view for UI."""
    if risk_distance <= 0:
        raise ValueError("risk_distance must be positive")
    bot_levels = range(1, bot_rr + 1) if bot_rr else []
    sides = {
        "BUY": _side("BUY", entry, risk_distance, entry_index, bot_levels, bool(bot_rr)),
        "SELL": _side("SELL", entry, risk_distance, entry_index, bot_levels, bool(bot_rr)),
    }
    return {
        "round_id": round_id,
        "status": OPEN,
        "entry": entry,
        "entry_index": entry_index,
        "risk_distance": risk_distance,
        "sides": sides,
        # UI compatibility only.  It is the exact same mapping, never a second owner.
        "groups": sides,
        "winner_side": None,
        "resolution_reason": None,
        "resolved_once": False,
        "has_bot": bool(bot_rr),
        "has_viewers": False,
    }


def add_viewer_level(round_data: Dict[str, Any], direction: str, rr: float, username: str) -> None:
    """Attach a viewer payout level without changing physical TP1."""
    if round_data["status"] != OPEN:
        return
    side = round_data["sides"][direction]
    rr = float(rr)
    for level in side["levels"]:
        if abs(level["rr"] - rr) < 0.05 and not level.get("streamer"):
            if username not in level["users"]:
                level["users"].append(username)
            round_data["has_viewers"] = True
            return
    sign = 1 if direction == "BUY" else -1
    side["levels"].append({"rr": rr, "tp": round_data["entry"] + sign * round_data["risk_distance"] * rr,
                           "users": [username], "streamer": False, "resolved": False})
    side["levels"].sort(key=lambda item: item["rr"])
    side["max_rr"] = max(side["max_rr"], rr)
    round_data["has_viewers"] = True


def _hit(direction: str, candle: Dict[str, float], price: float, kind: str) -> bool:
    if direction == "BUY":
        return candle["low"] <= price if kind == "SL" else candle["high"] >= price
    return candle["high"] >= price if kind == "SL" else candle["low"] <= price


def _close_side(side: Dict[str, Any], reason: str) -> None:
    side["resolved"] = True
    side["close_reason"] = reason


def resolve_round(round_data: Dict[str, Any], candle: Dict[str, float]) -> List[Dict[str, Any]]:
    """Resolve a round exactly once and return domain events for adapters.

    Priority: (1) SL before TP for each individual side; (2) after excluding
    sides stopped in this candle, physical TP1 decides the round; (3) if both
    TP1s remain possible in one OHLC candle, BUY wins deterministically.
    TP2+ never overrides TP1: a TP1 winner closes the round atomically.
    """
    if round_data is None or round_data.get("status") != OPEN or round_data.get("resolved_once"):
        return []
    if candle.get("high") is None or candle.get("low") is None:
        return []

    events: List[Dict[str, Any]] = []
    # A TP1 of one side is geometrically the opposite side's SL.  Therefore a
    # TP1 candidate wins over that *opposite* SL; only a same-side SL+TP1 wick
    # invalidates the candidate (conservative intrabar priority).
    same_side_sl = {direction: _hit(direction, candle, round_data["sides"][direction]["sl"], "SL")
                    for direction in ("BUY", "SELL")}
    tp1_hits = [direction for direction in ("BUY", "SELL")
                if not same_side_sl[direction]
                and _hit(direction, candle, round_data["sides"][direction]["tp1_price"], "TP")]
    if tp1_hits:
        winner = "BUY" if "BUY" in tp1_hits else "SELL"
        loser = "SELL" if winner == "BUY" else "BUY"
        winner_side = round_data["sides"][winner]
        loser_side = round_data["sides"][loser]
        _close_side(winner_side, "TP1")
        if not loser_side["resolved"]:
            _close_side(loser_side, "OPPOSITE_TP1")
            events.append({"type": "SIDE_CLOSED", "side": loser, "reason": "OPPOSITE_TP1", "side_data": loser_side})
        for level in winner_side["levels"]:
            level["resolved"] = True
        round_data["winner_side"] = winner
        round_data["resolution_reason"] = "TP1"
        events.append({"type": "ROUND_TP1", "side": winner, "reason": "TP1", "side_data": winner_side,
                       "levels": winner_side["levels"]})
    else:
        eligible: List[str] = []
        for direction in ("BUY", "SELL"):
            side = round_data["sides"][direction]
            if same_side_sl[direction]:
                _close_side(side, "SL")
                events.append({"type": "SIDE_SL", "side": direction, "reason": "SL", "side_data": side})
            else:
                eligible.append(direction)
        if not eligible:
            round_data["resolution_reason"] = "DOUBLE_SL"
        # A one-sided SL is terminal too: the dual contest has a surviving side,
        # but no TP1 winner occurred.  It is intentionally resolved atomically.
        survivor = eligible[0] if len(eligible) == 1 else None
        if survivor:
            _close_side(round_data["sides"][survivor], "OPPOSITE_SL")
            events.append({"type": "SIDE_CLOSED", "side": survivor, "reason": "OPPOSITE_SL",
                           "side_data": round_data["sides"][survivor]})
            round_data["resolution_reason"] = "SL"
        elif len(eligible) == 2:
            return []

    round_data["status"] = RESOLVED
    round_data["resolved_once"] = True
    events.append({"type": "ROUND_RESOLVED", "round_id": round_data["round_id"],
                   "winner_side": round_data["winner_side"], "reason": round_data["resolution_reason"]})
    return events
