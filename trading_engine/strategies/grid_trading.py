"""
Grid Trading Strategy (Neutral Market) — V4 Safe-Grid
Designed for low volatility, ranging markets (ADX < adx_max).
Places a grid of Limit Orders around the current price.

V4 Safety Belts:
  1. Global Strategy SL  — close all + pause 4h if unrealised PnL < -3% of budget
  2. ADX Ejector Seat    — market-close net position if trending away >1% on CANCEL_ALL
  3. Budget Balance      — signals reserved budget to RiskManager before placing orders
"""
import logging
from datetime import datetime, timedelta
try:
    import pandas_ta as ta
except ImportError:
    import pandas_ta_classic as ta
from trading_engine.core.strategy import BaseStrategy

logger = logging.getLogger("GridTradingStrategy")


class GridTradingStrategy(BaseStrategy):
    def __init__(self, name="Neutral_Grid_Bot", params=None):
        super().__init__(name, params)
        self.params = params or {}

        # Grid Settings
        self.grid_levels      = self.params.get('grid_levels', 5)
        self.grid_spacing_pct = self.params.get('grid_spacing_pct', 1.2)
        self.max_capital      = self.params.get('max_capital', 100.0)

        # Safety Filters
        self.adx_max        = self.params.get('adx_max', 25)
        self.adx_stop_loss  = self.params.get('adx_stop_loss', 30)

        # V4 Safety Belt 1: Global Strategy SL
        self.global_sl_pct      = self.params.get('global_sl_pct', 3.0)   # -3% of budget
        self.pause_hours        = self.params.get('pause_hours', 4)
        self._paused_until      = None   # datetime when pause expires

        # V4 Safety Belt 2: ADX Ejector Seat
        self.ejector_threshold_pct = self.params.get('ejector_threshold_pct', 1.0)  # 1% offside

        # Internal state
        self.active_grid    = []   # [{price, type, id, status}]
        self.reference_price = None

    # ------------------------------------------------------------------
    # Core candle handler
    # ------------------------------------------------------------------
    def on_candle_close(self, candle_manager, active_positions=None):
        """
        active_positions: list of position dicts from the engine (optional).
        When provided, enables Safety Belt 1 (Global SL) checks.
        """
        df = candle_manager.buffer.copy()
        if len(df) < 20:
            return None

        # --- Pause Check (Safety Belt 1 cooldown) ---
        if self._paused_until and datetime.now() < self._paused_until:
            remaining = (self._paused_until - datetime.now()).seconds // 60
            if df['time'].iloc[-1].minute % 30 == 0:
                logger.warning(f"[{self.name}] ⏸️ Strategy paused for {remaining}m more (Global SL triggered).")
            return None

        # Calculate ADX
        adx_df = df.ta.adx(length=14)
        if adx_df is None:
            return None
        curr_adx = adx_df[adx_df.columns[0]].iloc[-1]
        curr_price = float(df['close'].iloc[-1])

        # ------------------------------------------------------------------
        # Safety Belt 1: Global Strategy SL
        # ------------------------------------------------------------------
        if active_positions and self.active_grid:
            my_positions = [p for p in active_positions
                            if p.get('strategy_id') == self.name]
            if my_positions:
                total_unrealised = sum(
                    (curr_price - p['entry_price']) * p['qty']
                    if p['side'] == 'BUY'
                    else (p['entry_price'] - curr_price) * p['qty']
                    for p in my_positions
                )
                loss_pct = (total_unrealised / self.max_capital) * 100
                if loss_pct <= -self.global_sl_pct:
                    logger.error(
                        f"[{self.name}] 🛑 GLOBAL SL HIT: Unrealised PnL = {loss_pct:.2f}% "
                        f"(limit: -{self.global_sl_pct}%). Closing all + pausing {self.pause_hours}h."
                    )
                    self._paused_until = datetime.now() + timedelta(hours=self.pause_hours)
                    self.active_grid = []
                    self.reference_price = None
                    # Signal engine to close all open positions for this strategy at market
                    return {
                        "strategy": self.name,
                        "action": "CANCEL_ALL",
                        "market_close_positions": True,   # Belt 1: close open positions too
                        "reason": f"Global SL: {loss_pct:.2f}% loss on ${self.max_capital} budget",
                    }

        # ------------------------------------------------------------------
        # Safety Belt 2: ADX Ejector Seat
        # ------------------------------------------------------------------
        if curr_adx > self.adx_stop_loss:
            if self.active_grid:
                logger.warning(
                    f"[{self.name}] 🚨 TREND DETECTED (ADX: {curr_adx:.1f} > {self.adx_stop_loss}). "
                    f"Ejector seat engaged."
                )
                self.active_grid = []
                self.reference_price = None

                # Build ejector payload
                ejector_payload = {
                    "strategy": self.name,
                    "action": "CANCEL_ALL",
                    "reason": f"Trend Detected (ADX {curr_adx:.1f})",
                    "market_close_positions": False,
                }

                # Check if net position is offside by > ejector_threshold_pct
                if active_positions:
                    my_positions = [p for p in active_positions
                                    if p.get('strategy_id') == self.name]
                    if my_positions:
                        avg_entry = sum(p['entry_price'] * p['qty'] for p in my_positions) / \
                                    sum(p['qty'] for p in my_positions)
                        net_side  = my_positions[0]['side']  # all grid buys are same side
                        offside_pct = ((curr_price - avg_entry) / avg_entry) * 100
                        if net_side == 'BUY':
                            offside = offside_pct < -self.ejector_threshold_pct
                        else:
                            offside = offside_pct > self.ejector_threshold_pct

                        if offside:
                            logger.error(
                                f"[{self.name}] 💺 EJECTOR: Net position {offside_pct:.2f}% offside "
                                f"(threshold: {self.ejector_threshold_pct}%). Market closing."
                            )
                            ejector_payload["market_close_positions"] = True
                            ejector_payload["net_side"] = net_side
                            ejector_payload["avg_entry"] = avg_entry

                return ejector_payload
            return None

        # ------------------------------------------------------------------
        # Entry: Start Grid (only when no active grid and ADX is calm)
        # ------------------------------------------------------------------
        if not self.active_grid and curr_adx < self.adx_max:
            return self._initialize_grid(curr_price)

        return None

    def on_tick(self, current_price, active_positions):
        """Tick hook — reserved for future real-time SL checks."""
        return None

    # ------------------------------------------------------------------
    # Grid Initialization
    # ------------------------------------------------------------------
    def _initialize_grid(self, center_price):
        """
        Generates LIMIT buy orders below center price.
        Each buy has a TP one grid level above (the rebalance target).
        Sells are placed only after a buy fills (spot-safe, long-only).
        """
        logger.info(
            f"[{self.name}] 🕸️ Initializing Grid at ${center_price:,.2f} "
            f"(Spacing: {self.grid_spacing_pct}%, Budget: ${self.max_capital})"
        )
        self.reference_price = center_price
        half_levels = (self.grid_levels - 1) // 2
        qty_per_level_usdt = self.max_capital / (self.grid_levels - 1)
        orders = []

        for i in range(1, half_levels + 1):
            price    = center_price * (1 - (i * self.grid_spacing_pct / 100))
            qty      = qty_per_level_usdt / price
            tp_price = price * (1 + self.grid_spacing_pct / 100)
            sig = self.generate_signal(
                side="BUY",
                price=price,
                take_profit=tp_price,
                order_type="LIMIT",
                reason=f"Grid Buy Level {i}",
                metadata={"grid_level": -i}
            )
            sig['qty'] = qty
            orders.append(sig)

        self.active_grid = [
            {'id': 'PENDING', 'price': o['price'], 'type': o['side']}
            for o in orders
        ]

        return {
            "strategy": self.name,
            "action": "PLACE_BATCH",
            "orders": orders,
            # V4 Safety Belt 3: tell RiskManager how much budget this grid will lock
            "reserved_budget": self.max_capital,
        }

    # ------------------------------------------------------------------
    # Rebalance on Fill
    # ------------------------------------------------------------------
    def on_order_update(self, order):
        """
        Called by engine when a grid order fills.
        BUY fill  → place SELL one level up (take profit)
        SELL fill → place BUY one level down (reload)
        """
        if order['status'] != 'FILLED':
            return None

        fill_qty   = order.get('filled_qty', order.get('qty', 0))
        fill_price = order.get('avg_price', order.get('entry_price', 0))

        if order['side'] == 'BUY':
            sell_price = fill_price * (1 + self.grid_spacing_pct / 100)
            sig = self.generate_signal(
                side="SELL",
                price=sell_price,
                order_type="LIMIT",
                reason="Grid TP (Rebalance)",
                metadata={"related_order_id": order['id']}
            )
            sig['qty'] = fill_qty
            return sig

        elif order['side'] == 'SELL':
            buy_price = fill_price * (1 - self.grid_spacing_pct / 100)
            tp_price  = buy_price * (1 + self.grid_spacing_pct / 100)
            sig = self.generate_signal(
                side="BUY",
                price=buy_price,
                take_profit=tp_price,
                order_type="LIMIT",
                reason="Grid Reload",
                metadata={"related_order_id": order['id']}
            )
            sig['qty'] = fill_qty
            return sig

        return None
