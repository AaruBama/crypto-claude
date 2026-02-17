"""
Configuration for crypto trading dashboard
"""
import os
from datetime import datetime

# Exchange Settings
EXCHANGE = "binance"
TESTNET = False  # Use testnet for paper trading later

# Symbols to track
PRIMARY_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
ALT_SYMBOLS = ["SOLUSDT", "BNBUSDT", "ADAUSDT"]  # Can expand later

# Timeframes for data collection
TIMEFRAMES = {
    "1m": "1 minute",
    "5m": "5 minutes", 
    "15m": "15 minutes",
    "1h": "1 hour",
    "4h": "4 hours",
    "1d": "1 day"
}

# Default timeframe for main chart
DEFAULT_TIMEFRAME = "15m"

# Data collection settings
DATA_UPDATE_INTERVAL = 60  # seconds
HISTORICAL_DAYS = 30  # How many days of history to fetch initially

# Technical Indicator Settings
INDICATORS = {
    "ema_short": 50,
    "ema_long": 200,
    "rsi_period": 14,
    "atr_period": 14,
    "adx_period": 14,
    "volume_ma_period": 20,
    "bollinger_period": 20,
    "bollinger_std": 2,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9
}

# Strategy Configurations (The "Library")
STRATEGIES = {
    "8_30_EMA": {
        "id": "strat_8_30",
        "name": "8-30 EMA Trend Ride",
        "type": "ema_cross",
        "fast": 8,
        "slow": 30,
        "color_fast": "#ffff00",  # Yellow
        "color_slow": "#ffa500",  # Orange
        "logic": "Buy when 8 EMA crosses above 30 EMA. Sell when it crosses below.",
        "risk_profile": "Conservative (Trend Following)",
        "ideal_regime": "trending",
        "description": "Trend-following with 8 (fast) and 30 (slow) EMA"
    },
    "9_20_EMA": {
        "id": "strat_9_20",
        "name": "9-20 Momentum Scalp",
        "type": "ema_cross",
        "fast": 9,
        "slow": 20,
        "color_fast": "#00ffff",  # Cyan
        "color_slow": "#0000ff",  # Blue
        "logic": "Buy when 9 EMA crosses above 20 EMA. Sell when it crosses below.",
        "risk_profile": "Aggressive (High frequency)",
        "ideal_regime": "volatile",
        "description": "Scalping strategy with 9 (fast) and 20 (slow) EMA"
    },
    "RSI_MEAN_REVERSION": {
        "id": "strat_rsi_rev",
        "name": "RSI Mean Reversion",
        "type": "oscillator",
        "buy_threshold": 30,
        "sell_threshold": 70,
        "logic": "Buy when RSI < 30 (Oversold). Sell when RSI > 70 (Overbought).",
        "risk_profile": "Moderate (Counter-trend)",
        "ideal_regime": "ranging",
        "description": "Classic buy low, sell high using RSI extremes"
    },
    "BB_BREAKOUT": {
        "id": "strat_bb_break",
        "name": "Bollinger Band Breakout",
        "type": "volatility_breakout",
        "squeeze_threshold": 0.05, # Bandwidth
        "logic": "Buy when price closes above Upper Band after a Squeeze. Sell if closes below Lower Band.",
        "risk_profile": "Aggressive (Volatile Expansion)",
        "ideal_regime": "volatile",
        "description": "Catching explosive moves after low volatility squeezes"
    },
    "MACD_REVERSAL": {
        "id": "strat_macd_rev",
        "name": "MACD Trend Reversal",
        "type": "macd_cross",
        "logic": "Buy when MACD Hist turns green (Bullish Cross) below zero line. Sell when turns red above zero.",
        "risk_profile": "Moderate (Momentum Reversal)",
        "ideal_regime": "reversal",
        "description": "Early trend reversal detection using MACD Momentum"
    },
    "GOLDEN_CROSS": {
        "id": "strat_golden_cross",
        "name": "Golden Cross (50/200)",
        "type": "ema_cross",
        "fast": 50,
        "slow": 200,
        "color_fast": "#FFD700", # Gold
        "color_slow": "#FFFFFF", # White
        "logic": "Buy when 50 EMA crosses above 200 EMA. Sell when it crosses below (Death Cross).",
        "risk_profile": "Conservative (Long Term)",
        "ideal_regime": "trending",
        "description": "Major long-term market regime shift indicator"
    },
    "VWAP_PULLBACK": {
        "id": "strat_vwap",
        "name": "VWAP Pullback",
        "type": "price_action",
        "logic": "Buy when price is in uptrend but touches VWAP from above. Sell when price touches VWAP from below in downtrend.",
        "risk_profile": "Low (Trend Continuation)",
        "ideal_regime": "trending",
        "description": "Institutional entry points at fair value during trends"
    }
}

# Market Regime Thresholds
REGIME_THRESHOLDS = {
    "adx_trending": 25,  # ADX > 25 = trending
    "adx_strong": 40,    # ADX > 40 = strong trend
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    "atr_high_percentile": 75,  # Top 25% = high volatility
    "range_threshold": 2.5  # % price range for ranging market
}

# Alert Thresholds
ALERTS = {
    "funding_rate_extreme": 0.01,  # 1% funding
    "oi_spike_percent": 20,  # 20% OI increase
    "volume_spike_multiplier": 3,  # 3x average volume
    "price_stretch_percent": 2,  # 2% from VWAP
    "latency_threshold_ms": 1000
}

# Risk Management
RISK = {
    "max_position_size_percent": 2,  # 2% of capital per trade
    "max_daily_loss_percent": 5,     # 5% max daily loss
    "max_leverage": 3
}

# Data Storage
DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "storage")
DB_PATH = os.path.join(DATA_DIR, "crypto_data.db")

# Dashboard Settings
DASHBOARD = {
    "refresh_interval": 5,  # seconds
    "chart_height": 600,
    "show_tooltips": True,  # Beginner mode
    "dark_mode": True
}

# Session Times (UTC)
SESSION_TIMES = {
    "asia": {"start": 0, "end": 8},      # 00:00 - 08:00 UTC
    "london": {"start": 8, "end": 16},   # 08:00 - 16:00 UTC
    "ny": {"start": 13, "end": 21}       # 13:00 - 21:00 UTC
}

# API Rate Limits
RATE_LIMITS = {
    "binance_weight_limit": 1200,  # per minute
    "request_delay": 0.1  # seconds between requests
}
