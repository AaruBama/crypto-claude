import os
import pandas as pd
import numpy as np
import pandas_ta as ta
import vectorbt as vbt
from trading_engine.config import STRATEGIES, LIVE_ALLOCATION

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
    
    # Align data
    print("⏳ Aligning indices...")
    df_combined = pd.DataFrame({'BTC': df_btc['close'], 'SOL': df_sol['close']}).dropna()
    close = df_combined
    
    print("📈 Calculating Indicators...")
    
    configs = {
        'BTC': STRATEGIES['ADAPTIVE_ENGINE']['params'],
        'SOL': STRATEGIES['ADAPTIVE_ENGINE_SOL']['params']
    }
    
    budgets = {
        'BTC': LIVE_ALLOCATION['BTC_Adaptive']['budget'], # 200
        'SOL': LIVE_ALLOCATION['SOL_Adaptive']['budget']  # 100
    }
    
    # We will build boolean DataFrames for entries/shorts
    mr1_entries = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=False)
    mr1_shorts = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=False)
    
    mr2_entries = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=False)
    mr2_shorts = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=False)
    
    trend_entries = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=False)
    trend_shorts = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=False)
    
    # Size DataFrames
    mr1_size = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=0.0)
    mr2_size = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=0.0)
    trend_size = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=0.0)
    
    # SL/TP DataFrames
    sl_mr1 = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=0.0)
    tp_mr1 = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=0.0)
    
    sl_mr2 = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=0.0)
    sl_trend = pd.DataFrame(index=close.index, columns=['BTC', 'SOL'], data=0.0)
    
    # Portfolio correlation over last 100 periods
    print("🔗 Calculating Rolling Correlation...")
    rolling_corr = close['BTC'].rolling(100).corr(close['SOL']).fillna(0)
    
    for sym, df_orig in [('BTC', df_btc), ('SOL', df_sol)]:
        df = df_orig.reindex(close.index) # Align
        
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
        z_std = c_close.rolling(cfg.get('z_score_period', 20)).std()
        z_score = (c_close - z_mean) / z_std
        
        ema_200 = df.ta.ema(length=200)
        
        atr_pct = atr / c_close
        chaos_threshold = atr_pct.quantile(0.95)
        chaos_mask = atr_pct >= chaos_threshold
        
        adx_falling = adx < adx.shift(1)
        
        ranging_mask = (adx <= cfg.get('adx_limit', 25)) & (~chaos_mask)
        trending_mask = (adx > cfg.get('adx_limit', 25)) & (~chaos_mask)
        
        # Mean Reversion
        mr_buy = (c_close <= bbl) & (rsi < cfg.get('rsi_lower', 30)) & (z_score < -cfg.get('z_score_threshold', 2.5)) & (rvol > cfg.get('rvol_threshold', 2.5)) & ranging_mask
        mr_sell = (c_close >= bbu) & (rsi > cfg.get('rsi_upper', 70)) & (z_score > cfg.get('z_score_threshold', 2.5)) & (rvol > cfg.get('rvol_threshold', 2.5)) & ranging_mask
        
        mr1_entries[sym] = mr_buy.fillna(False)
        mr1_shorts[sym] = mr_sell.fillna(False)
        mr2_entries[sym] = mr_buy.fillna(False)
        mr2_shorts[sym] = mr_sell.fillna(False)
        
        # Sizes for MR: 50% budget
        mr1_size[sym] = budget * 0.5
        mr2_size[sym] = budget * 0.5
        
        # Trend Following
        trend_buy = (c_close > bbu) & (~adx_falling) & trending_mask & (c_close > ema_200)
        trend_sell = (c_close < bbl) & (~adx_falling) & trending_mask & (c_close < ema_200)
        
        trend_entries[sym] = trend_buy.fillna(False)
        trend_shorts[sym] = trend_sell.fillna(False)
        
        # Base size for Trend: 100% budget
        trend_size[sym] = pd.Series(budget, index=close.index)
        
        # Stops
        sl_mr1[sym] = (atr * cfg.get('sl_atr_mult', 1.5) / c_close).fillna(0.015)
        tp_dist_mid = (abs(c_close - bbm) / c_close).fillna(0.015)
        tp_mr1[sym] = tp_dist_mid
        
        sl_mr2[sym] = (atr * cfg.get('tp_atr_mult', 3.0) / c_close).fillna(0.015)
        
        # Trend fat tail stop: 10.0 ATR
        sl_trend[sym] = (atr * 10.0 / c_close).fillna(0.04)

    # Apply Correlation Filter for Trend Size
    both_trend_signals = (trend_entries['BTC'] | trend_shorts['BTC']) & (trend_entries['SOL'] | trend_shorts['SOL'])
    corr_override = both_trend_signals & (rolling_corr > 0.8)
    
    trend_size.loc[corr_override, 'BTC'] *= 0.5
    trend_size.loc[corr_override, 'SOL'] *= 0.5
    
    print(f"🔗 Correlation overrides applied to {corr_override.sum()} concurrent signals.")

    print("🚀 Running VectorBT Simulation for Portfolio 1 (Mean Reversion Tier 1)...")
    pf_mr1 = vbt.Portfolio.from_signals(
        close,
        entries=mr1_entries,
        short_entries=mr1_shorts,
        sl_stop=sl_mr1,
        tp_stop=tp_mr1,
        fees=0.0002,
        freq='5T',
        init_cash=300.0,
        size=mr1_size,
        size_type='value'
    )
    
    print("🚀 Running VectorBT Simulation for Portfolio 2 (Mean Reversion Tier 2)...")
    pf_mr2 = vbt.Portfolio.from_signals(
        close,
        entries=mr2_entries,
        short_entries=mr2_shorts,
        sl_stop=sl_mr2,
        sl_trail=True,
        tp_stop=0.10,
        fees=0.0002,
        freq='5T',
        init_cash=300.0,
        size=mr2_size,
        size_type='value'
    )
    
    print("🚀 Running VectorBT Simulation for Portfolio 3 (Trend Follower)...")
    pf_trend = vbt.Portfolio.from_signals(
        close,
        entries=trend_entries,
        short_entries=trend_shorts,
        sl_stop=sl_trend,
        sl_trail=True,
        fees=0.0002,
        freq='5T',
        init_cash=300.0,
        size=trend_size,
        size_type='value'
    )
    
    # Combined Performance
    t1_profit = pf_mr1.total_profit().sum()
    t2_profit = pf_mr2.total_profit().sum()
    tr_profit = pf_trend.total_profit().sum()
    total_net = t1_profit + t2_profit + tr_profit
    
    mr_trades = pf_mr1.trades.count().sum() + pf_mr2.trades.count().sum()
    tr_trades = pf_trend.trades.count().sum()
    total_trades = mr_trades + tr_trades
    
    # Weighted Win Rate
    mr1_wr = pf_mr1.trades.win_rate().fillna(0)
    mr2_wr = pf_mr2.trades.win_rate().fillna(0)
    tr_wr = pf_trend.trades.win_rate().fillna(0)
    
    wins = (mr1_wr * pf_mr1.trades.count()).sum() + (mr2_wr * pf_mr2.trades.count()).sum() + (tr_wr * pf_trend.trades.count()).sum()
    win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
    
    # Aggregate Equity Curve
    total_equity_curve = (pf_mr1.value() - 300.0) + (pf_mr2.value() - 300.0) + (pf_trend.value() - 300.0)
    total_equity_curve = total_equity_curve.sum(axis=1) + 300.0
    
    # Calculate Max Drawdown from the combined equity curve
    cumulative_max = total_equity_curve.expanding().max()
    drawdown = (total_equity_curve - cumulative_max) / cumulative_max
    max_drawdown = drawdown.min() * 100
    
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
    asset_pnl = pf_mr1.total_profit() + pf_mr2.total_profit() + pf_trend.total_profit()
    for sym in ['BTC', 'SOL']:
        print(f"{sym:<4}: PnL ${asset_pnl[sym]:.2f}")
    
    print("="*50)

if __name__ == '__main__':
    run_multi_asset_backtest()
