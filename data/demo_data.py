"""
Demo Data Generator - Simulates market data for testing without network access
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

class DemoDataGenerator:
    """Generates realistic-looking demo data for testing"""
    
    def __init__(self, base_price=50000, volatility=0.02):
        self.base_price = base_price
        self.volatility = volatility
        self.current_price = base_price
        self.trend = np.random.choice([-1, 0, 1])  # down, sideways, up
        
    def generate_klines(self, symbol, interval, limit=500):
        """Generate realistic OHLCV candlestick data"""
        
        # Time intervals
        interval_minutes = {
            '1m': 1, '5m': 5, '15m': 15, '1h': 60, '4h': 240, '1d': 1440
        }
        minutes = interval_minutes.get(interval, 15)
        
        # Generate timestamps
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=minutes * limit)
        timestamps = pd.date_range(start=start_time, end=end_time, periods=limit)
        
        # Generate price data with trend
        np.random.seed(42)  # For reproducibility
        
        # Create a trending random walk
        trend_strength = 0.0001 * self.trend
        returns = np.random.randn(limit) * self.volatility + trend_strength
        prices = self.base_price * np.exp(np.cumsum(returns))
        
        # Generate OHLC from prices
        data = []
        for i, price in enumerate(prices):
            # Add some intracandle volatility
            high = price * (1 + abs(np.random.randn()) * 0.005)
            low = price * (1 - abs(np.random.randn()) * 0.005)
            open_price = prices[i-1] if i > 0 else price
            close_price = price
            
            # Volume (higher volume during volatile periods)
            base_volume = 1000
            volume = base_volume * (1 + abs(np.random.randn()) * 2)
            
            data.append({
                'open': open_price,
                'high': max(high, open_price, close_price),
                'low': min(low, open_price, close_price),
                'close': close_price,
                'volume': volume,
                'quote_volume': volume * close_price,
                'trades': int(volume / 10)
            })
        
        df = pd.DataFrame(data, index=timestamps)
        self.current_price = df['close'].iloc[-1]
        
        return df
    
    def get_current_price(self, symbol):
        """Get current (last) price"""
        return self.current_price
    
    def get_24h_stats(self, symbol):
        """Generate 24h statistics"""
        change_24h = (np.random.randn() * 5)  # -10% to +10% typical daily change
        
        return {
            'symbol': symbol,
            'price': self.current_price,
            'change_24h': change_24h,
            'high_24h': self.current_price * 1.05,
            'low_24h': self.current_price * 0.95,
            'volume_24h': 50000,
            'quote_volume_24h': 50000 * self.current_price,
            'open_time': datetime.now() - timedelta(days=1),
            'close_time': datetime.now()
        }
    
    def get_funding_rate(self, symbol):
        """Generate funding rate data"""
        return {
            'symbol': symbol,
            'funding_rate': np.random.randn() * 0.0001,  # Small funding rate
            'funding_time': datetime.now(),
            'mark_price': self.current_price
        }
    
    def get_open_interest(self, symbol):
        """Generate open interest data"""
        return {
            'symbol': symbol,
            'open_interest': 100000000,  # $100M
            'timestamp': datetime.now()
        }
    
    def get_market_cap_data(self):
        """Generate market cap estimates"""
        btc_supply = 19_600_000
        eth_supply = 120_000_000
        
        btc_price = 50000 if 'BTC' in str(self.current_price) else self.current_price
        eth_price = 2500
        
        btc_cap = btc_price * btc_supply
        eth_cap = eth_price * eth_supply
        total_cap = btc_cap * 2
        
        return {
            'btc_market_cap': btc_cap,
            'eth_market_cap': eth_cap,
            'total_market_cap': total_cap,
            'btc_dominance': (btc_cap / total_cap) * 100,
            'timestamp': datetime.now()
        }
    
    def ping(self):
        """Simulate ping"""
        return 50 + np.random.rand() * 50  # 50-100ms


# Create generators for different symbols
_generators = {}

def get_demo_collector(symbol='BTCUSDT'):
    """Get or create a demo data generator for a symbol"""
    if symbol not in _generators:
        base_prices = {
            'BTCUSDT': 50000,
            'ETHUSDT': 2500,
            'SOLUSDT': 100,
            'BNBUSDT': 300,
            'ADAUSDT': 0.5
        }
        _generators[symbol] = DemoDataGenerator(
            base_price=base_prices.get(symbol, 100)
        )
    return _generators[symbol]


if __name__ == "__main__":
    print("Testing Demo Data Generator...")
    
    gen = DemoDataGenerator(base_price=50000)
    
    print("\n1. Generating candlestick data...")
    klines = gen.generate_klines("BTCUSDT", "15m", limit=100)
    print(klines.head())
    print(f"   Generated {len(klines)} candles")
    
    print("\n2. Current price:")
    print(f"   ${gen.get_current_price('BTCUSDT'):,.2f}")
    
    print("\n3. 24h stats:")
    stats = gen.get_24h_stats("BTCUSDT")
    print(f"   Change: {stats['change_24h']:.2f}%")
    
    print("\n4. Market cap data:")
    mc = gen.get_market_cap_data()
    print(f"   BTC Dominance: {mc['btc_dominance']:.1f}%")
    
    print("\n✓ Demo generator working!")
