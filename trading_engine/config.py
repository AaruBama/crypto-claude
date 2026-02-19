
"""
Trading Engine configuration.
Separate from dashboard config to avoid circular dependencies during migration.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Engine Settings
ENGINE_SETTINGS = {
    "symbol": "BTC/USDT",
    "timeframe": "15m",         # V7.1: 15m candles for signal quality
    "update_interval": 1,       # seconds
    "paper_trading": True,      # ✅ PAPER MODE: No real orders sent
    "LIVE_TRADING_ENABLED": False,
    "VOL_SPIKE_THRESHOLD": 1.5,
    "Z_SCORE_THRESHOLD": 3.0,
}

# ──────────────────────────────────────────────────────────────────
# V7.1 Strategy Switches (2026-02-20 A/B Test Conclusion)
# Pure momentum outperforms MR-inclusive by ~8% CAGR with 5× lower DD.
# MR disabled by default; set to True to re-enable for testing.
# ──────────────────────────────────────────────────────────────────
ENABLE_MEAN_REVERSION = False
ENABLE_MOMENTUM_BREAKOUT = True

# Momentum-specific settings
MOMENTUM_CONSECUTIVE_LOSS_LIMIT = 3    # Pause after N consecutive losers
MOMENTUM_LOSS_COOLDOWN_HOURS = 48      # Hours to pause after streak
MOMENTUM_WEEKLY_COMPOUND_THRESHOLD = 1.5  # % weekly PnL to trigger compounding
MOMENTUM_COMPOUND_FRACTION = 0.5       # Fraction of weekly return to reinvest

# Risk Limits
RISK_SETTINGS = {
    "max_drawdown_daily": 3.0,        # % of daily starting balance
    "max_position_size_usd": 2000,    # Cap single position size
    "max_open_positions": 50,          # Hard limit on concurrent positions
    "stop_loss_default_pct": 1.5,
    "fee_rate": 0.00075,              # Binance 0.075% (0.1% - 25% BNB discount)
    "tax_rate": 0.01,                 # Estimated Tax Buffer (1% of profits)
    "slippage_penalty": 0.0005,       # -0.05% slippage on entry & exit (simulated)
    "min_profit_pct": 0.5,            # 🛡️ Quality Filter: Only take trades targeting > 0.50% profit
}

# Strategy Settings
STRATEGIES = {
    "TRAFFIC_LIGHT": {
        "id": "traffic_light",
        "name": "Traffic Light Breakout",
        "params": {
            "vol_filter": 1.5,
            "risk_reward": 3.0
        }
    },
    "MEAN_REVERSION": {
        "id": "mean_reversion",
        "name": "Bollinger RSI Scalper (BTC) — V5 Precision",
        "params": {
            "bb_period": 20,
            "bb_std": 2.0,
            "rsi_lower": 30,
            "rsi_upper": 70,
            "adx_limit": 25,
            "atr_period": 14,
            "sl_atr_mult": 1.5,
            "tp_target_pct": 0,         # Overridden by tp_atr_mult
            "tp_atr_mult": 3.0,         # V5 Optimal 2-Tier Asymmetric Exit
            # V4: RVOL — raised for better signal quality
            "rvol_period": 20,
            "rvol_threshold": 2.5,      # Exhaustion spike optimal value
            # V5: Z-Score precision filter
            # Entry only when price is >2.5 std-devs below 20-bar mean (~0.6% of candles).
            # Note: adx_must_fall intentionally NOT used — ADX always rises on the crash
            # candle that creates the oversold BB touch, making it logically antagonistic.
            # Z-Score alone cuts ~50% of marginal signals vs baseline.
            "z_score_period": 20,
            "z_score_threshold": 2.5,   # V5 optimal: 64 trades, 50% WR, $7.06 net P&L (90d backtest)
            "adx_must_fall": False,      # Disabled — see note above
        }
    },
    "MEAN_REVERSION_SOL": {
        "id": "mean_reversion_sol",
        "name": "Bollinger RSI Scalper (SOL) — V5 Asymmetric",
        "params": {
            "bb_period": 20,
            "bb_std": 3.0,            # 3-sigma — only absolute panic dips
            "rsi_lower": 25,          # Tougher oscillator filter
            "rsi_upper": 75,
            "adx_limit": 25,
            "atr_period": 14,
            # V5: Tight SL to keep losers small (21% WR needs small L / big W)
            "sl_atr_mult": 1.5,       # Standard 1.5 multiplier
            "tp_target_pct": 0,       # Overridden by tp_atr_mult below
            # V5: Asymmetric TP — let winners run to max(BB upper, entry + 3.0×ATR)
            # At 21% WR: need avg winner ≥ 3× avg loser to survive fees.
            # 1.5×ATR target vs 1.2×ATR stop = 1.25:1 raw R/R minimum.
            # BB upper is usually 2.0–3.5×ATR away at entry, giving 2–3:1 real R/R.
            "tp_atr_mult": 3.0,       # V5 Optimal 2-Tier Asymmetric Exit
            # V4: RVOL — 2.5x
            "rvol_period": 20,
            "rvol_threshold": 2.5,
            # V5: Z-Score applied to SOL as well now!
            "z_score_threshold": 2.5,
            "adx_must_fall": False,
        }
    },
    "GRID_TRADING": {
        "id": "neutral_grid",
        "name": "Neutral Grid Bot (Selective)",
        "params": {
            "grid_levels": 5,
            "grid_spacing_pct": 1.2,          
            "max_capital": 75.0,              
            "adx_max": 20,                    
            "adx_stop_loss": 28,              
            "global_sl_pct": 3.0,             
            "pause_hours": 4,                  
            "ejector_threshold_pct": 3.0,      
        }
    },
    "ADAPTIVE_ENGINE": {
        "id": "adaptive_engine_btc",
        "name": "V7 Chameleon (BTC)",
        "params": {
            "bb_period": 20,
            "bb_std": 2.0,
            "rsi_lower": 30,
            "rsi_upper": 70,
            "adx_limit": 30,
            "atr_period": 14,
            "sl_atr_mult": 1.5,
            "tp_atr_mult": 3.0,
            "rvol_period": 20,
            "rvol_threshold": 3.0,
            "z_score_period": 20,
            "z_score_threshold": 3.0,
        }
    },
    "ADAPTIVE_ENGINE_SOL": {
        "id": "adaptive_engine_sol",
        "name": "V7 Chameleon (SOL)",
        "params": {
            "bb_period": 20,
            "bb_std": 3.0,
            "rsi_lower": 25,
            "rsi_upper": 75,
            "adx_limit": 35,
            "atr_period": 14,
            "sl_atr_mult": 1.5,
            "tp_atr_mult": 4.0,
            "rvol_period": 20,
            "rvol_threshold": 3.0,
            "z_score_period": 20,
            "z_score_threshold": 3.0,
        }
    }
}

# Active Strategies List (Concurrent Execution)
# ⚠️  SAFETY: Only add a strategy here AFTER it has been backtested.
# ✅  LIVE PLAN: Mean Reversion only. Grid is opt-in via SELECTIVE_GRID rule.
ACTIVE_STRATEGIES = ["ADAPTIVE_ENGINE", "ADAPTIVE_ENGINE_SOL"]

# ------------------------------------------------------------------
# V4 Live Allocation — $300 Account
# ------------------------------------------------------------------
# Slot          Budget    Strategy              Rationale
# ──────────────────────────────────────────────────────────────────
# BTC_MeanRev   $150      Mean Reversion BTC    Safe play, 48.8% WR
# SOL_MeanRev   $75       Mean Reversion SOL    Aggressive, 29% WR
# USDT_Reserve  $75       Cash (no strategy)    Keeps RiskManager happy;
#                                               activated as Grid budget
#                                               ONLY when 1D ADX < 20
# ──────────────────────────────────────────────────────────────────
LIVE_ALLOCATION = {
    "BTC_Adaptive": {"budget": 200.0, "symbol": "BTC/USDT", "strategy": "ADAPTIVE_ENGINE"},
    "SOL_Adaptive": {"budget": 100.0, "symbol": "SOL/USDT", "strategy": "ADAPTIVE_ENGINE_SOL"},
    # "USDT_Reserve": None  (Fully Deployed)
}

# ------------------------------------------------------------------
# Selective Grid Rule (V4)
# ------------------------------------------------------------------
# The Grid is NOT run 24/7. Activate it manually ONLY when:
#   1. The 4H chart shows a clear Horizontal Channel (price bouncing between two levels)
#   2. The 1D ADX is BELOW 20 (confirmed ranging market, no trend)
#   3. No major news event in the next 24h (earnings, CPI, Fed, etc.)
#
# When activated, the Grid uses the $75 USDT_Reserve budget.
# It auto-deactivates when ADX > adx_stop_loss (28) via the Ejector Seat.
SELECTIVE_GRID = {
    "enabled": False,               # ← FLIPPED BACK TO FALSE (Grid failed backtest: -4% PnL + conflicts)
    "activation_adx_1d_max": 20,    # Only activate if 1D ADX < 20
    "budget": 75.0,                 # Draws from USDT_Reserve
    "symbol": "BTC",                # Default: BTC grid (tighter spreads, more liquid)
    "params": STRATEGIES["GRID_TRADING"]["params"],
}

# Breakeven Protection (V3)
# If a trade reaches trigger_pct profit, move SL to entry + sl_buffer_pct
BREAKEVEN_PROTECTION = {
    "enabled": True,
    "trigger_pct": 0.6,       # Move SL when trade is 0.6% in profit
    "sl_buffer_pct": 0.1,     # SL moves to entry + 0.1% (covers entry fee)
}

# Phase 4 Micro-Live Safety Caps — scaled for $300 account
MICRO_LIVE_LIMITS = {
    # max_trade_usd: max notional per single order.
    # Must be >= largest strategy budget ($150 BTC) to avoid blocking valid signals.
    # The real per-strategy cap is enforced via LIVE_ALLOCATION budgets.
    "max_trade_usd": 1000.0,
    "max_total_exposure_usd": 2000.0  # Max 75% of $300 deployed at any time
}

# API Keys (from .env)
env_key = os.getenv("BINANCE_API_KEY", "")
API_KEY = env_key if env_key and "your_" not in env_key.lower() else None
# Check for both common naming conventions
API_SECRET = os.getenv("BINANCE_API_SECRET") or os.getenv("BINANCE_SECRET_KEY")
