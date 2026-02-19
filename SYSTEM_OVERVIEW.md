# 🤖 Crypto Trading Bot — System Overview
> **Last updated:** February 19, 2026 | **Version:** V5 (Production-Ready Paper Trading)  
> **Account Size:** $300 USDT | **Mode:** Paper Trading (no real orders)

---

## Table of Contents
1. [Architecture Overview](#1-architecture-overview)
2. [Capital Allocation](#2-capital-allocation)
3. [Active Strategies](#3-active-strategies)
   - [BTC Mean Reversion — V5 Precision](#btc-mean-reversion--v5-precision)
   - [SOL Mean Reversion — V5 Asymmetric](#sol-mean-reversion--v5-asymmetric)
   - [Selective Grid Trading](#selective-grid-trading-dormant)
4. [Signal & Entry Logic (Shared)](#4-signal--entry-logic-shared)
5. [Risk Management](#5-risk-management)
6. [Dynamic Config System](#6-dynamic-config-system)
7. [Backtest Results (90 Days)](#7-backtest-results-90-days)
8. [Key Tunable Parameters](#8-key-tunable-parameters)
9. [Operational Checklist](#9-operational-checklist)

---

## 1. Architecture Overview

```
┌────────────────────────────────────────────────────────────────┐
│                        Trading Engine                          │
│                                                                │
│  ┌─────────────┐    ┌──────────────────┐    ┌──────────────┐  │
│  │  Binance    │───▶│  CandleManager   │───▶│  Strategies  │  │
│  │  WebSocket  │    │  (5m buffer,     │    │  (per asset) │  │
│  │  (1m ticks) │    │   500 candles)   │    └──────┬───────┘  │
│  └─────────────┘    └──────────────────┘           │          │
│                                                     ▼          │
│  ┌─────────────┐    ┌──────────────────┐    ┌──────────────┐  │
│  │  Dashboard  │◀───│   RiskManager    │◀───│   Signal     │  │
│  │  (Streamlit)│    │  (pre-trade gate)│    │   Router     │  │
│  └─────────────┘    └──────────────────┘    └──────────────┘  │
│                                                     │          │
│                      ┌──────────────────────────────▼──────┐  │
│                      │          Exchange / Paper Engine      │  │
│                      │  (Binance API or simulated fills)    │  │
│                      └─────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

### Key files
| File | Role |
|------|------|
| `trading_engine/main.py` | Engine entry point, orchestrates all strategies |
| `trading_engine/config.py` | **Single source of truth** for all parameters |
| `trading_engine/strategies/mean_reversion.py` | BTC + SOL strategy logic |
| `trading_engine/strategies/grid_trading.py` | Selective Grid strategy |
| `trading_engine/core/risk_manager.py` | Pre-trade gates, circuit breaker, position sizing |
| `trading_engine/core/candle_manager.py` | Rolling 5m candle buffer |
| `trading_engine/backtest_engine.py` | 90-day multi-asset backtester |
| `dashboard/app.py` | Streamlit real-time dashboard |

---

## 2. Capital Allocation (V6 High-Octane)

```
$300 Total Account (Fully Deployed)
├── $200  →  BTC Mean Reversion   (67% — Core income engine)
└── $100  →  SOL Mean Reversion   (33% — Asymmetric alpha)
```
> **Change in V6:** Removed the $75 cash reserve. Full deployment maximizes returns. "Grid" logic is disabled, so reserve was dead capital.

**Position sizing per trade:** 2% of strategy budget at risk  
- BTC: risk $4.00/trade → larger positions reduce fee impact relative to PnL  
- SOL: risk $2.00/trade

---

## 3. Active Strategies

### BTC Mean Reversion — V6 Precision

**Philosophy:** BTC is highly liquid. V6 adds a **Quality Filter**: we strictly reject any trade where the profit target (BB Mid) is less than **0.50%** away. This eliminates "churn" trades in tight ranges where fees consume the gains.

**Timeframe:** 5-minute candles  
**Direction:** Both — BUY oversold dips, SELL overbought spikes

#### Entry Conditions (ALL must be true)

| Filter | Parameter | Value | Purpose |
|--------|-----------|-------|---------|
| **Bollinger Band** | `bb_std=2.0, bb_period=20` | Price ≤ lower band | Identifies extreme price |
| **RSI** | `rsi_lower=30` | RSI < 30 | Confirms oscillator is oversold |
| **Z-Score** | `z_score=2.5` | &#124;z&#124; > 2.5 | Statistical outlier check |
| **RVOL** | `rvol=1.6x` | Vol > 1.6× avg | Climax move check |
| **Profit Quality** | **`min_profit_pct=0.50`** | **Target > 0.50%** | **V6 Magic:** Skips 35% of low-quality signals. Doubles PnL by avoiding fee churn. |
| **ADX Trend Guard** | `adx_limit=25` | ADX < 25 | Skips strong trends |

> **Note on `adx_must_fall`:** An earlier version required ADX to be falling at entry. This was removed — when price crashes hard enough to trigger the BB/RSI/Z-Score gates, that same crash *pumps* ADX. They are logically antagonistic. The Z-Score threshold alone handles selectivity.

#### Take Profit & Stop Loss
- **Take Profit:** Bollinger Band mid (20-period SMA) — the natural mean-reversion target
- **Stop Loss:** `entry ± (ATR × 1.5)` — 1.5× the 14-period Average True Range
- **Breakeven Protection:** Once trade is 0.6% in profit, SL moves to entry + 0.1% (covers round-trip fees)

#### Backtest Results (90 days, $200 budget)
```
Trades:        41    |  Win Rate:    48.8%
Avg PnL/Trade: $0.31 |  Total Net:  $12.73
Max Drawdown:  -4.5%
```
> **V6 vs V5:** Trades dropped from 64 to 41, but Net PnL **doubled** ($7 vs $12.7). Quality > Quantity.

---

### SOL Mean Reversion — V6 Asymmetric

**Philosophy:** Unchanged from V5, but scaled up to $100 budget.
**Logic:** 3-sigma BB + 3x RVOL + Asymmetric TP (1.5x ATR).

**Timeframe:** 5-minute candles  
**Direction:** Both — BUY capitulation dips, SELL euphoric spikes

#### Entry Conditions (ALL must be true)

| Filter | Parameter | Value | Purpose |
|--------|-----------|-------|---------|
| **Bollinger Band** | `bb_std=3.0, bb_period=20` | Price ≤ **3-sigma** lower band | Only enters on *absolute* panic dips — far rarer than BTC's 2-sigma |
| **RSI** | `rsi_period=14, rsi_lower=25` | RSI < 25 (tighter than BTC's 30) | Must be deeply oversold |
| **RVOL** | `rvol_period=20, threshold=3.0x` | Current volume > 3.0× average | True climax capitulation only — best net P&L per 90-day sweep |
| **ADX Trend Guard** | `adx_limit=25` | ADX < 25 | Same trend filter as BTC |

> **Z-Score disabled for SOL:** The 3-sigma Bollinger Band already guarantees the price is at an extreme statistical outlier. Adding Z-Score would create redundant filtering.

#### Take Profit & Stop Loss — Asymmetric Mode
- **Take Profit:** `max(BB upper band, entry + 1.5 × ATR)` — whichever is *higher*
  - This lets winners run past the mean, all the way to the overbought extreme
  - On the Feb 6 SOL $68→$85 capitulation, this captured a $12.72 win on a $75 budget
- **Stop Loss:** `entry ± (ATR × 1.2)` — *tighter* than BTC (1.2× vs 1.5×)
  - Rationale: At 13% win rate, minimizing loser size is critical. A $0.38 avg loser, even 20 times in a row = -$7.60, easily covered by one good winner ($5.39 avg)

#### Why the math works
```
At 13% WR with 14.3x actual R/R:
  Every 23 trades: 3 winners × $5.39 = $16.17 gross
                  20 losers × $0.38 =  -$7.60 gross
                  Net gross:           +$8.57
                  Fees (23 × ~$0.11):  -$2.57
                  Net after fees:      +$8.61  ✅

Break-even WR at 14.3x R/R = 1 / (1 + 14.3) = 6.5%
Actual WR = 13% = 2× the minimum needed
```

#### Backtest Results (90 days, $100 budget)
```
Trades:        22    |  Win Rate:    13.6%
Avg PnL/Trade: $0.54 |  Total Net:  $11.90
Actual R/R:   14.0x
```
> ⚠️ **Critical caveat:** $8.63 of the $8.63 net P&L came from 3 winners. The Feb 6 SOL crash ($68→$85, +$12.72) was a rare event. With only 3 winners in 90 days, the system needs sustained live monitoring (6+ months) before drawing conclusions. One bad quarter (0-1 winners) would generate a loss.

### 🚫 Rejected Strategy: ETH Mean Reversion
**Tested:** Feb 2026  
**Result:** **-18%** loss in backtesting (100 trades, 22% WR).  
**Reason:** ETH lacks the clean mean-reversion behavior of BTC (too many "fake" reversions that keep dumping) and fails to catch the massive asymmetric bounces of SOL. It combines the worst traits of both for this specific strategy logic. **Do not enable without a complete strategy rewrite.**

### 🚫 Rejected Strategy: Traffic Light V1 (BTC)
**Tested:** Feb 2026 w/ $75 budget  
**Result:** **-2.5%** loss (-$1.91). 30% WR on 10 trades.  
**Reason:** Breakout logic conflicts with Mean Reversion logic on the same asset (13 "Asset Guard" blocks). Low win rate plus modest R/R (1.5) leads to negative expectancy. Distracts from the profitable MeanRev core. **Disabled.**

---

### Selective Grid Trading (DISABLED)
**Tested:** Feb 2026 w/ $75 budget  
**Result:** **Not Viable** for $300 account size.  
**Backtest:** -$4.04 loss + 64 "Asset Guard" blocks (prevented profitable MeanRev trades).  
**Conclusion:** Grid and MeanRev strategies conflict when trading the same asset with tight position limits (< 5 positions). Grid requires a dedicated sub-account or larger capital to run without cannibalizing the main strategy. **Kept in code but disabled in config.**

---

## 4. Signal & Entry Logic (Shared)

### Candle Flow
```
Exchange (1m tick) ──▶ CandleManager.add_candle()
                              │
               Every 5m candle close:
                              ▼
                  strategy.on_candle_close(cm)
                              │
                    ┌─────────┴─────────┐
                    │  Calculate:        │
                    │  • BB (pandas_ta)  │
                    │  • RSI (pandas_ta) │
                    │  • ADX (pandas_ta) │
                    │  • ATR (pandas_ta) │
                    │  • RVOL (manual)   │
                    │  • Z-Score (numpy) │
                    └─────────┬─────────┘
                              │
                  Apply filters in order:
                  1. Bar count sufficient?
                  2. ADX < limit? (trend guard)
                  3. Price outside BB?
                  4. RSI extreme?
                  5. Z-Score extreme? (BTC only)
                  6. RVOL spike present?
                              │
                         Signal dict ──▶ RiskManager ──▶ Exchange
```

### Signal Dictionary Structure
```python
{
    "side": "BUY" | "SELL",
    "price": float,          # Entry price
    "sl": float,             # Stop loss price
    "tp": float,             # Take profit price
    "order_type": "MARKET",
    "reason": str,           # Human-readable reason (logged/displayed)
    "metadata": {
        "adx": float,
        "rsi": float,
        "rvol": float,
        "z_score": float,    # BTC only
        "adx_falling": bool,
    }
}
```

### Scan Log (every 2 min, regardless of signal)
```
📊 [BTC_MeanRev] Scan | Price: 67508.75 | RSI: 28.4 | ADX: 18.2↓ | Z: -2.61 | RVOL: 1.73x
```

---

## 5. Risk Management

All trades pass through `RiskManager.check_trade_allowed()` which runs 5 sequential gates:

### Gate 1: Circuit Breaker (Lockout)
- If daily realized P&L < **-3.0%** of starting day balance → **24-hour lockout**
- All pending orders cancelled during lockout
- Resets automatically after 24h

### Gate 2: Position Limit
- Max **5 open positions** simultaneously (2 strategies × up to 2 positions + 1 buffer)

### Gate 3: Micro-Live Exposure Cap
- Max total notional exposure: **$225** (75% of $300)
- Prevents over-leveraging even if multiple signals fire simultaneously

### Gate 4: Break-Even Filter
- Requires TP target to be at least **0.30%** away from entry
- Prevents entering trades where fees would consume all potential profit

### Gate 5: Budget Balance (Strategy Isolation)
- Each strategy has a reserved budget
- Prevents BTC strategy from consuming SOL's capital and vice versa
- Grid budget ($75) is separately reserved when active

### Breakeven Protection (Post-Entry)
- **Trigger:** Trade moves 0.6% in profit
- **Action:** SL moves to entry + 0.1% (locks in enough to cover round-trip fees)
- Shown in backtest as `breakeven_moved: True` in trade reports

### Fee Structure
| Component | Rate | Notes |
|-----------|------|-------|
| Exchange fee | 0.075% | Binance with BNB discount applied |
| Slippage | 0.05% | Applied in backtest to both entry and exit |
| Tax buffer | 1.0% | Applied to winning trades only (TDS estimate) |
| **Effective round-trip** | **~0.20–0.25%** | Entry fee + exit fee + slippage |

---

## 6. Dynamic Config System

Everything is controlled from a **single file:** `trading_engine/config.py`

### Quick Reference — All Tunable Parameters

#### `ENGINE_SETTINGS`
```python
"paper_trading": True         # ← Flip to False ONLY for live trading
"LIVE_TRADING_ENABLED": False # ← Second safety gate for live
"VOL_SPIKE_THRESHOLD": 1.5    # Global RVOL default (overridden per-strategy)
"Z_SCORE_THRESHOLD": 2.2      # Global Z-Score default (overridden per-strategy)
```

#### `RISK_SETTINGS`
```python
"max_drawdown_daily": 2.5     # % daily loss before circuit breaker fires
"max_open_positions": 5       # Hard cap on concurrent open positions
"fee_rate": 0.00075           # Binance fee (0.075% with BNB discount)
"tax_rate": 0.01              # 1% tax buffer on profits
"slippage_penalty": 0.0005    # Simulated slippage per side
```

#### `BREAKEVEN_PROTECTION`
```python
"enabled": True
"trigger_pct": 0.6            # Move SL when 0.6% in profit
"sl_buffer_pct": 0.1          # New SL = entry + 0.1%
```

#### `LIVE_ALLOCATION` — Capital Split
```python
"BTC_MeanRev": {"budget": 150.0}   # $150 to BTC strategy
"SOL_MeanRev": {"budget":  75.0}   # $75 to SOL strategy
"USDT_Reserve": {"budget":  75.0}  # $75 held as cash (for Grid)
```

#### BTC Strategy Params (`STRATEGIES["MEAN_REVERSION"]`)
```python
"bb_period": 20, "bb_std": 2.0       # 2-sigma Bollinger Band
"rsi_lower": 30, "rsi_upper": 70     # RSI thresholds
"adx_limit": 25                       # Max ADX before skipping
"sl_atr_mult": 1.5                    # SL = entry ± 1.5 × ATR
"tp_target_pct": 0                    # Use BB-mid (set > 0 to add floor)
"tp_atr_mult": 0.0                    # Disabled — BTC uses BB-mid
"rvol_threshold": 1.6                 # 1.6× avg volume required
"z_score_threshold": 2.5              # ★ KEY: only enters top 0.6% extremes
"adx_must_fall": False                # Intentionally off (logically conflicts)
```

#### SOL Strategy Params (`STRATEGIES["MEAN_REVERSION_SOL"]`)
```python
"bb_period": 20, "bb_std": 3.0       # 3-sigma BB — much rarer entries
"rsi_lower": 25, "rsi_upper": 75     # Tighter RSI thresholds
"adx_limit": 25
"sl_atr_mult": 1.2                    # ★ Tight SL — minimize losers
"tp_target_pct": 0
"tp_atr_mult": 1.5                    # ★ KEY: TP = max(BB upper, entry + 1.5×ATR)
"rvol_threshold": 3.0                 # 3.0× — true capitulation only
"z_score_threshold": 0.0              # Disabled — 3-sigma BB is sufficient
"adx_must_fall": False
```

### How to Tune

| Goal | Parameter to Change |
|------|--------------------|
| Fewer BTC trades | Raise `z_score_threshold` (2.5→2.8) |
| More BTC trades | Lower `z_score_threshold` (2.5→2.2) or `rvol_threshold` |
| Bigger SOL winners | Raise `tp_atr_mult` (1.5→2.0) |
| Smaller SOL losses | Lower `sl_atr_mult` (1.2→1.0) |
| Fewer SOL entries | Raise `rvol_threshold` (3.0→3.5) or `bb_std` (3.0→3.5) |
| Activate Grid | Set `SELECTIVE_GRID["enabled"] = True` |
| Go live | Set `paper_trading: False`, `LIVE_TRADING_ENABLED: True` |

---

## 7. Backtest Results (90 Days - V6 Final)

**Period:** Nov 20, 2025 → Feb 17, 2026  
**Config:** V6 ($200 BTC / $100 SOL / MinProfit 0.5%)

### Portfolio Summary
```
Initial Balance:    $300.00
Final Balance:      $316.85
Net P&L:            +$16.85  (+5.6% return in 90 days → ~24% annualized)
Max Drawdown:       -4.58%   (Improved from -4.65%)
Sharpe Proxy:       5.6% / 4.58% = 1.22

Total Trades:       63      (Reduced from 87)
Avg Net PnL/Trade:  $0.39   (4.8x improvement vs $0.08)
Total Fees:         $15.59
```

### Notable Trades
| Date | Asset | Side | Entry | Exit | Net P&L | Note |
|------|-------|------|-------|------|---------|------|
| Feb 6, 2026 | SOL | BUY | $68.12 | $84.91 | **+$16.96** | Sized up winner |
| Dec 15, 2025 | BTC | BUY | $88,107 | $86,991 | **-$2.69** | Max loss (managed) |

### Optimization History
| Version | Change | Result (90d) |
|---------|--------|--------------|
| V5 Core | $150/$75/$75 Res | +$7.22 (+2.4%) |
| V5.1 ETH | Added ETH ($75) | -$12.81 (Loss) |
| V5.2 Grid | Added Grid ($75) | -$0.12 (Breakeven) |
| **V6 Final** | **Full Deploy ($200/$100) + Quality Filter (0.5%)** | **+$16.85 (+5.6%) 🚀** |

---

## 8. Key Tunable Parameters

### Critical Numbers to Know

| Number | What it means |
|--------|--------------|
| **0.50%** | **Minimum Profit Target** — The most important new number. If potential gain < 0.5%, we pass. |
| **2.5** | BTC Z-Score — Statistical entry trigger. |
| **1.6×** | BTC RVOL — Volume confirmation. |
| **3.0σ** | SOL BB — Extreme entry trigger. |
| **$200** | BTC Capital Allocation |
| **$100** | SOL Capital Allocation |

---

## 9. Operational Checklist

### Daily (takes < 2 min)
- [ ] Check `engine.log` for circuit breaker trips or error patterns
- [ ] Review dashboard equity curve — any unusual spikes?
- [ ] Confirm both strategies are actively scanning (log shows 📊 Scan lines)

### Weekly
- [ ] Export `data/backtests/trade_report.csv` and review win/loss distribution
- [ ] Check if recent SOL trades are hitting SL or TP (confirms logic is working)
- [ ] Consider if market regime has shifted (if ADX consistently > 25, BTC trades dry up — expected)

### Before Activating Grid (Checklist)
- [ ] Open 4H BTC chart — is there a clear horizontal channel?
- [ ] Check 1D ADX — is it below 20?
- [ ] Check economic calendar — no major events next 24h?
- [ ] Set `SELECTIVE_GRID["enabled"] = True` in `config.py`
- [ ] Restart engine

### Before Going Live (Paper → Real)
- [ ] Complete minimum 30 days of paper trading with no critical errors
- [ ] Verify Binance API key has **Trade** permission (not withdrawal)
- [ ] Set `paper_trading: False` AND `LIVE_TRADING_ENABLED: True` in `config.py`
- [ ] Start with reduced position sizing (lower budgets by 50%) for first 2 weeks
- [ ] Confirm circuit breaker is working by checking daily P&L resets

---

## Appendix: Terminology

| Term | Definition |
|------|-----------|
| **Bollinger Band (BB)** | Price channel = 20-SMA ± N×std. Price outside = statistically rare |
| **RSI** | Relative Strength Index. < 30 = oversold, > 70 = overbought |
| **ADX** | Average Directional Index. < 20 = ranging, > 25 = trending |
| **ATR** | Average True Range. Measures recent volatility in price units |
| **RVOL** | Relative Volume = current bar volume ÷ N-bar average volume |
| **Z-Score** | Standard deviations from mean: `z = (price - mean) / std` |
| **Capitulation** | A sharp, high-volume sell-off where all remaining holders give up |
| **Mean Reversion** | Tendency of price to return toward its average after extreme moves |
| **R/R** | Risk/Reward ratio = (TP - entry) ÷ (entry - SL) |
| **Asymmetric TP** | TP target that is much larger than the SL, allowing rare big winners to compensate many small losers |
| **RVOL Climax** | A candle with >3× average volume — indicates a washout/blowoff |
| **Circuit Breaker** | Automatic 24h trading halt when daily losses exceed threshold |
| **Breakeven Protection** | Moving SL to entry once a trade is in profit by a set amount |
| **Asset Guard** | Prevents two strategies from holding the same asset simultaneously |
