# 🧪 48-Hour Smoke Test Checklist

**Objective**: Verify system stability, data connectivity, and strategy logic in a safe "Paper Trading" environment before risking real capital.

## ✅ Phase 1: Immediate Verification (Start Here)
1.  **[ ] Verify Bot Status**
    *   Run `./monitor.sh` in your terminal.
    *   **Success**: Logs stream continuously.
    *   **Fail**: "Container not found" or logs stop immediately.

2.  **[ ] Verify Data Connection**
    *   Check logs for: `✅ Production Engine Started. Monitoring: BTC/USDT, SOL/USDT`.
    *   **Critical**: Ensure NO `Ticker Fetch Error` messages appear.
    *   **Success**: You see lines like `📊 [BTC_MeanRev] Scan | Price: ...` every few minutes.

3.  **[ ] Verify Notifications**
    *   Check Telegram.
    *   **Success**: You received a "🚀 **Startup**" message.
    *   **Success**: You receive a "💓 **Heartbeat**" message every 60 minutes.

## 🔎 Phase 2: Monitoring (First 12 Hours)
4.  **[ ] Check for "Silence"**
    *   If the bot goes silent (no logs for >5 mins), it may have crashed.
    *   Run `./monitor.sh` to check for Python Tracebacks.

5.  **[ ] Valid Signals (Paper Trades)**
    *   Since this is Mean Reversion, trades might be rare (only on dips).
    *   If a trade happens:
        *   **[ ] Telegram Alert**: "🟢 BUY Signal" received?
        *   **[ ] Order Log**: "🚀 LIVE ORDER SENT" (simulated) appears in logs?
        *   **[ ] Order Type**: Verify it says `LIMIT_MAKER` (or treated as LIMIT in Paper Mode).

## 🛡️ Phase 3: Safety Checks (Ongoing)
6.  **[ ] Circuit Breaker Validation**
    *   The bot tracks "Daily PnL". Since it's Paper Mode, this is virtual.
    *   Ensure no "⛔ SECURITY BLOCK" errors appear unless the daily loss limit (-3%) is actually hit.

7.  **[ ] Resource Usage**
    *   Cloud VM should not freeze.
    *   If SSH becomes unresponsive, the bot might be using too much RAM (unlikely with Micro-Live settings).

## 🏁 Phase 4: The "Go Live" Decision (After 48 Hours)
*   **Condition**: Bot ran for 48h with ZERO crashes and correct data scanning.
*   **Action**:
    1.  Edit `config.py`: Set `paper_trading = False`.
    2.  Update `.env` on server: Ensure `LIVE_TRADING_ENABLED=true`.
    3.  Redeploy: `./deploy_remote.sh`.
