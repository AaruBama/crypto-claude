import logging
from datetime import datetime, timedelta
from trading_engine.config import RISK_SETTINGS

logger = logging.getLogger("RiskManager")


class RiskManager:
    def __init__(self, initial_balance: float = 10000.0):
        self.initial_day_balance = initial_balance
        self.balance = initial_balance
        self.max_daily_loss_pct = 3.0
        self.daily_realized_pnl = 0.0
        self.lockout_until = None

        # V4 Safety Belt 3: Budget Balance
        # Maps strategy_id → reserved USD amount.
        # A reservation prevents other strategies from consuming that capital.
        self._reserved_budgets: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Balance Management
    # ------------------------------------------------------------------
    def update_balance(self, new_balance: float):
        """Syncs risk manager with actual exchange balance."""
        self.balance = new_balance

    def deduct_execution_fees(self, trade_value_usd: float) -> float:
        """Deducts exchange fees on order execution."""
        fee = trade_value_usd * RISK_SETTINGS.get("fee_rate", 0.001)
        self.balance -= fee
        return fee

    def add_realized_pnl(self, pnl_amount: float, trade_value_usd: float = 0) -> dict:
        """Called when a trade closes. Subtracts exit fee and tracks potential tax."""
        exit_fee = trade_value_usd * RISK_SETTINGS.get("fee_rate", 0.001)
        tax = 0
        if pnl_amount > 0:
            tax = pnl_amount * RISK_SETTINGS.get("tax_rate", 0.0)

        net_pnl = pnl_amount - exit_fee - tax
        self.daily_realized_pnl += net_pnl
        self.balance += net_pnl

        # Circuit Breaker
        loss_pct = (
            (self.daily_realized_pnl / self.initial_day_balance) * 100
            if self.initial_day_balance > 0 else 0
        )
        if loss_pct <= -self.max_daily_loss_pct:
            logger.error(
                f"🚨 CIRCUIT BREAKER TRIGGERED: Daily Loss {loss_pct:.2f}% "
                f"hits limit ({self.max_daily_loss_pct}%)"
            )
            self.lockout_until = datetime.now() + timedelta(hours=24)

        return {"net_pnl": net_pnl, "fee": exit_fee, "tax": tax}

    # ------------------------------------------------------------------
    # Lockout
    # ------------------------------------------------------------------
    def is_locked_out(self) -> bool:
        """Checks if the account is in a 24h cooldown."""
        if self.lockout_until and datetime.now() < self.lockout_until:
            return True
        elif self.lockout_until and datetime.now() >= self.lockout_until:
            self.lockout_until = None
            self.daily_realized_pnl = 0.0
            self.initial_day_balance = self.balance
            return False
        return False

    # ------------------------------------------------------------------
    # V4 Safety Belt 3: Budget Balance (Strategy Reservations)
    # ------------------------------------------------------------------
    def reserve_budget(self, strategy_id: str, amount_usd: float):
        """
        Called when a strategy (e.g. Grid) locks capital into pending orders.
        Prevents other strategies from consuming that capital.
        """
        self._reserved_budgets[strategy_id] = amount_usd
        total_reserved = sum(self._reserved_budgets.values())
        logger.info(
            f"💰 BUDGET RESERVE: [{strategy_id}] reserved ${amount_usd:.2f}. "
            f"Total reserved: ${total_reserved:.2f} / ${self.balance:.2f}"
        )

    def release_budget(self, strategy_id: str):
        """Called when a strategy's grid is cancelled or fully closed."""
        released = self._reserved_budgets.pop(strategy_id, 0)
        if released:
            logger.info(f"💰 BUDGET RELEASED: [{strategy_id}] freed ${released:.2f}")

    def get_available_budget(self, requesting_strategy_id: str) -> float:
        """
        Returns the USD available to a strategy, excluding other strategies'
        reservations. The requesting strategy's own reservation is excluded
        (it already 'owns' that capital).
        """
        other_reserved = sum(
            v for k, v in self._reserved_budgets.items()
            if k != requesting_strategy_id
        )
        available = max(0.0, self.balance - other_reserved)
        return available

    def check_budget_available(
        self, strategy_id: str, required_usd: float
    ) -> bool:
        """
        Returns True if the strategy can afford `required_usd`.
        A strategy can always use its own reserved budget.
        The guard only blocks consuming capital reserved by OTHER strategies.
        """
        own_reservation  = self._reserved_budgets.get(strategy_id, 0)
        other_reserved   = sum(v for k, v in self._reserved_budgets.items() if k != strategy_id)
        # Capital available = balance - what others have locked
        available = max(0.0, self.balance - other_reserved)

        # If the trade fits within own reservation, always allow
        if required_usd <= own_reservation:
            return True

        if available < required_usd:
            logger.warning(
                f"💸 BUDGET GUARD: [{strategy_id}] needs ${required_usd:.2f} "
                f"but only ${available:.2f} available after other reservations "
                f"(${other_reserved:.2f} locked by others)."
            )
            return False
        return True

    # ------------------------------------------------------------------
    # Pre-Trade Gate
    # ------------------------------------------------------------------
    def check_trade_allowed(
        self,
        current_positions: int,
        current_exposure_usd: float = 0,
        entry_price: float = None,
        tp_price: float = None,
        strategy_id: str = "Unknown",
        trade_usd: float = 0,
    ) -> bool:
        """
        Runs pre-trade checks:
        1. Lockout?
        2. Max positions?
        3. Micro-Live exposure cap?
        4. Break-Even filter (min 0.60% TP)?
        5. V4: Budget Balance — does this strategy have reserved room?
        """
        from trading_engine.config import MICRO_LIVE_LIMITS

        # 1. Lockout
        if self.is_locked_out():
            logger.warning(f"❌ RISK ALERT: Account locked until {self.lockout_until}")
            return False

        # 2. Position Limit
        if current_positions >= RISK_SETTINGS.get("max_open_positions", 10):
            logger.warning(f"❌ RISK ALERT: Max Open Positions Reached ({current_positions})")
            return False

        # 3. Micro-Live Cap
        if current_exposure_usd >= MICRO_LIVE_LIMITS["max_total_exposure_usd"]:
            logger.warning(f"❌ MICRO-LIVE: Max Total Exposure Reached (${current_exposure_usd:.2f})")
            return False

        # 4. Break-Even Filter (0.60% min target) — skip for grid orders (tp close to entry by design)
        if entry_price and tp_price:
            profit_target_pct = (abs(tp_price - entry_price) / entry_price) * 100
            # Grid spacing is 1.2% which clears the 0.60% bar — only block if truly tiny
            min_profit = RISK_SETTINGS.get("min_profit_pct", 0.30)
            if profit_target_pct < min_profit:
                logger.info(
                    f"🛡️ BREAK-EVEN FILTER: Discarding signal with {profit_target_pct:.2f}% target "
                    f"(Min {min_profit:.2f}% required)"
                )
                return False

        # 5. V4 Budget Balance
        if trade_usd > 0 and strategy_id != "Unknown":
            if not self.check_budget_available(strategy_id, trade_usd):
                return False

        return True

    # ------------------------------------------------------------------
    # Position Sizing
    # ------------------------------------------------------------------
    def calculate_position_size(
        self, entry_price: float, stop_loss: float, risk_pct: float = 1.0
    ) -> float:
        """
        Qty = (Balance × Risk%) / |Entry - StopLoss|
        Capped by MICRO_LIVE_LIMITS.
        """
        from trading_engine.config import MICRO_LIVE_LIMITS

        if self.balance <= 0 or self.is_locked_out():
            return 0.0

        risk_amount_usd = self.balance * (risk_pct / 100)
        price_diff = abs(entry_price - stop_loss)

        if price_diff <= 0:
            return 0.0

        qty = risk_amount_usd / price_diff

        # Cap: max $20 per trade (Micro-Live)
        trade_usd = qty * entry_price
        if trade_usd > MICRO_LIVE_LIMITS["max_trade_usd"]:
            logger.info(
                f"🛡️ MICRO-LIMIT: Capping trade from ${trade_usd:.2f} "
                f"to ${MICRO_LIVE_LIMITS['max_trade_usd']}"
            )
            qty = MICRO_LIVE_LIMITS["max_trade_usd"] / entry_price

        # Cap: max position size from config
        max_usd = RISK_SETTINGS.get("max_position_size_usd", 2000)
        if (qty * entry_price) > max_usd:
            qty = max_usd / entry_price

        return round(qty, 6)
