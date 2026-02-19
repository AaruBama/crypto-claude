
"""
BacktestEngine v2 — Multi-Strategy, Multi-Asset
Supports concurrent strategy execution across multiple assets.
Applies per-strategy budgets and asset-guard collision prevention.
"""
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
from trading_engine.core.risk_manager import RiskManager
from trading_engine.core.candle_manager import CandleManager
from trading_engine.strategies.adaptive_engine import AdaptiveStrategy
from trading_engine.strategies.grid_trading import GridTradingStrategy
from trading_engine.config import STRATEGIES


class BacktestEngine:
    def __init__(
        self,
        initial_balance=10000.0,
        strategy_configs=None,
    ):
        """
        strategy_configs: list of dicts, each with keys:
            - 'class': strategy class (e.g. MeanReversionStrategy)
            - 'name': human-readable name (e.g. 'BTC_MeanRev')
            - 'symbol': asset symbol (e.g. 'BTC')
            - 'params': dict of strategy params
            - 'budget': max USD allocated to this strategy
        """
        self.risk_manager = RiskManager(initial_balance=initial_balance)
        self.balance = initial_balance
        self.initial_balance = initial_balance

        # --- Update 1: Strategy Router ---
        self.strategies = []
        if strategy_configs:
            for cfg in strategy_configs:
                instance = cfg['class'](name=cfg['name'], params=cfg.get('params', {}))
                instance._symbol = cfg['symbol']
                instance._budget = cfg.get('budget', 100.0)
                self.strategies.append(instance)

        # Per-symbol candle managers
        self.candle_managers = {}  # {symbol: CandleManager}

        # State
        self.equity_curve = []
        self.trades = []
        self.active_positions = []   # Each has strategy_id + symbol
        self.pending_orders = []
        self.lockouts = []

        # Stats
        self.total_signals = 0
        self.rejected_risk = 0
        self.expired_orders = 0
        self.cancelled_risk = 0
        self.asset_guard_blocks = 0

    # ------------------------------------------------------------------
    # Update 2: Multi-Asset Data Loading
    # ------------------------------------------------------------------
    def load_data(self, data_dict):
        """
        Accepts a dict of {symbol: {'1m': df_or_path, '5m': df_or_path}}.
        Example:
            bt.load_data({
                'BTC': {'1m': 'data/BTC_1m.csv', '5m': 'data/BTC_5m.csv'},
                'SOL': {'1m': 'data/SOL_1m.csv', '5m': 'data/SOL_5m.csv'},
            })
        Also accepts legacy two-arg form for backwards compatibility.
        """
        self.data = {}  # {symbol: {'1m': df, '5m': df}}
        for symbol, frames in data_dict.items():
            m1 = frames['1m']
            m5 = frames['5m']
            if isinstance(m1, str):
                m1 = pd.read_csv(m1)
            if isinstance(m5, str):
                m5 = pd.read_csv(m5)
            m1['time'] = pd.to_datetime(m1['time'])
            m5['time'] = pd.to_datetime(m5['time'])
            self.data[symbol] = {'1m': m1.set_index('time'), '5m': m5}
            self.candle_managers[symbol] = CandleManager(limit=500)

    def load_data_legacy(self, m1_data, m5_data, symbol='BTC'):
        """Backwards-compatible single-asset loader."""
        self.load_data({symbol: {'1m': m1_data, '5m': m5_data}})

    # ------------------------------------------------------------------
    # Update 2: Multi-Asset Tick Loop
    # ------------------------------------------------------------------
    def run(self):
        print("⚙️ Starting Multi-Asset Backtest...")

        # Build a unified timeline from all 5m dataframes
        all_5m = {}
        for symbol, frames in self.data.items():
            all_5m[symbol] = frames['5m'].set_index('time')

        # Align all symbols to the intersection of timestamps
        common_times = None
        for symbol, df in all_5m.items():
            times = set(df.index)
            common_times = times if common_times is None else common_times & times
        common_times = sorted(common_times)

        last_day = None

        for curr_time in common_times:
            current_day = curr_time.date()

            # --- Daily Reset ---
            if last_day and current_day != last_day:
                self.risk_manager.daily_realized_pnl = 0.0
                self.risk_manager.initial_day_balance = self.balance
            last_day = current_day

            # --- Lockout Check ---
            if self.risk_manager.is_locked_out():
                if self.pending_orders:
                    self.cancelled_risk += len(self.pending_orders)
                    self.pending_orders = []
                self.lockouts.append(curr_time)
                continue

            # --- Per-Symbol Candle Update ---
            rows = {}
            for symbol, df in all_5m.items():
                if curr_time in df.index:
                    row = df.loc[curr_time]
                    rows[symbol] = row
                    self.candle_managers[symbol].add_candle(
                        row['open'], row['high'], row['low'],
                        row['close'], row['volume'], curr_time
                    )
            self._last_rows = rows  # V4: expose for CANCEL_ALL market-close handler

            # --- 1m Tick Execution (per symbol) ---
            # Track which positions closed this tick for grid rebalancing
            positions_before = {p['id']: p for p in self.active_positions}
            for symbol, row in rows.items():
                next_interval = curr_time + timedelta(minutes=5)
                m1_df = self.data[symbol]['1m']
                fine_data = m1_df.loc[curr_time: next_interval - timedelta(minutes=1)]
                for t1, m1_row in fine_data.iterrows():
                    self._check_execution_at_tick(m1_row['close'], t1, symbol)

            # --- Grid Rebalance: call on_order_update for newly closed grid positions ---
            active_ids = {p['id'] for p in self.active_positions}
            for pos_id, pos in positions_before.items():
                if pos_id not in active_ids and pos.get('strategy_id', '').endswith('_Grid'):
                    for strategy in self.strategies:
                        if strategy.name == pos.get('strategy_id'):
                            closed_order = {
                                'id': pos_id,
                                'side': pos['side'],
                                'avg_price': pos['entry_price'],
                                'filled_qty': pos['qty'],
                                'qty': pos['qty'],
                                'status': 'FILLED',
                            }
                            rebalance_sig = strategy.on_order_update(closed_order)
                            if rebalance_sig and isinstance(rebalance_sig, dict) and 'side' in rebalance_sig:
                                rebalance_sig['strategy_id'] = strategy.name
                                rebalance_sig['symbol'] = pos.get('symbol', strategy._symbol)
                                rebalance_sig['budget'] = strategy._budget
                                self._handle_single_order(rebalance_sig, curr_time, expiry_minutes=1440)

            # --- Strategy Signal Collection (all strategies × all assets) ---
            self.risk_manager.update_balance(self.balance)
            all_signals = []

            for strategy in self.strategies:
                sym = strategy._symbol
                if sym not in rows:
                    continue
                cm = self.candle_managers[sym]
                # V4: pass active_positions so grid can run Global SL + Ejector checks
                try:
                    signal = strategy.on_candle_close(cm, active_positions=self.active_positions)
                except TypeError:
                    signal = strategy.on_candle_close(cm)
                if signal and isinstance(signal, dict):
                    if 'side' in signal or 'action' in signal:
                        signal['strategy_id'] = strategy.name
                        signal['symbol'] = sym
                        signal['budget'] = strategy._budget
                        all_signals.append(signal)

            # --- Portfolio & Correlation Awareness (V7) ---
            trend_signals = [s for s in all_signals if 'Momentum' in s.get('reason', '')]
            if len(trend_signals) >= 2:
                syms = [s['symbol'] for s in trend_signals]
                if 'BTC/USDT' in syms and 'SOL/USDT' in syms:
                    cm_btc = self.candle_managers.get('BTC/USDT')
                    cm_sol = self.candle_managers.get('SOL/USDT')
                    if cm_btc is not None and cm_sol is not None:
                        if len(cm_btc.buffer) > 100 and len(cm_sol.buffer) > 100:
                            import numpy as np
                            btc_closes = cm_btc.buffer['close'].iloc[-100:].astype(float)
                            sol_closes = cm_sol.buffer['close'].iloc[-100:].astype(float)
                            corr = np.corrcoef(btc_closes, sol_closes)[0, 1]
                            if corr > 0.8:
                                if not self.quiet:
                                    logger.info(f"🔗 [Correlated Assets] BTC/SOL Corr = {corr:.2f} (>0.8). Halving Trend Breakout sizes!")
                                for sig in trend_signals:
                                    if sig.get('action') == 'PLACE_BATCH':
                                        for order in sig.get('orders', []):
                                            if 'metadata' not in order: order['metadata'] = {}
                                            order['metadata']['qty_pct'] = order['metadata'].get('qty_pct', 1.0) * 0.5
                                    else:
                                        if 'metadata' not in sig: sig['metadata'] = {}
                                        sig['metadata']['qty_pct'] = sig['metadata'].get('qty_pct', 1.0) * 0.5

            # --- Collision Prevention & Execution ---
            for signal in all_signals:
                if signal.get('action') == 'PLACE_BATCH':
                    self.total_signals += len(signal.get('orders', []))
                elif 'side' in signal:
                    self.total_signals += 1
                self._handle_signal(signal, curr_time)

            # --- Equity Snapshot ---
            total_unrealised = 0
            for pos in self.active_positions:
                sym = pos.get('symbol', 'BTC')
                if sym in rows:
                    total_unrealised += self._calc_pnl(pos, rows[sym]['close'])
            self.equity_curve.append({
                'time': curr_time,
                'balance': self.balance,
                'equity': self.balance + total_unrealised
            })

    # ------------------------------------------------------------------
    # Update 3: Signal Handling with Asset Guard
    # ------------------------------------------------------------------
    def _handle_signal(self, signal, timestamp):
        action      = signal.get('action')
        strategy_id = signal.get('strategy_id', '')
        sym         = signal.get('symbol', 'BTC')

        # --- CANCEL_ALL: Grid shutting down (trend or Global SL) ---
        if action == 'CANCEL_ALL':
            # 1. Cancel all pending orders for this strategy
            before = len(self.pending_orders)
            self.pending_orders = [
                o for o in self.pending_orders
                if o.get('strategy_id') != strategy_id
            ]
            cancelled = before - len(self.pending_orders)
            if cancelled:
                self.cancelled_risk += cancelled

            # 2. V4 Safety Belt 1+2: Market-close open positions if flagged
            if signal.get('market_close_positions'):
                my_positions = [
                    p for p in self.active_positions
                    if p.get('strategy_id') == strategy_id
                ]
                last_rows = getattr(self, '_last_rows', {})
                for pos in my_positions:
                    close_price = None
                    for s, row in last_rows.items():
                        if s == pos.get('symbol', sym):
                            close_price = float(row['close'])
                    if close_price is None:
                        continue
                    gross_pnl = self._calc_pnl(pos, close_price)
                    costs = self.risk_manager.add_realized_pnl(
                        gross_pnl, trade_value_usd=close_price * pos['qty']
                    )
                    self.balance += costs['net_pnl']
                    self.trades.append({
                        **pos,
                        'exit_price': close_price,
                        'closed_at': timestamp,
                        'gross_pnl': gross_pnl,
                        'net_pnl': costs['net_pnl'],
                        'fees': pos.get('entry_fee', 0) + costs['fee'],
                        'taxes': costs['tax'],
                        'exit_reason': signal.get('reason', 'CANCEL_ALL'),
                    })
                self.active_positions = [
                    p for p in self.active_positions
                    if p.get('strategy_id') != strategy_id
                ]

            # 3. V4 Safety Belt 3: Release budget reservation
            self.risk_manager.release_budget(strategy_id)
            return

        # --- PLACE_BATCH: Grid initializing multiple limit orders ---
        if action == 'PLACE_BATCH':
            # V4 Safety Belt 3: Reserve budget so Mean Reversion keeps its share
            reserved = signal.get('reserved_budget', 0)
            if reserved:
                self.risk_manager.reserve_budget(strategy_id, reserved)
            for sub_signal in signal.get('orders', []):
                sub_signal['strategy_id'] = strategy_id
                sub_signal['symbol'] = sym
                sub_signal['budget'] = signal['budget']
                self._handle_single_order(sub_signal, timestamp, expiry_minutes=1440)
            return

        # --- Default: Single order signal ---
        self._handle_single_order(signal, timestamp, expiry_minutes=5)

    def _handle_single_order(self, signal, timestamp, expiry_minutes=5):
        """Queues a single pending order with asset guard and risk checks."""
        sym         = signal['symbol']
        strategy_id = signal['strategy_id']
        budget      = signal.get('budget', 100.0)

        # --- Asset Guard: pause strategy if another strategy holds this asset ---
        asset_positions = [p for p in self.active_positions if p.get('symbol') == sym]
        for pos in asset_positions:
            if pos.get('strategy_id') != strategy_id:
                self.asset_guard_blocks += 1
                return

        sl_price  = signal.get('sl')
        qty       = signal.get('qty') or self._size_from_budget(signal['price'], sl_price, budget)
        trade_usd = qty * signal['price']

        total_exposure = len(self.active_positions) + len(self.pending_orders)
        if qty > 0 and self.risk_manager.check_trade_allowed(
            total_exposure,
            entry_price=signal['price'],
            tp_price=signal.get('tp'),
            strategy_id=strategy_id,
            trade_usd=trade_usd,
        ):
            self.pending_orders.append({
                'id': f"bt_{strategy_id}_{len(self.trades) + self.total_signals}_{len(self.pending_orders)}",
                'side': signal['side'],
                'trigger_price': signal['price'],
                'qty': qty,
                'sl': sl_price,
                'tp': signal.get('tp'),
                'expiry': timestamp + timedelta(minutes=expiry_minutes),
                'status': 'PENDING',
                'strategy_id': strategy_id,
                'symbol': sym,
                'order_type': signal.get('order_type', 'STOP_MARKET'),  # LIMIT vs STOP_MARKET
            })
        else:
            self.rejected_risk += 1

    def _size_from_budget(self, price, sl_price, budget):
        """Position size capped to strategy budget."""
        if sl_price:
            risk_per_unit = abs(price - sl_price)
            if risk_per_unit <= 0:
                return 0
            # Risk 2% of budget per trade
            risk_amount = budget * 0.02
            qty = risk_amount / risk_per_unit
        else:
            qty = (budget * 0.02) / price
        # Hard cap: never exceed full budget
        max_qty = budget / price
        return min(qty, max_qty)

    def _check_execution_at_tick(self, current_price, tick_time, symbol='BTC'):
        from trading_engine.config import RISK_SETTINGS
        slippage = RISK_SETTINGS.get("slippage_penalty", 0.0005)

        active_pending = []
        for order in self.pending_orders:
            if order.get('symbol', 'BTC') != symbol:
                active_pending.append(order)
                continue
            if tick_time > order['expiry']:
                self.expired_orders += 1
                continue

            triggered = False
            order_type = order.get('order_type', 'STOP_MARKET')

            if order_type == 'LIMIT':
                # LIMIT BUY: fill when price drops to or below the limit price
                # LIMIT SELL: fill when price rises to or above the limit price
                if order['side'] == 'BUY' and current_price <= order['trigger_price']:
                    triggered = True
                    exec_price = order['trigger_price'] * (1 + slippage)  # slight slippage on fill
                elif order['side'] == 'SELL' and current_price >= order['trigger_price']:
                    triggered = True
                    exec_price = order['trigger_price'] * (1 - slippage)
            else:
                # STOP_MARKET / default: breakout direction
                if order['side'] == 'BUY' and current_price >= order['trigger_price']:
                    triggered = True
                    exec_price = current_price * (1 + slippage)
                elif order['side'] == 'SELL' and current_price <= order['trigger_price']:
                    triggered = True
                    exec_price = current_price * (1 - slippage)

            if triggered:
                order_strategy_id = order.get('strategy_id', 'Unknown')
                if self.risk_manager.check_trade_allowed(
                    len(self.active_positions),
                    entry_price=exec_price,
                    tp_price=order['tp'],
                    strategy_id=order_strategy_id,
                    trade_usd=exec_price * order['qty'],
                ):
                    entry_fee = self.risk_manager.deduct_execution_fees(exec_price * order['qty'])
                    self.balance -= entry_fee
                    self.active_positions.append({
                        'id': order['id'],
                        'side': order['side'],
                        'entry_price': exec_price,
                        'qty': order['qty'],
                        'sl': order['sl'],
                        'tp': order['tp'],
                        'opened_at': tick_time,
                        'entry_fee': entry_fee,
                        'strategy_id': order.get('strategy_id', 'Unknown'),  # Update 3
                        'symbol': order.get('symbol', symbol),               # Update 3
                    })
                else:
                    self.cancelled_risk += 1
            else:
                active_pending.append(order)
        self.pending_orders = active_pending

        remaining_positions = []
        for pos in self.active_positions:
            if pos.get('symbol', 'BTC') != symbol:
                remaining_positions.append(pos)
                continue

            # --- Breakeven Plus Protection ---
            from trading_engine.config import BREAKEVEN_PROTECTION
            if BREAKEVEN_PROTECTION.get('enabled') and not pos.get('breakeven_moved'):
                if pos['side'] == 'BUY':
                    unrealised_pct = (current_price - pos['entry_price']) / pos['entry_price'] * 100
                    if unrealised_pct >= BREAKEVEN_PROTECTION['trigger_pct']:
                        new_sl = pos['entry_price'] * (1 + BREAKEVEN_PROTECTION['sl_buffer_pct'] / 100)
                        if pos['sl'] is None or new_sl > pos['sl']:
                            pos['sl'] = new_sl
                            pos['breakeven_moved'] = True
                elif pos['side'] == 'SELL':
                    unrealised_pct = (pos['entry_price'] - current_price) / pos['entry_price'] * 100
                    if unrealised_pct >= BREAKEVEN_PROTECTION['trigger_pct']:
                        new_sl = pos['entry_price'] * (1 - BREAKEVEN_PROTECTION['sl_buffer_pct'] / 100)
                        if pos['sl'] is None or new_sl < pos['sl']:
                            pos['sl'] = new_sl
                            pos['breakeven_moved'] = True

            exit_triggered = False
            exit_price = current_price

            if pos['side'] == "BUY":
                if pos['sl'] and current_price <= pos['sl']:
                    exit_triggered = True
                    exit_price = current_price * (1 - slippage)
                elif pos['tp'] and current_price >= pos['tp']:
                    exit_triggered = True
                    exit_price = current_price * (1 - slippage)
            elif pos['side'] == "SELL":
                if pos['sl'] and current_price >= pos['sl']:
                    exit_triggered = True
                    exit_price = current_price * (1 + slippage)
                elif pos['tp'] and current_price <= pos['tp']:
                    exit_triggered = True
                    exit_price = current_price * (1 + slippage)

            if exit_triggered:
                gross_pnl = self._calc_pnl(pos, exit_price)
                costs = self.risk_manager.add_realized_pnl(gross_pnl, trade_value_usd=exit_price * pos['qty'])
                net_pnl = costs['net_pnl']
                self.balance += net_pnl
                self.trades.append({
                    **pos,
                    'exit_price': exit_price,
                    'closed_at': tick_time,
                    'gross_pnl': gross_pnl,
                    'net_pnl': net_pnl,
                    'fees': pos['entry_fee'] + costs['fee'],
                    'taxes': costs['tax'],
                })
            else:
                remaining_positions.append(pos)
        self.active_positions = remaining_positions

    def _calc_pnl(self, pos, current_price):
        if pos['side'] == "BUY":
            return (current_price - pos['entry_price']) * pos['qty']
        else:
            return (pos['entry_price'] - current_price) * pos['qty']

    # ------------------------------------------------------------------
    # Report — now broken down by strategy and symbol
    # ------------------------------------------------------------------
    def generate_report(self):
        df_equity = pd.DataFrame(self.equity_curve)
        df_trades = pd.DataFrame(self.trades) if self.trades else pd.DataFrame()

        print("\n" + "="*50)
        print("📊 BACKTEST REPORT: Multi-Strategy / Multi-Asset")
        print("="*50)
        print(f"Initial Balance:    ${self.initial_balance:,.2f}")
        print(f"Final Balance:      ${self.balance:,.2f}")
        print(f"Net P&L:            ${self.balance - self.initial_balance:,.2f}")
        print(f"\nTotal Signals:      {self.total_signals}")
        print(f"Rejected (Risk):    {self.rejected_risk}")
        print(f"Asset Guard Blocks: {self.asset_guard_blocks}")
        print(f"Expired Orders:     {self.expired_orders}")
        print(f"Cancelled (Risk):   {self.cancelled_risk}")
        print(f"Filled Trades:      {len(self.trades)}")
        print(f"Lockout Count:      {len(self.lockouts)}")

        if not df_trades.empty:
            win_rate = (df_trades['net_pnl'] > 0).mean() * 100
            print(f"\nOverall Win Rate:   {win_rate:.2f}%")
            print(f"Avg Net PnL/Trade:  ${df_trades['net_pnl'].mean():.2f}")
            print(f"Total Fees Paid:    ${df_trades['fees'].sum():.2f}")
            print(f"Total Tax Buffer:   ${df_trades['taxes'].sum():.2f}")

            # Per-strategy breakdown
            print("\n--- Per-Strategy Breakdown ---")
            for strat_id, group in df_trades.groupby('strategy_id'):
                wr = (group['net_pnl'] > 0).mean() * 100
                print(f"  [{strat_id}]  Trades: {len(group)}  WinRate: {wr:.1f}%  Net PnL: ${group['net_pnl'].sum():.2f}")

            # Per-symbol breakdown
            if 'symbol' in df_trades.columns:
                print("\n--- Per-Symbol Breakdown ---")
                for sym, group in df_trades.groupby('symbol'):
                    wr = (group['net_pnl'] > 0).mean() * 100
                    print(f"  [{sym}]  Trades: {len(group)}  WinRate: {wr:.1f}%  Net PnL: ${group['net_pnl'].sum():.2f}")

        if not df_equity.empty:
            df_equity['max_equity'] = df_equity['equity'].cummax()
            df_equity['drawdown'] = (df_equity['equity'] - df_equity['max_equity']) / df_equity['max_equity']
            print(f"\nMax Drawdown:       {df_equity['drawdown'].min()*100:.2f}%")

        # Save artifacts
        os.makedirs("data/backtests/", exist_ok=True)
        if not df_equity.empty:
            df_equity.to_csv("data/backtests/equity_curve.csv", index=False)
        if not df_trades.empty:
            df_trades.to_csv("data/backtests/trade_report.csv", index=False)
        print("\n✅ Reports saved to data/backtests/")
        return df_trades, df_equity


# ------------------------------------------------------------------
# Example: 90-Day Full Truth Test
# ------------------------------------------------------------------
# V4 Live Backtest — $300 Account Configuration
# Run: python3 trading_engine/backtest_engine.py
# ------------------------------------------------------------------
if __name__ == "__main__":
    from trading_engine.config import LIVE_ALLOCATION, SELECTIVE_GRID, STRATEGIES

    # ----------------------------------------------------------------
    # Core Strategy Configs — V7 Chameleon Adaptive Engine
    # ----------------------------------------------------------------
    strategy_configs = [
        {
            # 💰 $150 — BTC Adaptive (Chameleon)
            'class': AdaptiveStrategy,
            'name': 'BTC_Adaptive',
            'symbol': 'BTC',
            'budget': LIVE_ALLOCATION['BTC_Adaptive']['budget'],   # $200
            'params': STRATEGIES['ADAPTIVE_ENGINE']['params'],
        },
        {
            # 💰 $75 — SOL Adaptive (Chameleon)
            'class': AdaptiveStrategy,
            'name': 'SOL_Adaptive',
            'symbol': 'SOL',
            'budget': LIVE_ALLOCATION['SOL_Adaptive']['budget'],   # $100
            'params': STRATEGIES['ADAPTIVE_ENGINE_SOL']['params'],
        },
        # ----------------------------------------------------------------
        # 💰 $75 USDT RESERVE — held as cash, not deployed by default.
        # ----------------------------------------------------------------
        # SELECTIVE GRID — Uncomment ONLY when ALL conditions are met:
        #   ✅ 1. The 4H chart shows a clear Horizontal Channel
        #   ✅ 2. The 1D ADX is BELOW 20 (truly ranging, no trend)
        #   ✅ 3. No major macro event in the next 24h (CPI, Fed, etc.)
        #
        # {
        #     'class': GridTradingStrategy,
        #     'name': 'BTC_Grid',
        #     'symbol': 'BTC',
        #     'budget': SELECTIVE_GRID['budget'],   # $75 from USDT Reserve
        #     'params': SELECTIVE_GRID['params'],
        # },
    ]

    # Optionally inject Grid if SELECTIVE_GRID is enabled in config
    if SELECTIVE_GRID.get('enabled'):
        strategy_configs.append({
            'class': GridTradingStrategy,
            'name': f"{SELECTIVE_GRID['symbol']}_Grid",
            'symbol': SELECTIVE_GRID['symbol'],
            'budget': SELECTIVE_GRID['budget'],
            'params': SELECTIVE_GRID['params'],
        })
        print(f"📊 SELECTIVE GRID ACTIVE: {SELECTIVE_GRID['symbol']} @ ${SELECTIVE_GRID['budget']}")
    else:
        print("💰 USDT Reserve ($75) held as cash — Grid is OFF (1D ADX check required to activate)")

    bt = BacktestEngine(initial_balance=1000.0, strategy_configs=strategy_configs)

    data_files = {
        'BTC': {
            '1m': 'data/historical/BTC_USDT_1m_365d.csv',
            '5m': 'data/historical/BTC_USDT_5m_365d.csv',
        },
        'SOL': {
            '1m': 'data/historical/SOL_USDT_1m_365d.csv',
            '5m': 'data/historical/SOL_USDT_5m_365d.csv',
        },
    }

    available = {
        sym: paths for sym, paths in data_files.items()
        if os.path.exists(paths['1m']) and os.path.exists(paths['5m'])
    }

    if not available:
        print("❌ No historical data files found. Run the downloader first.")
        print("   Expected: data/historical/BTC_USDT_1m_90d.csv, etc.")
    else:
        print(f"✅ Found data for: {list(available.keys())}")
        bt.load_data(available)
        bt.run()
        bt.generate_report()
