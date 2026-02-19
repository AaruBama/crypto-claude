import logging
import pandas as pd
import numpy as np

try:
    import pandas_ta as ta
except ImportError:
    import pandas_ta_classic as ta

from trading_engine.core.strategy import BaseStrategy

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
    V7 Chameleon Hybrid Adaptive Engine.
    Dynamically switches between:
    - Ranging: precision Bollinger/Z-score/RVOL sniper.
    - Trending: Momentum BB-Breakout with fat-tail trailing stops.
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
        self.adx_limit  = self.params.get('adx_limit', 25)
        # Filters
        self.rvol_period       = self.params.get('rvol_period', 20)
        self.rvol_threshold    = self.params.get('rvol_threshold', 2.5)
        self.z_score_period    = self.params.get('z_score_period', 20)
        self.z_score_threshold = self.params.get('z_score_threshold', 2.5)
        # Risk
        self.atr_period    = self.params.get('atr_period', 14)
        self.sl_atr_mult   = self.params.get('sl_atr_mult', 1.5)
        self.tp_atr_mult   = self.params.get('tp_atr_mult', 3.0) 
        
        self.regime_detector = RegimeDetector(
            adx_period=self.adx_period, 
            atr_period=self.atr_period, 
            lookback=100, 
            chaos_pct=0.95
        )

    def on_candle_close(self, candle_manager, active_positions=None):
        df = candle_manager.buffer.copy()
        regime = self.regime_detector.get_market_regime(df, self.adx_limit)
        
        if regime == "UNKNOWN" or regime == "CHAOS":
            # Stand down during CHAOS
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

        if active_positions is not None:
            my_positions = [p for p in active_positions if p.get('strategy_id') == self.name]
            if len(my_positions) > 0:
                return None  # Wait for position to close

        if df['time'].iloc[-1].minute % 5 == 0:
            logger.info(f"🦎 [{self.name}] Regime: {regime} | Price: {curr_price:.2f} | ADX: {float(adx_df[adx_col].iloc[-1]):.1f}")

        # Core Routing based on Market Regime
        if regime == "RANGING":
            return self._mean_reversion_logic(curr_price, curr_rsi, rvol, z_score, curr_atr, curr_bb_lower, curr_bb_mid, curr_bb_upper)
            
        elif regime == "TRENDING":
            adx_rising = False
            if len(adx_df) > 1:
                adx_rising = float(adx_df[adx_col].iloc[-1]) > float(adx_df[adx_col].iloc[-2])
                
            return self._trend_follower_logic(curr_price, adx_rising, curr_atr, curr_bb_lower, curr_bb_mid, curr_bb_upper)

        return None

    def _mean_reversion_logic(self, curr_price, curr_rsi, rvol, z_score, curr_atr, curr_bb_lower, curr_bb_mid, curr_bb_upper):
        """
        Deploy standard Precision Mean Reversion logic (2-Tier Exit).
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
                    self.generate_signal("BUY", entry_price, stop_loss, mid_tp, "Tier 1 (Mid)", order_type="LIMIT_MAKER", metadata={"qty_pct": 0.5}),
                    self.generate_signal("BUY", entry_price, stop_loss, runner_tp, "Tier 2 (Runner)", order_type="LIMIT_MAKER", metadata={"qty_pct": 0.5, "trailing_sl": True})
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
                    self.generate_signal("SELL", entry_price, stop_loss, mid_tp, "Tier 1 (Mid)", order_type="LIMIT_MAKER", metadata={"qty_pct": 0.5}),
                    self.generate_signal("SELL", entry_price, stop_loss, runner_tp, "Tier 2 (Runner)", order_type="LIMIT_MAKER", metadata={"qty_pct": 0.5, "trailing_sl": True})
                ]
            }
            
        return None

    def _trend_follower_logic(self, curr_price, adx_rising, curr_atr, curr_bb_lower, curr_bb_mid, curr_bb_upper):
        """
        Deploy Trend Following breakout logic with wide trailing stops.
        """
        if not adx_rising: return None
        
        if curr_price > curr_bb_upper:
            # Upside breakout
            entry_price = curr_price
            stop_loss = entry_price - (curr_atr * 3.0) # Fat tail trailing SL
            take_profit = entry_price + (curr_atr * 15) # Very high target to let trailing stop do its job
            
            return self.generate_signal(
                "BUY", entry_price, stop_loss, take_profit, "Momentum Breakout",
                order_type="LIMIT_MAKER", metadata={"qty_pct": 1.0, "trailing_sl": True, "trailing_offset": 3.0}
            )
            
        elif curr_price < curr_bb_lower:
            # Downside breakout
            entry_price = curr_price
            stop_loss = entry_price + (curr_atr * 3.0)
            take_profit = entry_price - (curr_atr * 15)
            
            return self.generate_signal(
                "SELL", entry_price, stop_loss, take_profit, "Momentum Breakdown",
                order_type="LIMIT_MAKER", metadata={"qty_pct": 1.0, "trailing_sl": True, "trailing_offset": 3.0}
            )
            
        return None

    def on_tick(self, current_price, active_positions):
        pass
