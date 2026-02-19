
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
from trading_engine.backtest_engine import BacktestEngine

class OptimizationEngine:
    def __init__(self, m1_path, m5_path):
        self.m1_path = m1_path
        self.m5_path = m5_path
        self.df_1m = pd.read_csv(m1_path)
        self.df_5m = pd.read_csv(m5_path)
        self.df_1m['time'] = pd.to_datetime(self.df_1m['time'])
        self.df_5m['time'] = pd.to_datetime(self.df_5m['time'])
        
    def run_grid_search(self, rr_range=[1.5, 2.0, 2.5, 3.0]):
        """
        Tests multiple Risk:Reward ratios on the full dataset.
        """
        results = []
        print(f"🔍 Starting Grid Search over R:R ratios: {rr_range}")
        
        for rr in rr_range:
            print(f"🧪 Testing R:R = {rr}...")
            bt = BacktestEngine(strategy_params={"risk_reward": rr, "test_mode": False})
            bt.load_data(self.df_1m, self.df_5m)
            bt.run()
            
            pnl = bt.balance - 10000.0
            win_rate = 0
            if bt.trades:
                win_rate = (pd.DataFrame(bt.trades)['pnl'] > 0).mean() * 100
                
            results.append({
                'risk_reward': rr,
                'final_pnl': pnl,
                'win_rate': win_rate,
                'total_trades': len(bt.trades)
            })
            
        return pd.DataFrame(results)

    def run_walk_forward(self, rr_range=[1.5, 2.0, 2.5, 3.0], window_days=30):
        """
        Implements Rolling Window Optimization.
        Train on Period 1, Test on Period 2.
        """
        print(f"🏃 Starting Walk-Forward Optimization ({window_days} day windows)...")
        
        start_time = self.df_5m['time'].min()
        end_time = self.df_5m['time'].max()
        
        current_train_start = start_time
        all_test_results = []
        
        while current_train_start + timedelta(days=window_days * 2) <= end_time:
            train_end = current_train_start + timedelta(days=window_days)
            test_end = train_end + timedelta(days=window_days)
            
            print(f"📅 Window: Train [{current_train_start.date()} to {train_end.date()}] | Test [{train_end.date()} to {test_end.date()}]")
            
            # 1. OPTIMIZE (Train)
            best_rr = None
            max_pnl = -np.inf
            
            train_m1 = self.df_1m[(self.df_1m['time'] >= current_train_start) & (self.df_1m['time'] < train_end)]
            train_m5 = self.df_5m[(self.df_5m['time'] >= current_train_start) & (self.df_5m['time'] < train_end)]
            
            if train_m5.empty: break
            
            for rr in rr_range:
                bt = BacktestEngine(strategy_params={"risk_reward": rr, "test_mode": False})
                bt.load_data(train_m1, train_m5)
                bt.run()
                pnl = bt.balance - 10000.0
                if pnl > max_pnl:
                    max_pnl = pnl
                    best_rr = rr
                    
            print(f"⭐ Best R:R for Training Period: {best_rr} (PnL: ${max_pnl:.2f})")
            
            # 2. VALIDATE (Test)
            test_m1 = self.df_1m[(self.df_1m['time'] >= train_end) & (self.df_1m['time'] < test_end)]
            test_m5 = self.df_5m[(self.df_5m['time'] >= train_end) & (self.df_5m['time'] < test_end)]
            
            bt_test = BacktestEngine(strategy_params={"risk_reward": best_rr, "test_mode": False})
            bt_test.load_data(test_m1, test_m5)
            bt_test.run()
            
            pnl_test = bt_test.balance - 10000.0
            all_test_results.append({
                'period': f"{train_end.date()} to {test_end.date()}",
                'best_rr': best_rr,
                'test_pnl': pnl_test,
                'trades': len(bt_test.trades)
            })
            
            # Rolling: Move window forward
            current_train_start = train_end
            
        return pd.DataFrame(all_test_results)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", type=str, default="BTC/USDT")
    args = parser.parse_args()
    
    clean_symbol = args.symbol.replace("/", "_")
    m1_file = f"data/historical/{clean_symbol}_1m_90d.csv"
    m5_file = f"data/historical/{clean_symbol}_5m_90d.csv"
    
    if os.path.exists(m1_file):
        opt = OptimizationEngine(m1_file, m5_file)
        
        # 1. Grid Search
        gs_results = opt.run_grid_search()
        gs_results.to_csv(f"data/backtests/grid_search_{clean_symbol}.csv", index=False)
        print(f"\n✅ Grid Search for {args.symbol} Complete.")
        
        # 2. Walk Forward
        wf_results = opt.run_walk_forward()
        wf_results.to_csv(f"data/backtests/walk_forward_{clean_symbol}.csv", index=False)
        print(f"\n✅ Walk-Forward for {args.symbol} Complete.")
    else:
        print(f"❌ Data not found for {args.symbol} at {m1_file}")
