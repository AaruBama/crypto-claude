import os
import requests
import logging
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

logger = logging.getLogger("Notifier")

def _send(text, parse_mode="Markdown"):
    """Internal sender with error handling."""
    if not TOKEN or not CHAT_ID:
        logger.warning("⚠️ Telegram Notifier not configured. Skipping alert.")
        return False

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": parse_mode
    }

    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code != 200:
            logger.error(f"❌ Telegram Error: {response.text}")
        return True
    except Exception as e:
        logger.error(f"❌ Telegram Connection Failed: {e}")
        return False

def send_alert(message):
    """Generic alert wrapper."""
    return _send(f"⚠️ *SYSTEM ALERT*\n\n{message}")

def send_signal(symbol, side, price, strategy, reason):
    """Notify when a strategy generates a signal (before execution)."""
    icon = "🔵" if side == "BUY" else "🟠"
    msg = (
        f"{icon} *SIGNAL DETECTED: {symbol}*\n"
        f"Side: *{side}*\n"
        f"Price: `${price:,.2f}`\n"
        f"Strategy: `{strategy}`\n"
        f"Trigger: _{reason}_\n"
        f"🕒 _Waiting for execution..._"
    )
    return _send(msg)

def send_trade_entry(symbol, side, price, size, strategy):
    """Notify when an order is filled on exchange."""
    icon = "🚀" if side == "BUY" else "📉"
    msg = (
        f"{icon} *ORDER FILLED: {symbol}*\n"
        f"Side: *{side}*\n"
        f"Price: `${price:,.2f}`\n"
        f"Size: `{size:.4f}`\n"
        f"Strategy: `{strategy}`\n"
        f"⚡ _Position Active_"
    )
    return _send(msg)

def send_trade_exit(symbol, side, price, pnl, roi_pct, reason):
    """Notify when a position is closed."""
    icon = "💰" if pnl > 0 else "🔻"
    outcome = "PROFIT" if pnl > 0 else "LOSS"
    msg = (
        f"{icon} *TRADE CLOSED: {symbol}*\n"
        f"Outcome: *{outcome}*\n"
        f"PnL: `${pnl:+.2f}` ({roi_pct:+.2f}%)\n"
        f"Exit Price: `${price:,.2f}`\n"
        f"Reason: _{reason}_"
    )
    return _send(msg)

def send_heartbeat(status, balance, active_positions, uptime_hours=0, pnl=0.0):
    """Hourly system status report."""
    pnl_icon = "📈" if pnl >= 0 else "📉"
    msg = (
        f"💓 *SYSTEM PULSE*\n"
        f"Status: *{status}*\n"
        f"Uptime: `{uptime_hours:.1f}h`\n"
        f"Balance: `${balance:,.2f}`\n"
        f"PnL (Session): `{pnl:+,.2f}` {pnl_icon}\n"
        f"Positions: `{active_positions}`\n"
        f"Mode: `PRODUCTION`"
    )
    return _send(msg)

if __name__ == "__main__":
    send_heartbeat("ONLINE", 300.0, 0)
