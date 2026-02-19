# Implementation Plan: Crypto Trading Bot Architecture Hardening

This plan outlines the steps to transform the current "Advanced Prototype" into a robust, semi-automated trading system capable of handling real capital with reduced risk.

## Phase 1: Decoupling & Architecture (The Engine Room) ✅ DONE
**Overview:** Successfully separated the monolithic Streamlit app into a dedicated backend `TradingEngine` and a separate frontend dashboard.
**Status:**
- [x] **Create `TradingEngine` (Backend):** Implemented `trading_engine/main.py`. Runs independently.
- [x] **Implement Robust Database:** Created `trading_engine/db.py` (SQLite + WAL). Schema includes `strategies`, `signals`, `trades`.
- [x] **Update Frontend:** Added "🏆 Scoreboard" tab in Dashboard (`app.py`) reading from DB.
- [x] **Verify Loop:** Ran `TrafficLightStrategy` end-to-end. Signals -> DB -> UI confirmed working.

## Phase 1.5: Core Strategy Implementation ✅ DONE
- [x] **Abstract Strategy Class:** Defined in `core/strategy.py`.
- [x] **Traffic Light Strategy:** Implemented `strategies/traffic_light.py` with `on_candle_close` logic (Inside Bar detection).
- [x] **Candle Manager:** Implemented stateful buffer for historical context.

## Phase 2: Risk Management & Execution Safety (The Seatbelt) ✅ DONE

### 2.1 Advanced Order Management ✅
- [x] **Breakout Traps:** Implemented `STOP_MARKET` orders in `Exchange` and tick-based pending checks in `TradingEngine`.
- [x] **Order Database:** Created `orders` table to track PENDING/EXPIRED statuses.

### 2.2 Dynamic Position Sizing ✅
- [x] **Risk-Based Sizing:** Integrated `RiskManager` with $10k balance and 1% risk per trade formula.
- [x] **Context Preservation:** Preserving strategy and signal IDs throughout the pending order lifecycle.

### 2.3 Safety Circuit Breakers ✅
- [x] **Daily Drawdown Limit:** Implemented 3% realized loss lockout (24 hours).
- [x] **Exposure Limit:** Maximum 3 concurrent open trades enforced.
- [x] **Last-Look Validation:** Exchange verifies risk limits immediately before filling pending orders.

### 2.3 Latency & Error Handling
- **Task:** Add robust retries and error handling.
    - Handle `ConnectionError`, `Timeout`, and Exchange API rate limits gracefully (Exponential Backoff).
    - Alerting: Integrate Telegram/Discord/Slack alerts for "Trade Entered," "Stop Loss Hit," or "System Error."

## Phase 3: Strategy Validation (The Lab)

### 3.1 Advanced Backtesting Engine
- **Task:** Expand the `Strategy Lab` tab.
    - ingest months of historical 1-minute/5-minute data.
    - Run `detect_all_signals` across the history.
    - Simulate execution with spread, fees (0.1%), and slippage.
    - Output: Win Rate, Profit Factor, Max Drawdown, Sharpe Ratio.
- **Why:** You simply cannot trade a strategy ("9-20 EMA") without knowing its historical expectancy.

### 3.2 Walk-Forward Analysis
- **Task:** Optimization routine.
    - "Train" on Jan-June data to find best EMA lengths.
    - "Test" on July-Dec data to see if it holds up.
- **Why:** Prevents overfitting (curve fitting).

### 3.3 Strategy "Filters" & Regime Detection 2.0
- **Task:** Refine `StrategyRouter`.
    - **Trend Filter:** Only take EMA crosses if Price > 200 EMA (Longs) or Price < 200 EMA (Shorts).
    - **Volatility Filter:** Don't trade breakout strategies if ATR is extremely low (dead market).
    - **News Filter:** Pause signals 1 hour before major economic events.

## Phase 4: AI & LLM Refinement (The Co-Pilot)

### 4.1 Specialized Agents (vs General LLM)
- **Task:** Instead of one big "Advisory" prompt, create specialized prompts.
    - **Sentiment Agent:** Scrapes Twitter/News for "General Sentiment."
    - **Technical Agent:** Looks purely at price/indicators.
    - **Risk Agent:** Judges if the trade fits risk parameters.
- **Task:** Use smaller, faster models (e.g., Haiku/Flash) for rapid updates, and larger models (Opus/Pro) for daily summaries.

### 4.2 Hallucination Guardrails
- **Task:** Validate LLM output.
    - If LLM says "RSI is 20," verify against the actual calculated RSI. If mismatch, discard LLM output.
    - Force JSON output for all critical decisions.

## Execution Timeline

1.  **Week 1 (Architectural Split):** Build `engine.py` and SQLite DB. Decouple Streamlit.
2.  **Week 2 (Risk & Connectors):** Implement Exchange API connection (CCXT library is good) and OCO orders.
3.  **Week 3 (Backtesting):** Build the robust backtester and optimize the 5 current strategies.
4.  **Week 4 (UI Polish & Alerting):** Re-connect the UI to the DB and set up Telegram alerts.

This plan moves you from a "Dashboard" to a "Quant System."
