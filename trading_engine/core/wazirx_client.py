"""
WazirX REST API Client
Implements authentication (HMAC-SHA256), market data, and trading endpoints
as documented at https://docs.wazirx.com/

Supported security types:
  NONE        — public endpoints (ping, time, klines, tickers)
  MARKET_DATA — requires X-API-KEY header
  TRADE       — requires X-API-KEY header + HMAC-SHA256 signature

Symbol convention on WazirX: lowercase, no slash — e.g. "btcusdt", "solusdt".
The helpers accept both "BTC/USDT" (CCXT-style) and "btcusdt" (native) forms.
"""

import hashlib
import hmac
import logging
import time
from urllib.parse import urlencode

import requests

from trading_engine.config import (
    WAZIRX_API_KEY,
    WAZIRX_API_SECRET,
    WAZIRX_BASE_URL,
    WAZIRX_SETTINGS,
)

logger = logging.getLogger("WazirXClient")

# Interval mapping from CCXT/engine convention → WazirX kline param
_INTERVAL_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "2h": "2h", "4h": "4h", "6h": "6h",
    "12h": "12h", "1d": "1d", "1w": "1w",
}


def _to_wazirx_symbol(symbol: str) -> str:
    """Convert 'BTC/USDT' or 'BTCUSDT' → 'btcusdt'."""
    return symbol.replace("/", "").lower()


class WazirXClient:
    """
    Lightweight WazirX REST client.

    Usage:
        client = WazirXClient()              # uses keys from config / .env
        ticker = client.get_ticker("BTC/USDT")
        klines = client.get_klines("BTC/USDT", interval="15m", limit=100)
        order  = client.create_order("BTC/USDT", "buy", qty=0.001, price=85000)
    """

    # Minimum seconds between consecutive requests (WazirX allows ~1 req/s for most endpoints)
    _MIN_REQUEST_INTERVAL = 1.0
    # Ticker cache TTL in seconds — avoids double-fetching within the same engine tick
    _TICKER_CACHE_TTL = 2.0

    def __init__(self, api_key: str = None, api_secret: str = None):
        self.api_key = api_key or WAZIRX_API_KEY
        self.api_secret = api_secret or WAZIRX_API_SECRET
        self.base_url = WAZIRX_BASE_URL
        self.recv_window = WAZIRX_SETTINGS["recv_window"]
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/x-www-form-urlencoded"})
        self._last_request_time = 0.0  # epoch seconds of last outbound request
        self._ticker_cache: dict[str, tuple[float, dict]] = {}  # symbol → (fetched_at, ticker)

        if self.api_key:
            self.session.headers.update({"X-API-KEY": self.api_key})
            logger.info(f"WazirXClient initialised with API key {self.api_key[:4]}...{self.api_key[-4:]}")
        else:
            logger.info("WazirXClient initialised in public-only mode (no API key)")

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _sign(self, params: dict) -> str:
        """Return HMAC-SHA256 hex signature over the URL-encoded params string."""
        if not self.api_secret:
            raise ValueError("WAZIRX_API_SECRET is not set — cannot sign request.")
        payload = urlencode(params)
        return hmac.new(
            self.api_secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _throttle(self):
        """Sleep if needed to stay within the 1 req/s rate limit."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._MIN_REQUEST_INTERVAL:
            time.sleep(self._MIN_REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def _get(self, path: str, params: dict = None, signed: bool = False) -> dict | list:
        self._throttle()
        params = params or {}
        if signed:
            params["timestamp"] = int(time.time() * 1000)
            params["recvWindow"] = self.recv_window
            params["signature"] = self._sign(params)
        try:
            resp = self.session.get(f"{self.base_url}{path}", params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as e:
            logger.error(f"WazirX GET {path} HTTP error: {e.response.status_code} — {e.response.text}")
            return {}
        except Exception as e:
            logger.error(f"WazirX GET {path} error: {e}")
            return {}

    def _post(self, path: str, params: dict = None) -> dict:
        self._throttle()
        params = params or {}
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = self.recv_window
        params["signature"] = self._sign(params)
        try:
            resp = self.session.post(f"{self.base_url}{path}", data=params, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as e:
            logger.error(f"WazirX POST {path} HTTP error: {e.response.status_code} — {e.response.text}")
            return {}
        except Exception as e:
            logger.error(f"WazirX POST {path} error: {e}")
            return {}

    def _delete(self, path: str, params: dict = None) -> dict:
        self._throttle()
        params = params or {}
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = self.recv_window
        params["signature"] = self._sign(params)
        try:
            resp = self.session.delete(f"{self.base_url}{path}", data=params, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as e:
            logger.error(f"WazirX DELETE {path} HTTP error: {e.response.status_code} — {e.response.text}")
            return {}
        except Exception as e:
            logger.error(f"WazirX DELETE {path} error: {e}")
            return {}

    # ──────────────────────────────────────────────────────────────────────────
    # Public / Market Data endpoints (NONE / MARKET_DATA)
    # ──────────────────────────────────────────────────────────────────────────

    def ping(self) -> bool:
        """Returns True if WazirX API is reachable."""
        result = self._get("/sapi/v1/ping")
        return result == {} or "msg" not in result  # successful ping returns {}

    def get_server_time(self) -> int:
        """Returns server time in milliseconds."""
        data = self._get("/sapi/v1/time")
        return data.get("serverTime", int(time.time() * 1000))

    def get_exchange_info(self) -> dict:
        """Returns exchange metadata including all available symbols."""
        return self._get("/sapi/v1/exchangeInfo")

    def get_system_status(self) -> dict:
        """Returns system status (normal / system maintenance)."""
        return self._get("/sapi/v1/systemStatus")

    def get_ticker(self, symbol: str) -> dict:
        """
        Fetch 24-hour ticker for a single symbol.
        Returns a normalised dict compatible with the rest of the engine:
          { 'last', 'bid', 'ask', 'high', 'low', 'volume', 'quoteVolume',
            'change', 'changePercent', 'symbol' }
        Results are cached for _TICKER_CACHE_TTL seconds to avoid double-fetching
        within the same engine tick.
        """
        now = time.time()
        cached = self._ticker_cache.get(symbol)
        if cached and (now - cached[0]) < self._TICKER_CACHE_TTL:
            return cached[1]

        wx_symbol = _to_wazirx_symbol(symbol)
        raw = self._get("/sapi/v1/ticker/24hr", params={"symbol": wx_symbol})
        if not raw:
            return {}
        result = {
            "symbol": symbol,
            "last": float(raw.get("lastPrice", 0)),
            "bid": float(raw.get("bidPrice", 0)),
            "ask": float(raw.get("askPrice", 0)),
            "high": float(raw.get("highPrice", 0)),
            "low": float(raw.get("lowPrice", 0)),
            "volume": float(raw.get("volume", 0)),
            "quoteVolume": float(raw.get("quoteVolume", 0)),
            "change": float(raw.get("priceChange", 0)),
            "changePercent": float(raw.get("priceChangePercent", 0)),
        }
        self._ticker_cache[symbol] = (now, result)
        return result

    def get_all_tickers(self) -> list[dict]:
        """Fetch 24-hour tickers for all symbols."""
        return self._get("/sapi/v1/tickers/24hr") or []

    def get_klines(self, symbol: str, interval: str = "15m", limit: int = 100) -> list[list]:
        """
        Fetch OHLCV candlestick data.

        Returns a list of [timestamp_ms, open, high, low, close, volume] rows
        — the same shape as CCXT's fetch_ohlcv so the rest of the engine
        (CandleManager, strategies) works without changes.
        """
        wx_symbol = _to_wazirx_symbol(symbol)
        wx_interval = _INTERVAL_MAP.get(interval, interval)
        raw = self._get(
            "/sapi/v1/klines",
            params={"symbol": wx_symbol, "interval": wx_interval, "limit": limit},
        )
        if not raw or not isinstance(raw, list):
            return []
        # WazirX kline row: [openTime, open, high, low, close, volume, closeTime, quoteAssetVolume]
        return [
            [int(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5])]
            for row in raw
        ]

    def get_order_book(self, symbol: str, limit: int = 20) -> dict:
        """Fetch order book depth."""
        wx_symbol = _to_wazirx_symbol(symbol)
        return self._get("/sapi/v1/depth", params={"symbol": wx_symbol, "limit": limit})

    def get_recent_trades(self, symbol: str, limit: int = 50) -> list:
        """Fetch recent public trades."""
        wx_symbol = _to_wazirx_symbol(symbol)
        return self._get("/sapi/v1/trades", params={"symbol": wx_symbol, "limit": limit}) or []

    # ──────────────────────────────────────────────────────────────────────────
    # Account endpoints (TRADE / USER_DATA — require signature)
    # ──────────────────────────────────────────────────────────────────────────

    def get_account(self) -> dict:
        """Returns full account information including balances."""
        return self._get("/sapi/v1/account", signed=True)

    def get_funds(self) -> list[dict]:
        """
        Returns fund balances as a list of dicts:
          [{ 'asset', 'free', 'locked' }, ...]
        """
        data = self._get("/sapi/v1/funds", signed=True)
        if isinstance(data, list):
            return data
        return data.get("balances", [])

    def get_usdt_balance(self) -> float:
        """Convenience: return free USDT balance."""
        for fund in self.get_funds():
            if fund.get("asset", "").upper() == "USDT":
                return float(fund.get("free", 0))
        return 0.0

    # ──────────────────────────────────────────────────────────────────────────
    # Order endpoints
    # ──────────────────────────────────────────────────────────────────────────

    def create_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        order_type: str = "limit",
        stop_price: float = None,
    ) -> dict:
        """
        Place a limit or stop_limit order on WazirX.

        WazirX does NOT support market orders — callers must always supply a price.
        side:       "buy" | "sell"
        order_type: "limit" | "stop_limit"
        stop_price: required when order_type == "stop_limit"

        Returns the raw WazirX order response dict, or {} on failure.
        """
        wx_symbol = _to_wazirx_symbol(symbol)
        params = {
            "symbol": wx_symbol,
            "side": side.lower(),
            "type": order_type.lower(),
            "quantity": qty,
            "price": price,
        }
        if order_type.lower() == "stop_limit":
            if stop_price is None:
                raise ValueError("stop_price is required for stop_limit orders")
            params["stopPrice"] = stop_price

        logger.info(f"WazirX ORDER: {side.upper()} {qty} {symbol} @ {price} ({order_type})")
        return self._post("/sapi/v1/order", params=params)

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        """Cancel an open order by its WazirX order ID."""
        wx_symbol = _to_wazirx_symbol(symbol)
        return self._delete("/sapi/v1/order", params={"symbol": wx_symbol, "orderId": order_id})

    def cancel_all_orders(self, symbol: str) -> dict:
        """Cancel all open orders for a symbol."""
        wx_symbol = _to_wazirx_symbol(symbol)
        return self._delete("/sapi/v1/openOrders", params={"symbol": wx_symbol})

    def get_open_orders(self, symbol: str = None) -> list[dict]:
        """Returns all open orders, optionally filtered by symbol."""
        params = {}
        if symbol:
            params["symbol"] = _to_wazirx_symbol(symbol)
        data = self._get("/sapi/v1/openOrders", params=params, signed=True)
        return data if isinstance(data, list) else []

    def get_all_orders(self, symbol: str, limit: int = 100) -> list[dict]:
        """Returns order history for a symbol."""
        wx_symbol = _to_wazirx_symbol(symbol)
        data = self._get("/sapi/v1/allOrders", params={"symbol": wx_symbol, "limit": limit}, signed=True)
        return data if isinstance(data, list) else []

    def get_my_trades(self, symbol: str, limit: int = 100) -> list[dict]:
        """Returns personal trade history for a symbol."""
        wx_symbol = _to_wazirx_symbol(symbol)
        data = self._get("/sapi/v1/myTrades", params={"symbol": wx_symbol, "limit": limit}, signed=True)
        return data if isinstance(data, list) else []

    # ──────────────────────────────────────────────────────────────────────────
    # WebSocket auth token (needed for private streams)
    # ──────────────────────────────────────────────────────────────────────────

    def create_auth_token(self) -> str:
        """
        Creates a 30-minute WebSocket auth token for private streams.
        Returns the token string, or "" on failure.
        """
        data = self._post("/sapi/v1/create_auth_token")
        token = data.get("auth_key", "")
        if token:
            logger.info("WazirX WebSocket auth token created (valid 30 min).")
        return token
