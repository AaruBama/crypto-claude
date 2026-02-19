
"""
Traffic Light Strategy Implementation.
A Breakout/Reversal strategy based on candle color shifts and inside bars.
Enhanced with Volume Filtering and Trap Detection.
"""
from trading_engine.core.strategy import BaseStrategy

class TrafficLightStrategy(BaseStrategy):
    def __init__(self, name="Traffic_Light_V1", params=None):
        super().__init__(name, params)
        self.params = params or {}
        self.risk_reward_ratio = self.params.get('risk_reward', 1.5)
        self.test_mode = self.params.get('test_mode', False)
        
    def on_candle_close(self, candle_manager):
        """
        Check for Traffic Light Setup on candle close.
        Enhanced with Volume Filter (1.5x Avg of last 10).
        """
        if len(candle_manager.buffer) < 12: # Need 10 for avg volume + 2 for setup
            return None
            
        curr = candle_manager.buffer.iloc[-1]
        prev = candle_manager.buffer.iloc[-2]
        
        # 1. Volume Confirmation
        avg_volume = candle_manager.buffer['volume'].iloc[-11:-1].mean()
        vol_multiplier = self.params.get('vol_filter', 1.5)
        has_volume_confirmation = curr['volume'] >= (avg_volume * vol_multiplier)
        
        # 2. Define Candle Properties
        prev_color = "GREEN" if prev['close'] > prev['open'] else "RED"
        curr_color = "GREEN" if curr['close'] > curr['open'] else "RED"
        
        # Inside Bar Check
        is_inside_bar = (curr['high'] <= prev['high']) and (curr['low'] >= prev['low'])
        
        # Test Mode Override
        if self.test_mode:
            is_inside_bar = True 
        
        signal = None
        
        # LOGIC: BULLISH SETUP
        if prev_color == "RED" and curr_color == "GREEN" and is_inside_bar:
            if not has_volume_confirmation and not self.test_mode:
                return None # Filtered by volume
                
            entry_price = float(curr['high'])
            stop_loss = float(prev['low']) 
            
            risk = entry_price - stop_loss
            take_profit = entry_price + (risk * self.risk_reward_ratio)
            
            signal = self.generate_signal(
                side="BUY",
                price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason="Bullish Traffic Light (Vol Confirmed)",
                order_type="STOP_MARKET",
                metadata={
                    "setup_low": float(curr['low']), 
                    "setup_high": float(curr['high']),
                    "has_vol": True
                }
            )
            
        # LOGIC: BEARISH SETUP
        elif prev_color == "GREEN" and curr_color == "RED" and is_inside_bar:
            if not has_volume_confirmation and not self.test_mode:
                return None # Filtered by volume
                
            entry_price = float(curr['low'])
            stop_loss = float(prev['high'])
            
            risk = stop_loss - entry_price
            take_profit = entry_price - (risk * self.risk_reward_ratio)
            
            signal = self.generate_signal(
                side="SELL",
                price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason="Bearish Traffic Light (Vol Confirmed)",
                order_type="STOP_MARKET",
                metadata={
                    "setup_low": float(curr['low']), 
                    "setup_high": float(curr['high']),
                    "has_vol": True
                }
            )
            
        return signal

    def on_tick(self, current_price, active_positions):
        """
        Trap Detection logic:
        If price hit entry but is now back inside the 'Inside Bar' range,
        record it as a potential failed breakout (Trap).
        """
        for pos in active_positions:
            if pos.get('strategy_id') == self.name:
                setup_low = pos.get('metadata', {}).get('setup_low')
                setup_high = pos.get('metadata', {}).get('setup_high')
                
                if not setup_low or not setup_high: continue
                
                # Check for "Trap" (Re-entry into setup range after trigger)
                is_trapped = False
                if pos['side'] == "BUY" and current_price < setup_high:
                    is_trapped = True
                elif pos['side'] == "SELL" and current_price > setup_low:
                    is_trapped = True
                    
                if is_trapped:
                    # In a real system, we might move SL to BE or close early here.
                    # For now, we return a trigger to log this setup as 'Failed'
                    return {"type": "TRAP_DETECTED", "order_id": pos['id'], "price": current_price}
        return None
