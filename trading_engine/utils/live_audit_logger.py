
"""
LIVE PERFORMANCE AUDITOR
Audits the first 5 trades from Binance to verify Slippage, Fees, and Net Realism.
"""
import sys
import os
import ccxt
import pandas as pd
from datetime import datetime

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from trading_engine.config import API_KEY, API_SECRET, RISK_SETTINGS
from trading_engine.db import DatabaseHandler, LiveAuditHandler

def perform_live_audit(order_id, signal_price, gross_pnl, side, symbol):
    """
    Performs audit for a single completed order and logs to DB.
    """
    # 🛡️ Skip audit for Simulation / Paper trades
    if not order_id or str(order_id).startswith("paper_"):
        return None

    if not API_KEY or not API_SECRET:
        return None

    try:
        exchange = ccxt.binance({
            'apiKey': API_KEY,
            'secret': API_SECRET,
            'enableRateLimit': True,
        })
        
        symbol_clean = symbol.replace("/", "")
        exchange_trades = exchange.fetch_my_trades(symbol_clean, limit=20, params={'orderId': order_id})
        
        if not exchange_trades:
            return None

        total_qty = sum([t['amount'] for t in exchange_trades])
        total_cost = sum([t['cost'] for t in exchange_trades])
        avg_fill_price = total_cost / total_qty
        actual_fee = sum([t['fee']['cost'] for t in exchange_trades if t['fee']])
        
        # Slippage vs Signal
        slippage_usd = abs(avg_fill_price - signal_price)
        slippage_pct = (slippage_usd / signal_price) * 100
        
        # True Net
        true_net_pnl = gross_pnl - actual_fee
        
        # Save to Audit DB
        audit_db = LiveAuditHandler()
        audit_db.add_audit_entry(
            side=side,
            order_id=order_id,
            signal_price=signal_price,
            fill_price=avg_fill_price,
            slippage_pct=slippage_pct,
            fee_usd=actual_fee,
            net_pnl=true_net_pnl
        )

        # 🚨 EMERGENCY ALERT: High Slippage
        if slippage_pct > 0.2:
            from trading_engine.utils.notifier import send_emergency_alert
            msg = (
                f"High slippage detected on {symbol}!\n"
                f"Slippage: *{slippage_pct:.3f}%*\n"
                f"Target: {signal_price}\n"
                f"Actual: {avg_fill_price}"
            )
            send_emergency_alert(msg)
        
        return {
            "slippage_pct": slippage_pct,
            "fee_usd": actual_fee,
            "true_net": true_net_pnl
        }

    except Exception as e:
        # Don't print the numeric error if it's just a paper trade we missed
        if "Illegal characters" not in str(e):
            print(f"❌ Audit Error for {order_id}: {e}")
        return None

def run_live_audit():
    print("📋 STARTING LIVE PERFORMANCE AUDIT (History Check)...\n")
    
    db = DatabaseHandler()
    with db._get_conn() as conn:
        query = """
        SELECT t.*, s.price as signal_price 
        FROM trades t
        LEFT JOIN signals s ON t.signal_id = s.id
        WHERE t.status IN ('CLOSED', 'TRAPPED')
        ORDER BY t.closed_at DESC
        LIMIT 5
        """
        local_trades = pd.read_sql_query(query, conn)

    if local_trades.empty:
        print("ℹ️ No closed trades found.")
        return

    verified_count = 0
    for idx, row in local_trades.iterrows():
        res = perform_live_audit(
            row['order_id'], 
            row['signal_price'] or row['entry_price'],
            row['pnl_amount'],
            row['side'],
            row['symbol']
        )
        if res:
            verified_count += 1
            slip_color = "🔴" if res['slippage_pct'] > 0.15 else "🟢"
            print(f"Trade Order {row['order_id']} | Slip: {slip_color} {res['slippage_pct']:.3f}% | Fee: ${res['fee_usd']:.4f}")
    
    if verified_count == 0:
        print("ℹ️ All historical trades were Simulation/Paper trades. No live data to verify yet.")

if __name__ == "__main__":
    run_live_audit()
