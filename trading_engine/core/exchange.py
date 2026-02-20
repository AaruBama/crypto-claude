
"""
Basic Exchange Wrapper (Paper Trading by Default)
Simulates order placement and execution.
Now supports real data fetching via CCXT (Binance) or the native WazirX client.

Set ACTIVE_EXCHANGE=wazirx in .env to route all live trading through WazirX.
Binance remains the default so existing setups are unaffected.
"""
import ccxt
import time
import logging
from trading_engine.config import (
    ENGINE_SETTINGS, API_KEY, API_SECRET,
    ACTIVE_EXCHANGE, WAZIRX_API_KEY, WAZIRX_SETTINGS,
)

logger = logging.getLogger("Exchange")

class Exchange:
    def __init__(self, paper_mode=True, risk_manager=None):
        self.paper = paper_mode
        self.live_enabled = ENGINE_SETTINGS.get("LIVE_TRADING_ENABLED", False)
        self.balance = 300.0 if paper_mode else 0.0
        self.risk_manager = risk_manager
        self.pending_orders = []  # List of dicts: {id, symbol, side, qty, price, type, timestamp, expiry}
        self.active_positions = [] # List of dicts: {trade_id, symbol, side, qty, entry_price, sl, tp, strategy_id, signal_id}
        self.signal_timestamps = {} # {signal_id: start_ms}

        self.exchange_name = ACTIVE_EXCHANGE  # "binance" | "wazirx"

        if self.exchange_name == "wazirx":
            self._init_wazirx(paper_mode)
        else:
            self._init_binance(paper_mode)

    # ──────────────────────────────────────────────────────────────────────────
    # Initialisation helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _init_binance(self, paper_mode):
        """Set up the CCXT Binance client (original behaviour)."""
        ccxt_config = {
            'enableRateLimit': True,
            'timeout': 15000,
        }
        if API_KEY and len(str(API_KEY)) > 5:
            logger.info(f"🔑 Binance API Key: {API_KEY[:4]}...{API_KEY[-4:]}")
            ccxt_config['apiKey'] = API_KEY
            ccxt_config['secret'] = API_SECRET
        else:
            logger.info("🌍 Binance: No API Key — Public Mode")

        self.client = ccxt.binance(ccxt_config)
        self.wazirx = None
        self.markets = {}

        if not paper_mode:
            self._connect_api()
            try:
                self.markets = self.client.load_markets()
                logger.info(f"📦 Loaded {len(self.markets)} Binance markets.")
            except Exception as e:
                logger.error(f"⚠️ Failed to load Binance markets: {e}")

            if self.live_enabled:
                logger.warning("🚨 WARNING: LIVE TRADING IS ENABLED (Binance). Real orders will be sent.")
            else:
                logger.info("🛡️ SAFE MODE: Live trading disabled. Paper trading only.")
        else:
            logger.info("🔌 Binance — Paper Mode: TRUE, Data: REAL")

    def _init_wazirx(self, paper_mode):
        """Set up the native WazirX client."""
        from trading_engine.core.wazirx_client import WazirXClient
        self.wazirx = WazirXClient()
        self.client = None   # No CCXT client for WazirX
        self.markets = {}

        if not paper_mode:
            if not WAZIRX_API_KEY:
                logger.error("❌ WAZIRX_API_KEY not set — cannot use live WazirX trading.")
            else:
                # Verify connectivity
                if self.wazirx.ping():
                    logger.info("✅ WazirX API reachable.")
                else:
                    logger.warning("⚠️ WazirX ping failed — check connectivity.")

                # Load account to confirm auth works
                try:
                    account = self.wazirx.get_account()
                    if account:
                        logger.info("🔑 WazirX account authenticated successfully.")
                except Exception as e:
                    logger.error(f"⚠️ WazirX account check failed: {e}")

                if self.live_enabled:
                    logger.warning("🚨 WARNING: LIVE TRADING IS ENABLED (WazirX). Real orders will be sent.")
                else:
                    logger.info("🛡️ SAFE MODE: Live trading disabled. Paper trading only.")
        else:
            logger.info("🔌 WazirX — Paper Mode: TRUE, Data: REAL")

    def quantize_amount(self, symbol, amount):
        """
        Adjusts amount to respect exchange precision and LOT_SIZE.
        For WazirX, falls back to 6 decimal places (no CCXT helper available).
        """
        if self.exchange_name == "wazirx":
            return round(amount, 6)

        if not self.markets or symbol not in self.markets:
            return round(amount, 6)
        return float(self.client.amount_to_precision(symbol, amount))

    def _connect_api(self):
        """Connects to Binance API using ccxt."""
        if not API_KEY:
            print("❌ WARNING: No Binance API Key found.")
        print("🔌 Connected to Exchange (Binance, Paper: False)")

    def get_ticker(self, symbol="BTC/USDT"):
        """
        Fetches the full ticker object from the active exchange.
        Returns a normalised dict with at least a 'last' key.
        """
        try:
            if self.exchange_name == "wazirx":
                return self.wazirx.get_ticker(symbol)
            return self.client.fetch_ticker(symbol)
        except Exception as e:
            logger.error(f"Ticker Fetch Error ({self.exchange_name}): {e}")
            return None

    def get_latest_price(self, symbol="BTC/USDT"):
        """
        Fetches the latest price from the active exchange.
        """
        try:
            ticker = self.get_ticker(symbol)
            return float(ticker['last']) if ticker else 65000.0
        except Exception:
            return 65000.0  # Fallback

    def fetch_ohlcv(self, symbol, timeframe=None, limit=100):
        """
        Fetch OHLCV candles from the active exchange.
        Returns list of [timestamp_ms, open, high, low, close, volume].
        Used by _preload_data and _on_candle_close in main.py via self.exchange.client.fetch_ohlcv —
        this method provides a unified interface so callers can use either exchange.
        """
        tf = timeframe or ENGINE_SETTINGS.get("timeframe", "15m")
        if self.exchange_name == "wazirx":
            return self.wazirx.get_klines(symbol, interval=tf, limit=limit)
        return self.client.fetch_ohlcv(symbol, timeframe=tf, limit=limit)
        
    def create_order(self, symbol, side, qty, price=None, order_type="MARKET", stop_loss=None, take_profit=None, expiry_seconds=300, strategy_id="Unknown", signal_id=None):
        """
        Unified order entry point for both paper and live modes.
        Handles MARKET, LIMIT, and STOP_MARKET order types.
        Returns order_id string on success, None on failure.
        """
        import uuid
        import time
        from datetime import datetime
        order_id = f"paper_{uuid.uuid4().hex[:8]}"
        start_time_ms = int(time.time() * 1000)
        
        if signal_id:
            self.signal_timestamps[signal_id] = start_time_ms

        if self.paper:
            # --- LIMIT & STOP ORDERS: Queue as Pending ---
            # Treat LIMIT_MAKER as LIMIT for paper trading simulation
            if order_type in ("LIMIT", "STOP_MARKET", "LIMIT_MAKER"):
                logger.info(f"[{strategy_id}] ⏳ PENDING {order_type}: {side} {qty:.6f} {symbol} @ {price:.2f}")
                self.pending_orders.append({
                    "id": order_id,
                    "symbol": symbol,
                    "side": side,
                    "qty": qty,
                    "trigger_price": price,
                    "price": price,
                    "type": order_type,
                    "status": "PENDING",
                    "timestamp": datetime.now(),
                    "expiry": datetime.now().timestamp() + expiry_seconds,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "strategy_id": strategy_id,
                    "signal_id": signal_id,
                    "start_time_ms": start_time_ms
                })
                return order_id

            # --- MARKET ORDERS: Instant Simulated Fill ---
            else:
                avg_price = price if price else self.get_latest_price(symbol)
                latency = int(time.time() * 1000) - start_time_ms
                logger.info(f"[{strategy_id}] 📝 PAPER FILL: {side} {qty:.6f} {symbol} @ {avg_price:.2f} (latency: {latency}ms)")
                
                position = {
                    "id": order_id,
                    "symbol": symbol,
                    "side": side,
                    "qty": qty,
                    "entry_price": avg_price,
                    "sl": stop_loss,
                    "tp": take_profit,
                    "strategy_id": strategy_id,
                    "signal_id": signal_id
                }
                self.active_positions.append(position)
                return order_id

        else:
            # --- LIVE TRADING SAFETY CHECK ---
            if not self.live_enabled:
                raise Exception("⛔ SECURITY BLOCK: LIVE_TRADING_ENABLED is False!")

            if self.exchange_name == "wazirx":
                return self._live_order_wazirx(symbol, side, qty, price, order_type, stop_loss)
            else:
                return self._live_order_binance(symbol, side, qty, price, order_type)

    def _live_order_wazirx(self, symbol, side, qty, price, order_type, stop_loss=None):
        """
        Execute a live order on WazirX.
        WazirX only supports LIMIT and STOP_LIMIT orders — no MARKET type.
        LIMIT_MAKER is treated as a regular LIMIT (WazirX has no postOnly flag).
        """
        if price is None:
            # WazirX has no market orders — fall back to last price
            price = self.get_latest_price(symbol)
            logger.warning(f"⚠️ WazirX: No price supplied for {order_type} order — using last price {price}")

        wx_type = "limit"
        wx_stop = None
        if order_type in ("STOP_MARKET", "STOP_LIMIT"):
            wx_type = "stop_limit"
            wx_stop = stop_loss or price  # Use SL price as the stop trigger

        try:
            response = self.wazirx.create_order(
                symbol=symbol,
                side=side,
                qty=qty,
                price=price,
                order_type=wx_type,
                stop_price=wx_stop,
            )
            if response and response.get("id"):
                logger.info(f"🚀 WAZIRX LIVE ORDER SENT: {side} {qty} {symbol} @ {price} | ID: {response['id']}")
                return str(response["id"])
            else:
                logger.error(f"❌ WazirX order failed: {response}")
                return None
        except Exception as e:
            logger.error(f"❌ WazirX LIVE EXECUTION FAILED: {e}")
            return None

    def _live_order_binance(self, symbol, side, qty, price, order_type):
        """Execute a live order on Binance via CCXT (original logic)."""
        try:
            ccxt_type = "market"
            params = {}

            if order_type == "LIMIT":
                ccxt_type = "limit"
                params['timeInForce'] = 'GTC'
            elif order_type == "LIMIT_MAKER":
                ccxt_type = "limit"
                params['postOnly'] = True
                params['timeInForce'] = 'GTC'

            last_error = None
            max_retries = 3 if order_type == "LIMIT_MAKER" else 1

            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        logger.info(f"⏳ Waiting 5s before retry {attempt+1}/{max_retries}...")
                        time.sleep(5)
                        ticker = self.client.fetch_ticker(symbol)
                        price = ticker['bid'] if side.lower() == 'buy' else ticker['ask']
                        logger.info(f"♻️ RETRY {attempt+1}: Updated {side} Limit Price to {price}")

                    response = self.client.create_order(
                        symbol=symbol,
                        type=ccxt_type,
                        side=side.lower(),
                        amount=qty,
                        price=price if "limit" in ccxt_type else None,
                        params=params
                    )
                    log_msg = f"🚀 BINANCE LIVE ORDER SENT: {side} {qty} {symbol}"
                    if "limit" in ccxt_type:
                        log_msg += f" @ {price}"
                    logger.info(log_msg)
                    return str(response['id'])

                except (ccxt.OrderImmediatelyFillable, ccxt.ExchangeError) as e:
                    if order_type == "LIMIT_MAKER" and ("PostOnly" in str(e) or "OrderImmediatelyFillable" in str(e)):
                        logger.warning("⚠️ LIMIT_MAKER Rejected (Price moved). Retrying...")
                        last_error = e
                        continue
                    else:
                        raise e

            if last_error:
                logger.error(f"❌ BINANCE LIVE EXECUTION FAILED after retries: {last_error}")
                return None

        except Exception as e:
            logger.error(f"❌ BINANCE LIVE EXECUTION FAILED: {e}")
            return None

    # Backwards-compat alias
    def place_order(self, symbol, side, qty, price=None, type="MARKET", **kwargs):
        return self.create_order(symbol, side, qty, price=price, order_type=type, **kwargs)


    def check_pending_orders(self, current_price, symbol_filter=None):
        """
        Checks pending orders against current price.
        Returns (filled_orders, expired_orders)
        """
        from datetime import datetime
        filled_orders = []
        expired_orders = []
        active_orders = []
        
        now = datetime.now().timestamp()
        
        for order in self.pending_orders:
            # Multi-Asset Filter
            if symbol_filter and order['symbol'] != symbol_filter:
                active_orders.append(order)
                continue

            # Check Expiry
            # Check Expiry
            if now > order['expiry']:
                logger.info(f"🗑️ Order Expired: {order['id']} ({order['side']} @ {order['trigger_price']})")
                order['status'] = "EXPIRED"
                expired_orders.append(order)
                continue
            
            triggered = False
            
            # BUY STOP: Trigger if Price >= Trigger Price
            if order['side'] == "BUY" and current_price >= order['trigger_price']:
                triggered = True
                
            # SELL STOP: Trigger if Price <= Trigger Price
            elif order['side'] == "SELL" and current_price <= order['trigger_price']:
                triggered = True
                
            if triggered:
                # LAST LOOK RISK CHECK: Ensure we haven't hit limits while order was pending
                if self.risk_manager and not self.risk_manager.check_trade_allowed(len(self.active_positions)):
                    logger.warning(f"❌ RISK REJECTED: Cancelling triggered order {order['id']} (Limits hit)")
                    order['status'] = "CANCELLED"
                    expired_orders.append(order) # Treat as expired/discarded for main loop cleanup
                    continue

                import time
                fill_time_ms = int(time.time() * 1000)
                # Latency = Now - Start of order request (or signal timestamp)
                latency = fill_time_ms - order.get('start_time_ms', fill_time_ms)
                # If we have a original signal_id, use that for true E2E latency
                if order.get('signal_id') in self.signal_timestamps:
                    latency = fill_time_ms - self.signal_timestamps[order['signal_id']]

                logger.info(f"⚡ ORDER TRIGGERED: {order['side']} {order['symbol']} @ {current_price} (Target: {order['trigger_price']}) | Latency: {latency}ms")
                order['status'] = "FILLED"
                order['avg_price'] = current_price # Slippage = 0 for now
                order['filled_qty'] = order['qty']
                order['latency_ms'] = latency
                
                # Create active position
                position = {
                    "id": order['id'],
                    "symbol": order['symbol'],
                    "side": order['side'],
                    "qty": order['qty'],
                    "entry_price": order['avg_price'],
                    "sl": order['stop_loss'],
                    "tp": order.get('take_profit'),
                    "strategy_id": order.get('strategy_id'),
                    "signal_id": order.get('signal_id')
                }
                self.active_positions.append(position)
                
                filled_orders.append(order)
            else:
                active_orders.append(order)
                
        self.pending_orders = active_orders
        return filled_orders, expired_orders

    def check_positions(self, current_price, symbol_filter=None):
        """
        Checks active positions against current price for SL/TP exit.
        Returns list of closed position dicts.
        """
        closed_positions = []
        remaining_positions = []
        
        for pos in self.active_positions:
            # Multi-Asset Filter
            if symbol_filter and pos['symbol'] != symbol_filter:
                remaining_positions.append(pos)
                continue

            exit_triggered = False
            exit_reason = ""
            
            # LONG EXITS
            if pos['side'] == "BUY":
                if pos['sl'] and current_price <= pos['sl']:
                    exit_triggered = True
                    exit_reason = "STOP_LOSS"
                elif pos['tp'] and current_price >= pos['tp']:
                    exit_triggered = True
                    exit_reason = "TAKE_PROFIT"
                    
            # SHORT EXITS
            elif pos['side'] == "SELL":
                if pos['sl'] and current_price >= pos['sl']:
                    exit_triggered = True
                    exit_reason = "STOP_LOSS"
                elif pos['tp'] and current_price <= pos['tp']:
                    exit_triggered = True
                    exit_reason = "TAKE_PROFIT"
                    
            if exit_triggered:
                logger.info(f"💰 EXIT TRIGGERED: {pos['side']} {pos['symbol']} @ {current_price} (Reason: {exit_reason})")
                
                # Calculate PnL
                if pos['side'] == "BUY":
                    pnl_amount = (current_price - pos['entry_price']) * pos['qty']
                    pnl_pct = ((current_price / pos['entry_price']) - 1) * 100
                else:
                    pnl_amount = (pos['entry_price'] - current_price) * pos['qty']
                    pnl_pct = ((pos['entry_price'] / current_price) - 1) * 100
                    
                self.balance += pnl_amount
                
                closed_pos = pos.copy()
                closed_pos['exit_price'] = current_price
                closed_pos['exit_reason'] = exit_reason
                closed_pos['pnl_amount'] = pnl_amount
                closed_pos['pnl_pct'] = pnl_pct
                
                closed_positions.append(closed_pos)
            else:
                remaining_positions.append(pos)
                
        self.active_positions = remaining_positions
        return closed_positions
