
"""
Basic Candle Manager
Maintains in-memory buffer of recent candles.
Calculates indicators using pandas-ta or similar.
"""
import pandas as pd
try:
    import pandas_ta as ta
except ImportError:
    import pandas_ta_classic as ta

class CandleManager:
    def __init__(self, limit=500):
        self.limit = limit
        self.buffer = pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume', 'time'])
        
    def add_candle(self, open, high, low, close, volume, timestamp):
        """
        Adds a single new candle.
        Re-calculates indicators on demand.
        """
        new_row = {
            'time': timestamp,
            'open': open,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume
        }
        
        # Append as dictionary
        df_new = pd.DataFrame([new_row])
        if self.buffer.empty:
            self.buffer = df_new
        else:
            self.buffer = pd.concat([self.buffer, df_new], ignore_index=True)
        
        # Trim
        if len(self.buffer) > self.limit:
            self.buffer = self.buffer.iloc[-self.limit:]
            
    def get_indicators(self):
        """
        Calculates indicators based on current buffer.
        """
        if len(self.buffer) < 50:
            return None
            
        df = self.buffer.copy()
        
        # Add basic TA
        df.ta.ema(length=9, append=True)
        df.ta.ema(length=20, append=True)
        df.ta.rsi(length=14, append=True)
        df.ta.adx(length=14, append=True)
        
        return df.iloc[-1]
