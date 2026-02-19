
import ccxt
import pandas as pd
import time
from datetime import datetime, timedelta
import os

def download_hyperliquid_data(symbol="BTC/USDC:USDC", timeframe="5m", days=30, save_path="data/historical/"):
    """
    Downloads historical OHLCV data from Hyperliquid using CCXT.
    """
    exchange = ccxt.hyperliquid({
        'enableRateLimit': True,
    })
    
    os.makedirs(save_path, exist_ok=True)
    # Using a slightly different naming convention to distinguish from Binance
    file_name = f"HL_{symbol.split('/')[0]}_{timeframe}_{days}d.csv"
    full_path = os.path.join(save_path, file_name)
    
    print(f"🚀 Downloading {days} days of {timeframe} Hyperliquid data for {symbol}...")
    
    # Hyperliquid fetch_ohlcv supports 'since'
    since = exchange.parse8601((datetime.now() - timedelta(days=days)).isoformat())
    all_ohlcv = []
    
    while since < exchange.milliseconds():
        try:
            limit = 1000
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since, limit)
            if not ohlcv:
                break
            
            # Progress update
            last_ts = ohlcv[-1][0]
            if last_ts == since: # Prevent infinite loop if CCXT returns same data
                break
                
            since = last_ts + 1
            all_ohlcv.extend(ohlcv)
            
            current_date = datetime.fromtimestamp(since / 1000).strftime('%Y-%m-%d %H:%M')
            print(f"📥 Batch received. Last timestamp: {current_date} | Total candles: {len(all_ohlcv)}")
            
            time.sleep(exchange.rateLimit / 1000) 
            
        except Exception as e:
            print(f"⚠️ Error fetching data: {e}")
            time.sleep(5)
            continue

    if not all_ohlcv:
        print("❌ No data fetched.")
        return None

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
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--timeframe", type=str, default="5m")
    args = parser.parse_args()
    
    download_hyperliquid_data(symbol="BTC/USDC:USDC", timeframe=args.timeframe, days=args.days)
    download_hyperliquid_data(symbol="SOL/USDC:USDC", timeframe=args.timeframe, days=args.days)
