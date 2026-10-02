"""SQLite persistence for trades, debates, and portfolio snapshots."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from superkraken.config import settings
from superkraken.state import ExecutionResult, TradeAction


class Database:
    """Manages SQLite database for historical records."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or (settings.data_dir / "superkraken.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    fee REAL NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT,
                    confidence REAL,
                    reasoning TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS debates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    bull_summary TEXT,
                    bear_summary TEXT,
                    consensus_action TEXT,
                    confidence REAL,
                    full_log_json TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    total_value REAL NOT NULL,
                    cash REAL NOT NULL,
                    daily_drawdown_pct REAL NOT NULL,
                    realized_pnl_today REAL NOT NULL,
                    positions_json TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    details TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    def log_trade(
        self,
        execution: ExecutionResult,
        confidence: float = 0.0,
        reasoning: str = "",
    ) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO trades (order_id, symbol, action, price, quantity, fee, status, message, confidence, reasoning)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    execution.order_id,
                    execution.symbol,
                    execution.action.value,
                    execution.filled_price,
                    execution.filled_qty,
                    execution.fee,
                    execution.status,
                    execution.message,
                    confidence,
                    reasoning,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def log_debate(
        self,
        symbol: str,
        bull_summary: str,
        bear_summary: str,
        consensus_action: str,
        confidence: float,
        full_log: List[Dict[str, Any]],
    ) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO debates (symbol, bull_summary, bear_summary, consensus_action, confidence, full_log_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    bull_summary,
                    bear_summary,
                    consensus_action,
                    confidence,
                    json.dumps(full_log),
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def get_recent_trades(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?
                """,
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_today_trade_count(self, symbol: Optional[str] = None) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if symbol:
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM trades 
                    WHERE symbol = ? AND DATE(timestamp) = DATE('now')
                    """,
                    (symbol,),
                )
            else:
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM trades 
                    WHERE DATE(timestamp) = DATE('now')
                    """
                )
            row = cursor.fetchone()
            return row[0] if row else 0

    def log_audit_event(self, event_type: str, details: str = "") -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO audit_log (event_type, details)
                VALUES (?, ?)
                """,
                (event_type, details),
            )
            conn.commit()
            return cursor.lastrowid

    def get_recent_audit_events(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?
                """,
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]


db = Database()
