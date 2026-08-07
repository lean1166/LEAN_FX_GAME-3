"""Initial home screen with proper Order Block detection and mitigation logic."""

import pygame
import random

from app.charts.generator import generate_candles, trigger_market_exhaustion
from app.ui.grid import GridView
from app.ui.header import HeaderView


class HomeScreen:
    """Manages market flow, 2s intervals, and structural smart money validations."""

    def __init__(self, width: int, height: int) -> None:
        from app.charts.chart import ChartView

        self._width = width
        self._height = height
        self._grid = GridView(width, height)
        self._header = HeaderView(width)
        
        self._total_candles = generate_candles(100)
        self._chart = ChartView(width, height, self._total_candles)
        
        # CONTROLES DE TIEMPO ORIGINALES
        self._timer = pygame.time.get_ticks()
        self._fast_interval = 2000  
        self._reaction_interval = 20000  

        # VARIABLES DE INTERACCIÓN ORIGINALES
        self.buttons_active = False
        self.button_timer = 0
        self.time_left = 0
        self.last_broken_id = -1
        
        # LÓGICA DE ESTRUCTURA SMC SIMÉTRICA
        self.order_blocks = []  
        self._detect_initial_order_blocks()

        # ESTADÍSTICAS REALES VINCULADAS
        self.fxp_balance = 10000
        self.wins = 0
        self.losses = 0

    def _detect_initial_order_blocks(self) -> None:
        """Busca y actualiza dinámicamente los BOS alcistas o bajistas en base a fractales."""
        self.order_blocks = []
        total = len(self._total_candles)
        
        for i in range(total - 5, 12, -1):
            c_prev = self._total_candles[i]
            
            # --- DETECCIÓN DE BOS ALCISTA ---
            if c_prev["close"] < c_prev["open"]:  
                rango_fractal = self._total_candles[i-10:i]
                maximo_fractal = max(c["high"] for c in rango_fractal)
                
                idx_maximo_fractal = i - 10
                for idx, c in enumerate(rango_fractal):
                    if c["high"] == maximo_fractal:
                        idx_maximo_fractal = i - 10 + idx
                        break
                
                for j in range(i + 1, min(i + 15, total)):
                    if self._total_candles[j]["close"] > maximo_fractal:
                        self.order_blocks.append({
                            "type": "ALCISTA",
                            "high": c_prev["high"],
                            "low": c_prev["low"],
                            "id": i,
                            "bos_price": maximo_fractal,
                            "bos_id": j,
                            "fractal_idx": idx_maximo_fractal  
                        })
                        return  

            # --- DETECCIÓN DE BOS BAJISTA ---
            elif c_prev["close"] > c_prev["open"]:  
                rango_fractal = self._total_candles[i-10:i]
                minimo_fractal = min(c["low"] for c in rango_fractal)
                
                idx_minimo_fractal = i - 10
                for idx, c in enumerate(rango_fractal):
                    if c["low"] == minimo_fractal:
                        idx_minimo_fractal = i - 10 + idx
                        break
                
                for j in range(i + 1, min(i + 15, total)):
                    if self._total_candles[j]["close"] < minimo_fractal:
                        self.order_blocks.append({
                            "type": "BAJISTA",
                            "high": c_prev["high"],
                            "low": c_prev["low"],
                            "id": i,
                            "bos_price": minimo_fractal,
                            "bos_id": j,
                            "fractal_idx": idx_minimo_fractal  
                        })
                        return

    def draw(self, target: pygame.Surface) -> None:
        current_time = pygame.time.get_ticks()

        last_candle = self._total_candles[-1]
        tick_range = 1.5 if self.buttons_active else 0.6
        tick_movement = random.uniform(-tick_range, tick_range)
        last_candle["close"] += tick_movement
        
        if last_candle["close"] > last_candle["high"]:
            last_candle["high"] = last_candle["close"]
        if last_candle["close"] < last_candle["low"]:
            last_candle["low"] = last_candle["close"]

        valid_blocks = []
        for ob in self.order_blocks:
            if ob["type"] == "BAJISTA" and last_candle["close"] >= ob["high"]:
                continue  
            if ob["type"] == "ALCISTA" and last_candle["close"] <= ob["low"]:
                continue  
            valid_blocks.append(ob)
        self.order_blocks = valid_blocks

        if not self.order_blocks:
            self._detect_initial_order_blocks()

        # --- CORREGIDO: Acceso mediante el índice [0] para evitar el TypeError de raíz ---
        if self.order_blocks and not self._chart.active_trade:
            ob = self.order_blocks[0]  # Extraemos explícitamente el primer bloque como dict
            current_candle_id = len(self._total_candles)
            
            if ob["low"] <= last_candle["close"] <= ob["high"] and self.last_broken_id != current_candle_id:
                if not self.buttons_active:
                    self.buttons_active = True
                    self.button_timer = current_time
                    self.last_broken_id = current_candle_id

        if self._chart.active_trade:
            current_price = last_candle["close"]
            trade = self._chart.active_trade
            
            if trade["type"] == "BUY":
                trade["pnl"] = (current_price - trade["price"]) * 15.0
                if current_price >= trade["tp"]: 
                    # Congelar PnL al valor exacto del TP
                    trade["pnl"] = (trade["tp"] - trade["price"]) * 15.0
                    trigger_market_exhaustion(1) # Reacción bajista
                    self._close_position_auto(is_win=True)
                elif current_price <= trade["sl"]: 
                    self._close_position_auto(is_win=False)
            else:
                trade["pnl"] = (trade["price"] - current_price) * 15.0
                if current_price <= trade["tp"]: 
                    # Congelar PnL al valor exacto del TP
                    trade["pnl"] = (trade["price"] - trade["tp"]) * 15.0
                    trigger_market_exhaustion(-1) # Reacción alcista
                    self._close_position_auto(is_win=True)
                elif current_price >= trade["sl"]: 
                    self._close_position_auto(is_win=False)

        if self.buttons_active:
            elapsed = current_time - self.button_timer
            self.time_left = max(0, 20 - (elapsed // 1000))
            if elapsed >= self._reaction_interval:
                self.buttons_active = False
                self._timer = current_time

        mouse_pos = pygame.mouse.get_pos()
        mouse_x, mouse_y = mouse_pos, mouse_pos
        mouse_pressed = pygame.mouse.get_pressed()
        
        if mouse_pressed:
            btn_width = 200
            x_btn = self._width - 250
            
            if self.buttons_active:
                risk_distance = 45.0  
                reward_distance = risk_distance * 2.0  
                
                if x_btn <= mouse_x <= x_btn + btn_width and 585 <= mouse_y <= 635:
                    entry = last_candle["close"]
                    self._chart.active_trade = {"type": "BUY", "price": entry, "sl": entry - risk_distance, "tp": entry + reward_distance, "pnl": 0.0}
                    self.buttons_active = False
                    self._timer = current_time
                    pygame.time.wait(300)
                elif x_btn <= mouse_x <= x_btn + btn_width and 650 <= mouse_y <= 700:
                    entry = last_candle["close"]
                    self._chart.active_trade = {"type": "SELL", "price": entry, "sl": entry + risk_distance, "tp": entry - reward_distance, "pnl": 0.0}
                    self.buttons_active = False
                    self._timer = current_time
                    pygame.time.wait(300)
            
            elif self._chart.active_trade:
                if x_btn <= mouse_x <= x_btn + btn_width and 520 <= mouse_y <= 575:
                    self._close_position_auto(is_win=(self._chart.active_trade["pnl"] >= 0))

        if not self.buttons_active:
            if current_time - self._timer >= self._fast_interval:
                new_candles = generate_candles(1, base_price=last_candle["close"])
                self._total_candles.extend(new_candles)
                self._timer = current_time

        self._chart._candles = self._total_candles
        self._chart.buttons_active = self.buttons_active
        self._chart.time_left = self.time_left
        self._chart.order_blocks = self.order_blocks
        
        self._chart.fxp_balance = self.fxp_balance
        self._chart.wins = self.wins
        self._chart.losses = self.losses

        self._grid.draw(target)
        self._chart.draw(target)
        self._header.draw(target)

    def _close_position_auto(self, is_win: bool) -> None:
        final_pnl = int(self._chart.active_trade["pnl"])
        self.fxp_balance += final_pnl
        if is_win: self.wins += 1
        else: self.losses += 1
        self._chart.active_trade = None
        self._timer = pygame.time.get_ticks()
