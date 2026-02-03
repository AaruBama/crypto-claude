"""
Data Collector - Fetches live market data from Binance
"""
import time
import pandas as pd
import numpy as np
from binance.client import Client
from binance.exceptions import BinanceAPIException
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

class MarketDataCollector:
    """Collects real-time and historical market data"""
    
    def __init__(self, api_key=None, api_secret=None):
        """
        Initialize Binance client
        For public data (prices, volume), API keys are optional
        """
        self.client = Client(api_key or "", api_secret or "")
        self.last_request_time = 0
        
    def _rate_limit(self):
        """Simple rate limiting"""
        elapsed = time.time() - self.last_request_time
        if elapsed < config.RATE_LIMITS["request_delay"]:
            time.sleep(config.RATE_LIMITS["request_delay"] - elapsed)
        self.last_request_time = time.time()
    
    def get_current_price(self, symbol):
        """Get current price for a symbol"""
        try:
            self._rate_limit()
            ticker = self.client.get_symbol_ticker(symbol=symbol)
            return float(ticker['price'])
        except BinanceAPIException as e:
            print(f"Error fetching price for {symbol}: {e}")
            return None
    
    def get_24h_stats(self, symbol):
        """Get 24h statistics including volume, price change"""
        try:
            self._rate_limit()
            ticker = self.client.get_ticker(symbol=symbol)
            return {
                'symbol': symbol,
                'price': float(ticker['lastPrice']),
                'change_24h': float(ticker['priceChangePercent']),
                'high_24h': float(ticker['highPrice']),
                'low_24h': float(ticker['lowPrice']),
                'volume_24h': float(ticker['volume']),
                'quote_volume_24h': float(ticker['quoteVolume']),
                'open_time': pd.to_datetime(ticker['openTime'], unit='ms'),
                'close_time': pd.to_datetime(ticker['closeTime'], unit='ms')
            }
        except BinanceAPIException as e:
            print(f"Error fetching 24h stats for {symbol}: {e}")
            return None
    
    def get_klines(self, symbol, interval, limit=500, start_time=None):
        """
        Get candlestick data (OHLCV)
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            interval: Timeframe (e.g., '15m', '1h', '4h')
            limit: Number of candles (max 1000)
            start_time: Starting timestamp (optional)
        
        Returns:
            DataFrame with OHLCV data
        """
        try:
            self._rate_limit()
            klines = self.client.get_klines(
                symbol=symbol,
                interval=interval,
                limit=limit,
                startTime=int(start_time.timestamp() * 1000) if start_time else None
            )
            
            # Convert to DataFrame
            df = pd.DataFrame(klines, columns=[
                'open_time', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                'taker_buy_quote', 'ignore'
            ])
            
            # Convert to proper types
            df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
            df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')
            
            for col in ['open', 'high', 'low', 'close', 'volume', 'quote_volume']:
                df[col] = df[col].astype(float)
            
            df['trades'] = df['trades'].astype(int)
            
            # Set index to open_time
            df.set_index('open_time', inplace=True)
            
            return df[['open', 'high', 'low', 'close', 'volume', 'quote_volume', 'trades']]
            
        except BinanceAPIException as e:
            print(f"Error fetching klines for {symbol}: {e}")
            return None
    
    def get_funding_rate(self, symbol):
        """
        Get current funding rate and mark price for perpetual futures.
        Uses the 'futures_mark_price' endpoint which is more reliable for real-time data.
        """
        try:
            self._rate_limit()
            # Mark price endpoint includes current funding rate
            data = self.client.futures_mark_price(symbol=symbol)
            
            if data:
                return {
                    'symbol': symbol,
                    'funding_rate': float(data['lastFundingRate']),
                    'funding_time': pd.to_datetime(data['nextFundingTime'], unit='ms'),
                    'mark_price': float(data['markPrice'])
                }
            return None
        except Exception as e:
            print(f"Error fetching funding rate for {symbol}: {e}")
            return None

    def get_futures_price(self, symbol):
        """Get current price for perpetual futures using Mark Price as fallback"""
        try:
            self._rate_limit()
            try:
                ticker = self.client.futures_symbol_ticker(symbol=symbol)
                return float(ticker['price'])
            except:
                # Fallback to mark price if ticker fails
                data = self.client.futures_mark_price(symbol=symbol)
                return float(data['markPrice']) if data else None
        except Exception as e:
            print(f"Error fetching futures price for {symbol}: {e}")
            return None
    
    def get_funding_rate_history(self, symbol, limit=100):
        """Get historical funding rates"""
        try:
            self._rate_limit()
            history = self.client.futures_funding_rate(symbol=symbol, limit=limit)
            
            df = pd.DataFrame(history)
            df['fundingTime'] = pd.to_datetime(df['fundingTime'], unit='ms')
            df['fundingRate'] = df['fundingRate'].astype(float)
            df.set_index('fundingTime', inplace=True)
            
            return df[['fundingRate']]
        except Exception as e:
            print(f"Error fetching funding history for {symbol}: {e}")
            return None
    
    def get_open_interest(self, symbol):
        """
        Get current open interest for futures
        
        Open Interest = total number of outstanding contracts
        """
        try:
            self._rate_limit()
            oi = self.client.futures_open_interest(symbol=symbol)
            return {
                'symbol': symbol,
                'open_interest': float(oi['openInterest']),
                'timestamp': pd.to_datetime(oi['time'], unit='ms')
            }
        except Exception as e:
            print(f"Error fetching open interest for {symbol}: {e}")
            return None
    
    def get_market_cap_data(self):
        """
        Get total crypto market cap and BTC dominance
        Note: Binance doesn't provide this directly, so we estimate
        """
        try:
            # Get BTC price
            btc_stats = self.get_24h_stats('BTCUSDT')
            eth_stats = self.get_24h_stats('ETHUSDT')
            
            if btc_stats and eth_stats:
                # Rough estimates (you can use CoinGecko API for accurate data)
                btc_supply = 19_600_000  # Approximate circulating supply
                eth_supply = 120_000_000
                
                btc_cap = btc_stats['price'] * btc_supply
                eth_cap = eth_stats['price'] * eth_supply
                
                # Very rough total market cap estimate
                # In reality, you'd sum all coins or use an API
                total_cap = btc_cap * 2  # Rough 50% dominance assumption
                
                return {
                    'btc_market_cap': btc_cap,
                    'eth_market_cap': eth_cap,
                    'total_market_cap': total_cap,
                    'btc_dominance': (btc_cap / total_cap) * 100,
                    'timestamp': datetime.now()
                }
            return None
        except Exception as e:
            print(f"Error estimating market cap: {e}")
            return None
    
    def get_orderbook(self, symbol, limit=100):
        """Get current orderbook depth"""
        try:
            self._rate_limit()
            depth = self.client.get_order_book(symbol=symbol, limit=limit)
            
            return {
                'symbol': symbol,
                'bids': [(float(price), float(qty)) for price, qty in depth['bids']],
                'asks': [(float(price), float(qty)) for price, qty in depth['asks']],
                'timestamp': datetime.now()
            }
        except Exception as e:
            print(f"Error fetching orderbook for {symbol}: {e}")
            return None
    
    def get_recent_trades(self, symbol, limit=100):
        """Get recent trades"""
        try:
            self._rate_limit()
            trades = self.client.get_recent_trades(symbol=symbol, limit=limit)
            
            df = pd.DataFrame(trades)
            df['time'] = pd.to_datetime(df['time'], unit='ms')
            df['price'] = df['price'].astype(float)
            df['qty'] = df['qty'].astype(float)
            df['isBuyerMaker'] = df['isBuyerMaker'].astype(bool)
            
            return df
        except Exception as e:
            print(f"Error fetching recent trades for {symbol}: {e}")
            return None
    
    def get_exchange_info(self):
        """Get exchange trading rules and symbol info"""
        try:
            self._rate_limit()
            info = self.client.get_exchange_info()
            return info
        except Exception as e:
            print(f"Error fetching exchange info: {e}")
            return None
    
    def ping(self):
        """Test connectivity and measure latency"""
        try:
            start = time.time()
            self.client.ping()
            latency = (time.time() - start) * 1000  # Convert to ms
            return latency
        except Exception as e:
            print(f"Ping failed: {e}")
            return None


if __name__ == "__main__":
    # Test the collector
    collector = MarketDataCollector()
    
    print("Testing Market Data Collector...")
    print("\n1. Current BTC Price:")
    price = collector.get_current_price("BTCUSDT")
    print(f"   ${price:,.2f}")
    
    print("\n2. 24h Statistics:")
    stats = collector.get_24h_stats("BTCUSDT")
    if stats:
        print(f"   Price: ${stats['price']:,.2f}")
        print(f"   24h Change: {stats['change_24h']:.2f}%")
        print(f"   24h Volume: {stats['volume_24h']:,.2f} BTC")
    
    print("\n3. Recent Candlesticks (15m):")
    klines = collector.get_klines("BTCUSDT", "15m", limit=5)
    if klines is not None:
        print(klines)
    
    print("\n4. Exchange Latency:")
    latency = collector.ping()
    print(f"   {latency:.2f} ms")
    
    print("\n✓ Data collector working!")
