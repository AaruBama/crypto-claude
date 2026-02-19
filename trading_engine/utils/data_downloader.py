
import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
import os

def download_historical_data(symbol="BTC/USDT", timeframe="1m", days=90, save_path="data/historical/"):
    """
    Downloads historical OHLCV data from Binance using CCXT.
    Handles pagination for large datasets.
    """
    exchange = ccxt.binance({
        'enableRateLimit': True,
    })
    
    os.makedirs(save_path, exist_ok=True)
    file_name = f"{symbol.replace('/', '_')}_{timeframe}_{days}d.csv"
    full_path = os.path.join(save_path, file_name)
    
    print(f"🚀 Downloading {days} days of {timeframe} data for {symbol}...")
    
    since = exchange.parse8601((datetime.now() - timedelta(days=days)).isoformat())
    all_ohlcv = []
    
    while since < exchange.milliseconds():
        try:
            limit = 1000
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since, limit)
            if not ohlcv:
                break
            
            since = ohlcv[-1][0] + 1
            all_ohlcv.extend(ohlcv)
            
            # Progress update
            current_date = datetime.fromtimestamp(since / 1000).strftime('%Y-%m-%d %H:%M')
            print(f"📥 Batch received. Last timestamp: {current_date} | Total candles: {len(all_ohlcv)}")
            
            time.sleep(exchange.rateLimit / 1000) # Respect rate limits
            
        except Exception as e:
            print(f"⚠️ Error fetching data: {e}")
            time.sleep(10)
            continue

    # Convert to DataFrame
    df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['time'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    # Save to CSV
    df.to_csv(full_path, index=False)
    print(f"✅ Download complete! Saved to {full_path}")
    return df

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", type=str, default="BTC/USDT")
    parser.add_argument("--days", type=int, default=90)
    args = parser.parse_args()
    
    # Download 1m and 5m data
    download_historical_data(symbol=args.symbol, timeframe="1m", days=args.days)
    download_historical_data(symbol=args.symbol, timeframe="5m", days=args.days)
