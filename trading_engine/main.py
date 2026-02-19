
"""
Trading Engine Entry Point (Multi-Asset V6)
The main event loop that orchestrates data fetching, strategy execution, and order management.
Now optimized for Multi-Asset Mean Reversion (BTC & SOL).
"""
import time
import sys
import logging
from datetime import datetime

# Local imports
from trading_engine.config import ENGINE_SETTINGS, STRATEGIES, LIVE_ALLOCATION, ACTIVE_STRATEGIES
from trading_engine.core.exchange import Exchange
from trading_engine.core.risk_manager import RiskManager
from trading_engine.core.candle_manager import CandleManager
from trading_engine.db import DatabaseHandler
from trading_engine.strategies.adaptive_engine import AdaptiveStrategy
from trading_engine.strategies.grid_trading import GridTradingStrategy
from trading_engine.utils.notifier import send_trade_entry, send_trade_exit, send_signal, send_heartbeat, send_alert

import os

# Setup Logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/engine.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("TradingEngine")

class TradingEngine:
    def __init__(self):
        logger.info("🚀 Initializing Trading Engine (Chameleon V7)...")
        
        # 1. Initialize Core Components
        self.db = DatabaseHandler() 
        self.risk_manager = RiskManager()
        self.exchange = Exchange(paper_mode=ENGINE_SETTINGS['paper_trading'], risk_manager=self.risk_manager)
        
        # 2. Identify Active Symbols
        self.symbols = set()
        for alloc in LIVE_ALLOCATION.values():
            if alloc.get('symbol'):
                self.symbols.add(alloc['symbol'])
        
        # Per-symbol Candle Managers
        self.candle_managers = {
            sym: CandleManager(limit=ENGINE_SETTINGS.get('candle_limit', 500)) 
            for sym in self.symbols
        }
        
        # 3. Load Active Strategies
        self.strategies = []
        
        # BTC Chameleon Adaptive Strategy
        if "ADAPTIVE_ENGINE" in ACTIVE_STRATEGIES:
            self.strategies.append(AdaptiveStrategy(
                "BTC_Adaptive", 
                params=STRATEGIES["ADAPTIVE_ENGINE"]["params"]
            ))
            # Set internal props for strategy routing
            self.strategies[-1]._symbol = LIVE_ALLOCATION['BTC_Adaptive']['symbol']
            self.strategies[-1]._budget = LIVE_ALLOCATION['BTC_Adaptive']['budget']
            logger.info(f"✅ Loaded Strategy: BTC_Adaptive (Budget: ${self.strategies[-1]._budget})")

        # SOL Chameleon Adaptive Strategy
        if "ADAPTIVE_ENGINE_SOL" in ACTIVE_STRATEGIES:
            self.strategies.append(AdaptiveStrategy(
                "SOL_Adaptive",
                params=STRATEGIES["ADAPTIVE_ENGINE_SOL"]["params"]
            ))
            self.strategies[-1]._symbol = LIVE_ALLOCATION['SOL_Adaptive']['symbol']
            self.strategies[-1]._budget = LIVE_ALLOCATION['SOL_Adaptive']['budget']
            logger.info(f"✅ Loaded Strategy: SOL_Adaptive (Budget: ${self.strategies[-1]._budget})")

        # Selective Grid
        if "GRID_TRADING" in ACTIVE_STRATEGIES and False: # Disabled in code
             pass
        
        self.last_candle_minute = None
        self.last_heartbeat_time = time.time()
        self.start_time = time.time()
        self.running = False
        
        # Preload data
        self._preload_data()

    def _preload_data(self):
        logger.info(f"⏳ Pre-loading historical data for {self.symbols}...")
        for sym in self.symbols:
            try:
                ohlcv = self.exchange.client.fetch_ohlcv(sym, timeframe=ENGINE_SETTINGS['timeframe'], limit=100)
                for candle in ohlcv:
                    ts = datetime.fromtimestamp(candle[0] / 1000)
                    self.candle_managers[sym].add_candle(candle[1], candle[2], candle[3], candle[4], candle[5], ts)
                logger.info(f"✅ {sym}: Pre-loaded {len(ohlcv)} candles.")
            except Exception as e:
                logger.error(f"❌ Pre-load failed for {sym}: {e}")

    def start(self):
        self.running = True
        send_heartbeat("STARTING", self.risk_manager.balance, 0)
        logger.info(f"✅ Production Engine Started. Monitoring: {', '.join(self.symbols)}")
        
        while self.running:
            try:
                self._tick()
                time.sleep(ENGINE_SETTINGS['update_interval'])
            except KeyboardInterrupt:
                self.stop()
            except Exception as e:
                logger.error(f"⚠️ Loop Error: {e}")
                time.sleep(5)

    def stop(self):
        self.running = False
        logger.info("🛑 Engine Stopped.")
        send_alert("Engine Stopped manually or crashed.")

    def _tick(self):
        """Single iteration."""
        now = time.time()
        
        # --- 0. Heartbeat (Every 15 mins for Smoke Test) ---
        if now - self.last_heartbeat_time > 900:
            uptime = (now - self.start_time) / 3600
            active_count = len(self.exchange.active_positions)
            session_pnl = self.risk_manager.balance - self.risk_manager.initial_day_balance
            
            logger.info("💓 Heartbeat sent.")
            send_heartbeat("ONLINE", self.risk_manager.balance, active_count, uptime_hours=uptime, pnl=session_pnl)
            
            self.last_heartbeat_time = now

        # --- 1. Update Market Data (All Symbols) ---
        current_prices = {}
        for sym in self.symbols:
            try:
                ticker = self.exchange.get_ticker(sym)
                if ticker:
                    current_prices[sym] = ticker['last']
            except Exception as e:
                logger.error(f"⚠️ Ticker Error {sym}: {e}")

        if not current_prices:
            return

        # --- 2. Process Candle Closure ---
        current_minute = datetime.now().minute
        if self.last_candle_minute is None:
            self.last_candle_minute = current_minute
        
        if current_minute != self.last_candle_minute:
            logger.info(f"🕒 Candle Close Detected: {datetime.now().strftime('%H:%M')}")
            for sym in self.symbols:
                if sym in current_prices:
                    self._on_candle_close(sym)
            self.last_candle_minute = current_minute

        # --- 3. Update Pending Orders & Positions ---
        if self.exchange.pending_orders:
            # We assume check_order_status handles all symbols if we pass current prices?
            # Actually Exchange.check_order_status takes `current_price` (singular).
            # We must loop.
            # TODO: Refactor Exchange to handle multi-symbol status checks efficiently.
            # For now, simplistic loop:
            pass # Exchange needs update, but let's assume one pass with 'BTC' price works for BTC orders? 
            # Wait, check_order_status iterates self.pending_orders.
            # It compares order['symbol'] with passed price? 
            # No, standard implementation takes 1 price.
            # We need to call check_order_status for EACH symbol that has pending orders?
            # Or pass a dict of prices.
            
            # Temporary fix: Loop per symbol
            for sym, price in current_prices.items():
                self.exchange.check_pending_orders(price, symbol_filter=sym)

        # Retrieve executed trades (handled by Exchange internally -> returns list)
        all_executed = []
        all_expired = []
        for sym, price in current_prices.items():
             ex, exp = self.exchange.check_pending_orders(price, symbol_filter=sym)
             all_executed.extend(ex)
             all_expired.extend(exp)
        
        for order in all_executed:
            self._handle_executed_order(order)
            
        for order in all_expired:
            self.db.update_order_status(order['id'], "EXPIRED")

        # --- 4. Position Monitoring ---
        # Update trailing stops / check exits
        # Exchange.check_positions needs dict of prices?
        # Standard implementation takes 1 price.
        # We need to loop.
        all_closed = []
        for sym, price in current_prices.items():
            closed = self.exchange.check_positions(price, symbol_filter=sym)
            all_closed.extend(closed)
            
        for pos in all_closed:
            self._handle_closed_position(pos)

    def _handle_executed_order(self, order):
        logger.info(f"⚡ ORDER EXECUTED: {order['id']} ({order['side']}) at {order['price']}")
        self.db.log_trade_open(
            strategy_id=order['strategy_id'],
            signal_id=order['signal_id'],
            order_id=order['id'],
            symbol=order['symbol'],
            side=order['side'],
            quantity=order['qty'],
            entry_price=order['price'],
            fees=0
        )
        send_trade_entry(order['symbol'], order['side'], order['price'], order['qty'], order['strategy_id'])

    def _handle_closed_position(self, pos):
        logger.info(f"💰 POSITION CLOSED: {pos['id']} ({pos['exit_reason']})")
        costs = self.risk_manager.add_realized_pnl(pos['pnl_amount'], trade_value_usd=pos['exit_price'] * pos['qty'])
        
        self.db.log_trade_close(
            order_id=pos['id'],
            exit_price=pos['exit_price'],
            pnl_amount=pos['pnl_amount'], 
            pnl_pct=pos['pnl_pct'],
            fees=costs['fee'], 
            taxes=costs['tax'],
            is_trap=(pos['exit_reason'] == "STOP_LOSS")
        )
        self.db.update_order_status(pos['id'], "CLOSED")
        
        roi_pct = (pos['pnl_amount'] / (pos['entry_price'] * pos['qty'])) * 100
        send_trade_exit(pos['symbol'], pos['side'], pos['exit_price'], pos['pnl_amount'] - costs['fee'], roi_pct, pos['exit_reason'])

    def _on_candle_close(self, symbol):
        try:
            # Fetch 2 candles
            klines = self.exchange.client.fetch_ohlcv(symbol, timeframe=ENGINE_SETTINGS['timeframe'], limit=2)
            if not klines or len(klines) < 2: return
            
            # Add to manager
            c = klines[0]
            ts = datetime.fromtimestamp(c[0] / 1000)
            self.candle_managers[symbol].add_candle(c[1], c[2], c[3], c[4], c[5], ts)
            
            # Check Strategies
            for strategy in self.strategies:
                # Strategy Routing: Only check if symbol matches
                if getattr(strategy, '_symbol', None) != symbol:
                    continue
                    
                signal = strategy.on_candle_close(self.candle_managers[symbol])
                if signal:
                    # Inject Strategy ID and Budget
                    signal['strategy_id'] = strategy.name
                    signal['budget'] = getattr(strategy, '_budget', 100.0)
                    self._execute_signal(signal, strategy)
                    
        except Exception as e:
            logger.error(f"❌ Candle Process Error ({symbol}): {e}")

    def _execute_signal(self, signal, strategy):
        # Notify detection
        send_signal(signal['symbol'], signal['side'], signal['price'], strategy.name, signal.get('reason', 'Signal'))
        
        # Risk Check
        active_positions = self.exchange.active_positions # List of dicts
        # Filter for this strategy? Or global?
        # Risk Manager manages global limit (Gate 2) and budget (Gate 5).
        
        # Calculate size
        from trading_engine.config import RISK_SETTINGS
        if signal.get('qty'):
             qty = signal['qty']
        else:
             # Default sizing logic (Risk %)
             # RiskManager uses balance, entry, sl
             sl = signal.get('sl')
             if sl:
                 qty = self.risk_manager.calculate_position_size(signal['price'], sl)
             else:
                 qty = 0 # Fallback?
        
        # Override qty if budget constrained (Backtest engine does this)
        # Here we rely on RiskManager.check_trade_allowed
        
        trade_val = qty * signal['price']
        
        if self.risk_manager.check_trade_allowed(
            len(active_positions), 
            current_exposure_usd=sum(p['qty']*p['entry_price'] for p in active_positions),
            entry_price=signal['price'], 
            tp_price=signal.get('tp'),
            strategy_id=strategy.name, 
            trade_usd=trade_val
        ):
             # Log signal to DB
             signal_id = self.db.log_signal(strategy.name, signal['side'], signal['price'], signal['metadata'])
             
             # Execute
             order_id = self.exchange.create_order(
                 symbol=signal['symbol'],
                 side=signal['side'],
                 qty=qty,
                 price=signal['price'],
                 stop_loss=signal.get('sl'),
                 take_profit=signal.get('tp'),
                 order_type=signal['order_type'],
                 strategy_id=strategy.name,
                 signal_id=signal_id
             )
             if order_id:
                 logger.info(f"✅ Order Placed: {order_id}")
             else:
                 send_alert(f"❌ Order Placement Failed: {signal['symbol']}")
        else:
             logger.info(f"🛡️ Risk Rejection: {signal['symbol']} (See logs)")

if __name__ == "__main__":
    engine = TradingEngine()
    engine.start()
