
import sqlite3
import json

def inject_clean_data():
    conn = sqlite3.connect("data/trading_bot.db")
    
    try:
        # Single Transaction
        with conn:
            # 1. Clear Old Data
            conn.execute("DELETE FROM trades")
            conn.execute("DELETE FROM signals")
            conn.execute("DELETE FROM performance")
            print("🧹 Cleared existing data.")

            # 2. Seed Performance
            conn.execute("INSERT INTO performance (total_balance, equity) VALUES (10000, 10000)")
            
            # 3. Inject Signals
            # Signal A (Buy)
            cur = conn.execute(
                "INSERT INTO signals (strategy_id, type, price, metadata) VALUES (?, ?, ?, ?)",
                ("Traffic_Light_V1", "BUY", 64200.50, json.dumps({"reason": "Bullish Inside Bar", "confidence": "High"}))
            )
            sig_a_id = cur.lastrowid
            
            # Signal B (Sell - No Trade)
            conn.execute(
                "INSERT INTO signals (strategy_id, type, price, metadata) VALUES (?, ?, ?, ?)",
                ("Email_Cross_8_30", "SELL", 64850.00, json.dumps({"reason": "Death Cross", "confidence": "Med"}))
            )

            # Signal C (Sell - Active)
            cur = conn.execute(
                "INSERT INTO signals (strategy_id, type, price, metadata) VALUES (?, ?, ?, ?)",
                ("Traffic_Light_V1", "SELL", 64900.00, json.dumps({"reason": "Bearish Test Flip", "confidence": "Test"}))
            )
            sig_c_id = cur.lastrowid
            
            print("✅ Injected 3 Signals.")
            
            # 4. Inject Trades
            # Trade A: Closed Winner
            conn.execute(
                """INSERT INTO trades (symbol, strategy_id, side, entry_price, exit_price, quantity, status, pnl_amount, pnl_pct, closed_at, signal_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)""",
                ("BTC/USDT", "Traffic_Light_V1", "BUY", 64200.50, 64500.50, 0.1, "CLOSED", 30.0, 0.47, sig_a_id)
            )

            # Trade C: Active Loser
            conn.execute(
                """INSERT INTO trades (symbol, strategy_id, side, entry_price, quantity, status, signal_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                ("BTC/USDT", "Traffic_Light_V1", "SELL", 64900.00, 0.5, "OPEN", sig_c_id)
            )
            
            print("✅ Injected Trades.")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    inject_clean_data()
