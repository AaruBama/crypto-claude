# 🚀 Crypto Trading Dashboard

A professional-grade cryptocurrency trading dashboard built for learning algorithmic trading, with focus on visibility and understanding market conditions.

## 🧠 Dashboard Mental Model

Your dashboard answers 4 critical questions:
1. **What is the market doing right now?** → Market Overview
2. **Is it calm or aggressive?** → Volatility & Momentum
3. **Is price stretched or fair?** → VWAP Analysis
4. **Is this a good environment to trade?** → Market Regime

## ✨ Features

### 📊 Market Overview
- Real-time BTC & ETH prices
- 24h price changes
- Market cap & BTC dominance
- Exchange latency monitoring

### 📈 Price & Structure
- Interactive candlestick charts
- **VWAP** - Your fair price gravity line
- EMA 50 & 200 for trend
- Bollinger Bands for volatility
- Volume analysis
- Previous session levels

### ⚡ Volatility & Momentum
- **ATR** - How much price moves
- **RSI** - Overbought/oversold conditions
- Volume spike detection
- Distance from VWAP (stretched vs fair)

### 🎯 Market Regime Detection
- **Trending** 🟢 - Follow the trend
- **Ranging** 🟡 - Mean reversion plays
- **Volatile** 🔴 - Be cautious
- ADX trend strength indicator

### 📈 Derivatives (Crypto-Specific)
- Funding rates (long vs short sentiment)
- Open interest tracking
- Perp-spot spread analysis

### 🧠 Learning Mode
- Hover tooltips explaining every metric
- Beginner-friendly interpretations
- No jargon without explanation

## 🛠️ Installation

### Prerequisites
- Python 3.8+
- pip package manager

### Setup

1. **Clone or download this project**

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Run the dashboard**
```bash
cd dashboard
streamlit run app.py
```

The dashboard will open in your browser at `http://localhost:8501`

## 📖 Usage Guide

### Symbol Selection
- Choose from BTC, ETH, and major altcoins
- Uses Binance spot market data

### Timeframes
- 1m, 5m, 15m - For day trading
- 1h, 4h - For swing trading
- 1d - For position trading

### Understanding the Dashboard

#### VWAP (Most Important!)
- **Price above VWAP** = Buyers in control
- **Price below VWAP** = Sellers in control
- **Repeated rejection** = Ranging market
- **Clean break** = Expansion coming

#### Market Regime
- **🟢 Trending** - ADX > 25, clear direction
  - Best for: Trend following strategies
  - Avoid: Counter-trend trades
  
- **🟡 Ranging** - ADX < 25, tight range
  - Best for: Mean reversion, range trading
  - Avoid: Trend following
  
- **🔴 Volatile** - High ATR percentile
  - Best for: Standing aside or reduced size
  - Avoid: Large positions

#### RSI Interpretation
- **NOT** a direct buy/sell signal
- Shows if move is emotional or controlled
- RSI > 70 + volume spike = emotional buying
- RSI < 30 + volume spike = emotional selling

#### Funding Rates
- **High positive funding** (>0.01%) = Longs overcrowded
  - Possible reversal down
- **High negative funding** (<-0.01%) = Shorts overcrowded
  - Possible short squeeze up
- **Near zero** = Balanced market

## 🚀 Chameleon V7.1: Adaptive Pure Momentum

Chameleon V7.1 is a major upgrade focus on **Pure Momentum** and **Capital Preservation**. It eliminates counter-trend "bleeding" by dynamically disabling mean reversion during strong market breakouts.

### Deployment Guide (V7.1)

#### 1. Configure the Environment
Copy `.env.template` to `.env` and ensure the following flags are set correctly for your stage:

```bash
# Recommended for first 48h (Smoke Test)
PAPER_TRADING=True
LIVE_TRADING_ENABLED=False

# Strategy Setup
ENABLE_MEAN_REVERSION=False
ENABLE_MOMENTUM_BREAKOUT=True

# Assets (Managed in trading_engine/config.py)
# Currently set to 100% BTC ($300 allocation)
```

#### 2. Local Verification
Before zipping for remote deployment, verify the backtest results match your configuration:
```bash
PYTHONPATH=. ./venv/bin/python trading_engine/multi_asset_vbt_backtest.py
```

#### 3. Push to Remote VM
Use the optimized deployment script to package and upload the code:
```bash
./deploy_remote.sh
```

#### 4. Remote Monitoring
Once deployed, monitor the logs on your GCP instance:
```bash
# Connect to VM
gcloud compute ssh crypto-trading-bot --zone=asia-south1-a

# View live logs
tail -f bot/logs/engine.log
```

## 🎯 Phase 2: Live Deployment Workflow
1. **Backtest Selection**: Choose the best performing pair (V7.1: Solo BTC).
2. **Paper Smoke Test**: Run for 48-72 hours on VM with `PAPER_TRADING=True`.
3. **Phased Ramp-up**: (Automated in V7.1) Once `LIVE_TRADING_ENABLED=True`, the engine scales from 25% → 100% budget over 21 days.

## ⚠️ Important Notes

### This is NOT Financial Advice
- Use for educational purposes
- Start with paper trading
- Never risk money you can't afford to lose

### API Rate Limits
- Using public Binance API (no keys needed for market data)
- Automatic rate limiting included
- If you see errors, reduce refresh frequency

### Data Accuracy
- Market data is real-time from Binance
- Small delays possible during high volatility
- Cross-reference with exchange for critical decisions

## 🔧 Configuration

Edit `config.py` to customize:
- Symbols to track
- Indicator periods
- Alert thresholds
- Refresh intervals
- Display preferences

## 📚 Learning Resources

### Key Concepts to Study
1. **VWAP** - Volume Weighted Average Price
2. **Market Regime** - Trending vs Ranging vs Volatile
3. **Funding Rates** - Sentiment in crypto futures
4. **Open Interest** - Total outstanding contracts
5. **ATR** - Average True Range (volatility measure)

### Recommended Reading
- "Trading in the Zone" by Mark Douglas
- "Technical Analysis of Financial Markets" by John Murphy
- Binance Academy for crypto-specific concepts

## 🐛 Troubleshooting

### Dashboard won't start
```bash
# Make sure you're in the right directory
cd crypto-dashboard/dashboard

# Try running with full path
python -m streamlit run app.py
```

### "No module named X" errors
```bash
# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

### Data not loading
- Check your internet connection
- Binance may be temporarily down
- Try a different symbol
- Check Binance status: https://www.binance.com/en/support/announcement

### Slow performance
- Reduce number of candles in sidebar
- Increase refresh interval
- Close other programs using network

## 💡 Pro Tips

1. **Start with BTC** - Most liquid, clearest signals
2. **Use 15m timeframe** - Good balance for learning
3. **Watch VWAP religiously** - Your north star
4. **Respect the regime** - Don't trend-follow in ranging markets
5. **Volume confirms moves** - Price + volume = real move

## 📝 What's Tracked (Backend Data)

Currently collecting:
- ✅ OHLCV (multi-timeframe)
- ✅ Funding rates
- ✅ Open interest
- ✅ Volume analysis
- ⏳ Liquidation data (coming soon)
- ⏳ Order book depth (coming soon)

## 🤝 Contributing

This is a learning project. Feel free to:
- Add new indicators
- Improve visualizations
- Add more exchanges
- Enhance documentation

## 📄 License

MIT License - Free to use and modify

---

Built with ❤️ for learning algorithmic trading

**Remember**: The goal isn't to get rich quick. The goal is to understand markets deeply and build systems that work consistently over time.
