
"""
EMERGENCY STOP SCRIPT
Immediately cancels all open orders and liquidates all positions on Binance.
Usage: python3 trading_engine/utils/stop_everything.py
"""
import sys
import os
import ccxt
import time

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from trading_engine.config import API_KEY, API_SECRET

def emergency_stop():
    print("🚨 EMERGENCY STOP ACTIVATED 🚨")
    
    if not API_KEY or not API_SECRET:
        print("❌ Error: API Credentials not found. Cannot send live stop commands.")
        return

    exchange = ccxt.binance({
        'apiKey': API_KEY,
        'secret': API_SECRET,
        'enableRateLimit': True,
    })

    try:
        # 1. Cancel All Open Orders
        print("⏳ Cancelling all open orders...")
        # Get all open orders
        open_orders = exchange.fetch_open_orders()
        for order in open_orders:
            print(f"🧹 Cancelling {order['symbol']} Order {order['id']}")
            exchange.cancel_order(order['id'], order['symbol'])
        print(f"✅ Cancelled {len(open_orders)} orders.")

        # 2. Close All Positions (Market Sell/Buy)
        print("⏳ Fetching active positions...")
        balance = exchange.fetch_balance()
        # Find any non-zero balances (for spot) or active positions (for futures)
        # Note: This implementation assumes Spot for simplicity, 
        # but could be expanded to Futures positions.
        for asset, data in balance['total'].items():
            if data > 0 and asset not in ['USDT', 'BNB', 'FDUSD']: # Keep stablecoins and gas coins
                symbol = f"{asset}/USDT"
                print(f"📉 Liquidating {data} {asset}...")
                try:
                    exchange.create_market_sell_order(symbol, data)
                    print(f"✅ Sold {asset}.")
                except Exception as e:
                    print(f"⚠️ Failed to sell {asset}: {e}")

        print("\n🏁 Emergency Liquidaton Sequence Complete.")
        
    except Exception as e:
        print(f"❌ CRITICAL ERROR during emergency stop: {e}")

if __name__ == "__main__":
    confirm = input("⚠️ WARNING: This will close ALL positions and cancel ALL orders. Type 'CONFIRM' to proceed: ")
    if confirm == "CONFIRM":
        emergency_stop()
    else:
        print("Operation cancelled.")
