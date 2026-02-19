
"""
Database Helpers for Dashboard.
Read-Only access to the Trading Engine's SQLite DB.
"""
import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = "data/trading_bot.db"

def get_db_connection():
    ts = datetime.now().timestamp()
    # "file:data/trading_bot.db?mode=ro" opens in read-only mode to prevent UI blocking DB
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn

def get_dashboard_stats(current_price: float):
    """
    Aggregates high-level stats for the Scoreboard.
    Includes Gross vs Net PnL logic.
    """
    stats = {
        "pnl_gross": 0.0,
        "pnl_net": 0.0,
        "fees": 0.0,
        "taxes": 0.0,
        "pnl_unrealized": 0.0,
        "win_rate": 0.0,
        "total_trades": 0,
        "active_trades": 0
    }
    
    try:
        with get_db_connection() as conn:
            # 1. Closed Trades Analysis
            query = """
            SELECT 
                COUNT(*) as count, 
                SUM(pnl_amount) as gross_pnl, 
                SUM(fees) as total_fees,
                SUM(taxes) as total_taxes,
                SUM(CASE WHEN pnl_amount > 0 THEN 1 ELSE 0 END) as wins 
            FROM trades 
            WHERE status IN ('CLOSED', 'TRAPPED')
            """
            cursor = conn.execute(query)
            row = cursor.fetchone()
            if row:
                stats["total_trades"] = row["count"]
                stats["pnl_gross"] = row["gross_pnl"] or 0.0
                stats["fees"] = row["total_fees"] or 0.0
                stats["taxes"] = row["total_taxes"] or 0.0
                stats["pnl_net"] = stats["pnl_gross"] - stats["fees"] - stats["taxes"]
                
                wins = row["wins"] or 0
                if stats["total_trades"] > 0:
                    stats["win_rate"] = (wins / stats["total_trades"]) * 100
            
            # 2. Unrealized PnL (Open Trades)
            cursor = conn.execute("SELECT * FROM trades WHERE status='OPEN'")
            open_trades = cursor.fetchall()
            stats["active_trades"] = len(open_trades)
            
            for t in open_trades:
                entry = t["entry_price"]
                qty = t["quantity"]
                side = t["side"]
                entry_fees = t["fees"] or 0.0
                
                # Logic: (Current - Entry) * Qty
                diff = current_price - entry
                if side == "SELL":
                    diff = -diff
                
                # Unrealized Net = (Price Diff * Qty) - Entry Fees - Est. Exit Fee
                # We show simple unrealized for now but could subtract fees
                stats["pnl_unrealized"] += (diff * qty) - entry_fees
                
    except Exception as e:
        print(f"DB Error: {e}")
        
    return stats

import json

def get_recent_signals_df(limit=20):
    """
    Returns a DataFrame of recent signals (Setups).
    Parses metadata JSON to extract reason.
    """
    try:
        conn = get_db_connection()
        query = "SELECT id, strategy_id, type, price, metadata, timestamp FROM signals ORDER BY id DESC LIMIT ?"
        df = pd.read_sql_query(query, conn, params=(limit,))
        conn.close()
        
        # Parse metadata JSON safely
        def parse_reason(meta_str):
            try:
                data = json.loads(meta_str)
                return data.get('reason', 'N/A')
            except:
                return 'Error'
                
        if not df.empty:
            df['reason'] = df['metadata'].apply(parse_reason)
            # Clean up display
            df = df[['timestamp', 'strategy_id', 'type', 'price', 'reason']]
            
        return df
    except Exception as e:
        print(f"Signal Fetch Error: {e}")
        return pd.DataFrame()

def get_recent_trades_df(limit=20):
    """
    Returns a DataFrame of recent trades for display.
    """
    try:
        conn = get_db_connection()
        query = "SELECT id, strategy_id, symbol, side, entry_price, exit_price, pnl_pct, status, opened_at FROM trades ORDER BY id DESC LIMIT ?"
        df = pd.read_sql_query(query, conn, params=(limit,))
        conn.close()
        return df
    except Exception as e:
        return pd.DataFrame()

def get_multi_bot_comparison():
    """
    Returns side-by-side performance for comparison (Bot A vs Bot B).
    """
    try:
        with get_db_connection() as conn:
            query = """
            SELECT 
                strategy_id as Bot, 
                COUNT(*) as Total_Trades,
                SUM(pnl_amount) as Net_PnL,
                SUM(CASE WHEN pnl_amount > 0 THEN 1 ELSE 0 END) as Wins,
                SUM(CASE WHEN status='TRAPPED' THEN 1 ELSE 0 END) as Failed_Breakouts
            FROM trades
            GROUP BY strategy_id
            """
            df = pd.read_sql_query(query, conn)
            if not df.empty:
                df['Win_Rate'] = (df['Wins'] / df['Total_Trades']) * 100
                # Profit Factor calculation
                df = df.round(2)
            return df
    except Exception as e:
        print(f"Comparison Fetch Error: {e}")
def clear_db():
    # Helper to clear DB (Needs write access)
    try:
        conn = sqlite3.connect(DB_PATH) # Normal write mode
        conn.execute("DELETE FROM trades")
        conn.execute("DELETE FROM signals")
        conn.execute("DELETE FROM performance")
        conn.commit()
        conn.close()
        print("Dashboard Request: DB Cleared.")
        return True
    except Exception as e:
        print(f"Error clearing DB: {e}")
        return False

def get_live_audit_data(limit=10):
    """
    Fetches real-world execution metrics from the Live Audit database.
    """
    AUDIT_DB = "data/live_trades.db"
    try:
        if not os.path.exists(AUDIT_DB):
            return pd.DataFrame(), {"total_fees": 0.0, "avg_slippage": 0.0}
            
        conn = sqlite3.connect(f"file:{AUDIT_DB}?mode=ro", uri=True)
        # Fetch logs
        query = "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?"
        df = pd.read_sql_query(query, conn, params=(limit,))
        
        # Fetch stats
        stats_query = "SELECT SUM(fee_usd) as total_fees, AVG(slippage_pct) as avg_slippage FROM audit_logs"
        cursor = conn.execute(stats_query)
        row = cursor.fetchone()
        stats = {
            "total_fees": row[0] or 0.0,
            "avg_slippage": row[1] or 0.0
        }
        
        conn.close()
        return df, stats
    except Exception as e:
        print(f"Audit Fetch Error: {e}")
        return pd.DataFrame(), {"total_fees": 0, "avg_slippage": 0}

import os
