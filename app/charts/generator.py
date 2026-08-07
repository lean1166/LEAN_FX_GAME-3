"""
Generador de velas para LEAN FX LIVE.

Genera un mercado continuo con:
- Tendencias largas
- Pullbacks naturales
- Volatilidad variable
- Sin límites artificiales de precio
"""

import random
from typing import Dict, List


class MarketState:
    def __init__(self):
        self.direction = random.choice([-1, 1])
        self.remaining = random.randint(18, 45)
        self.volatility = random.uniform(4, 9)
        self.exhaustion_active = False
        self.exhaustion_dir = 0

    def force_exhaustion(self, current_direction):
        """Activa un agotamiento/reacción natural."""
        self.exhaustion_active = True
        self.exhaustion_dir = -current_direction
        self.remaining = random.randint(5, 12)  # Duración corta del retroceso
        self.volatility = random.uniform(6, 12)  # Un poco más de volatilidad en el retroceso

    def update(self):
        self.remaining -= 1

        if self.remaining <= 0:
            if self.exhaustion_active:
                self.exhaustion_active = False
            
            self.direction *= -1
            self.remaining = random.randint(18, 45)
            self.volatility = random.uniform(4, 9)


_state = MarketState()


def trigger_market_exhaustion(current_direction: int):
    """Interfaz para forzar el agotamiento desde fuera."""
    _state.force_exhaustion(current_direction)

def generate_candles(
    count: int,
    base_price: float = 1000.0
) -> List[Dict[str, float]]:

    candles = []

    price = base_price

    for _ in range(count):

        _state.update()
        
        # Determinar dirección efectiva (respetar agotamiento si está activo)
        effective_dir = _state.exhaustion_dir if _state.exhaustion_active else _state.direction

        # 80% sigue tendencia o agotamiento
        # 20% hace pequeño pullback
        if random.random() < 0.80:
            body = random.uniform(
                _state.volatility * 0.5,
                _state.volatility * 1.5,
            ) * effective_dir
        else:
            body = random.uniform(
                1,
                _state.volatility * 0.7,
            ) * -effective_dir

        open_price = price

        close_price = open_price + body

        upper_wick = random.uniform(0.5, _state.volatility)

        lower_wick = random.uniform(0.5, _state.volatility)

        high = max(open_price, close_price) + upper_wick

        low = min(open_price, close_price) - lower_wick

        candles.append(
            {
                "open": round(open_price, 2),
                "high": round(high, 2),
                "low": round(low, 2),
                "close": round(close_price, 2),
            }
        )

        price = close_price

    return candles