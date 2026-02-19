"""Temporary BTC-only debug — run once, then delete."""
import os, sys
sys.path.insert(0, '.')

from trading_engine.backtest_engine import BacktestEngine
from trading_engine.strategies.mean_reversion import MeanReversionStrategy
from trading_engine.config import STRATEGIES

params = STRATEGIES['MEAN_REVERSION']['params']
print(f"BTC params: z_score_threshold={params.get('z_score_threshold')} "
      f"rvol_threshold={params.get('rvol_threshold')} "
      f"adx_must_fall={params.get('adx_must_fall')}")

strategy_configs = [{
    'class': MeanReversionStrategy,
    'name': 'BTC_MeanRev',
    'symbol': 'BTC',
    'budget': 150.0,
    'params': params,
}]

bt = BacktestEngine(initial_balance=300.0, strategy_configs=strategy_configs)
data_files = {
    'BTC': {
        '1m': 'data/historical/BTC_USDT_1m_90d.csv',
        '5m': 'data/historical/BTC_USDT_5m_90d.csv',
    }
}
available = {s: p for s, p in data_files.items() if os.path.exists(p['1m'])}
bt.load_data(available)
bt.run()

print(f"\nBTC Trades: {len(bt.trades)}")
print(f"BTC Signals: {bt.total_signals}")
print(f"BTC Rejected: {bt.rejected_risk}")
for t in bt.trades[:5]:
    print(f"  → {t.get('side')} @ {t.get('entry_price'):.2f} | net: {t.get('net_pnl'):.2f}")
