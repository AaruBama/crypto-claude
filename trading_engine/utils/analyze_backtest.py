
"""
HIGH-SCALE BACKTEST COMPARISON
Runs 90-day BTC/USDT backtest with $20 vs $100 limits.
Calculates Break-Even Point and Fee-Eater Analysis.
"""
import sys
import os
import pandas as pd
import numpy as np

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading_engine.backtest_engine import BacktestEngine
from trading_engine.strategies.traffic_light import TrafficLightStrategy
from trading_engine.strategies.mean_reversion import MeanReversionStrategy
from trading_engine.config import RISK_SETTINGS, STRATEGIES

def run_analysis():
    print("🚀 STARTING HIGH-SCALE BACKTEST ANALYSIS...")
    
    m1_file = "data/historical/BTC_USDT_1m_90d.csv"
    m5_file = "data/historical/BTC_USDT_5m_90d.csv"
    
    if not os.path.exists(m1_file) or not os.path.exists(m5_file):
        print("❌ Error: Historical data files not found.")
        return

    m1_df = pd.read_csv(m1_file)
    m5_df = pd.read_csv(m5_file)

    # --- RUN COMPARISONS ---
    results = []
    from trading_engine import config
    config.MICRO_LIVE_LIMITS["max_trade_usd"] = 100.0

    # Test Scenarios
    scenarios = [
        {"name": "Traffic Light (3x RR)", "class": TrafficLightStrategy, "params": STRATEGIES["TRAFFIC_LIGHT"]["params"]},
        {"name": "Mean Reversion (Scalper)", "class": MeanReversionStrategy, "params": STRATEGIES["MEAN_REVERSION"]["params"]}
    ]

    for sc in scenarios:
        print(f"\n--- Testing Strategy: {sc['name']} ---")
        bt = BacktestEngine(strategy_class=sc['class'], strategy_params=sc['params'])
        bt.load_data(m1_df, m5_df)
        bt.run()
        
        net_profit = bt.balance - 10000.0
        win_rate = 0
        if bt.trades:
            df_t = pd.DataFrame(bt.trades)
            win_rate = (df_t['net_pnl'] > 0).mean() * 100
            
        results.append({
            "name": sc['name'],
            "profit": net_profit,
            "win_rate": win_rate,
            "trades": len(bt.trades)
        })

    # 3. FINAL SUMMARY
    fee_rate = RISK_SETTINGS.get("fee_rate", 0.00075)
    slippage = RISK_SETTINGS.get("slippage_penalty", 0.0005)
    
    # Cost per round trip (2 legs)
    total_cost_pct = (fee_rate * 2 + slippage * 2) * 100
    
    print("\n" + "="*50)
    print("📋 STRATEGY COMPARISON REPORT (@ $100 Cap)")
    print("="*50)
    for data in results:
        print(f"{data['name']:<25} => Net Profit: ${data['profit']:>8.2f} | Win Rate: {data['win_rate']:>5.1f}% | Trades: {data['trades']}")
    
    print("\n📈 BREAK-EVEN ANALYSIS")
    print(f"Exchange Fee (Round):  {fee_rate*2*100:.2f}%")
    print(f"Slippage Penalty:      {slippage*2*100:.2f}%")
    print(f"TOTAL COST PER TRADE:  {total_cost_pct:.3f}%")
    print(f"👉 MIN PRICE MOVE:    You need >{total_cost_pct:.3f}% to be profitable.")

    print("\n🍴 THE 'FEE-EATER' ANALYSIS")
    # Take Profit is typically 1.5% - 2.0% in Traffic Light
    tp_pct = 1.5 # Default estimate
    fricton_ratio = (total_cost_pct / tp_pct) * 100
    print(f"Assuming TP of {tp_pct}%:")
    print(f"Fees/Slippage eat {fricton_ratio:.1f}% of every winning trade.")
    
    if fricton_ratio > 20:
        print("⚠️ WARNING: High friction! Costs are eating too much profit.")
        print("ACTION: Consider increasing TP target or moving to a 2.5x RR ratio.")
    else:
        print("✅ Profit room looks healthy.")

    print("\n🏁 Analysis Complete.")

if __name__ == "__main__":
    run_analysis()
