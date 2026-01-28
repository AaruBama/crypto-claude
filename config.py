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
    "bollinger_std": 2
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
