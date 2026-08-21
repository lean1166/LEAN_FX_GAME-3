from trading_round import OPEN, RESOLVED, add_viewer_level, create_round, resolve_round


def candle(high, low):
    return {"high": high, "low": low}


def test_buy_rr1_tp1_closes_sell():
    round_data = create_round(1, 100, 10, 4, bot_rr=1)
    events = resolve_round(round_data, candle(110, 101))
    assert round_data["winner_side"] == "BUY"
    assert round_data["sides"]["SELL"]["close_reason"] == "OPPOSITE_TP1"
    assert any(e["type"] == "ROUND_TP1" for e in events)


def test_sell_rr1_tp1_closes_buy():
    round_data = create_round(2, 100, 10, 4, bot_rr=1)
    resolve_round(round_data, candle(99, 90))
    assert round_data["winner_side"] == "SELL"
    assert round_data["sides"]["BUY"]["close_reason"] == "OPPOSITE_TP1"


def test_buy_rr2_physical_tp1_closes_sell():
    round_data = create_round(3, 100, 10, 4)
    add_viewer_level(round_data, "BUY", 2, "ana")
    resolve_round(round_data, candle(110, 101))
    assert round_data["winner_side"] == "BUY"
    assert round_data["sides"]["BUY"]["tp1_price"] == 110
    assert round_data["sides"]["SELL"]["resolved"]


def test_sell_rr3_physical_tp1_closes_buy():
    round_data = create_round(4, 100, 10, 4)
    add_viewer_level(round_data, "SELL", 3, "bea")
    resolve_round(round_data, candle(99, 90))
    assert round_data["winner_side"] == "SELL"
    assert round_data["sides"]["SELL"]["tp1_price"] == 90
    assert round_data["sides"]["BUY"]["resolved"]


def test_both_sides_share_one_round_and_views_cannot_duplicate_resolution():
    round_data = create_round(5, 100, 10, 4, bot_rr=2)
    active_trade = viewer_trade_active = round_data  # derived compatibility views
    first = resolve_round(active_trade, candle(110, 101))
    second = resolve_round(viewer_trade_active, candle(110, 101))
    assert active_trade is viewer_trade_active
    assert len([e for e in first if e["type"] == "ROUND_RESOLVED"]) == 1
    assert second == []


def test_tp1_and_sl_same_candle_prefers_sl_for_that_side():
    round_data = create_round(6, 100, 10, 4, bot_rr=2)
    resolve_round(round_data, candle(120, 90))
    assert round_data["resolution_reason"] == "DOUBLE_SL"
    assert round_data["winner_side"] is None


def test_tp1_and_tp2_same_candle_resolves_only_tp1_once():
    round_data = create_round(7, 100, 10, 4)
    add_viewer_level(round_data, "BUY", 2, "ana")
    events = resolve_round(round_data, candle(121, 101))
    assert round_data["winner_side"] == "BUY"
    assert len([e for e in events if e["type"] == "ROUND_TP1"]) == 1
    assert resolve_round(round_data, candle(121, 101)) == []


def test_closed_round_cannot_recreate_opposite_side_or_process_twice():
    round_data = create_round(8, 100, 10, 4)
    resolve_round(round_data, candle(110, 101))
    add_viewer_level(round_data, "SELL", 3, "bea")
    assert round_data["status"] == RESOLVED
    assert not round_data["sides"]["SELL"]["levels"]
    assert resolve_round(round_data, candle(99, 90)) == []
