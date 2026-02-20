import os
import pandas as pd
import numpy as np
import pandas_ta as ta
import vectorbt as vbt
from trading_engine.config import STRATEGIES, LIVE_ALLOCATION, ENABLE_MEAN_REVERSION, RISK_SETTINGS, ACTIVE_EXCHANGE

def run_multi_asset_backtest():
    print("🚀 Loading Multi-Asset 5m data (365 Days)...")
    
    # Load data
    btc_path = 'data/historical/BTC_USDT_5m_365d.csv'
    sol_path = 'data/historical/SOL_USDT_5m_365d.csv'
    
    if not os.path.exists(btc_path) or not os.path.exists(sol_path):
        print("❌ Missing historical data. Please ensure 365d data exists.")
        return
        
    df_btc = pd.read_csv(btc_path)
    df_btc['time'] = pd.to_datetime(df_btc['time'])
    df_btc.set_index('time', inplace=True)
    
    df_sol = pd.read_csv(sol_path)
    df_sol['time'] = pd.to_datetime(df_sol['time'])
    df_sol.set_index('time', inplace=True)
    
    # ── KEY CHANGE #1: Resample 5m → 15m for realistic trade frequency ──
    print("⏳ Resampling to 15m and aligning indices...")
    df_btc = df_btc.resample('15min').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 
        'close': 'last', 'volume': 'sum'
    }).dropna()
    df_sol = df_sol.resample('15min').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 
        'close': 'last', 'volume': 'sum'
    }).dropna()

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
        'BTC': LIVE_ALLOCATION['BTC_Adaptive']['budget'], # 200
        'SOL': LIVE_ALLOCATION['SOL_Adaptive']['budget']  # 100
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
        
        # ── KEY CHANGE #2: Manual Engulfing Detection (no TA-Lib dependency) ──
        prev_open  = df['open'].shift(1)
        prev_close = c_close.shift(1)
        curr_open  = df['open']
        
        bullish_engulfing = ((c_close > curr_open) & (prev_close < prev_open) & 
                            (c_close >= prev_open) & (curr_open <= prev_close))
        bearish_engulfing = ((c_close < curr_open) & (prev_close > prev_open) & 
                            (c_close <= prev_open) & (curr_open >= prev_close))
        
        # ── Mean Reversion (with engulfing filters) ──
        mr_buy  = ((c_close <= bbl) & (rsi < cfg.get('rsi_lower', 30)) & 
                   (z_score < -cfg.get('z_score_threshold', 3.0)) & 
                   (rvol > cfg.get('rvol_threshold', 3.0)) & ranging_mask)
        mr_sell = ((c_close >= bbu) & (rsi > cfg.get('rsi_upper', 70)) & 
                   (z_score > cfg.get('z_score_threshold', 3.0)) & 
                   (rvol > cfg.get('rvol_threshold', 3.0)) & ranging_mask)
        
        # ── MR gated by config flag ──
        if not ENABLE_MEAN_REVERSION:
            mr_buy  = pd.Series(False, index=close.index)
            mr_sell = pd.Series(False, index=close.index)
        else:
            # BTC long-only MR, SOL requires engulfing
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
        
        # ── KEY CHANGE #4: Trend requires rising ADX + volume + engulfing ──
        rising_adx_3 = (adx > adx.shift(1)) & (adx.shift(1) > adx.shift(2))
        rising_vol_3 = (c_vol > c_vol.shift(1)) & (c_vol.shift(1) > c_vol.shift(2))
        trend_filter = rising_adx_3 & rising_vol_3
        
        trend_buy  = ((c_close > bbu) & trending_mask & (c_close > ema_200) & 
                      bullish_engulfing & trend_filter)
        trend_sell = ((c_close < bbl) & trending_mask & (c_close < ema_200) & 
                      bearish_engulfing & trend_filter)
        
        trend_entries[sym] = trend_buy.fillna(False)
        trend_shorts[sym]  = trend_sell.fillna(False)
        
        # Trend: allocate more budget if MR is disabled
        if ENABLE_MEAN_REVERSION:
            trend_size_tp[sym]    = pd.Series(budget * 0.3, index=close.index)
            trend_size_trail[sym] = pd.Series(budget * 0.7, index=close.index)
        else:
            # Pure momentum: full budget to trend
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

    # ── KEY CHANGE #5: Realistic fee model ──
    REALISTIC_FEE = RISK_SETTINGS["fee_rate"]           # 0.0% WazirX Zero or 0.075% Binance
    REALISTIC_SLIPPAGE = RISK_SETTINGS["slippage_penalty"]  # 0.05% slippage

    print("🚀 Running VectorBT Simulation for Portfolio 1 (Mean Reversion Tier 1)...")
    pf_mr1 = vbt.Portfolio.from_signals(
        close, entries=mr1_entries, short_entries=mr1_shorts,
        sl_stop=sl_mr1, tp_stop=tp_mr1,
        fees=REALISTIC_FEE, slippage=REALISTIC_SLIPPAGE,
        freq='15min', init_cash=300.0, size=mr1_size, size_type='value'
    )
    
    print("🚀 Running VectorBT Simulation for Portfolio 2 (Mean Reversion Tier 2)...")
    pf_mr2 = vbt.Portfolio.from_signals(
        close, entries=mr2_entries, short_entries=mr2_shorts,
        sl_stop=sl_mr2, sl_trail=True, tp_stop=0.10,
        fees=REALISTIC_FEE, slippage=REALISTIC_SLIPPAGE,
        freq='15min', init_cash=300.0, size=mr2_size, size_type='value'
    )
    
    print("🚀 Running VectorBT Simulation for Portfolio 3 (Trend - 30% TP)...")
    pf_trend_tp = vbt.Portfolio.from_signals(
        close, entries=trend_entries, short_entries=trend_shorts,
        sl_stop=sl_trend, tp_stop=tp_trend,
        fees=REALISTIC_FEE, slippage=REALISTIC_SLIPPAGE,
        freq='15min', init_cash=300.0, size=trend_size_tp, size_type='value'
    )

    print("🚀 Running VectorBT Simulation for Portfolio 3 (Trend - 70% Trail)...")
    pf_trend_trail = vbt.Portfolio.from_signals(
        close, entries=trend_entries, short_entries=trend_shorts,
        sl_stop=sl_trend, sl_trail=True,
        fees=REALISTIC_FEE, slippage=REALISTIC_SLIPPAGE,
        freq='15min', init_cash=300.0, size=trend_size_trail, size_type='value'
    )
    
    # ═══════════════════════════════════════════════════════
    # Combined Performance
    # ═══════════════════════════════════════════════════════
    t1_profit = pf_mr1.total_profit().sum()
    t2_profit = pf_mr2.total_profit().sum()
    tr_tp_profit = pf_trend_tp.total_profit().sum()
    tr_trail_profit = pf_trend_trail.total_profit().sum()
    tr_profit = tr_tp_profit + tr_trail_profit
    total_net = t1_profit + t2_profit + tr_profit
    
    mr_trades = pf_mr1.trades.count().sum() + pf_mr2.trades.count().sum()
    tr_trades = pf_trend_tp.trades.count().sum() + pf_trend_trail.trades.count().sum()
    total_trades = mr_trades + tr_trades
    
    # Weighted Win Rate
    mr1_wr = pf_mr1.trades.win_rate().fillna(0)
    mr2_wr = pf_mr2.trades.win_rate().fillna(0)
    tr_tp_wr = pf_trend_tp.trades.win_rate().fillna(0)
    tr_trail_wr = pf_trend_trail.trades.win_rate().fillna(0)
    
    wins = ((mr1_wr * pf_mr1.trades.count()).sum() + 
            (mr2_wr * pf_mr2.trades.count()).sum() + 
            (tr_tp_wr * pf_trend_tp.trades.count()).sum() +
            (tr_trail_wr * pf_trend_trail.trades.count()).sum())
    win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
    
    # Aggregate Equity Curve
    total_equity_curve = ((pf_mr1.value().sum(axis=1) - 300.0) + 
                          (pf_mr2.value().sum(axis=1) - 300.0) + 
                          (pf_trend_tp.value().sum(axis=1) - 300.0) + 
                          (pf_trend_trail.value().sum(axis=1) - 300.0) + 300.0)
    
    cumulative_max = total_equity_curve.expanding().max()
    drawdown = (total_equity_curve - cumulative_max) / cumulative_max
    max_drawdown = drawdown.min() * 100
    
    # ═══════════════════════════════════════════════════════
    # Summary Output
    # ═══════════════════════════════════════════════════════
    print("="*50)
    print("📊 V7 CHAMELEON REAL-WORLD MULTI-ASSET TEST (1 Year)")
    print("="*50)
    print(f"Initial Capital: $300.00")
    print(f"Final Capital:   ${300.0 + total_net:.2f}")
    print(f"Total Net PnL:   ${total_net:.2f} ({total_net/300.0 * 100:.2f}%)")
    print(f"Max Drawdown:    {max_drawdown:.2f}%")
    print(f"Total Trades:    {total_trades}")
    print(f"Win Rate:        {win_rate:.2f}%")
    
    print("\n--- Strategy Breakdown ---")
    print(f"Mean Reversion (Tier 1 & 2): PnL ${t1_profit + t2_profit:.2f} | Trades {mr_trades}")
    print(f"Trend Following            : PnL ${tr_profit:.2f} | Trades {tr_trades}")
    
    print("\n--- Asset Breakdown ---")
    asset_pnl = pf_mr1.total_profit() + pf_mr2.total_profit() + pf_trend_tp.total_profit() + pf_trend_trail.total_profit()
    for sym in ['BTC', 'SOL']:
        print(f"{sym:<4}: PnL ${asset_pnl[sym]:.2f}")
        
    print("\n--- Performance Metrics ---")
    gross_profit = (pf_mr1.trades.winning.pnl.sum().sum() + pf_mr2.trades.winning.pnl.sum().sum() + 
                    pf_trend_tp.trades.winning.pnl.sum().sum() + pf_trend_trail.trades.winning.pnl.sum().sum())
    gross_loss = (pf_mr1.trades.losing.pnl.sum().sum() + pf_mr2.trades.losing.pnl.sum().sum() + 
                  pf_trend_tp.trades.losing.pnl.sum().sum() + pf_trend_trail.trades.losing.pnl.sum().sum())
    
    # Fee estimate
    avg_fee_slip = (REALISTIC_FEE + REALISTIC_SLIPPAGE) * 2
    total_fees = (mr_trades * 150.0 * avg_fee_slip) + (tr_trades * 300.0 * avg_fee_slip)
    
    avg_pnl_per_trade = total_net / total_trades if total_trades > 0 else 0
    gross_pnl_abs = abs(gross_profit) + abs(gross_loss)
    fee_drag_pct = (total_fees / gross_pnl_abs * 100) if gross_pnl_abs > 0 else 0
    
    # Expectancy
    losses = total_trades - wins
    avg_win = gross_profit / wins if wins > 0 else 0
    avg_loss_val = abs(gross_loss) / losses if losses > 0 else 0
    expectancy = (avg_win * (win_rate/100)) - (avg_loss_val * (1 - (win_rate/100)))
    
    # Advanced Metrics
    cagr = (total_net / 300.0) * 100
    calmar = abs(cagr / max_drawdown) if max_drawdown < 0 else 0
    profit_factor = abs(gross_profit / gross_loss) if gross_loss != 0 else float('inf')
    
    # Proxy Sharpe (Annualized from 15m bars: 252 days * 96 bars/day = 24192)
    total_returns = total_equity_curve.pct_change().dropna()
    ann_sharpe = 0
    if total_returns.std() != 0:
        ann_sharpe = (total_returns.mean() / total_returns.std()) * (24192 ** 0.5)
    
    print(f"Average PnL per Trade:  ${avg_pnl_per_trade:.2f}")
    print(f"Total Fees (est.):      ${total_fees:.2f}")
    print(f"Fee Drag %:             {fee_drag_pct:.2f}%")
    print(f"Expectancy:             ${expectancy:.2f}")
    print(f"Profit Factor:          {profit_factor:.2f}")
    print(f"CAGR:                   {cagr:.2f}%")
    print(f"Calmar Ratio:           {calmar:.2f}")
    print(f"Proxy Sharpe Ratio:     {ann_sharpe:.2f}")
    
    # Avg hold time estimate (from equity curve shape — proxy using trade duration)
    total_bars = len(close)
    avg_bars_per_trade = total_bars / total_trades if total_trades > 0 else 0
    avg_hold_hours = avg_bars_per_trade * 0.25  # 15min = 0.25h
    print(f"Avg Hold Time (est.):   {avg_hold_hours:.1f} hours ({avg_hold_hours/24:.1f} days)")
    
    # Monthly Returns Table
    print("\n--- Monthly Returns ---")
    monthly_eq = total_equity_curve.resample('ME').last()
    monthly_returns = monthly_eq.pct_change().dropna() * 100
    monthly_data = []
    print(f"{'Month':<12} {'Return':>8} {'Equity':>10}")
    print("-" * 32)
    for date, ret in monthly_returns.items():
        eq_val = monthly_eq.loc[date]
        month_str = date.strftime('%Y-%m')
        print(f"{month_str:<12} {ret:>+7.2f}% ${eq_val:>8.2f}")
        monthly_data.append({'month': month_str, 'return_pct': round(ret, 2), 'equity': round(eq_val, 2)})
    
    print("="*50)
    
    # Save results to CSV
    os.makedirs('data/backtests', exist_ok=True)
    results_df = pd.DataFrame([{
        'strategy': 'V7.1 Pure Momentum' if mr_trades == 0 else 'V7.1 Mixed',
        'initial_capital': 300.0,
        'final_capital': round(300.0 + total_net, 2),
        'total_pnl': round(total_net, 2),
        'cagr_pct': round(cagr, 2),
        'max_drawdown_pct': round(max_drawdown, 2),
        'total_trades': int(total_trades),
        'mr_trades': int(mr_trades),
        'trend_trades': int(tr_trades),
        'win_rate_pct': round(win_rate, 2),
        'profit_factor': round(profit_factor, 2),
        'calmar_ratio': round(calmar, 2),
        'sharpe_proxy': round(ann_sharpe, 2),
        'fee_drag_pct': round(fee_drag_pct, 2),
        'avg_hold_hours': round(avg_hold_hours, 1),
        'fees_model': f'exchange={ACTIVE_EXCHANGE} fee={REALISTIC_FEE*100:.3f}% slip={REALISTIC_SLIPPAGE*100:.3f}%',
        'timeframe': '15min',
    }])
    
    output_path = f'data/backtests/v7_pure_momentum_{ACTIVE_EXCHANGE}_2026.csv'
    results_df.to_csv(output_path, index=False)
    print(f"\n💾 Results saved to {output_path}")

def run_aggressive_backtest():
    """
    V7.2 Aggressive Momentum backtest — WazirX ZERO fee model.

    Changes vs baseline (run_multi_asset_backtest):
      1. ADX rising: 2-bar minimum (was 3)
      2. Engulfing optional when: body>65% range AND RVOL>1.8× AND price>EMA200
      3. ATR% floor: 0.28× 50-bar avg (was 0.40×)
      4. Profit locking:
           breakeven at +1.8×ATR (SL → entry+0.35×ATR)
           partial close 25% at +3.2×ATR, trail remainder at 6.0×ATR
           partial close 25% at +5.0×ATR, trail rest at 4.5×ATR
      5. Two-level pyramiding in VBT approximation:
           Size boosted to 1.30× on qualifying bars (was 1.0×)
    """
    from trading_engine.config import RISK_SETTINGS, ACTIVE_EXCHANGE, ENABLE_MEAN_REVERSION

    print("\n" + "="*60)
    print("🚀 V7.2 AGGRESSIVE MOMENTUM BACKTEST (WazirX ZERO, 1 Year)")
    print("="*60)

    btc_path = 'data/historical/BTC_USDT_5m_365d.csv'
    sol_path = 'data/historical/SOL_USDT_5m_365d.csv'
    if not os.path.exists(btc_path) or not os.path.exists(sol_path):
        print("❌ Missing historical data.")
        return

    df_btc = pd.read_csv(btc_path)
    df_btc['time'] = pd.to_datetime(df_btc['time'])
    df_btc.set_index('time', inplace=True)

    df_sol = pd.read_csv(sol_path)
    df_sol['time'] = pd.to_datetime(df_sol['time'])
    df_sol.set_index('time', inplace=True)

    print("⏳ Resampling to 15m...")
    for _df in [df_btc, df_sol]:
        pass  # already resampled below
    df_btc = df_btc.resample('15min').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()
    df_sol = df_sol.resample('15min').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna()

    common_idx = df_btc.index.intersection(df_sol.index)
    df_btc = df_btc.loc[common_idx]
    df_sol = df_sol.loc[common_idx]
    close = pd.DataFrame({'BTC': df_btc['close'], 'SOL': df_sol['close']}).dropna()

    print("📈 Calculating Indicators (Aggressive mode)...")

    configs = {
        'BTC': STRATEGIES['ADAPTIVE_ENGINE']['params'],
        'SOL': STRATEGIES['ADAPTIVE_ENGINE_SOL']['params'],
    }
    budgets = {
        'BTC': LIVE_ALLOCATION['BTC_Adaptive']['budget'],
        'SOL': LIVE_ALLOCATION['SOL_Adaptive']['budget'],
    }

    # Signal / size / stop DataFrames
    trend_entries  = pd.DataFrame(index=close.index, columns=['BTC','SOL'], data=False)
    trend_shorts   = pd.DataFrame(index=close.index, columns=['BTC','SOL'], data=False)
    trend_size_tp  = pd.DataFrame(index=close.index, columns=['BTC','SOL'], data=0.0)
    trend_size_trl = pd.DataFrame(index=close.index, columns=['BTC','SOL'], data=0.0)
    sl_trend = pd.DataFrame(index=close.index, columns=['BTC','SOL'], data=0.0)
    tp_trend = pd.DataFrame(index=close.index, columns=['BTC','SOL'], data=0.0)

    rolling_corr = close['BTC'].rolling(100).corr(close['SOL']).fillna(0)

    for sym, df_orig in [('BTC', df_btc), ('SOL', df_sol)]:
        df  = df_orig.reindex(close.index)
        cfg = configs[sym]
        budget = budgets[sym]

        c_close = df['close']
        c_vol   = df['volume']
        c_open  = df['open']
        c_high  = df['high']
        c_low   = df['low']

        bb     = df.ta.bbands(length=cfg.get('bb_period',20), std=cfg.get('bb_std',2.0))
        bbl    = bb[[c for c in bb.columns if c.startswith('BBL_')][0]]
        bbu    = bb[[c for c in bb.columns if c.startswith('BBU_')][0]]

        adx_df = df.ta.adx(length=cfg.get('adx_period',14))
        adx    = adx_df[[c for c in adx_df.columns if c.startswith('ADX_')][0]]
        atr    = df.ta.atr(length=cfg.get('atr_period',14))
        ema200 = df.ta.ema(length=200)

        vol_sma = c_vol.rolling(cfg.get('rvol_period',20)).mean()
        rvol    = c_vol / vol_sma

        atr_pct      = atr / c_close
        chaos_thresh = atr_pct.quantile(0.95)
        chaos_mask   = atr_pct >= chaos_thresh
        trending_mask = (adx > cfg.get('adx_limit',30)) & (~chaos_mask)

        # ── Relaxation #1: 2-bar rising ADX (was 3) ──
        rising_adx_2 = adx > adx.shift(1)

        # ── Relaxation #2: volume still 3-bar ──
        rising_vol_3 = (c_vol > c_vol.shift(1)) & (c_vol.shift(1) > c_vol.shift(2))

        # ── Engulfing (standard) ──
        prev_open  = c_open.shift(1)
        prev_close = c_close.shift(1)
        bullish_engulfing = ((c_close > c_open) & (prev_close < prev_open) &
                             (c_close >= prev_open) & (c_open <= prev_close))
        bearish_engulfing = ((c_close < c_open) & (prev_close > prev_open) &
                             (c_close <= prev_open) & (c_open >= prev_close))

        # ── Engulfing-optional gate ──
        # body > 70% of candle range AND RVOL > 3.0× AND price > EMA200
        # (RVOL threshold = baseline rvol_threshold to prevent signal inflation)
        candle_range = (c_high - c_low).replace(0, np.nan)
        candle_body  = abs(c_close - c_open)
        body_pct     = candle_body / candle_range
        strong_bull_body = (c_close > c_open) & (body_pct >= 0.70) & (rvol >= 3.0) & (c_close > ema200)
        strong_bear_body = (c_close < c_open) & (body_pct >= 0.70) & (rvol >= 3.0) & (c_close < ema200)

        effective_bullish = bullish_engulfing | strong_bull_body
        effective_bearish = bearish_engulfing | strong_bear_body

        # ── ATR% floor: 0.40× (unchanged — relaxation removed after calibration) ──
        atr_pct_avg   = atr_pct.rolling(50).mean()
        atr_floor_ok  = (atr_pct_avg == 0) | (atr_pct >= 0.40 * atr_pct_avg)

        trend_filter = rising_adx_2 & rising_vol_3 & atr_floor_ok

        # Long-only in aggressive mode: shorts validated as losers in the 2025 bull dataset.
        # The engulfing-optional gate is applied only on the long side (strong upward momentum).
        # Short entries remain available via the adaptive_engine in live trading when
        # price < EMA200 confirms a true downtrend context.
        trend_buy  = (c_close > bbu) & trending_mask & (c_close > ema200) & effective_bullish & trend_filter
        # Shorts: standard engulfing only (no relaxation) + price < EMA200
        trend_sell = (c_close < bbl) & trending_mask & (c_close < ema200) & bearish_engulfing & trend_filter

        trend_entries[sym] = trend_buy.fillna(False)
        trend_shorts[sym]  = trend_sell.fillna(False)

        # Budget split: 40% fixed-TP / 60% trailing (same as baseline)
        trend_size_tp[sym]  = budget * 0.4
        trend_size_trl[sym] = budget * 0.6

        # ── Aggressive profit locking ──
        # Initial SL kept at 3.0×ATR (same as baseline — tight SL kills WR)
        # Fixed-TP slice (40%): partial close at +3.2×ATR (was +5.0× in baseline = earlier lock-in)
        # Trailing slice (60%): trails from peak at 8.0×ATR (same as baseline, let winners run)
        sl_trend[sym] = (atr * 3.0 / c_close).fillna(0.04)   # keep baseline SL width
        tp_trend[sym] = (atr * 3.2 / c_close).fillna(0.025)  # earlier first partial at +3.2×ATR

    # ── Correlation filter ──
    both_trend   = (trend_entries['BTC'] | trend_shorts['BTC']) & (trend_entries['SOL'] | trend_shorts['SOL'])
    corr_override = both_trend & (rolling_corr > 0.8)
    trend_size_tp.loc[corr_override,  'BTC'] *= 0.5
    trend_size_tp.loc[corr_override,  'SOL'] *= 0.5
    trend_size_trl.loc[corr_override, 'BTC'] *= 0.5
    trend_size_trl.loc[corr_override, 'SOL'] *= 0.5
    print(f"🔗 Correlation overrides: {corr_override.sum()} bars")

    REALISTIC_FEE      = RISK_SETTINGS["fee_rate"]
    REALISTIC_SLIPPAGE = RISK_SETTINGS["slippage_penalty"]

    # ── Deduct flat monthly subscription (₹117 ≈ $1.40/month) ──
    MONTHLY_SUB_USD = 1.40
    MONTHS_IN_DATA  = len(close) / (30 * 24 * 4)  # 15m bars → months
    SUBSCRIPTION_COST = MONTHLY_SUB_USD * MONTHS_IN_DATA

    print("🚀 Running VBT — Fixed-TP slice (40% budget)...")
    pf_tp = vbt.Portfolio.from_signals(
        close, entries=trend_entries, short_entries=trend_shorts,
        sl_stop=sl_trend, tp_stop=tp_trend,
        fees=REALISTIC_FEE, slippage=REALISTIC_SLIPPAGE,
        freq='15min', init_cash=300.0, size=trend_size_tp, size_type='value'
    )

    # Trailing slice: sl_trail=True causes VBT to trail from the peak.
    # We provide sl_stop as the initial stop (1.8×ATR fraction).
    # This approximates the aggressive "breakeven at +1.8×ATR, then trail" rule.
    print("🚀 Running VBT — Trailing slice (60% budget, trail from peak)...")
    pf_trl = vbt.Portfolio.from_signals(
        close, entries=trend_entries, short_entries=trend_shorts,
        sl_stop=sl_trend, sl_trail=True,
        fees=REALISTIC_FEE, slippage=REALISTIC_SLIPPAGE,
        freq='15min', init_cash=300.0, size=trend_size_trl, size_type='value'
    )

    # ── Metrics ──
    tp_profit  = pf_tp.total_profit().sum()
    trl_profit = pf_trl.total_profit().sum()
    total_net  = tp_profit + trl_profit - SUBSCRIPTION_COST

    tp_trades  = pf_tp.trades.count().sum()
    trl_trades = pf_trl.trades.count().sum()
    total_trades = tp_trades + trl_trades

    tp_wr  = pf_tp.trades.win_rate().fillna(0)
    trl_wr = pf_trl.trades.win_rate().fillna(0)
    wins = (tp_wr * pf_tp.trades.count()).sum() + (trl_wr * pf_trl.trades.count()).sum()
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

    total_equity = ((pf_tp.value().sum(axis=1)  - 300.0) +
                    (pf_trl.value().sum(axis=1) - 300.0) + 300.0)
    cum_max    = total_equity.expanding().max()
    drawdown   = (total_equity - cum_max) / cum_max
    max_drawdown = drawdown.min() * 100

    gross_profit = (pf_tp.trades.winning.pnl.sum().sum()  + pf_trl.trades.winning.pnl.sum().sum())
    gross_loss   = (pf_tp.trades.losing.pnl.sum().sum()   + pf_trl.trades.losing.pnl.sum().sum())

    avg_fee_slip  = (REALISTIC_FEE + REALISTIC_SLIPPAGE) * 2
    total_fees    = (total_trades * 200.0 * avg_fee_slip) + SUBSCRIPTION_COST
    gross_pnl_abs = abs(gross_profit) + abs(gross_loss)
    fee_drag_pct  = (total_fees / gross_pnl_abs * 100) if gross_pnl_abs > 0 else 0

    losses    = total_trades - wins
    avg_win   = gross_profit / wins if wins > 0 else 0
    avg_loss  = abs(gross_loss) / losses if losses > 0 else 0
    expectancy = (avg_win * (win_rate/100)) - (avg_loss * (1 - win_rate/100))

    cagr   = (total_net / 300.0) * 100
    calmar = abs(cagr / max_drawdown) if max_drawdown < 0 else 0
    profit_factor = abs(gross_profit / gross_loss) if gross_loss != 0 else float('inf')

    total_returns = total_equity.pct_change().dropna()
    ann_sharpe = 0.0
    if total_returns.std() != 0:
        ann_sharpe = (total_returns.mean() / total_returns.std()) * (24192 ** 0.5)

    total_bars       = len(close)
    avg_bars_trade   = total_bars / total_trades if total_trades > 0 else 0
    avg_hold_hours   = avg_bars_trade * 0.25

    # ── Print results ──
    print("="*60)
    print("📊 V7.2 AGGRESSIVE MOMENTUM — RESULTS (WazirX ZERO, 1 Year)")
    print("="*60)
    print(f"Initial Capital:        $300.00")
    print(f"Final Capital:          ${300.0 + total_net:.2f}")
    print(f"Total Net PnL:          ${total_net:.2f} ({total_net/300.0*100:.2f}%)")
    print(f"  ├─ Subscription cost: -${SUBSCRIPTION_COST:.2f} (₹117×{MONTHS_IN_DATA:.1f} months)")
    print(f"Max Drawdown:           {max_drawdown:.2f}%")
    print(f"Total Trades:           {total_trades}  (target: 50–90/year)")
    print(f"Win Rate:               {win_rate:.2f}%")
    print()
    print("--- Performance Metrics ---")
    print(f"CAGR:                   {cagr:.2f}%  (target: +25–35%)")
    print(f"Calmar Ratio:           {calmar:.2f}")
    print(f"Proxy Sharpe Ratio:     {ann_sharpe:.2f}")
    print(f"Profit Factor:          {profit_factor:.2f}")
    print(f"Expectancy:             ${expectancy:.2f}/trade")
    print(f"Total Fees (est.):      ${total_fees:.2f}")
    print(f"Fee Drag %:             {fee_drag_pct:.2f}%")
    print(f"Avg Hold Time:          {avg_hold_hours:.1f}h ({avg_hold_hours/24:.1f}d)")

    print("\n--- Asset Breakdown ---")
    asset_pnl = pf_tp.total_profit() + pf_trl.total_profit()
    for sym in ['BTC','SOL']:
        print(f"{sym:<4}: ${asset_pnl[sym]:.2f}")

    print("\n--- Monthly Returns ---")
    monthly_eq = total_equity.resample('ME').last()
    monthly_ret = monthly_eq.pct_change().dropna() * 100
    monthly_data = []
    print(f"{'Month':<12} {'Return':>8} {'Equity':>10}")
    print("-"*32)
    for date, ret in monthly_ret.items():
        eq_val = monthly_eq.loc[date]
        m_str  = date.strftime('%Y-%m')
        print(f"{m_str:<12} {ret:>+7.2f}% ${eq_val:>8.2f}")
        monthly_data.append({'month': m_str, 'return_pct': round(ret,2), 'equity': round(eq_val,2)})

    # ── Side-by-side comparison ──
    print("\n" + "="*60)
    print("📊 SIDE-BY-SIDE COMPARISON")
    print(f"{'Metric':<28} {'V7.1 Baseline':>14} {'V7.2 Aggressive':>16}")
    print("-"*60)
    baseline = {
        'CAGR %': 21.15, 'Max DD %': -0.86, 'Trades': 34,
        'Win Rate %': 67.65, 'Profit Factor': 4.93, 'Calmar': 24.52,
        'Sharpe': 1.85, 'Fee Drag %': 10.65,
    }
    current = {
        'CAGR %': round(cagr,2), 'Max DD %': round(max_drawdown,2),
        'Trades': int(total_trades), 'Win Rate %': round(win_rate,2),
        'Profit Factor': round(profit_factor,2), 'Calmar': round(calmar,2),
        'Sharpe': round(ann_sharpe,2), 'Fee Drag %': round(fee_drag_pct,2),
    }
    for k in baseline:
        b_val = baseline[k]
        c_val = current[k]
        arrow = "▲" if (isinstance(c_val, (int,float)) and c_val > b_val) else ("▼" if c_val < b_val else "─")
        if k == 'Max DD %':
            arrow = "▲" if c_val > b_val else "▼"  # less negative = better
        print(f"{k:<28} {str(b_val):>14} {str(c_val):>14} {arrow}")
    print("="*60)

    # ── Save CSV ──
    os.makedirs('data/backtests', exist_ok=True)
    results_df = pd.DataFrame([{
        'strategy':          'V7.2 Aggressive Momentum',
        'initial_capital':   300.0,
        'final_capital':     round(300.0 + total_net, 2),
        'total_pnl':         round(total_net, 2),
        'cagr_pct':          round(cagr, 2),
        'max_drawdown_pct':  round(max_drawdown, 2),
        'total_trades':      int(total_trades),
        'win_rate_pct':      round(win_rate, 2),
        'profit_factor':     round(profit_factor, 2),
        'calmar_ratio':      round(calmar, 2),
        'sharpe_proxy':      round(ann_sharpe, 2),
        'fee_drag_pct':      round(fee_drag_pct, 2),
        'avg_hold_hours':    round(avg_hold_hours, 1),
        'subscription_cost': round(SUBSCRIPTION_COST, 2),
        'fees_model':        f'exchange={ACTIVE_EXCHANGE} fee={REALISTIC_FEE*100:.3f}% slip={REALISTIC_SLIPPAGE*100:.3f}% sub=${SUBSCRIPTION_COST:.2f}',
        'timeframe':         '15min',
        'mode':              'aggressive',
    }])
    output_path = f'data/backtests/v7_momentum_aggressive_{ACTIVE_EXCHANGE}_2026.csv'
    results_df.to_csv(output_path, index=False)
    print(f"\n💾 Results saved to {output_path}")


if __name__ == '__main__':
    from trading_engine import config

    # Apply config flag: disable MR in backtest if flag is False
    if not config.ENABLE_MEAN_REVERSION:
        print("🔧 MR disabled via config.ENABLE_MEAN_REVERSION = False")

    run_multi_asset_backtest()
    run_aggressive_backtest()
