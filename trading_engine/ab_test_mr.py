"""
Quick A/B test: Relaxed MR vs Pure Momentum
Run from project root: PYTHONPATH=. ./venv/bin/python trading_engine/ab_test_mr.py
"""
import os
import pandas as pd
import numpy as np
import pandas_ta as ta
import vectorbt as vbt
from trading_engine.config import STRATEGIES, LIVE_ALLOCATION

def run_test(label, mr_enabled=True, z_override=None, rvol_override=None):
    # Load & resample
    df_btc = pd.read_csv('data/historical/BTC_USDT_5m_365d.csv', parse_dates=['time'], index_col='time')
    df_sol = pd.read_csv('data/historical/SOL_USDT_5m_365d.csv', parse_dates=['time'], index_col='time')
    
    df_btc = df_btc.resample('15min').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
    df_sol = df_sol.resample('15min').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
    
    common = df_btc.index.intersection(df_sol.index)
    df_btc, df_sol = df_btc.loc[common], df_sol.loc[common]
    close = pd.DataFrame({'BTC': df_btc['close'], 'SOL': df_sol['close']}).dropna()
    
    configs = {
        'BTC': STRATEGIES['ADAPTIVE_ENGINE']['params'].copy(),
        'SOL': STRATEGIES['ADAPTIVE_ENGINE_SOL']['params'].copy()
    }
    budgets = {
        'BTC': LIVE_ALLOCATION['BTC_Adaptive']['budget'],
        'SOL': LIVE_ALLOCATION['SOL_Adaptive']['budget']
    }
    
    # Apply overrides
    if z_override:
        for sym in configs:
            configs[sym]['z_score_threshold'] = z_override
    if rvol_override:
        for sym in configs:
            configs[sym]['rvol_threshold'] = rvol_override
    
    # DataFrames
    mr1_entries = pd.DataFrame(index=close.index, columns=['BTC','SOL'], data=False)
    mr1_shorts  = pd.DataFrame(index=close.index, columns=['BTC','SOL'], data=False)
    mr2_entries = pd.DataFrame(index=close.index, columns=['BTC','SOL'], data=False)
    mr2_shorts  = pd.DataFrame(index=close.index, columns=['BTC','SOL'], data=False)
    trend_entries = pd.DataFrame(index=close.index, columns=['BTC','SOL'], data=False)
    trend_shorts  = pd.DataFrame(index=close.index, columns=['BTC','SOL'], data=False)
    
    mr1_size = pd.DataFrame(index=close.index, columns=['BTC','SOL'], data=0.0)
    mr2_size = pd.DataFrame(index=close.index, columns=['BTC','SOL'], data=0.0)
    trend_size_tp   = pd.DataFrame(index=close.index, columns=['BTC','SOL'], data=0.0)
    trend_size_trail = pd.DataFrame(index=close.index, columns=['BTC','SOL'], data=0.0)
    
    sl_mr1   = pd.DataFrame(index=close.index, columns=['BTC','SOL'], data=0.0)
    tp_mr1   = pd.DataFrame(index=close.index, columns=['BTC','SOL'], data=0.0)
    sl_mr2   = pd.DataFrame(index=close.index, columns=['BTC','SOL'], data=0.0)
    sl_trend = pd.DataFrame(index=close.index, columns=['BTC','SOL'], data=0.0)
    tp_trend = pd.DataFrame(index=close.index, columns=['BTC','SOL'], data=0.0)
    
    rolling_corr = close['BTC'].rolling(100).corr(close['SOL']).fillna(0)
    
    for sym, df_orig in [('BTC', df_btc), ('SOL', df_sol)]:
        df = df_orig.reindex(close.index)
        cfg = configs[sym]
        budget = budgets[sym]
        c_close, c_vol = df['close'], df['volume']
        
        bb = df.ta.bbands(length=cfg.get('bb_period',20), std=cfg.get('bb_std',2.0))
        bbl = bb[[c for c in bb.columns if c.startswith('BBL_')][0]]
        bbm = bb[[c for c in bb.columns if c.startswith('BBM_')][0]]
        bbu = bb[[c for c in bb.columns if c.startswith('BBU_')][0]]
        
        rsi = df.ta.rsi(length=14)
        adx_df = df.ta.adx(length=14)
        adx = adx_df[[c for c in adx_df.columns if c.startswith('ADX_')][0]]
        atr = df.ta.atr(length=cfg.get('atr_period',14))
        
        vol_sma = c_vol.rolling(cfg.get('rvol_period',20)).mean()
        rvol = c_vol / vol_sma
        z_mean = c_close.rolling(cfg.get('z_score_period',20)).mean()
        z_std  = c_close.rolling(cfg.get('z_score_period',20)).std()
        z_score = (c_close - z_mean) / z_std
        ema_200 = df.ta.ema(length=200)
        
        atr_pct = atr / c_close
        chaos_mask = atr_pct >= atr_pct.quantile(0.95)
        adx_falling = adx < adx.shift(1)
        
        ranging_mask  = (adx <= cfg.get('adx_limit',30)) & (~chaos_mask)
        trending_mask = (adx > cfg.get('adx_limit',30)) & (~chaos_mask)
        
        # Engulfing
        prev_open, prev_close, curr_open = df['open'].shift(1), c_close.shift(1), df['open']
        bullish_eng = (c_close > curr_open) & (prev_close < prev_open) & (c_close >= prev_open) & (curr_open <= prev_close)
        bearish_eng = (c_close < curr_open) & (prev_close > prev_open) & (c_close <= prev_open) & (curr_open >= prev_close)
        
        # Mean Reversion
        if mr_enabled:
            z_thresh = cfg.get('z_score_threshold', 3.0)
            r_thresh = cfg.get('rvol_threshold', 3.0)
            
            mr_buy  = (c_close <= bbl) & (rsi < cfg.get('rsi_lower',30)) & (z_score < -z_thresh) & (rvol > r_thresh) & ranging_mask
            mr_sell = (c_close >= bbu) & (rsi > cfg.get('rsi_upper',70)) & (z_score > z_thresh) & (rvol > r_thresh) & ranging_mask
            
            if sym == 'BTC':
                mr_sell = pd.Series(False, index=close.index)
            elif sym == 'SOL':
                mr_buy  = mr_buy & bullish_eng
                mr_sell = mr_sell & bearish_eng
        else:
            mr_buy  = pd.Series(False, index=close.index)
            mr_sell = pd.Series(False, index=close.index)
        
        mr1_entries[sym] = mr_buy.fillna(False)
        mr1_shorts[sym]  = mr_sell.fillna(False)
        mr2_entries[sym] = mr_buy.fillna(False)
        mr2_shorts[sym]  = mr_sell.fillna(False)
        mr1_size[sym] = budget * 0.5
        mr2_size[sym] = budget * 0.5
        
        # Trend Following
        rising_adx_3 = (adx > adx.shift(1)) & (adx.shift(1) > adx.shift(2))
        rising_vol_3 = (c_vol > c_vol.shift(1)) & (c_vol.shift(1) > c_vol.shift(2))
        trend_filter = rising_adx_3 & rising_vol_3
        
        trend_buy  = (c_close > bbu) & trending_mask & (c_close > ema_200) & bullish_eng & trend_filter
        trend_sell = (c_close < bbl) & trending_mask & (c_close < ema_200) & bearish_eng & trend_filter
        
        trend_entries[sym] = trend_buy.fillna(False)
        trend_shorts[sym]  = trend_sell.fillna(False)
        
        # If MR disabled, give more budget to trend
        if mr_enabled:
            trend_size_tp[sym]    = pd.Series(budget * 0.3, index=close.index)
            trend_size_trail[sym] = pd.Series(budget * 0.7, index=close.index)
        else:
            trend_size_tp[sym]    = pd.Series(budget * 0.4, index=close.index)
            trend_size_trail[sym] = pd.Series(budget * 0.6, index=close.index)
        
        sl_mr1[sym] = (atr * cfg.get('sl_atr_mult',1.5) / c_close).fillna(0.015)
        tp_mr1[sym] = (abs(c_close - bbm) / c_close).fillna(0.015)
        sl_mr2[sym] = (atr * cfg.get('tp_atr_mult',3.0) / c_close).fillna(0.02)
        sl_trend[sym] = (atr * 8.0 / c_close).fillna(0.04)
        tp_trend[sym] = (atr * 5.0 / c_close).fillna(0.02)
    
    # Correlation filter
    both = (trend_entries['BTC'] | trend_shorts['BTC']) & (trend_entries['SOL'] | trend_shorts['SOL'])
    corr_mask = both & (rolling_corr > 0.8)
    for col in ['BTC','SOL']:
        trend_size_tp.loc[corr_mask, col] *= 0.5
        trend_size_trail.loc[corr_mask, col] *= 0.5
    
    FEE, SLIP = 0.00075, 0.0005
    
    pf_mr1 = vbt.Portfolio.from_signals(close, entries=mr1_entries, short_entries=mr1_shorts,
        sl_stop=sl_mr1, tp_stop=tp_mr1, fees=FEE, slippage=SLIP, freq='15min', init_cash=300.0, size=mr1_size, size_type='value')
    pf_mr2 = vbt.Portfolio.from_signals(close, entries=mr2_entries, short_entries=mr2_shorts,
        sl_stop=sl_mr2, sl_trail=True, tp_stop=0.10, fees=FEE, slippage=SLIP, freq='15min', init_cash=300.0, size=mr2_size, size_type='value')
    pf_tp = vbt.Portfolio.from_signals(close, entries=trend_entries, short_entries=trend_shorts,
        sl_stop=sl_trend, tp_stop=tp_trend, fees=FEE, slippage=SLIP, freq='15min', init_cash=300.0, size=trend_size_tp, size_type='value')
    pf_trail = vbt.Portfolio.from_signals(close, entries=trend_entries, short_entries=trend_shorts,
        sl_stop=sl_trend, sl_trail=True, fees=FEE, slippage=SLIP, freq='15min', init_cash=300.0, size=trend_size_trail, size_type='value')
    
    t1 = pf_mr1.total_profit().sum()
    t2 = pf_mr2.total_profit().sum()
    tr_tp = pf_tp.total_profit().sum()
    tr_trail = pf_trail.total_profit().sum()
    total_net = t1 + t2 + tr_tp + tr_trail
    
    mr_trades = pf_mr1.trades.count().sum() + pf_mr2.trades.count().sum()
    tr_trades = pf_tp.trades.count().sum() + pf_trail.trades.count().sum()
    total_trades = mr_trades + tr_trades
    
    # Win rate
    w = ((pf_mr1.trades.win_rate().fillna(0) * pf_mr1.trades.count()).sum() +
         (pf_mr2.trades.win_rate().fillna(0) * pf_mr2.trades.count()).sum() +
         (pf_tp.trades.win_rate().fillna(0) * pf_tp.trades.count()).sum() +
         (pf_trail.trades.win_rate().fillna(0) * pf_trail.trades.count()).sum())
    wr = (w / total_trades * 100) if total_trades > 0 else 0
    
    eq = ((pf_mr1.value().sum(axis=1) - 300) + (pf_mr2.value().sum(axis=1) - 300) +
          (pf_tp.value().sum(axis=1) - 300) + (pf_trail.value().sum(axis=1) - 300) + 300)
    dd = ((eq - eq.expanding().max()) / eq.expanding().max()).min() * 100
    
    # Profit factor
    gp = sum(pf.trades.winning.pnl.sum().sum() for pf in [pf_mr1, pf_mr2, pf_tp, pf_trail])
    gl = sum(pf.trades.losing.pnl.sum().sum() for pf in [pf_mr1, pf_mr2, pf_tp, pf_trail])
    pf_ratio = abs(gp / gl) if gl != 0 else float('inf')
    
    cagr = total_net / 300 * 100
    calmar = abs(cagr / dd) if dd < 0 else 0
    
    ret = eq.pct_change().dropna()
    sharpe = (ret.mean() / ret.std()) * (24192 ** 0.5) if ret.std() != 0 else 0
    
    fee_est = (mr_trades * 150 + tr_trades * 300) * (FEE + SLIP) * 2
    
    print(f"\n{'='*55}")
    print(f"  {label}")
    print(f"{'='*55}")
    print(f"  Net PnL:       ${total_net:>8.2f} ({cagr:>+6.2f}%)")
    print(f"  Max Drawdown:  {dd:>8.2f}%")
    print(f"  Total Trades:  {total_trades:>8}")
    print(f"    MR Trades:   {mr_trades:>8}")
    print(f"    Trend Trades:{tr_trades:>8}")
    print(f"  Win Rate:      {wr:>8.2f}%")
    print(f"  Profit Factor: {pf_ratio:>8.2f}")
    print(f"  Calmar Ratio:  {calmar:>8.2f}")
    print(f"  Sharpe Proxy:  {sharpe:>8.2f}")
    print(f"  Fees (est.):   ${fee_est:>8.2f}")
    print(f"  MR PnL:        ${t1+t2:>8.2f}")
    print(f"  Trend PnL:     ${tr_tp+tr_trail:>8.2f}")
    print(f"{'='*55}")
    
    return {'label': label, 'pnl': total_net, 'cagr': cagr, 'dd': dd, 'trades': total_trades,
            'calmar': calmar, 'sharpe': sharpe, 'pf': pf_ratio}

if __name__ == '__main__':
    print("\n🔬 Running A/B Test Suite...")
    
    # Baseline (current committed config: z=3.0, rvol=3.0)
    baseline = run_test("📊 BASELINE (z=3.0, rvol=3.0)")
    
    # Test A: Relaxed MR (z=2.8, rvol=2.8 ≈ score 0.78)
    test_a = run_test("🅰️  RELAXED MR (z=2.8, rvol=2.8)", mr_enabled=True, z_override=2.8, rvol_override=2.8)
    
    # Test B: Pure Momentum (MR disabled)
    test_b = run_test("🅱️  PURE MOMENTUM (MR disabled)", mr_enabled=False)
    
    print(f"\n{'='*55}")
    print("  📈 COMPARISON SUMMARY")
    print(f"{'='*55}")
    print(f"{'Metric':<20} {'Baseline':>12} {'Relaxed MR':>12} {'Pure Momo':>12}")
    print(f"{'-'*55}")
    for key, fmt in [('cagr','%'), ('dd','%'), ('trades',''), ('calmar',''), ('sharpe',''), ('pf','')]:
        b = baseline[key]; a = test_a[key]; c = test_b[key]
        if fmt == '%':
            print(f"{key.upper():<20} {b:>11.2f}% {a:>11.2f}% {c:>11.2f}%")
        else:
            print(f"{key.upper():<20} {b:>12.2f} {a:>12.2f} {c:>12.2f}")
    print(f"{'='*55}")
