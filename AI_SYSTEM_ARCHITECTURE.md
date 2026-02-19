# 🤖 V7 "Chameleon" Trading Engine: System Architecture & Logic Guide

> **Note to AI Agents:** This document contains the comprehensive reference architecture for the V7 "Chameleon" Trading Engine. It describes the physical file structure, market logic, execution pathways, and risk protocols. Do not skip components while building context.

---

## 1. System Overview

The V7 Engine is an **Adaptive Multi-Asset Cryptocurency Trading Bot** designed to operate natively on `1m` and `5m` tick data using Binance via `ccxt`. It is a fully autonomous pipeline featuring real-time data ingestion, dynamic regime classification, backtesting, and Dockerized remote deployment.

**Goal:** Capture 25%+ annual PnL by toggling between Mean Reversion (Ranging markets) and Momentum Breakout (Trending markets) based on continuous mathematically derived market state classifications.

**Target Assets:** `BTC/USDT`, `SOL/USDT`.

---

## 2. Core Execution Loop (`trading_engine/main.py`)

The engine runs a centralized while-loop orchestrating the sequence of events across active strategies:

1. **Heartbeat & Ticker Fetch:** Fetches real-time price from the `Exchange` class.
2. **Candle Construction:** Routes raw ticks to `CandleManager`, which constructs synthetic `1m` or `5m` candles via a rolling `pandas.DataFrame`.
3. **Indicator Computation:** When a candle closes, `pandas_ta` applies technical indicators (BBands, RSI, ADX, ATR, Z-Score, RVOL) entirely in-memory.
4. **Strategy Evaluation:** Passes the fully formed DataFrame to the `AdaptiveStrategy` instance.
5. **Portfolio Conflict Resolution:** (Multi-Asset) Checks for identical trade vectors (e.g., both BTC and SOL triggering trend signals). Applies a Pearson correlation check.
6. **Risk Analysis:** `RiskManager` evaluates max open positions, maximum daily limits, and aggregate USD exposure.
7. **Order Execution:** Dispatches passing signals to the `Exchange` component (Live API or Local Paper Tracker).
8. **Logging & Persistence:** Records signals, trades, latencies, and equity states to `db.sqlite` (WAL Mode enabled).

---

## 3. The "Chameleon" Strategy Logic (`adaptive_engine.py`)

The core of V7 is the `AdaptiveStrategy` class layered with a `RegimeDetector`. The system does not lock into one trading philosophy.

### A. Regime Detection (`RegimeDetector`)
Calculated at every candle close over a rolling `100-period` lookback window:
*   **Volatility (ATR%) Check:** Calculates `ATR / Close_Price`. If the current value is >= the `95th percentile` (chaos threshold), the regime is **`CHAOS`**. The bot stands down to protect capital during flash-crashes.
*   **Trend (ADX) Check:** Calculates the Average Directional Index (ADX). 
    *   If `ADX > 25`, the regime is **`TRENDING`**.
    *   If `ADX <= 25`, the regime is **`RANGING`**.

### B. Ranging Mode Protocol: "Mean Reversion"
If `RANGING` is active, the engine attempts to fade the extremes of the Bollinger Bands using strict filters.
*   **Entry Triggers:**
    *   Price touches or breaches Bollinger Band Outer Layers (`BB_Lower` / `BB_Upper`).
    *   `RSI` is extreme (`< 30` or `> 70`).
    *   **Z-Score** distance from the mean is critical (`|Z| > 2.5`).
    *   **Relative Volume (RVOL):** Spiked `> 2.5x` the 20-period moving average.
*   **Execution Strategy:**
    *   Fires a `PLACE_BATCH` signal splitting the trade into **Tier 1 (50%)** and **Tier 2 (50%)**.
    *   **Tier 1:** Standard Take Profit at `BB_Mid` and Stop Loss at `1.5x ATR`.
    *   **Tier 2:** Trailing Stop Loss activated at `3.0x ATR` for catching runners.

### C. Trending Mode Protocol: "Momentum Breakout"
If `TRENDING` is active, the engine pivots to ride momentum using wide trailing stops.
*   **Entry Triggers:**
    *   Price crosses outside the Bollinger Bands in the direction of the trend.
    *   `ADX` must be rising (`ADX(current) > ADX(previous)`).
    *   **Macro Filter:** Price must be on the favorable side of the `EMA_200`. This prevents getting whip-sawed by fake 5-minute breakouts during larger macroeconomic downtrends.
*   **Execution Strategy:**
    *   Executes full size (100% budget).
    *   Utilizes a "Fat Tail" **`10.0x ATR`** Trailing Stop Loss. It never hits a hard Take Profit; it simply lets the trend ride until momentum entirely collapses.

---

## 4. Risk & Portfolio Constraints

*   **Portfolio Correlation Guard:** If *both* BTC and SOL trigger a Trend Breakout signal simultaneously, the engine calculates the `.corrcoef()` on their last 100 close prices. If `Pearson Correlation > 0.8`, the sizes for *both* trades are sliced by **`50%`**. This prevents the portfolio from becoming double-leveraged against a highly correlated macro flash dump.
*   **Micro-Live Limits (`config.py`):** Maximum trade USD exposure caps protect the underlying balance during Paper Trading or tiny Live Deployments.
*   **Account Lockout (`risk_manager.py`):** Includes mechanisms to halt entirely if daily drawdowns breach critical thresholds.

---

## 5. Unified VectorBT Optimization Pipeline

Instead of standard iterative looping, V7 features `fast_optimization.py` and `multi_asset_vbt_backtest.py` utilizing **VectorBT**.

*   VectorBT processes 100k+ rows simultaneously via NumPy matrix broadcasting.
*   Since the V7 Adaptive Strategy splits trades dynamically, the VectorBT script models **three independent simulated portfolios per asset**:
    1.  `pf_mr1`: Mean Reversion Tier 1
    2.  `pf_mr2`: Mean Reversion Tier 2
    3.  `pf_trend`: Momentum Breakout
*   The results are aggregated natively (`pf_mr1.total_profit() + pf_mr2.total_profit() + pf_trend.total_profit()`) to provide instantaneous 365-day PnL feedback for complex grid hyper-parameters without waiting 45 minutes for pandas iterations.

---

## 6. Exchange & Infrastructure Modules

*   **`core/exchange.py`**: A unified wrapper. When `paper_mode=False`, it passes CCXT execution payloads to Binance. When `paper_mode=True`, it intercepts the orders, holds them in memory (`self.pending_orders`), and mathematically models triggered limit slices and SL/TP triggers using real-time price action without incurring actual exchange risks.
*   **`core/candle_manager.py`**: A time-series ring buffer. Holds strict sizes (`max_size=2000`) of candles. Handles mapping raw ticks safely onto OHLC structures.
*   **`trading_engine/db.py`**: SQLite3 database leveraging `PRAGMA journal_mode=WAL` to allow simultaneous reads from the dashboard API and high-speed writes from the trading engine thread without locking collisions.

## 7. Operational Notes for Agent Modification
1.  **Do not edit `.py` module file structures that break the `config.py` dependency injections.** Engine modules rely heavily on globally injected dict states from `config`.
2.  If testing new indicators, ensure they execute inside the `df.ta` extensions properly in both `candle_manager` and the VectorBT simulacra.
3.  Deployments are executed via `deploy_remote.sh`, which zips the repo and forces Docker atomic swaps via a temporary swap directory with root `sudo` commands on a GCP Debian VM.
