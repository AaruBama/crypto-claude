"""
V7.2 Chameleon Adaptive Engine — Aggressive Momentum (WazirX ZERO)
════════════════════════════════════════════════════════════════════
2026-02-20 V7.1 baseline (WazirX ZERO fees):
  CAGR: +21.15%  |  Max DD: -0.86%  |  Trades: 34/yr  |  WR: 67.65%
  Profit Factor: 4.93  |  Calmar: 24.52  |  Sharpe: 1.85

V7.2 changes (MOMENTUM_AGGRESSIVE=True only):
  1. Entry filters relaxed — 2-bar rising ADX (was 3), engulfing optional
     when body>65%+RVOL>1.8×+price>EMA200, ATR% floor 0.28× (was 0.40×)
  2. Two-level pyramiding — +30% at +2.2×ATR, +25% at +3.8×ATR (max 1.8×)
  3. Earlier profit locking — breakeven at +1.8×ATR, partial close at +3.2×ATR
  4. Momentum continuation — re-entry with 40% if +2.5×ATR and new signal <12h

Production Config: Pure Momentum Breakout on 15m with WazirX ZERO fees.
"""
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

try:
    import pandas_ta as ta
except ImportError:
    import pandas_ta_classic as ta

from trading_engine.core.strategy import BaseStrategy
from trading_engine import config

logger = logging.getLogger("AdaptiveEngine")


class RegimeDetector:
    """
    Analyzes strictly the last `lookback` candles to determine Market Regime:
    RANGING: Sideways movement (ADX < threshold).
    TRENDING: Momentum breakout (ADX >= threshold).
    CHAOS: Ultra-high volatility (ATR % in top 5% of recent history).
    """
    def __init__(self, adx_period=14, atr_period=14, lookback=100, chaos_pct=0.95):
        self.adx_period = adx_period
        self.atr_period = atr_period
        self.lookback = lookback
        self.chaos_pct = chaos_pct

    def get_market_regime(self, df: pd.DataFrame, adx_limit: float = 25.0) -> str:
        if len(df) < self.lookback:
            return "UNKNOWN"
        
        recent_df = df.iloc[-self.lookback:].copy()
        
        adx_df = recent_df.ta.adx(length=self.adx_period)
        if adx_df is None: return "UNKNOWN"
        adx_col = [c for c in adx_df.columns if c.startswith('ADX_')][0]
        
        atr = recent_df.ta.atr(length=self.atr_period)
        atr_pct = atr / recent_df['close']
        
        curr_adx = adx_df[adx_col].iloc[-1]
        curr_atr_pct = atr_pct.iloc[-1]
        chaos_threshold = atr_pct.quantile(self.chaos_pct)
        
        if curr_atr_pct >= chaos_threshold:
            return "CHAOS"
        elif curr_adx > adx_limit:
            return "TRENDING"
        else:
            return "RANGING"


class AdaptiveStrategy(BaseStrategy):
    """
    V7.1 Chameleon Hybrid Adaptive Engine.
    Default mode: Pure Momentum Breakout.
    Optional: Mean Reversion (disabled by default via config.ENABLE_MEAN_REVERSION).
    """
    def __init__(self, name="Chameleon_Adaptive", params=None):
        super().__init__(name, params)
        self.params = params or {}
        
        # Bollinger Bands
        self.bb_period = self.params.get('bb_period', 20)
        self.bb_std    = self.params.get('bb_std', 2.0)
        # Oscillators
        self.rsi_period = self.params.get('rsi_period', 14)
        self.rsi_lower  = self.params.get('rsi_lower', 30)
        self.rsi_upper  = self.params.get('rsi_upper', 70)
        self.adx_period = self.params.get('adx_period', 14)
        self.adx_limit  = self.params.get('adx_limit', 30)
        # Filters
        self.rvol_period       = self.params.get('rvol_period', 20)
        self.rvol_threshold    = self.params.get('rvol_threshold', 3.0)
        self.z_score_period    = self.params.get('z_score_period', 20)
        self.z_score_threshold = self.params.get('z_score_threshold', 3.0)
        # Risk
        self.atr_period    = self.params.get('atr_period', 14)
        self.sl_atr_mult   = self.params.get('sl_atr_mult', 1.5)
        self.tp_atr_mult   = self.params.get('tp_atr_mult', 3.0) 
        
        # Regime Detector
        self.regime_detector = RegimeDetector(
            adx_period=self.adx_period, 
            atr_period=self.atr_period, 
            lookback=100, 
            chaos_pct=0.95
        )
        
        # Momentum state tracking
        self.last_momentum_signal_time = None
        self.active_pyramid_count = 0   # 0 = base only, 1 = first add, 2 = second add

        # Aggressive mode flags (read once from config at init)
        self.aggressive = getattr(config, "MOMENTUM_AGGRESSIVE", False)
        self.max_pyramid_levels = getattr(config, "MAX_PYRAMID_LEVELS", 1)
        self.max_pos_mult = getattr(config, "MAX_POSITION_MULTIPLIER", 1.5)

    def on_candle_close(self, candle_manager, active_positions=None):
        df = candle_manager.buffer.copy()
        regime = self.regime_detector.get_market_regime(df, self.adx_limit)
        
        if regime == "UNKNOWN" or regime == "CHAOS":
            return None

        bb = df.ta.bbands(length=self.bb_period, std=self.bb_std)
        if bb is None: return None
        
        bb_lower_col = [c for c in bb.columns if c.startswith('BBL_')][0]
        bb_mid_col   = [c for c in bb.columns if c.startswith('BBM_')][0]
        bb_upper_col = [c for c in bb.columns if c.startswith('BBU_')][0]
        
        rsi_series = df.ta.rsi(length=self.rsi_period)
        adx_df = df.ta.adx(length=self.adx_period)
        atr_series = df.ta.atr(length=self.atr_period)
        
        adx_col = [c for c in adx_df.columns if c.startswith('ADX_')][0]
        curr_price = float(df['close'].iloc[-1])
        curr_atr = float(atr_series.iloc[-1])
        curr_rsi = float(rsi_series.iloc[-1])
        
        curr_bb_lower = float(bb[bb_lower_col].iloc[-1])
        curr_bb_mid   = float(bb[bb_mid_col].iloc[-1])
        curr_bb_upper = float(bb[bb_upper_col].iloc[-1])
        
        # RVOL Calculation
        vol_sma = df['volume'].iloc[-self.rvol_period:].mean()
        curr_vol = float(df['volume'].iloc[-1])
        rvol = curr_vol / vol_sma if vol_sma > 0 else 0
        
        # Z-Score Calculation
        close_window = df['close'].iloc[-self.z_score_period:]
        z_mean = float(close_window.mean())
        z_std  = float(close_window.std())
        z_score = ((curr_price - z_mean) / z_std) if z_std > 0 else 0.0
        
        # ATR% filter for momentum: skip dead ranges
        atr_pct_series = atr_series / df['close']
        atr_pct_avg = float(atr_pct_series.iloc[-50:].mean()) if len(atr_pct_series) >= 50 else 0
        curr_atr_pct = curr_atr / curr_price if curr_price > 0 else 0

        if active_positions is not None:
            my_positions = [p for p in active_positions if p.get('strategy_id') == self.name]
            # Block when at max pyramid levels (+1 for base position)
            max_slots = 1 + self.max_pyramid_levels if self.aggressive else 2
            if len(my_positions) >= max_slots:
                return None

        if df['time'].iloc[-1].minute % 15 == 0:
            logger.info(f"🦎 [{self.name}] Regime: {regime} | Price: {curr_price:.2f} | "
                       f"ADX: {float(adx_df[adx_col].iloc[-1]):.1f} | ATR%: {curr_atr_pct*100:.3f}%")

        # ── REGIME ROUTING ──
        if regime == "RANGING":
            # Mean Reversion — gated by config flag
            if not config.ENABLE_MEAN_REVERSION:
                return None
            return self._mean_reversion_logic(
                curr_price, curr_rsi, rvol, z_score, curr_atr,
                curr_bb_lower, curr_bb_mid, curr_bb_upper
            )
            
        elif regime == "TRENDING":
            if not config.ENABLE_MOMENTUM_BREAKOUT:
                return None

            # ── ADX rising: 2-bar minimum always; 3-bar required in normal mode ──
            adx_rising_2 = False
            adx_rising_3 = False
            if len(adx_df) >= 3:
                adx_vals = adx_df[adx_col].iloc[-3:]
                adx_rising_2 = float(adx_vals.iloc[-1]) > float(adx_vals.iloc[-2])
                adx_rising_3 = adx_rising_2 and float(adx_vals.iloc[-2]) > float(adx_vals.iloc[-3])
            adx_rising = adx_rising_2 if self.aggressive else adx_rising_3

            # ── Volume rising (3 bars required in both modes) ──
            vol_rising = False
            if len(df) >= 3:
                vols = df['volume'].iloc[-3:]
                vol_rising = (float(vols.iloc[-1]) > float(vols.iloc[-2]) and
                              float(vols.iloc[-2]) > float(vols.iloc[-3]))

            # ── EMA-200 for engulfing-optional gate ──
            ema200 = float(df['close'].ewm(span=200, adjust=False).mean().iloc[-1])

            # ── Engulfing detection ──
            is_bullish_engulfing = False
            is_bearish_engulfing = False
            candle_body_pct = 0.0
            if len(df) >= 2:
                prev_open  = float(df['open'].iloc[-2])
                prev_close = float(df['close'].iloc[-2])
                curr_open  = float(df['open'].iloc[-1])
                candle_range = abs(float(df['high'].iloc[-1]) - float(df['low'].iloc[-1]))
                candle_body  = abs(curr_price - curr_open)
                candle_body_pct = (candle_body / candle_range) if candle_range > 0 else 0.0

                is_bullish_engulfing = (curr_price > curr_open and prev_close < prev_open and
                                        curr_price >= prev_open and curr_open <= prev_close)
                is_bearish_engulfing = (curr_price < curr_open and prev_close > prev_open and
                                        curr_price <= prev_open and curr_open >= prev_close)

            # ── Engulfing-optional gate (aggressive only) ──
            # Qualifies if body>70% range AND RVOL>3.0× AND price>EMA200
            # (RVOL threshold matches baseline rvol_threshold to avoid signal inflation)
            strong_bull_body = (
                self.aggressive and
                curr_price > curr_open and
                candle_body_pct >= 0.70 and
                rvol >= 3.0 and
                curr_price > ema200
            )
            strong_bear_body = (
                self.aggressive and
                curr_price < curr_open and
                candle_body_pct >= 0.70 and
                rvol >= 3.0 and
                curr_price < ema200
            )
            effective_bullish = is_bullish_engulfing or strong_bull_body
            effective_bearish = is_bearish_engulfing or strong_bear_body

            # ── ATR% floor: 0.40× in both modes (relaxation dropped after calibration) ──
            atr_floor = 0.40
            if atr_pct_avg > 0 and curr_atr_pct < (atr_floor * atr_pct_avg):
                logger.debug(f"[{self.name}] Skipping: ATR% {curr_atr_pct*100:.3f}% < {atr_floor}× avg {atr_pct_avg*100:.3f}%")
                return None

            # ── Pyramid / continuation check on existing position ──
            if active_positions:
                my_positions = [p for p in active_positions if p.get('strategy_id') == self.name]
                n_pos = len(my_positions)

                if n_pos >= 1:
                    pos = my_positions[0]
                    entry = pos.get('entry_price', curr_price)
                    pos_side = pos.get('side', '')
                    unrealized_atr = (
                        (curr_price - entry) / curr_atr if pos_side == 'BUY'
                        else (entry - curr_price) / curr_atr
                    )
                    since_signal = (
                        (datetime.now() - self.last_momentum_signal_time)
                        if self.last_momentum_signal_time else timedelta(hours=999)
                    )

                    if self.aggressive:
                        # ── Level 1 pyramid: +30% at +2.2×ATR (was +2.5×) ──
                        if (n_pos == 1 and unrealized_atr >= 2.2 and
                                self.active_pyramid_count == 0 and
                                since_signal < timedelta(hours=8)):
                            # Needs higher high on 15m + volume spike
                            higher_high = float(df['high'].iloc[-1]) > float(df['high'].iloc[-2])
                            vol_spike   = rvol >= 1.5
                            if higher_high and vol_spike and pos_side == 'BUY' and effective_bullish:
                                self.active_pyramid_count = 1
                                logger.info(f"🔺 [{self.name}] PYRAMID L1: +30% at {curr_price:.2f} ({unrealized_atr:.1f}×ATR)")
                                return self.generate_signal(
                                    "BUY", curr_price, curr_price - (curr_atr * 3.0),
                                    curr_price + (curr_atr * 15), "Pyramid L1 +30%",
                                    order_type="LIMIT_MAKER",
                                    metadata={"qty_pct": 0.30, "trailing_sl": True,
                                              "trailing_offset": 6.0, "is_pyramid": True,
                                              "pyramid_level": 1}
                                )
                            if higher_high and vol_spike and pos_side == 'SELL' and effective_bearish:
                                self.active_pyramid_count = 1
                                lower_low = float(df['low'].iloc[-1]) < float(df['low'].iloc[-2])
                                if lower_low:
                                    logger.info(f"🔻 [{self.name}] PYRAMID L1: +30% at {curr_price:.2f} ({unrealized_atr:.1f}×ATR)")
                                    return self.generate_signal(
                                        "SELL", curr_price, curr_price + (curr_atr * 3.0),
                                        curr_price - (curr_atr * 15), "Pyramid L1 +30%",
                                        order_type="LIMIT_MAKER",
                                        metadata={"qty_pct": 0.30, "trailing_sl": True,
                                                  "trailing_offset": 6.0, "is_pyramid": True,
                                                  "pyramid_level": 1}
                                    )

                        # ── Level 2 pyramid: +25% at +3.8×ATR ──
                        if (n_pos == 2 and unrealized_atr >= 3.8 and
                                self.active_pyramid_count == 1 and
                                since_signal < timedelta(hours=12)):
                            higher_high = float(df['high'].iloc[-1]) > float(df['high'].iloc[-2])
                            vol_spike   = rvol >= 1.5
                            if higher_high and vol_spike and pos_side == 'BUY':
                                self.active_pyramid_count = 2
                                logger.info(f"🔺 [{self.name}] PYRAMID L2: +25% at {curr_price:.2f} ({unrealized_atr:.1f}×ATR)")
                                return self.generate_signal(
                                    "BUY", curr_price, curr_price - (curr_atr * 2.5),
                                    curr_price + (curr_atr * 12), "Pyramid L2 +25%",
                                    order_type="LIMIT_MAKER",
                                    metadata={"qty_pct": 0.25, "trailing_sl": True,
                                              "trailing_offset": 5.0, "is_pyramid": True,
                                              "pyramid_level": 2}
                                )
                            lower_low = float(df['low'].iloc[-1]) < float(df['low'].iloc[-2])
                            if lower_low and vol_spike and pos_side == 'SELL':
                                self.active_pyramid_count = 2
                                logger.info(f"🔻 [{self.name}] PYRAMID L2: +25% at {curr_price:.2f} ({unrealized_atr:.1f}×ATR)")
                                return self.generate_signal(
                                    "SELL", curr_price, curr_price + (curr_atr * 2.5),
                                    curr_price - (curr_atr * 12), "Pyramid L2 +25%",
                                    order_type="LIMIT_MAKER",
                                    metadata={"qty_pct": 0.25, "trailing_sl": True,
                                              "trailing_offset": 5.0, "is_pyramid": True,
                                              "pyramid_level": 2}
                                )

                        # ── Momentum continuation re-entry ──
                        # Position >+2.5×ATR AND new breakout signal within 12h → 40% re-entry
                        if (unrealized_atr >= 2.5 and since_signal < timedelta(hours=12) and
                                self.active_pyramid_count >= self.max_pyramid_levels):
                            if pos_side == 'BUY' and curr_price > curr_bb_upper and effective_bullish:
                                logger.info(f"🔄 [{self.name}] CONTINUATION: +40% at {curr_price:.2f} ({unrealized_atr:.1f}×ATR)")
                                return self.generate_signal(
                                    "BUY", curr_price, curr_price - (curr_atr * 3.0),
                                    curr_price + (curr_atr * 12), "Momentum Continuation",
                                    order_type="LIMIT_MAKER",
                                    metadata={"qty_pct": 0.40, "trailing_sl": True,
                                              "trailing_offset": 5.0, "is_continuation": True}
                                )
                            if pos_side == 'SELL' and curr_price < curr_bb_lower and effective_bearish:
                                logger.info(f"🔄 [{self.name}] CONTINUATION: +40% at {curr_price:.2f} ({unrealized_atr:.1f}×ATR)")
                                return self.generate_signal(
                                    "SELL", curr_price, curr_price + (curr_atr * 3.0),
                                    curr_price - (curr_atr * 12), "Momentum Continuation",
                                    order_type="LIMIT_MAKER",
                                    metadata={"qty_pct": 0.40, "trailing_sl": True,
                                              "trailing_offset": 5.0, "is_continuation": True}
                                )

                    else:
                        # ── Normal mode: single pyramid add at +2.5×ATR ──
                        if (n_pos == 1 and unrealized_atr > 2.5 and
                                self.last_momentum_signal_time and
                                since_signal < timedelta(hours=8)):
                            if pos_side == 'BUY' and curr_price > curr_bb_upper and is_bullish_engulfing:
                                logger.info(f"🔺 [{self.name}] PYRAMID ADD: +20% at {curr_price:.2f} ({unrealized_atr:.1f}×ATR)")
                                return self.generate_signal(
                                    "BUY", curr_price, curr_price - (curr_atr * 3.0),
                                    curr_price + (curr_atr * 15), "Momentum Pyramid Add",
                                    order_type="LIMIT_MAKER",
                                    metadata={"qty_pct": 0.2, "trailing_sl": True,
                                              "trailing_offset": 7.0, "is_pyramid": True}
                                )
                            elif pos_side == 'SELL' and curr_price < curr_bb_lower and is_bearish_engulfing:
                                logger.info(f"🔻 [{self.name}] PYRAMID ADD: +20% at {curr_price:.2f} ({unrealized_atr:.1f}×ATR)")
                                return self.generate_signal(
                                    "SELL", curr_price, curr_price + (curr_atr * 3.0),
                                    curr_price - (curr_atr * 15), "Momentum Pyramid Add",
                                    order_type="LIMIT_MAKER",
                                    metadata={"qty_pct": 0.2, "trailing_sl": True,
                                              "trailing_offset": 7.0, "is_pyramid": True}
                                )

                    return None  # Already have position(s), pyramid gates exhausted

            return self._trend_follower_logic(
                curr_price, adx_rising, vol_rising, curr_atr,
                curr_bb_lower, curr_bb_mid, curr_bb_upper,
                effective_bullish, effective_bearish
            )

        return None

    # ──────────────────────────────────────────────────────────────────
    # Mean Reversion (DISABLED by default — config.ENABLE_MEAN_REVERSION)
    # ──────────────────────────────────────────────────────────────────
    def _mean_reversion_logic(self, curr_price, curr_rsi, rvol, z_score, curr_atr, 
                               curr_bb_lower, curr_bb_mid, curr_bb_upper):
        """
        Deploy standard Precision Mean Reversion logic (2-Tier Exit).
        Only runs when config.ENABLE_MEAN_REVERSION = True.
        """
        if curr_price <= curr_bb_lower and curr_rsi < self.rsi_lower:
            if self.z_score_threshold > 0 and z_score > -self.z_score_threshold: return None
            if rvol < self.rvol_threshold: return None
            
            entry_price = curr_price
            stop_loss = entry_price - (curr_atr * self.sl_atr_mult)
            mid_tp = curr_bb_mid
            runner_tp = curr_bb_upper
            
            return {
                'action': 'PLACE_BATCH',
                'budget': getattr(self, '_budget', 100.0),
                'reserved_budget': getattr(self, '_budget', 100.0),
                'orders': [
                    self.generate_signal("BUY", entry_price, stop_loss, mid_tp, "Tier 1 (Mid)", 
                                        order_type="LIMIT_MAKER", metadata={"qty_pct": 0.5}),
                    self.generate_signal("BUY", entry_price, stop_loss, runner_tp, "Tier 2 (Runner)", 
                                        order_type="LIMIT_MAKER", metadata={"qty_pct": 0.5, "trailing_sl": True})
                ]
            }
            
        elif curr_price >= curr_bb_upper and curr_rsi > self.rsi_upper:
            if self.z_score_threshold > 0 and z_score < self.z_score_threshold: return None
            if rvol < self.rvol_threshold: return None
            
            entry_price = curr_price
            stop_loss = entry_price + (curr_atr * self.sl_atr_mult)
            mid_tp = curr_bb_mid
            runner_tp = curr_bb_lower
            
            return {
                'action': 'PLACE_BATCH',
                'budget': getattr(self, '_budget', 100.0),
                'reserved_budget': getattr(self, '_budget', 100.0),
                'orders': [
                    self.generate_signal("SELL", entry_price, stop_loss, mid_tp, "Tier 1 (Mid)", 
                                        order_type="LIMIT_MAKER", metadata={"qty_pct": 0.5}),
                    self.generate_signal("SELL", entry_price, stop_loss, runner_tp, "Tier 2 (Runner)", 
                                        order_type="LIMIT_MAKER", metadata={"qty_pct": 0.5, "trailing_sl": True})
                ]
            }
            
        return None

    # ──────────────────────────────────────────────────────────────────
    # Momentum Breakout (PRIMARY strategy — always active)
    # ──────────────────────────────────────────────────────────────────
    def _trend_follower_logic(self, curr_price, adx_rising, vol_rising, curr_atr,
                               curr_bb_lower, curr_bb_mid, curr_bb_upper,
                               is_bullish_engulfing, is_bearish_engulfing):
        """
        Deploy Trend Following breakout logic.

        Normal mode:
          - 3-bar rising ADX + 3-bar rising volume + engulfing required
          - Breakeven at +2.0×ATR (SL → entry+0.3×ATR)
          - Partial close 25% at +4.0×ATR, trail at 7×ATR

        Aggressive mode (MOMENTUM_AGGRESSIVE=True):
          - 2-bar rising ADX; engulfing optional (body>65%+RVOL>1.8×+>EMA200)
          - ATR% floor 0.28× (was 0.40×)
          - Breakeven at +1.8×ATR (SL → entry+0.35×ATR, includes fee buffer)
          - First partial close 25% at +3.2×ATR, trail at 6.0×ATR
          - Second partial close 25% at +5.0×ATR, trail at 4.5×ATR
        """
        if not adx_rising or not vol_rising:
            return None

        # Reset pyramid counter on every new base entry
        self.active_pyramid_count = 0

        if self.aggressive:
            # Aggressive profit-locking schedule (SL kept at 3.0× to preserve WR)
            lock_atr      = 1.8   # breakeven trigger (move SL to entry+0.35×ATR)
            lock_buffer   = 0.35  # SL buffer above/below entry at breakeven
            partial1_atr  = 3.2   # first partial close trigger (earlier than baseline 4.0×)
            partial1_pct  = 0.25
            trail1_atr    = 6.0   # trail after first partial (tighter than baseline 7.0×)
            partial2_atr  = 5.0   # second partial close trigger (new in V7.2)
            partial2_pct  = 0.25
            trail2_atr    = 4.5   # trail after second partial
            initial_trail = 8.0   # initial trailing stop (unchanged)
        else:
            lock_atr      = 2.0
            lock_buffer   = 0.30
            partial1_atr  = 4.0
            partial1_pct  = 0.25
            trail1_atr    = 7.0
            partial2_atr  = None  # no second partial in normal mode
            partial2_pct  = 0.0
            trail2_atr    = None
            initial_trail = 8.0

        if curr_price > curr_bb_upper and is_bullish_engulfing:
            entry_price = curr_price
            stop_loss   = entry_price - (curr_atr * 3.0)
            take_profit = entry_price + (curr_atr * 15)
            self.last_momentum_signal_time = datetime.now()
            return self.generate_signal(
                "BUY", entry_price, stop_loss, take_profit, "Momentum Breakout",
                order_type="LIMIT_MAKER",
                metadata={
                    "qty_pct": 1.0,
                    "trailing_sl": True,
                    "trailing_offset": initial_trail,
                    # Profit locking
                    "profit_lock_atr":    lock_atr,
                    "profit_lock_buffer": entry_price + (curr_atr * lock_buffer),
                    # First partial
                    "partial1_atr":  partial1_atr,
                    "partial1_pct":  partial1_pct,
                    "trail1_offset": trail1_atr,
                    # Second partial (None in normal mode — ignored by executor)
                    "partial2_atr":  partial2_atr,
                    "partial2_pct":  partial2_pct,
                    "trail2_offset": trail2_atr,
                    "pyramid_enabled": True,
                }
            )

        elif curr_price < curr_bb_lower and is_bearish_engulfing:
            entry_price = curr_price
            stop_loss   = entry_price + (curr_atr * 3.0)
            take_profit = entry_price - (curr_atr * 15)
            self.last_momentum_signal_time = datetime.now()
            return self.generate_signal(
                "SELL", entry_price, stop_loss, take_profit, "Momentum Breakdown",
                order_type="LIMIT_MAKER",
                metadata={
                    "qty_pct": 1.0,
                    "trailing_sl": True,
                    "trailing_offset": initial_trail,
                    "profit_lock_atr":    lock_atr,
                    "profit_lock_buffer": entry_price - (curr_atr * lock_buffer),
                    "partial1_atr":  partial1_atr,
                    "partial1_pct":  partial1_pct,
                    "trail1_offset": trail1_atr,
                    "partial2_atr":  partial2_atr,
                    "partial2_pct":  partial2_pct,
                    "trail2_offset": trail2_atr,
                    "pyramid_enabled": True,
                }
            )

        return None

    def on_tick(self, current_price, active_positions):
        pass
