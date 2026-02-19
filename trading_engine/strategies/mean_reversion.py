"""
Mean Reversion Strategy (Bollinger + RSI + RVOL + Z-Score Scalper)

V4 Upgrade: Relative Volume (RVOL) filter added.
V5 Upgrade: Two-tier quality system — BTC and SOL have asymmetric TP logic.

BTC (High-Frequency → Precision):
  Entry requires:  price < lower BB
                   AND z_score < -z_score_threshold  (e.g. -2.2)
                   AND RSI < rsi_lower
                   AND RVOL > rvol_threshold          (e.g. 1.6x)
                   AND ADX is falling                 (trend weakening)
  TP: BB mid (quick snap-back capture on liquid BTC)

SOL (Low-Frequency → Asymmetric):
  Entry requires:  price < lower BB
                   AND RSI < rsi_lower
                   AND RVOL > rvol_threshold          (e.g. 3.0x climax)
  TP: max(BB upper, entry + tp_atr_mult × ATR)       — let winners run
  SL: entry - sl_atr_mult × ATR                      — tight to keep L/W ratio small

The Z-Score filter (BTC only) measures how many standard deviations the current
close is from its rolling mean. A z-score < -2.2 means the price is in the bottom
1% of its recent distribution — genuine extreme, not just a "normal dip."
"""
try:
    import pandas_ta as ta
except ImportError:
    import pandas_ta_classic as ta
import logging
import numpy as np
from trading_engine.core.strategy import BaseStrategy

logger = logging.getLogger("MeanReversionStrategy")


class MeanReversionStrategy(BaseStrategy):
    def __init__(self, name="Mean_Reversion_Scalper", params=None):
        super().__init__(name, params)
        self.params = params or {}

        # ── Bollinger Bands ─────────────────────────────────────────
        self.bb_period = self.params.get('bb_period', 20)
        self.bb_std    = self.params.get('bb_std', 2.0)      # SOL uses 3.0

        # ── Oscillators ──────────────────────────────────────────────
        self.rsi_period = self.params.get('rsi_period', 14)
        self.adx_period = self.params.get('adx_period', 14)

        # ── Entry thresholds ─────────────────────────────────────────
        self.rsi_lower = self.params.get('rsi_lower', 30)    # SOL uses 25
        self.rsi_upper = self.params.get('rsi_upper', 70)    # SOL uses 75
        self.adx_limit = self.params.get('adx_limit', 25)

        # ── V4: Relative Volume filter ───────────────────────────────
        self.rvol_period    = self.params.get('rvol_period', 20)
        self.rvol_threshold = self.params.get('rvol_threshold', 1.5)

        # ── V5: Z-Score filter (BTC precision mode) ──────────────────
        # Set z_score_threshold > 0 to enable. 0 disables it (SOL default).
        self.z_score_period    = self.params.get('z_score_period', 20)
        self.z_score_threshold = self.params.get('z_score_threshold', 0.0)  # |z| > this to fire

        # ── V5: ADX direction filter (BTC only) ──────────────────────
        # If True, only enter when ADX is FALLING (trend momentum weakening).
        self.adx_must_fall = self.params.get('adx_must_fall', False)

        # ── Risk / TP settings ───────────────────────────────────────
        self.atr_period    = self.params.get('atr_period', 14)
        self.sl_atr_mult   = self.params.get('sl_atr_mult', 1.5)
        # BTC: tp_target_pct=0 → use BB mid
        # SOL: tp_target_pct=0 + tp_atr_mult > 0 → use max(BB upper, entry + N×ATR)
        self.tp_target_pct = self.params.get('tp_target_pct', 0.0)
        self.tp_atr_mult   = self.params.get('tp_atr_mult', 0.0)   # 0 = disabled (BTC default)

    # ────────────────────────────────────────────────────────────────
    def on_candle_close(self, candle_manager):
        """
        Main signal generator. Runs on every closed 5m candle.
        """
        df = candle_manager.buffer.copy()
        min_bars = max(self.bb_period, self.rvol_period, self.z_score_period) + 5
        if len(df) < min_bars:
            return None

        # ── Indicators ──────────────────────────────────────────────
        bb = df.ta.bbands(length=self.bb_period, std=self.bb_std)
        if bb is None:
            return None
        bb_lower_col = [c for c in bb.columns if c.startswith('BBL_')][0]
        bb_mid_col   = [c for c in bb.columns if c.startswith('BBM_')][0]
        bb_upper_col = [c for c in bb.columns if c.startswith('BBU_')][0]

        rsi_series = df.ta.rsi(length=self.rsi_period)

        adx_df = df.ta.adx(length=self.adx_period)
        if adx_df is None:
            return None
        adx_col = [c for c in adx_df.columns if c.startswith('ADX_')][0]

        atr_series = df.ta.atr(length=self.atr_period)

        # V4: Relative Volume
        volume_sma      = df['volume'].iloc[-self.rvol_period:].mean()
        current_volume  = float(df['volume'].iloc[-1])
        relative_volume = (current_volume / volume_sma) if volume_sma > 0 else 0.0

        # V5: Z-Score of close over rolling window
        close_window = df['close'].iloc[-self.z_score_period:]
        z_mean = float(close_window.mean())
        z_std  = float(close_window.std())
        z_score = ((float(df['close'].iloc[-1]) - z_mean) / z_std) if z_std > 0 else 0.0

        # V5: ADX direction (current vs previous bar)
        curr_adx = float(adx_df[adx_col].iloc[-1])
        prev_adx = float(adx_df[adx_col].iloc[-2]) if len(adx_df) > 1 else curr_adx
        adx_falling = curr_adx < prev_adx

        # ── Current snapshot ─────────────────────────────────────────
        curr          = df.iloc[-1]
        curr_rsi      = float(rsi_series.iloc[-1])
        curr_bb_lower = float(bb[bb_lower_col].iloc[-1])
        curr_bb_upper = float(bb[bb_upper_col].iloc[-1])
        curr_bb_mid   = float(bb[bb_mid_col].iloc[-1])
        curr_atr      = float(atr_series.iloc[-1])
        curr_price    = float(curr['close'])

        # ── Periodic scan log ────────────────────────────────────────
        if df['time'].iloc[-1].minute % 2 == 0:
            adx_dir = "↓" if adx_falling else "↑"
            logger.info(
                f"📊 [{self.name}] Scan | Price: {curr_price:.2f} | "
                f"RSI: {curr_rsi:.1f} | ADX: {curr_adx:.1f}{adx_dir} | "
                f"Z: {z_score:.2f} | RVOL: {relative_volume:.2f}x"
            )

        # ── Trend Safety Filter ──────────────────────────────────────
        if curr_adx > self.adx_limit:
            if df['time'].iloc[-1].minute % 5 == 0:
                logger.info(
                    f"🛡️ [{self.name}] ADX Filter: trending (ADX: {curr_adx:.1f} > {self.adx_limit}) — skip."
                )
            return None

        # ── Near-band RVOL miss log ───────────────────────────────────
        near_lower = curr_price <= curr_bb_lower * 1.005
        near_upper = curr_price >= curr_bb_upper * 0.995
        if (near_lower or near_upper) and relative_volume < self.rvol_threshold:
            logger.info(
                f"📉 [{self.name}] RVOL miss near BB edge "
                f"(RVOL: {relative_volume:.2f}x < {self.rvol_threshold}x) — waiting for climax."
            )

        # ════════════════════════════════════════════════════════════
        # LONG entry
        # ════════════════════════════════════════════════════════════
        if curr_price <= curr_bb_lower and curr_rsi < self.rsi_lower:

            # V5 BTC: Z-Score gate
            if self.z_score_threshold > 0 and z_score > -self.z_score_threshold:
                logger.info(
                    f"🔬 [{self.name}] Z-Score gate: z={z_score:.2f} not extreme enough "
                    f"(need < -{self.z_score_threshold}) — skip."
                )
                return None

            # V5 BTC: RVOL gate
            if relative_volume < self.rvol_threshold:
                return None

            # V5 BTC: ADX direction gate
            if self.adx_must_fall and not adx_falling:
                logger.info(
                    f"📈 [{self.name}] ADX direction gate: ADX still rising "
                    f"({prev_adx:.1f} → {curr_adx:.1f}) — skip."
                )
                return None

            entry_price = curr_price
            stop_loss   = entry_price - (curr_atr * self.sl_atr_mult)

            # ── TP: 2-Tier Asymmetric Exit (50/50) ──
            if self.tp_atr_mult > 0:
                mid_tp = curr_bb_mid
                runner_tp = curr_bb_upper # opposite BB
                atr_sl = entry_price - (curr_atr * self.tp_atr_mult)
                stop_loss = atr_sl # 1.5 ATR initially
                
                rr_1 = (mid_tp - entry_price) / (entry_price - stop_loss) if (entry_price - stop_loss) > 0 else 0
                rr_2 = (runner_tp - entry_price) / (entry_price - stop_loss) if (entry_price - stop_loss) > 0 else 0
                
                logger.info(
                    f"🟢 [{self.name}] BUY BATCH | Price: {entry_price:.2f} | "
                    f"SL: {stop_loss:.2f} | TP1: {mid_tp:.2f} | TP2: {runner_tp:.2f}"
                )
                
                return {
                    'action': 'PLACE_BATCH',
                    'budget': getattr(self, '_budget', 100.0),
                    'reserved_budget': getattr(self, '_budget', 100.0),
                    'orders': [
                        self.generate_signal("BUY", entry_price, stop_loss, mid_tp, 
                            "Tier 1 (Mid)", order_type="LIMIT_MAKER", metadata={ "qty_pct": 0.5 }),
                        self.generate_signal("BUY", entry_price, stop_loss, runner_tp, 
                            "Tier 2 (Runner)", order_type="LIMIT_MAKER", metadata={ "qty_pct": 0.5, "trailing_sl": True })
                    ]
                }
            else:
                take_profit = curr_bb_mid
                if self.tp_target_pct > 0:
                    min_tp = entry_price * (1 + self.tp_target_pct / 100)
                    take_profit = max(take_profit, min_tp)
                if take_profit <= entry_price:
                    take_profit = curr_bb_upper

            rr = (take_profit - entry_price) / (entry_price - stop_loss) if (entry_price - stop_loss) > 0 else 0
            logger.info(
                f"🟢 [{self.name}] BUY | Price: {entry_price:.2f} | "
                f"RSI: {curr_rsi:.1f} | Z: {z_score:.2f} | RVOL: {relative_volume:.2f}x | "
                f"ADX {'↓' if adx_falling else '↑'} | "
                f"SL: {stop_loss:.2f} | TP: {take_profit:.2f} | R/R: {rr:.1f}x"
            )
            return self.generate_signal(
                side="BUY",
                price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason=(
                    f"MeanRev: BB Oversold | RSI {curr_rsi:.0f} | "
                    f"Z {z_score:.2f} | RVOL {relative_volume:.1f}x"
                ),
                order_type="LIMIT_MAKER",
                metadata={
                    "adx": curr_adx,
                    "rsi": curr_rsi,
                    "rvol": relative_volume,
                    "z_score": z_score,
                    "adx_falling": adx_falling,
                },
            )

        # ════════════════════════════════════════════════════════════
        # SHORT entry (symmetric logic)
        # ════════════════════════════════════════════════════════════
        elif curr_price >= curr_bb_upper and curr_rsi > self.rsi_upper:

            if self.z_score_threshold > 0 and z_score < self.z_score_threshold:
                logger.info(
                    f"🔬 [{self.name}] Z-Score gate: z={z_score:.2f} not extreme enough "
                    f"(need > +{self.z_score_threshold}) — skip."
                )
                return None

            if relative_volume < self.rvol_threshold:
                return None

            if self.adx_must_fall and not adx_falling:
                logger.info(
                    f"📈 [{self.name}] ADX direction gate: ADX still rising — skip."
                )
                return None

            entry_price = curr_price
            stop_loss   = entry_price + (curr_atr * self.sl_atr_mult)

            if self.tp_atr_mult > 0:
                mid_tp = curr_bb_mid
                runner_tp = curr_bb_lower # opposite BB
                atr_sl = entry_price + (curr_atr * self.tp_atr_mult)
                stop_loss = atr_sl # 1.5 ATR initially
                
                rr_1 = (entry_price - mid_tp) / (stop_loss - entry_price) if (stop_loss - entry_price) > 0 else 0
                rr_2 = (entry_price - runner_tp) / (stop_loss - entry_price) if (stop_loss - entry_price) > 0 else 0

                logger.info(
                    f"🔴 [{self.name}] SELL BATCH | Price: {entry_price:.2f} | "
                    f"SL: {stop_loss:.2f} | TP1: {mid_tp:.2f} | TP2: {runner_tp:.2f}"
                )
                
                return {
                    'action': 'PLACE_BATCH',
                    'budget': getattr(self, '_budget', 100.0),
                    'reserved_budget': getattr(self, '_budget', 100.0),
                    'orders': [
                        self.generate_signal("SELL", entry_price, stop_loss, mid_tp, 
                            "Tier 1 (Mid)", order_type="LIMIT_MAKER", metadata={ "qty_pct": 0.5 }),
                        self.generate_signal("SELL", entry_price, stop_loss, runner_tp, 
                            "Tier 2 (Runner)", order_type="LIMIT_MAKER", metadata={ "qty_pct": 0.5, "trailing_sl": True })
                    ]
                }
            else:
                take_profit = curr_bb_mid
                if self.tp_target_pct > 0:
                    min_tp = entry_price * (1 - self.tp_target_pct / 100)
                    take_profit = min(take_profit, min_tp)
                if take_profit >= entry_price:
                    take_profit = curr_bb_lower

            rr = (entry_price - take_profit) / (stop_loss - entry_price) if (stop_loss - entry_price) > 0 else 0
            logger.info(
                f"🔴 [{self.name}] SELL | Price: {entry_price:.2f} | "
                f"RSI: {curr_rsi:.1f} | Z: {z_score:.2f} | RVOL: {relative_volume:.2f}x | "
                f"ADX {'↓' if adx_falling else '↑'} | "
                f"SL: {stop_loss:.2f} | TP: {take_profit:.2f} | R/R: {rr:.1f}x"
            )
            return self.generate_signal(
                side="SELL",
                price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                reason=(
                    f"MeanRev: BB Overbought | RSI {curr_rsi:.0f} | "
                    f"Z {z_score:.2f} | RVOL {relative_volume:.1f}x"
                ),
                order_type="LIMIT_MAKER",
                metadata={
                    "adx": curr_adx,
                    "rsi": curr_rsi,
                    "rvol": relative_volume,
                    "z_score": z_score,
                    "adx_falling": adx_falling,
                },
            )

        return None

    def on_tick(self, current_price, active_positions):
        return None
