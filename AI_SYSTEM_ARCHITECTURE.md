# 🤖 V7.1 "Chameleon" Trading Engine: System Architecture & Logic Guide

> **Note to AI Agents:** This document contains the comprehensive reference architecture for the V7.1 "Chameleon" Trading Engine. It describes the physical file structure, market logic, execution pathways, and risk protocols. Do not skip components while building context.

---

## 0. Current Production Config (2026-02-20)

**Mode:** Pure Momentum Breakout (Mean Reversion DISABLED by default)

| Metric | Value |
|---|---|
| CAGR | +19.82% |
| Max Drawdown | -0.92% |
| Trades/Year | ~34 |
| Win Rate | 64.71% |
| Profit Factor | 4.44 |
| Calmar Ratio | 21.60 |
| Sharpe Proxy | 1.74 |
| Timeframe | 15m |
| Fee Model | 0.075% + 0.05% slippage |

**A/B Test Conclusion:** Pure momentum outperforms MR-inclusive by ~8% CAGR with 5× lower DD. MR was a consistent ~$30/year drag. Set `ENABLE_MEAN_REVERSION = True` in `config.py` to re-enable for testing.

---

## 1. System Overview

The V7.1 Engine is an **Adaptive Multi-Asset Cryptocurrency Trading Bot** designed to operate on `15m` candle data using Binance via `ccxt`. It is a fully autonomous pipeline featuring real-time data ingestion, dynamic regime classification, backtesting, and Dockerized remote deployment.

**Goal:** Capture ~20% annual PnL through Pure Momentum Breakout strategies with strict conviction filters (engulfing patterns, 3-bar ADX/volume confirmation).

**Target Assets:** `BTC/USDT`, `SOL/USDT`.

---

## 2. Core Execution Loop (`trading_engine/main.py`)

The engine runs a centralized while-loop orchestrating the sequence of events across active strategies:

1. **Heartbeat & Ticker Fetch:** Fetches real-time price from the `Exchange` class.
2. **Candle Construction:** Routes raw ticks to `CandleManager`, which constructs synthetic `15m` candles via a rolling `pandas.DataFrame`.
3. **Indicator Computation:** When a candle closes, `pandas_ta` applies technical indicators (BBands, RSI, ADX, ATR, Z-Score, RVOL, EMA200) entirely in-memory.
4. **Strategy Evaluation:** Passes the fully formed DataFrame to the `AdaptiveStrategy` instance.
5. **Portfolio Conflict Resolution:** (Multi-Asset) Checks for identical trade vectors. Applies a Pearson correlation check.
6. **Risk Analysis:** `RiskManager` evaluates max open positions, daily limits, momentum streak cooldowns, and aggregate USD exposure.
7. **Order Execution:** Dispatches passing signals to the `Exchange` component (Live API or Local Paper Tracker). LIMIT_MAKER orders only.
8. **Logging & Persistence:** Records signals, trades, latencies, and equity states to `db.sqlite` (WAL Mode enabled).

---

## 3. The "Chameleon" Strategy Logic (`adaptive_engine.py`)

The core of V7.1 is the `AdaptiveStrategy` class layered with a `RegimeDetector`.

### A. Regime Detection (`RegimeDetector`)
Calculated at every candle close over a rolling `100-period` lookback window:
*   **Volatility (ATR%) Check:** If current ATR% is >= `95th percentile`, regime is **`CHAOS`** — bot stands down.
*   **Trend (ADX) Check:**
    *   If `ADX > 30` (BTC) / `ADX > 35` (SOL) → **`TRENDING`** → Momentum Breakout
    *   If `ADX <= limit` → **`RANGING`** → Skipped (MR disabled by default)

### B. Trending Mode Protocol: "Momentum Breakout" (PRIMARY)
The production strategy. Fires only when ALL conviction filters align:
*   **Entry Triggers (ALL required):**
    *   Price crosses outside Bollinger Bands in trend direction
    *   **3-bar rising ADX** (ADX > ADX[-1] > ADX[-2])
    *   **3-bar rising volume** (Vol > Vol[-1] > Vol[-2])
    *   **Engulfing candle pattern** (bullish or bearish)
    *   Price on correct side of `EMA_200`
    *   ATR% > 0.4× 50-period average (dead range filter)
*   **Execution Strategy:**
    *   Full budget allocated (40% partial TP, 60% trailing)
    *   Stop Loss: 3.0× ATR from entry
    *   Take Profit: 15× ATR (high target — let trailing stop manage exit)
    *   Trailing offset: 8.0× ATR
*   **Profit Locking:**
    *   At +2× ATR: SL moves to entry + 0.3× ATR (fee buffer)
    *   At +4× ATR: close 25% position, trail remainder at 7× ATR
*   **Pyramid Logic:**
    *   Allow one 20% add-on if new signal fires within 8h and position > +2.5× ATR

### C. Ranging Mode Protocol: "Mean Reversion" (DISABLED by default)
Gated behind `config.ENABLE_MEAN_REVERSION`. Set to `True` to re-enable. When enabled:
*   Fires `PLACE_BATCH` with Tier 1 (50% at BB_Mid) and Tier 2 (50% trailing at BB_Upper)
*   Requires z_score > 3.0, RVOL > 3.0, RSI extremes

---

## 4. Risk & Portfolio Constraints

*   **Momentum Streak Protection:** After 3 consecutive losing momentum trades, entries are paused for 48 hours (`config.MOMENTUM_CONSECUTIVE_LOSS_LIMIT`).
*   **Weekly Compounding:** If weekly PnL > +1.5%, reinvest 50% of weekly returns into momentum budget.
*   **Portfolio Correlation Guard:** If both BTC and SOL trigger Trend Breakout simultaneously with `Pearson Correlation > 0.8`, sizes are cut to 50%.
*   **Micro-Live Limits (`config.py`):** Maximum trade USD exposure caps.
*   **Account Lockout (`risk_manager.py`):** Halts entirely if daily drawdowns breach critical thresholds.

---

## 5. Unified VectorBT Optimization Pipeline

V7.1 features `fast_optimization.py` and `multi_asset_vbt_backtest.py` utilizing **VectorBT**.

*   Data is resampled from 5m → 15m before processing.
*   The VectorBT script models **four independent simulated sub-portfolios per asset:**
    1.  `pf_mr1`: Mean Reversion Tier 1 (disabled when `ENABLE_MEAN_REVERSION = False`)
    2.  `pf_mr2`: Mean Reversion Tier 2 (disabled when `ENABLE_MEAN_REVERSION = False`)
    3.  `pf_trend_tp`: Momentum Breakout — 40% partial TP
    4.  `pf_trend_trail`: Momentum Breakout — 60% trailing
*   Results include CAGR, Calmar, Profit Factor, Sharpe, monthly returns table, and CSV export.

---

## 6. Exchange & Infrastructure Modules

*   **`core/exchange.py`**: Unified wrapper. `paper_mode=True` intercepts orders and simulates fills with realistic fees (0.075%) and slippage (0.05%). LIMIT_MAKER orders enforced for all entries.
*   **`core/candle_manager.py`**: Time-series ring buffer holding `max_size=2000` candles.
*   **`trading_engine/db.py`**: SQLite3 with `PRAGMA journal_mode=WAL` for concurrent reads/writes.
*   **`core/risk_manager.py`**: Includes streak protection, weekly compounding, budget balance, and circuit breaker.

## 7. Operational Notes for Agent Modification
1.  **Do not edit `.py` module file structures that break the `config.py` dependency injections.**
2.  `ENABLE_MEAN_REVERSION` and `ENABLE_MOMENTUM_BREAKOUT` are the master strategy switches.
3.  If testing new indicators, ensure they execute inside the `df.ta` extensions properly.
4.  Deployments are executed via `deploy_remote.sh` (Docker atomic swaps on GCP Debian VM).


