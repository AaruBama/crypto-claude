
"""
Abstract Strategy Base Class
All new strategies must inherit from this to be run by the engine.
"""
from abc import ABC, abstractmethod

class BaseStrategy(ABC):
    def __init__(self, name: str, params: dict = None):
        self.name = name
        self.params = params or {}
        
    @abstractmethod
    def on_candle_close(self, candle_index: int, open, high, low, close, volume):
        """
        Called when a new candle closes.
        Return a Signal object or None.
        """
        pass
        
    @abstractmethod
    def on_tick(self, current_price: float):
        """
        Called every tick (optional implementation).
        Useful for stop-limit orders or immediate exits.
        """
        pass
        
    def generate_signal(self, side: str, price: float, stop_loss: float = None, take_profit: float = None, reason: str = "", order_type: str = "MARKET", metadata: dict = None):
        """
        Helper to create a standardized signal format.
        side: "BUY" or "SELL"
        order_type: "MARKET" or "STOP_MARKET"
        """
        return {
            "strategy": self.name,
            "side": side.upper(),
            "price": price,
            "sl": stop_loss,
            "tp": take_profit,
            "reason": reason,
            "order_type": order_type,
            "metadata": metadata or {}
        }
