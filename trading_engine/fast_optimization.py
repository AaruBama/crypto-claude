import pandas as pd
import numpy as np
import os
import vectorbt as vbt
try:
    import pandas_ta as ta
except ImportError:
    import pandas_ta_classic as ta

def run_fast_optimization(m5_path, z_scores, rvols, adx_thresholds, tp_multipliers):
    print("🚀 Loading 5m data for VectorBT Fast Optimization...")
    df = pd.read_csv(m5_path)
    df['time'] = pd.to_datetime(df['time'])
    df.set_index('time', inplace=True)
    
    # Needs to be small for memory constraints on huge parameter sweeps
    close = df['close']
    low = df['low']
    high = df['high']
    volume = df['volume']
    
    # ── 1. Calculate base indicators for the sweep ──
    print("⏳ Calculating base indicators across the entire dataset...")
    # These parameters are static for Mean Reversion V5
    bb_period = 20
    bb_std_val = 2.0
    adx_period = 14
    atr_period = 14
    z_score_period = 20
    rvol_period = 20
    
    # Bollinger Bands
    bb = df.ta.bbands(length=bb_period, std=bb_std_val)
    if bb is None:
        raise ValueError("TA-Lib couldn't compute Bollinger Bands.")
        
    bb_lower_col = [c for c in bb.columns if c.startswith('BBL_')][0]
    bb_upper_col = [c for c in bb.columns if c.startswith('BBU_')][0]
    bb_mid_col = [c for c in bb.columns if c.startswith('BBM_')][0]
    
    bb_lower = bb[bb_lower_col]
    bb_upper = bb[bb_upper_col]
    bb_mid = bb[bb_mid_col]
    
    # RSI & ADX
    rsi = df.ta.rsi(length=14)
    adx_df = df.ta.adx(length=adx_period)
    adx_col = [c for c in adx_df.columns if c.startswith('ADX_')][0]
    adx = adx_df[adx_col]
    adx_falling = adx.diff() < 0
    
    # RVOL
    vol_sma = volume.rolling(window=rvol_period).mean()
    rvol = volume / vol_sma
    
    # Z-Score
    close_mean = close.rolling(window=z_score_period).mean()
    close_std = close.rolling(window=z_score_period).std()
    z_score = (close - close_mean) / close_std
    
    # ATR
    atr = df.ta.atr(length=atr_period)
    
    print("⚡ Vectorizing parameter combinations...")
    
    # Build a multi-index of all combinations
    import itertools
    combinations = list(itertools.product(z_scores, rvols, adx_thresholds, tp_multipliers))
    print(f"Total Combinations: {len(combinations)}")
    
    results = []
    
    # Static RSI thresholds for this sweep to keep permutations manageable
    rsi_lower_val = 30
    rsi_upper_val = 70
    
    sl_stop_base = (atr * 1.5 / close).fillna(0.015).values
    tp_mid = curr_pct_tp(close, bb_mid).values
    
    # Iterate through parameters (this is still faster than pure python backtesting)
    for i, (z, r, adx_thresh, tp_mult) in enumerate(combinations):
        
        # ── BUY CONDITIONS ──
        buy_cond = (
            (close <= bb_lower) & 
            (rsi < rsi_lower_val) & 
            (z_score < -z) & 
            (rvol > r) & 
            (adx <= adx_thresh)
        )
        
        # ── SELL CONDITIONS ──
        sell_cond = (
            (close >= bb_upper) & 
            (rsi > rsi_upper_val) & 
            (z_score > z) & 
            (rvol > r) & 
            (adx <= adx_thresh)
        )
        
        entries = buy_cond.fillna(False)
        short_entries = sell_cond.fillna(False)
        
        # ── 2-TIER EXIT SIMULATION ──
        # Tier 1: 50% exits at bb_mid, standard 1.5 ATR SL
        pf1 = vbt.Portfolio.from_signals(
            close,
            entries=entries,
            short_entries=short_entries,
            sl_stop=sl_stop_base,
            tp_stop=tp_mid,
            fees=0.0002,  # Conservative Maker Fee (0.02%)
            freq='5T',
            init_cash=150.0,
            size=75.0, # 50% of trade budget
            size_type='value'
        )
        
        # Tier 2: 50% exits with Trailing Stop or Opposite BB
        # We model the trailing stop via vbt sl_trail=True
        # Set TP to a very large number so trailing stop usually hits, OR approximate opposite BB
        trail_stop_pct = (atr * tp_mult / close).fillna(0.015).values
        pf2 = vbt.Portfolio.from_signals(
            close,
            entries=entries,
            short_entries=short_entries,
            sl_stop=trail_stop_pct,
            sl_trail=True,
            # We can use opposite BB as static TP for runner
            # Since tp_stop in vbt from_signals applies equally to long/short entries as a % distance:
            # For simplicity of runner, we let the trailing stop do the work.
            tp_stop=0.10, # 10% hard cap
            fees=0.0002,  # Conservative Maker Fee (0.02%)
            freq='5T',
            init_cash=150.0,
            size=75.0, # other 50%
            size_type='value'
        )
        
        total_pnl = pf1.total_profit() + pf2.total_profit()
        t1_len = len(pf1.trades)
        t2_len = len(pf2.trades)
        
        if t1_len + t2_len > 0:
            # Weighted win rate approximation
            win_rate = ((pf1.trades.win_rate() * t1_len) + (pf2.trades.win_rate() * t2_len)) / (t1_len + t2_len) * 100
        else:
            win_rate = 0.0
            
        results.append({
            'z_score': z,
            'rvol': r,
            'adx_threshold': adx_thresh,
            'tp_multiplier': tp_mult,
            'final_pnl': total_pnl,
            'win_rate': float(win_rate),
            'total_trades': t1_len
        })
        
        if (i+1) % 10 == 0:
            print(f"Processed {i+1}/{len(combinations)}...")
            
    res_df = pd.DataFrame(results)
    return res_df

def curr_pct_tp(close, target):
    # Returns the % difference between close and target for vbt tp_stop
    pct = (target - close).abs() / close
    return pct.fillna(0.01) # Default 1% if NaN

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", type=str, default="BTC/USDT")
    parser.add_argument("--days", type=int, default=365)
    args = parser.parse_args()
    
    clean_symbol = args.symbol.replace("/", "_")
    m5_file = f"data/historical/{clean_symbol}_5m_{args.days}d.csv"
    
    if os.path.exists(m5_file):
        z_scores = [2.5, 3.0, 3.5, 4.0]
        rvols = [2.0, 2.5, 3.0]
        adx_thresholds = [20, 25, 30]
        tp_multipliers = [1.0, 1.5, 2.0]
        
        res_df = run_fast_optimization(m5_file, z_scores, rvols, adx_thresholds, tp_multipliers)
        res_df = res_df.sort_values(by="final_pnl", ascending=False)
        output_file = f"data/backtests/vbt_optimization_{clean_symbol}.csv"
        
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        res_df.to_csv(output_file, index=False)
        
        print(f"\n✅ VectorBT Optimization Complete. Top 5 Results:\n{res_df.head(5)}")
        print(f"Saved to {output_file}")
    else:
        print(f"❌ Data not found for {args.symbol} at {m5_file}")
