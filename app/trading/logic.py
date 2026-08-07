import time

class Position:
    """
    Representa una operación individual (BUY o SELL) con su lógica de RR y colisiones.
    """
    STATUS_OPEN = "OPEN"
    STATUS_CLOSED = "CLOSED"

    def __init__(self, direction, entry_price, sl_price, rr_multipliers, start_index, users=None):
        self.direction = direction.upper()  # "BUY" o "SELL"
        self.entry_price = entry_price
        self.sl_price = sl_price
        self.start_index = start_index
        self.end_index = start_index
        self.status = self.STATUS_OPEN
        self.users = users if users else []
        self.close_reason = None
        self.close_price = None
        
        # Calcular niveles de TP basados en RR dinámico
        # Distancia del SL = |entry - sl|
        sl_distance = abs(entry_price - sl_price)
        self.tp_levels = []
        for rr in rr_multipliers:
            if self.direction == "BUY":
                tp_price = entry_price + (sl_distance * rr)
            else:
                tp_price = entry_price - (sl_distance * rr)
            
            self.tp_levels.append({
                "rr": rr,
                "tp_price": tp_price,
                "hit": False
            })
        
        # El TP final es el del multiplicador más alto
        self.final_tp = self.tp_levels[-1]["tp_price"] if self.tp_levels else entry_price

    def update_visual(self, current_index):
        """Actualiza la coordenada X final mientras la posición esté abierta."""
        if self.status == self.STATUS_OPEN:
            self.end_index = current_index

    def check_collision(self, candle):
        """
        Evalúa si la vela actual (High/Low) toca el SL o el TP final.
        Lógica BUY: Low <= SL (Perdida), High >= TP (Ganada).
        Lógica SELL: High >= SL (Perdida), Low <= TP (Ganada).
        """
        if self.status == self.STATUS_CLOSED:
            return None

        high = candle.get("high")
        low = candle.get("low")
        
        # Verificar SL (Prioridad: el SL siempre se evalúa primero o tiene más peso en simulación)
        sl_hit = False
        if self.direction == "BUY":
            if low <= self.sl_price:
                sl_hit = True
        else: # SELL
            if high >= self.sl_price:
                sl_hit = True
                
        if sl_hit:
            self.close("SL", self.sl_price)
            return "SL"

        # Verificar niveles de TP
        tp_hit_any = False
        for level in self.tp_levels:
            if not level["hit"]:
                hit = False
                if self.direction == "BUY":
                    if high >= level["tp_price"]:
                        hit = True
                else: # SELL
                    if low <= level["tp_price"]:
                        hit = True
                
                if hit:
                    level["hit"] = True
                    tp_hit_any = True
        
        # Si tocó el TP final, cerrar la posición de forma innegociable
        if self.tp_levels and self.tp_levels[-1]["hit"]:
            # Congelar exactamente en el precio del TP final para el PnL
            self.close("TP", self.final_tp)
            return "TP"
            
        return "TP_LEVEL" if tp_hit_any else None

    def close(self, reason, price):
        """Cierra la posición y congela sus parámetros visuales."""
        self.status = self.STATUS_CLOSED
        self.close_reason = reason
        self.close_price = price
        print(f"[TRADE RESOLVED] {self.direction} | Reason: {reason} | Entry: {self.entry_price:.2f} | Exit: {price:.2f}")

    def get_visual_data(self):
        """Retorna los datos necesarios para el renderizado."""
        return {
            "type": self.direction,
            "entry": self.entry_price,
            "sl": self.sl_price,
            "tp": self.final_tp,
            "tp_levels": self.tp_levels,
            "start_index": self.start_index,
            "end_index": self.end_index,
            "status": self.status
        }


class TradeManager:
    """
    Gestiona múltiples posiciones activas y su ciclo de vida.
    """
    def __init__(self):
        self.positions = []
        self.history = []

    def add_position(self, direction, entry_price, sl_price, rr_multipliers, current_index, users=None):
        pos = Position(direction, entry_price, sl_price, rr_multipliers, current_index, users)
        self.positions.append(pos)
        return pos

    def update(self, current_candle, current_index):
        """
        Actualiza todas las posiciones activas: colisiones y extensión visual.
        """
        resolutions = []
        for pos in self.positions[:]:  # Copia para poder remover
            # 1. Extensión visual continua
            pos.update_visual(current_index)
            
            # 2. Resolución de colisiones
            res = pos.check_collision(current_candle)
            
            if res in ["SL", "TP"]:
                resolutions.append((pos, res))
                self.history.append(pos)
                self.positions.remove(pos)
            elif res == "TP_LEVEL":
                resolutions.append((pos, "TP_LEVEL"))
                
        return resolutions

    def get_active_positions(self):
        return [p.get_visual_data() for p in self.positions]
