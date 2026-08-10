import pygame
import random

class TradeSimulator:
    def __init__(self, target, sim_info):
        self.target = target
        self.sim_info = sim_info
        self.current_price = 100.0
        self.trades = []

    def draw(self):
        # Clear the screen
        self.target.fill((255, 255, 255))

        # Draw trade overlay
        for trade in self.trades:
            self.draw_trade_overlay(trade)

        # Draw current price line
        pygame.draw.line(self.target, (0, 0, 255), (0, self.y_entry()), (self.sim_info.width, self.y_entry()))
        font = pygame.font.Font(None, 36)
        text = font.render(f"Price: {self.current_price:.2f}", True, (0, 0, 255))
        self.target.blit(text, (10, 10))

    def draw_trade_overlay(self, trade):
        # Get the y-coordinate of the entry candle
        y_entry = self.y_entry()
        sl_height = (self.sim_info.height / 2) * trade.sl_risk
        tp_height = (self.sim_info.height / 2) * trade.tp_risk
        box_width = self.sim_info.width - trade.x_entry

        if trade.type == 'BUY':
            y_sl = y_entry + sl_height
            y_tp = y_entry - tp_height

            # BUY: SL goes down from the entry, TP goes up from the same entry edge.
            pygame.draw.rect(self.target, (255, 0, 0), (trade.x_entry, y_entry, box_width, sl_height), 3)
            pygame.draw.rect(self.target, (0, 255, 0), (trade.x_entry, y_tp, box_width, tp_height), 3)

            # Draw lines and labels
            self.draw_trade_lines(trade, 'BUY', trade.sl_risk, trade.tp_risk, y_sl, y_tp)
        elif trade.type == 'SELL':
            y_sl = y_entry - sl_height
            y_tp = y_entry + tp_height

            # SELL: SL goes up from the entry, TP goes down from the same entry edge.
            pygame.draw.rect(self.target, (255, 0, 0), (trade.x_entry, y_sl, box_width, sl_height), 3)
            pygame.draw.rect(self.target, (0, 255, 0), (trade.x_entry, y_entry, box_width, tp_height), 3)

            # Draw lines and labels
            self.draw_trade_lines(trade, 'SELL', trade.sl_risk, trade.tp_risk, y_sl, y_tp)

    def draw_trade_lines(self, trade, trade_type, sl_risk, tp_risk, y_sl, y_tp):
        font = pygame.font.Font(None, 24)
        if trade_type == 'BUY':
            # Draw SL line
            pygame.draw.line(self.target, (255, 0, 0), (trade.x_entry, self.y_entry()), (self.sim_info.width, y_sl))
            sl_ratio = (abs(y_sl - self.y_entry()) / (self.sim_info.height / 2)) * sl_risk
            text = font.render(f"LÍMITE: {sl_ratio:.1f} R", True, (255, 0, 0))
            self.target.blit(text, (self.sim_info.width, y_sl - 30))

            # Draw TP line
            pygame.draw.line(self.target, (0, 255, 0), (trade.x_entry, self.y_entry()), (self.sim_info.width, y_tp))
            tp_ratio = (abs(y_tp - self.y_entry()) / (self.sim_info.height / 2)) * tp_risk
            text = font.render(f"TP: {tp_ratio:.1f} R", True, (0, 255, 0))
            self.target.blit(text, (self.sim_info.width, y_tp - 30))

        elif trade_type == 'SELL':
            # Draw SL line
            pygame.draw.line(self.target, (255, 0, 0), (trade.x_entry, self.y_entry()), (self.sim_info.width, y_sl))
            sl_ratio = (abs(y_sl - self.y_entry()) / (self.sim_info.height / 2)) * sl_risk
            text = font.render(f"LÍMITE: {sl_ratio:.1f} R", True, (255, 0, 0))
            self.target.blit(text, (self.sim_info.width, y_sl - 30))

            # Draw TP line
            pygame.draw.line(self.target, (0, 255, 0), (trade.x_entry, self.y_entry()), (self.sim_info.width, y_tp))
            tp_ratio = (abs(y_tp - self.y_entry()) / (self.sim_info.height / 2)) * tp_risk
            text = font.render(f"TP: {tp_ratio:.1f} R", True, (0, 255, 0))
            self.target.blit(text, (self.sim_info.width, y_tp - 30))

    def y_entry(self):
        # Calculate the y-coordinate of the entry candle
        return int((self.sim_info.height / 2) * (self.current_price / 100.0))

# SimInfo class for simulation information
class SimInfo:
    def __init__(self, width=800, height=600):
        self.width = width
        self.height = height

# Example usage
if __name__ == "__main__":
    pygame.init()
    sim_info = SimInfo()
    target = pygame.display.set_mode((sim_info.width, sim_info.height))

    trade_simulator = TradeSimulator(target, sim_info)
    trade_simulator.trades.append(TradeSimulator.Trade(trade_type='BUY', x_entry=100, sl_risk=1.5, tp_risk=2.0))
    trade_simulator.trades.append(TradeSimulator.Trade(trade_type='SELL', x_entry=300, sl_risk=2.0, tp_risk=1.5))

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        trade_simulator.current_price += random.uniform(-0.1, 0.1)
        trade_simulator.draw()
        pygame.display.flip()

    pygame.quit()
