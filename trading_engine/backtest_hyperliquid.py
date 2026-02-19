
import os
import pandas as pd
import numpy as np
import pandas_ta as ta
import vectorbt as vbt
from trading_engine.config import STRATEGIES, LIVE_ALLOCATION, ENABLE_MEAN_REVERSION

def run_hyperliquid_backtest():
    print("🚀 Loading Hyperliquid 15m data (Max Available ~52 Days)...")
    
    # Load data
    btc_path = 'data/historical/HL_BTC_15m_120d.csv'
    sol_path = 'data/historical/HL_SOL_15m_120d.csv'
    
    if not os.path.exists(btc_path) or not os.path.exists(sol_path):
        print("❌ Missing historical data. Please ensure HL 15m data exists.")
        return
        
    df_btc = pd.read_csv(btc_path)
    df_btc['time'] = pd.to_datetime(df_btc['time'])
    df_btc.set_index('time', inplace=True)
    
    df_sol = pd.read_csv(sol_path)
    df_sol['time'] = pd.to_datetime(df_sol['time'])
    df_sol.set_index('time', inplace=True)
    
    # Data is already 15m, but we'll ensure alignment
    print("⏳ Aligning indices...")
    df_btc = df_btc.resample('15min').first().dropna() 
    df_sol = df_sol.resample('15min').first().dropna()

    # Align on common timestamps
    common_idx = df_btc.index.intersection(df_sol.index)
    df_btc = df_btc.loc[common_idx]
    df_sol = df_sol.loc[common_idx]
    
    close = pd.DataFrame({'BTC': df_btc['close'], 'SOL': df_sol['close']}).dropna()
    
    print("📈 Calculating Indicators...")
    
    configs = {
        'BTC': STRATEGIES['ADAPTIVE_ENGINE']['params'],
        'SOL': STRATEGIES['ADAPTIVE_ENGINE_SOL']['params']
    }
    
    budgets = {
        'BTC': 200, 
        'SOL': 100 
    }
    
    # Boolean DataFrames for entries/shorts
    mr1_entries = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=False)
    mr1_shorts  = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=False)
    mr2_entries = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=False)
    mr2_shorts  = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=False)
    
    trend_entries = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=False)
    trend_shorts  = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=False)
    
    # Size DataFrames
    mr1_size        = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=0.0)
    mr2_size        = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=0.0)
    trend_size_tp   = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=0.0)
    trend_size_trail = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=0.0)
    
    # SL/TP DataFrames
    sl_mr1   = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=0.0)
    tp_mr1   = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=0.0)
    sl_mr2   = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=0.0)
    sl_trend = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=0.0)
    tp_trend = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=0.0)
    
    # Portfolio correlation over last 100 periods
    print("🔗 Calculating Rolling Correlation...")
    rolling_corr = close['BTC'].rolling(100).corr(close['SOL']).fillna(0)
    
    for sym, df_orig in [('BTC', df_btc), ('SOL', df_sol)]:
        df = df_orig.reindex(close.index)
        cfg = configs[sym]
        budget = budgets[sym]
        
        c_close = df['close']
        c_vol = df['volume']
        
        bb = df.ta.bbands(length=cfg.get('bb_period', 20), std=cfg.get('bb_std', 2.0))
        bbl = bb[[c for c in bb.columns if c.startswith('BBL_')][0]]
        bbm = bb[[c for c in bb.columns if c.startswith('BBM_')][0]]
        bbu = bb[[c for c in bb.columns if c.startswith('BBU_')][0]]
        
        rsi = df.ta.rsi(length=cfg.get('rsi_period', 14))
        adx_df = df.ta.adx(length=cfg.get('adx_period', 14))
        adx = adx_df[[c for c in adx_df.columns if c.startswith('ADX_')][0]]
        atr = df.ta.atr(length=cfg.get('atr_period', 14))
        
        vol_sma = c_vol.rolling(cfg.get('rvol_period', 20)).mean()
        rvol = c_vol / vol_sma
        
        z_mean = c_close.rolling(cfg.get('z_score_period', 20)).mean()
        z_std  = c_close.rolling(cfg.get('z_score_period', 20)).std()
        z_score = (c_close - z_mean) / z_std
        
        ema_200 = df.ta.ema(length=200)
        
        atr_pct = atr / c_close
        chaos_threshold = atr_pct.quantile(0.95)
        chaos_mask = atr_pct >= chaos_threshold
        
        adx_falling = adx < adx.shift(1)
        
        ranging_mask  = (adx <= cfg.get('adx_limit', 30)) & (~chaos_mask)
        trending_mask = (adx > cfg.get('adx_limit', 30)) & (~chaos_mask)
        
        # Manual Engulfing Detection
        prev_open  = df['open'].shift(1)
        prev_close = c_close.shift(1)
        curr_open  = df['open']
        
        bullish_engulfing = ((c_close > curr_open) & (prev_close < prev_open) & 
                            (c_close >= prev_open) & (curr_open <= prev_close))
        bearish_engulfing = ((c_close < curr_open) & (prev_close > prev_open) & 
                            (c_close <= prev_open) & (curr_open >= prev_close))
        
        # Mean Reversion 
        mr_buy  = ((c_close <= bbl) & (rsi < cfg.get('rsi_lower', 30)) & 
                   (z_score < -cfg.get('z_score_threshold', 3.0)) & 
                   (rvol > cfg.get('rvol_threshold', 3.0)) & ranging_mask)
        mr_sell = ((c_close >= bbu) & (rsi > cfg.get('rsi_upper', 70)) & 
                   (z_score > cfg.get('z_score_threshold', 3.0)) & 
                   (rvol > cfg.get('rvol_threshold', 3.0)) & ranging_mask)
        
        # MR gated by config flag
        if not ENABLE_MEAN_REVERSION:
            mr_buy  = pd.Series(False, index=close.index)
            mr_sell = pd.Series(False, index=close.index)
        else:
            if sym == 'BTC':
                mr_sell = pd.Series(False, index=close.index)
            elif sym == 'SOL':
                mr_buy  = mr_buy & bullish_engulfing
                mr_sell = mr_sell & bearish_engulfing
        
        mr1_entries[sym] = mr_buy.fillna(False)
        mr1_shorts[sym]  = mr_sell.fillna(False)
        mr2_entries[sym] = mr_buy.fillna(False)
        mr2_shorts[sym]  = mr_sell.fillna(False)
        
        mr1_size[sym] = budget * 0.5
        mr2_size[sym] = budget * 0.5
        
        # Trend requires rising ADX + volume + engulfing
        rising_adx_3 = (adx > adx.shift(1)) & (adx.shift(1) > adx.shift(2))
        rising_vol_3 = (c_vol > c_vol.shift(1)) & (c_vol.shift(1) > c_vol.shift(2))
        trend_filter = rising_adx_3 & rising_vol_3
        
        # ATR dead range filter (V7.1)
        atr_filter = atr_pct > (atr_pct.rolling(50).mean() * 0.4)

        trend_buy  = ((c_close > bbu) & trending_mask & (c_close > ema_200) & 
                      bullish_engulfing & trend_filter & atr_filter)
        trend_sell = ((c_close < bbl) & trending_mask & (c_close < ema_200) & 
                      bearish_engulfing & trend_filter & atr_filter)
        
        trend_entries[sym] = trend_buy.fillna(False)
        trend_shorts[sym]  = trend_sell.fillna(False)
        
        # Trend: allocate more budget if MR is disabled
        if ENABLE_MEAN_REVERSION:
            trend_size_tp[sym]    = pd.Series(budget * 0.3, index=close.index)
            trend_size_trail[sym] = pd.Series(budget * 0.7, index=close.index)
        else:
            trend_size_tp[sym]    = pd.Series(budget * 0.4, index=close.index)
            trend_size_trail[sym] = pd.Series(budget * 0.6, index=close.index)
        
        # Stops
        sl_mr1[sym] = (atr * cfg.get('sl_atr_mult', 1.5) / c_close).fillna(0.015)
        tp_mr1[sym] = (abs(c_close - bbm) / c_close).fillna(0.015)
        
        sl_mr2[sym] = (atr * cfg.get('tp_atr_mult', 3.0) / c_close).fillna(0.02)
        
        sl_trend[sym] = (atr * 8.0 / c_close).fillna(0.04)
        tp_trend[sym] = (atr * 5.0 / c_close).fillna(0.02)

    # Correlation Filter for Trend Size
    both_trend = (trend_entries['BTC'] | trend_shorts['BTC']) & (trend_entries['SOL'] | trend_shorts['SOL'])
    corr_override = both_trend & (rolling_corr > 0.8)
    
    trend_size_tp.loc[corr_override, 'BTC'] *= 0.5
    trend_size_tp.loc[corr_override, 'SOL'] *= 0.5
    trend_size_trail.loc[corr_override, 'BTC'] *= 0.5
    trend_size_trail.loc[corr_override, 'SOL'] *= 0.5
    
    print(f"🔗 Correlation overrides applied to {corr_override.sum()} concurrent signals.")

    # Realistic fee model for Hyperliquid
    REALISTIC_FEE = 0.00035      # Hyperliquid taker fee 0.035%
    REALISTIC_SLIPPAGE = 0.0002  # Hyperliquid conservative slippage 0.02%

    print("🚀 Running VectorBT Simulation (Hyperliquid Assumptions)...")
    pf_mr1 = vbt.Portfolio.from_signals(
        close, entries=mr1_entries, short_entries=mr1_shorts,
        sl_stop=sl_mr1, tp_stop=tp_mr1,
        fees=REALISTIC_FEE, slippage=REALISTIC_SLIPPAGE,
        freq='15min', init_cash=300.0, size=mr1_size, size_type='value'
    )
    
    pf_mr2 = vbt.Portfolio.from_signals(
        close, entries=mr2_entries, short_entries=mr2_shorts,
        sl_stop=sl_mr2, sl_trail=True, tp_stop=0.10,
        fees=REALISTIC_FEE, slippage=REALISTIC_SLIPPAGE,
        freq='15min', init_cash=300.0, size=mr2_size, size_type='value'
    )
    
    pf_trend_tp = vbt.Portfolio.from_signals(
        close, entries=trend_entries, short_entries=trend_shorts,
        sl_stop=sl_trend, tp_stop=tp_trend,
        fees=REALISTIC_FEE, slippage=REALISTIC_SLIPPAGE,
        freq='15min', init_cash=300.0, size=trend_size_tp, size_type='value'
    )

    pf_trend_trail = vbt.Portfolio.from_signals(
        close, entries=trend_entries, short_entries=trend_shorts,
        sl_stop=sl_trend, sl_trail=True,
        fees=REALISTIC_FEE, slippage=REALISTIC_SLIPPAGE,
        freq='15min', init_cash=300.0, size=trend_size_trail, size_type='value'
    )
    
    # Aggregates
    t1_profit = pf_mr1.total_profit().sum()
    t2_profit = pf_mr2.total_profit().sum()
    tr_tp_profit = pf_trend_tp.total_profit().sum()
    tr_trail_profit = pf_trend_trail.total_profit().sum()
    tr_profit = tr_tp_profit + tr_trail_profit
    total_net = t1_profit + t2_profit + tr_profit
    
    mr_trades = pf_mr1.trades.count().sum() + pf_mr2.trades.count().sum()
    tr_trades = pf_trend_tp.trades.count().sum() + pf_trend_trail.trades.count().sum()
    total_trades = mr_trades + tr_trades
    
    # Portfolio Metrics
    total_equity_curve = ((pf_mr1.value().sum(axis=1) - 300.0) + 
                          (pf_mr2.value().sum(axis=1) - 300.0) + 
                          (pf_trend_tp.value().sum(axis=1) - 300.0) + 
                          (pf_trend_trail.value().sum(axis=1) - 300.0) + 300.0)
    
    max_drawdown = ((total_equity_curve / total_equity_curve.expanding().max()) - 1).min() * 100
    
    print("="*50)
    print("📊 HYPERLIQUID BACKTEST RESULTS (30 Days)")
    print("="*50)
    print(f"Initial Capital: $300.00")
    print(f"Final Capital:   ${300.0 + total_net:.2f}")
    print(f"Total Net PnL:   ${total_net:.2f} ({total_net/300.0 * 100:.2f}%)")
    print(f"Max Drawdown:    {max_drawdown:.2f}%")
    print(f"Total Trades:    {total_trades}")
    
    print("\n--- Strategy Breakdown ---")
    print(f"Trend Following            : PnL ${tr_profit:.2f} | Trades {tr_trades}")
    print(f"Mean Reversion (Tier 1 & 2): PnL ${t1_profit + t2_profit:.2f} | Trades {mr_trades}")
    
    # Monthly equivalent return
    print(f"\nMonthly Return:        {total_net/300.0 * 100:.2f}%")
    
    # Sharpe proxy
    total_returns = total_equity_curve.pct_change().dropna()
    if total_returns.std() != 0:
        sharpe = (total_returns.mean() / total_returns.std()) * (24192 ** 0.5)
        print(f"Proxy Sharpe Ratio:    {sharpe:.2f}")

    print("="*50)

if __name__ == '__main__':
    run_hyperliquid_backtest()
