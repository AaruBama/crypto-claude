
"""
Database Handler for Trading Engine.
Manages SQLite connection with WAL mode for concurrent access.
Schema: strategies, signals, trades, performance.
"""
import sqlite3
import json
import os
import logging
from datetime import datetime

DB_PATH = "data/trading_bot.db"
logger = logging.getLogger("Database")

class DatabaseHandler:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()
        
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Access columns by name
        return conn
        
    def _init_db(self):
        """
        Initialize database tables and enable WAL mode.
        """
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with self._get_conn() as conn:
            # Enable Write-Ahead Logging for concurrency
            conn.execute("PRAGMA journal_mode=WAL;")
            
            # 1. Strategies Table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS strategies (
                id TEXT PRIMARY KEY,
                name TEXT,
                config JSON,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """)
            
            # 2. Signals Table (The Setup Memory)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT,
                type TEXT,
                price REAL,
                metadata JSON,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(strategy_id) REFERENCES strategies(id)
            );
            """)
            
            # 3. Trades Table (The Action Log)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER,
                order_id TEXT,
                symbol TEXT,
                strategy_id TEXT,
                side TEXT,
                entry_price REAL,
                exit_price REAL,
                quantity REAL,
                status TEXT DEFAULT 'OPEN',
                pnl_amount REAL DEFAULT 0,
                pnl_pct REAL DEFAULT 0,
                fees REAL DEFAULT 0,
                taxes REAL DEFAULT 0,
                latency_ms INTEGER DEFAULT 0,
                opened_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                closed_at DATETIME,
                FOREIGN KEY(signal_id) REFERENCES signals(id)
            );
            """)
            
            # 4. Orders Table (Pending objects)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                symbol TEXT,
                strategy_id TEXT,
                type TEXT,
                side TEXT,
                trigger_price REAL,
                quantity REAL,
                status TEXT DEFAULT 'PENDING',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # 5. Performance Table (Equity Curve)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                total_balance REAL,
                equity REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """)
            
            # Seed Initial Balance for Paper Trading (if empty)
            cursor = conn.execute("SELECT COUNT(*) FROM performance")
            if cursor.fetchone()[0] == 0:
                conn.execute(
                    "INSERT INTO performance (total_balance, equity) VALUES (?, ?)",
                    (10000.0, 10000.0)
                )
                logger.info("🌱 Seeded initial Paper Trading balance: $10,000")
                
            conn.commit()
            logger.info("✅ Database initialized with WAL mode.")

    def log_order(self, order_id, symbol, strategy_id, o_type, side, price, qty):
        """Logs a new order (usually PENDING)."""
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO orders (id, symbol, strategy_id, type, side, trigger_price, quantity, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')
                """,
                (order_id, symbol, strategy_id, o_type, side, price, qty)
            )
            conn.commit()

    def update_order_status(self, order_id, status):
        """Updates order status (FILLED, EXPIRED, CANCELLED)."""
        with self._get_conn() as conn:
            conn.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
            conn.commit()

    def log_signal(self, strategy_id, signal_type, price, metadata=None):
        """
        Logs a new signal setup. Returns signal_id.
        """
        with self._get_conn() as conn:
            cursor = conn.execute(
                "INSERT INTO signals (strategy_id, type, price, metadata) VALUES (?, ?, ?, ?)",
                (strategy_id, signal_type, price, json.dumps(metadata or {}))
            )
            conn.commit()
            return cursor.lastrowid

    def log_trade_open(self, symbol, strategy_id, side, price, qty, signal_id=None, order_id=None, latency_ms=0, fees=0.0):
        """
        Logs a new trade opening.
        """
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO trades (symbol, strategy_id, side, entry_price, quantity, signal_id, order_id, status, latency_ms, fees)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN', ?, ?)
                """,
                (symbol, strategy_id, side, price, qty, signal_id, order_id, latency_ms, fees)
            )
            conn.commit()
            return cursor.lastrowid
            
    def log_trade_close(self, trade_id=None, order_id=None, exit_price=0.0, pnl_amount=0.0, pnl_pct=0.0, fees=0.0, taxes=0.0, is_trap=False):
        """
        Updates a trade as CLOSED. Can supply either database ID or Exchange Order ID.
        If is_trap=True, marks it as 'TRAPPED' (Failed Breakout).
        """
        status = 'TRAPPED' if is_trap else 'CLOSED'
        with self._get_conn() as conn:
            if order_id:
                conn.execute(
                    f"""
                    UPDATE trades 
                    SET status='{status}', exit_price=?, pnl_amount=?, pnl_pct=?, fees=?, taxes=?, closed_at=CURRENT_TIMESTAMP
                    WHERE order_id=? AND status='OPEN'
                    """,
                    (exit_price, pnl_amount, pnl_pct, fees, taxes, order_id)
                )
            else:
                conn.execute(
                    f"""
                    UPDATE trades 
                    SET status='{status}', exit_price=?, pnl_amount=?, pnl_pct=?, fees=?, taxes=?, closed_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (exit_price, pnl_amount, pnl_pct, fees, taxes, trade_id)
                )
            conn.commit()

    def get_open_trades(self):
        """
        Returns list of active trades.
        """
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT * FROM trades WHERE status='OPEN'")
            return [dict(row) for row in cursor.fetchall()]
            
    def get_recent_performance(self, limit=100):
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT * FROM performance ORDER BY timestamp DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def clear_all_data(self):
        """
        Resets all tables for fresh testing.
        """
        with self._get_conn() as conn:
            conn.execute("DELETE FROM trades")
            conn.execute("DELETE FROM signals")
            conn.execute("DELETE FROM performance")
            conn.commit()
            print("🗑️ Database Cleared.")

class LiveAuditHandler:
    """
    Handles the dedicated data/live_trades.db for hands-free performance auditing.
    """
    def __init__(self, db_path="data/live_trades.db"):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._get_conn() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                side TEXT,
                order_id TEXT,
                signal_price REAL,
                fill_price REAL,
                slippage_pct REAL,
                fee_usd REAL,
                net_pnl REAL,
                is_critical INTEGER DEFAULT 0
            )""")
            conn.commit()

    def add_audit_entry(self, side, order_id, signal_price, fill_price, slippage_pct, fee_usd, net_pnl):
        is_critical = 1 if slippage_pct > 0.2 else 0
        if is_critical:
            print(f"🚨 CRITICAL EXECUTION EVENT: Slippage {slippage_pct:.3f}% is above 0.2% threshold!")
            
        with self._get_conn() as conn:
            conn.execute("""
            INSERT INTO audit_logs (side, order_id, signal_price, fill_price, slippage_pct, fee_usd, net_pnl, is_critical)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (side, order_id, signal_price, fill_price, slippage_pct, fee_usd, net_pnl, is_critical))
            conn.commit()
