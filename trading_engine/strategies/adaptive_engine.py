"""
V7.1 Chameleon Adaptive Engine — Pure Momentum Configuration
═══════════════════════════════════════════════════════════════
2026-02-20 A/B Test Conclusion:
  Pure momentum outperforms MR-inclusive by ~8% CAGR with 5× lower DD.
  - CAGR: +19.82% vs +11.47%  |  Max DD: -0.92% vs -2.62%
  - Profit Factor: 4.44 vs 1.41  |  Sharpe: 1.74 vs 0.82
  - Trades: 34/year vs 134/year  |  Fees: $25 vs $63

Production Config: Pure Momentum Breakout (15m context,
engulfing + ADX/vol confirmation), default MR disabled.
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
        self.active_pyramid_count = 0

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
            # Allow pyramid (1 add-on) but block if already at max
            if len(my_positions) >= 2:
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
            
            # ADX must be rising for momentum entry
            adx_rising = False
            if len(adx_df) >= 3:
                adx_vals = adx_df[adx_col].iloc[-3:]
                adx_rising = (float(adx_vals.iloc[-1]) > float(adx_vals.iloc[-2]) and 
                             float(adx_vals.iloc[-2]) > float(adx_vals.iloc[-3]))
            
            # Volume must be rising for 3 bars
            vol_rising = False
            if len(df) >= 3:
                vols = df['volume'].iloc[-3:]
                vol_rising = (float(vols.iloc[-1]) > float(vols.iloc[-2]) and 
                             float(vols.iloc[-2]) > float(vols.iloc[-3]))
            
            # Engulfing detection
            is_bullish_engulfing = False
            is_bearish_engulfing = False
            if len(df) >= 2:
                prev_open  = float(df['open'].iloc[-2])
                prev_close = float(df['close'].iloc[-2])
                curr_open  = float(df['open'].iloc[-1])
                
                is_bullish_engulfing = (curr_price > curr_open and prev_close < prev_open and 
                                       curr_price >= prev_open and curr_open <= prev_close)
                is_bearish_engulfing = (curr_price < curr_open and prev_close > prev_open and 
                                       curr_price <= prev_open and curr_open >= prev_close)
            
            # Min ATR% filter: skip if ATR% < 0.4× 50-period average (dead range)
            if atr_pct_avg > 0 and curr_atr_pct < (0.4 * atr_pct_avg):
                logger.debug(f"[{self.name}] Skipping: ATR% {curr_atr_pct*100:.3f}% < 0.4× avg {atr_pct_avg*100:.3f}%")
                return None
            
            # Check for pyramid opportunity on existing position
            if active_positions:
                my_positions = [p for p in active_positions if p.get('strategy_id') == self.name]
                if len(my_positions) == 1:
                    pos = my_positions[0]
                    entry = pos.get('entry_price', curr_price)
                    pos_side = pos.get('side', '')
                    unrealized_atr = (curr_price - entry) / curr_atr if pos_side == 'BUY' else (entry - curr_price) / curr_atr
                    
                    # Pyramid: add 20% if position > +2.5× ATR and new signal within 8h
                    if (unrealized_atr > 2.5 and self.last_momentum_signal_time and 
                        (datetime.now() - self.last_momentum_signal_time) < timedelta(hours=8)):
                        
                        if pos_side == 'BUY' and curr_price > curr_bb_upper and is_bullish_engulfing:
                            logger.info(f"🔺 [{self.name}] PYRAMID ADD: +20% at {curr_price:.2f} (unrealized: {unrealized_atr:.1f}× ATR)")
                            return self.generate_signal(
                                "BUY", curr_price, curr_price - (curr_atr * 3.0),
                                curr_price + (curr_atr * 15), "Momentum Pyramid Add",
                                order_type="LIMIT_MAKER",
                                metadata={"qty_pct": 0.2, "trailing_sl": True, "trailing_offset": 7.0, "is_pyramid": True}
                            )
                        elif pos_side == 'SELL' and curr_price < curr_bb_lower and is_bearish_engulfing:
                            logger.info(f"🔻 [{self.name}] PYRAMID ADD: +20% at {curr_price:.2f} (unrealized: {unrealized_atr:.1f}× ATR)")
                            return self.generate_signal(
                                "SELL", curr_price, curr_price + (curr_atr * 3.0),
                                curr_price - (curr_atr * 15), "Momentum Pyramid Add",
                                order_type="LIMIT_MAKER",
                                metadata={"qty_pct": 0.2, "trailing_sl": True, "trailing_offset": 7.0, "is_pyramid": True}
                            )
                    return None  # Already have a position, don't stack further
            
            return self._trend_follower_logic(
                curr_price, adx_rising, vol_rising, curr_atr, 
                curr_bb_lower, curr_bb_mid, curr_bb_upper,
                is_bullish_engulfing, is_bearish_engulfing
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
        Deploy Trend Following breakout logic with:
        - 3-bar rising ADX + volume confirmation
        - Engulfing candle pattern required
        - Dynamic trailing stops with profit locking:
            +2× ATR: SL → entry + 0.3× ATR (fee buffer)
            +4× ATR: close 25%, trail remainder at 7× ATR
        """
        # All three filters must pass: rising ADX, rising volume, engulfing
        if not adx_rising or not vol_rising:
            return None
        
        if curr_price > curr_bb_upper and is_bullish_engulfing:
            # Upside breakout
            entry_price = curr_price
            stop_loss = entry_price - (curr_atr * 3.0)
            take_profit = entry_price + (curr_atr * 15)
            
            self.last_momentum_signal_time = datetime.now()
            
            return self.generate_signal(
                "BUY", entry_price, stop_loss, take_profit, "Momentum Breakout",
                order_type="LIMIT_MAKER", 
                metadata={
                    "qty_pct": 1.0, 
                    "trailing_sl": True, 
                    "trailing_offset": 8.0,
                    "profit_lock_2atr": entry_price + (curr_atr * 0.3),  # SL moves to entry+0.3ATR at +2ATR
                    "partial_close_4atr": 0.25,  # Close 25% at +4ATR
                    "trail_after_partial": 7.0,   # Trail remainder at 7× ATR
                    "pyramid_enabled": True
                }
            )
            
        elif curr_price < curr_bb_lower and is_bearish_engulfing:
            # Downside breakout
            entry_price = curr_price
            stop_loss = entry_price + (curr_atr * 3.0)
            take_profit = entry_price - (curr_atr * 15)
            
            self.last_momentum_signal_time = datetime.now()
            
            return self.generate_signal(
                "SELL", entry_price, stop_loss, take_profit, "Momentum Breakdown",
                order_type="LIMIT_MAKER", 
                metadata={
                    "qty_pct": 1.0, 
                    "trailing_sl": True, 
                    "trailing_offset": 8.0,
                    "profit_lock_2atr": entry_price - (curr_atr * 0.3),
                    "partial_close_4atr": 0.25,
                    "trail_after_partial": 7.0,
                    "pyramid_enabled": True
                }
            )
            
        return None

    def on_tick(self, current_price, active_positions):
        pass
