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
    
    # Trend Base EMA Filter (Macro Trend)
    ema_200 = df.ta.ema(length=200)
    
    # Chaos filtering
    atr_pct = atr / close
    chaos_threshold = atr_pct.quantile(0.95)
    chaos_mask = atr_pct >= chaos_threshold
    
    print("⚡ Vectorizing parameter combinations...")
    
    # Build a multi-index of all combinations
    import itertools
    combinations = list(itertools.product(z_scores, rvols, adx_thresholds, tp_multipliers))
    print(f"Total Combinations: {len(combinations)}")
    
    results = []
    
    # Static RSI thresholds for this sweep to keep permutations manageable
    rsi_lower_val = 30
    rsi_upper_val = 70
    
    sl_stop_mr_base = (atr * 1.5 / close).fillna(0.015).values
    tp_mid = curr_pct_tp(close, bb_mid).values
    
    # Iterate through parameters (this is still faster than pure python backtesting)
    for i, (z, r, adx_thresh, tp_mult) in enumerate(combinations):
        
        # ── REGIME ROUTING ──
        ranging_mask = (adx <= adx_thresh) & (~chaos_mask)
        trending_mask = (adx > adx_thresh) & (~chaos_mask)
        
        # ── 1. RANGING MODE: Mean Reversion ──
        mr_buy = (close <= bb_lower) & (rsi < rsi_lower_val) & (z_score < -z) & (rvol > r) & ranging_mask
        mr_sell = (close >= bb_upper) & (rsi > rsi_upper_val) & (z_score > z) & (rvol > r) & ranging_mask
        
        mr_entries = mr_buy.fillna(False)
        mr_shorts = mr_sell.fillna(False)
        
        # Tier 1 MR: 50% exits at bb_mid, standard 1.5 ATR SL
        pf_mr1 = vbt.Portfolio.from_signals(
            close,
            entries=mr_entries,
            short_entries=mr_shorts,
            sl_stop=sl_stop_mr_base,
            tp_stop=tp_mid,
            fees=0.0002,
            freq='5T',
            init_cash=150.0,
            size=75.0, # 50%
            size_type='value'
        )
        
        # Tier 2 MR: 50% trails with User Defined tp_mult
        trail_pct_mr = (atr * tp_mult / close).fillna(0.015).values
        pf_mr2 = vbt.Portfolio.from_signals(
            close,
            entries=mr_entries,
            short_entries=mr_shorts,
            sl_stop=trail_pct_mr,
            sl_trail=True,
            tp_stop=0.10, # hard cap 10%
            fees=0.0002,
            freq='5T',
            init_cash=150.0,
            size=75.0, # 50%
            size_type='value'
        )
        
        # ── 2. TRENDING MODE: Momentum Breakout ──
        # Structural macro-trend filter prevents 5m chop whipsaws
        trend_buy = (close > bb_upper) & (~adx_falling) & trending_mask & (close > ema_200)
        trend_sell = (close < bb_lower) & (~adx_falling) & trending_mask & (close < ema_200)
        
        trend_entries = trend_buy.fillna(False)
        trend_shorts = trend_sell.fillna(False)
        
        # Trend Portfolio: Fat Tail Trailing Stop
        # 3.0 ATR on a 5m chart is too small to capture "10% moves", so we scale it 
        # (10x 5m ATR roughly approximates a 4H 2.5 ATR)
        trend_sl_pct = (atr * 10.0 / close).fillna(0.04).values
        pf_trend = vbt.Portfolio.from_signals(
            close,
            entries=trend_entries,
            short_entries=trend_shorts,
            sl_stop=trend_sl_pct,
            sl_trail=True,
            tp_stop=1.0, # Never hit TP, let trail exit
            fees=0.0002,
            freq='5T',
            init_cash=150.0,
            size=150.0, # 100% allocation for Trend Module
            size_type='value'
        )
        
        total_pnl = pf_mr1.total_profit() + pf_mr2.total_profit() + pf_trend.total_profit()
        t1_len = len(pf_mr1.trades)
        t2_len = len(pf_mr2.trades)
        tr_len = len(pf_trend.trades)
        total_trades = t1_len + t2_len + tr_len
        
        if total_trades > 0:
            win_wgts = (pf_mr1.trades.win_rate() * t1_len) + (pf_mr2.trades.win_rate() * t2_len) + (pf_trend.trades.win_rate() * tr_len)
            win_rate = win_wgts / total_trades * 100
        else:
            win_rate = 0.0
            
        results.append({
            'z_score': z,
            'rvol': r,
            'adx_threshold': adx_thresh,
            'tp_multiplier': tp_mult,
            'final_pnl': total_pnl,
            'win_rate': float(win_rate),
            'total_trades': total_trades
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
