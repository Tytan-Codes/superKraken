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
                    session_type TEXT NOT NULL DEFAULT 'PAPER',
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
            # Automatic schema migration for existing databases
            try:
                cursor.execute("ALTER TABLE trades ADD COLUMN session_type TEXT NOT NULL DEFAULT 'PAPER'")
            except sqlite3.OperationalError:
                pass

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
                    session_type TEXT NOT NULL DEFAULT 'PAPER',
                    event_type TEXT NOT NULL,
                    details TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS copilot_signals (
                    signal_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    bull_score REAL,
                    bear_score REAL,
                    indicators_json TEXT,
                    suggested_order_json TEXT,
                    risk_metrics_json TEXT,
                    bull_thesis TEXT,
                    bear_thesis TEXT,
                    summary TEXT,
                    user_action TEXT DEFAULT 'PENDING',
                    theoretical_outcome TEXT DEFAULT 'PENDING',
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS manual_positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    take_profit REAL NOT NULL,
                    notes TEXT,
                    status TEXT DEFAULT 'OPEN',
                    signal_id TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    closed_at DATETIME,
                    exit_price REAL,
                    realized_pnl REAL,
                    exit_reason TEXT
                )
                """
            )
            try:
                cursor.execute("ALTER TABLE manual_positions ADD COLUMN exit_reason TEXT")
            except Exception:
                pass
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS price_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    target_price REAL NOT NULL,
                    condition TEXT DEFAULT 'CROSS',
                    note TEXT,
                    triggered INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    def log_trade(
        self,
        execution: ExecutionResult,
        confidence: float = 0.0,
        reasoning: str = "",
        session_type: str = "PAPER",
    ) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO trades (session_type, order_id, symbol, action, price, quantity, fee, status, message, confidence, reasoning)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_type,
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

    def get_recent_trades(self, limit: int = 20, session_type: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if session_type:
                cursor.execute(
                    """
                    SELECT * FROM trades WHERE session_type = ? ORDER BY timestamp DESC LIMIT ?
                    """,
                    (session_type, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?
                    """,
                    (limit,),
                )
            return [dict(row) for row in (cursor.fetchall() or [])]

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

    def log_audit_event(self, event_type: str, details: str = "", session_type: str = "PAPER") -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO audit_log (session_type, event_type, details)
                VALUES (?, ?, ?)
                """,
                (session_type, event_type, details),
            )
            conn.commit()
            return cursor.lastrowid

    def get_recent_audit_events(self, limit: int = 10, session_type: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if session_type:
                cursor.execute(
                    """
                    SELECT * FROM audit_log WHERE session_type = ? ORDER BY timestamp DESC LIMIT ?
                    """,
                    (session_type, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?
                    """,
                    (limit,),
                )
            return [dict(row) for row in (cursor.fetchall() or [])]

    # --- Copilot Specific Storage & Analytics Methods ---

    def log_copilot_signal(self, signal: Any) -> str:
        """Persist a high-conviction signal recommendation."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO copilot_signals (
                    signal_id, symbol, action, confidence, bull_score, bear_score,
                    indicators_json, suggested_order_json, risk_metrics_json,
                    bull_thesis, bear_thesis, summary, user_action, theoretical_outcome
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal.signal_id,
                    signal.symbol,
                    signal.action.value if hasattr(signal.action, "value") else str(signal.action),
                    signal.confidence,
                    signal.bull_score,
                    signal.bear_score,
                    json.dumps(signal.indicators),
                    json.dumps(signal.suggested_order),
                    json.dumps(signal.risk_metrics),
                    signal.bull_thesis,
                    signal.bear_thesis,
                    signal.summary,
                    signal.user_action,
                    signal.theoretical_outcome,
                ),
            )
            conn.commit()
            return signal.signal_id

    def update_signal_user_action(self, signal_id: str, action: str, reasoning: str = "") -> None:
        """Record operator decision on a signal: 'PLACED' [Y] or 'SKIPPED' [N]."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE copilot_signals SET user_action = ? WHERE signal_id = ?",
                (action, signal_id),
            )
            conn.commit()

    def update_signal_outcome(self, signal_id: str, outcome: str, exit_price: Optional[float] = None) -> None:
        """Record theoretical market outcome: 'WIN' or 'LOSS'."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE copilot_signals SET theoretical_outcome = ? WHERE signal_id = ?",
                (outcome, signal_id),
            )
            conn.commit()

    def get_recent_signals(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent copilot signals for TUI ticker and history."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM copilot_signals ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            return [dict(row) for row in (cursor.fetchall() or [])]

    def create_manual_position(
        self,
        position_or_symbol: Any,
        action: Optional[str] = None,
        quantity: Optional[float] = None,
        entry_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        notes: str = "",
        signal_id: Optional[str] = None,
    ) -> int:
        """Log a manual trade placed by the human operator on Kraken Pro."""
        if hasattr(position_or_symbol, "symbol"):
            pos = position_or_symbol
            sym = pos.symbol
            act = getattr(pos, "action", getattr(pos, "side", "BUY"))
            qty = getattr(pos, "quantity", getattr(pos, "position_size", 0.0))
            ep = pos.entry_price
            sl = pos.stop_loss
            tp = pos.take_profit
            nt = getattr(pos, "notes", "")
            sid = getattr(pos, "signal_id", None)
        elif isinstance(position_or_symbol, dict):
            sym = position_or_symbol.get("symbol")
            act = position_or_symbol.get("action", position_or_symbol.get("side", "BUY"))
            qty = position_or_symbol.get("quantity", position_or_symbol.get("position_size", 0.0))
            ep = position_or_symbol.get("entry_price", 0.0)
            sl = position_or_symbol.get("stop_loss")
            tp = position_or_symbol.get("take_profit")
            nt = position_or_symbol.get("notes", "")
            sid = position_or_symbol.get("signal_id")
        else:
            sym = position_or_symbol
            act = action or "BUY"
            qty = quantity or 0.0
            ep = entry_price or 0.0
            sl = stop_loss
            tp = take_profit
            nt = notes
        sl = sl if sl is not None else 0.0
        tp = tp if tp is not None else 0.0

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO manual_positions (
                    symbol, action, quantity, entry_price, stop_loss, take_profit, notes, signal_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (sym, act.upper(), qty, ep, sl, tp, nt, sid),
            )
            conn.commit()
            return cursor.lastrowid

    def get_open_positions(self) -> List[Any]:
        """Retrieve all currently active positions requiring real-time level monitoring."""
        from superkraken.state import TrackedPosition
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM manual_positions WHERE status = 'OPEN' ORDER BY created_at ASC")
            rows = [dict(row) for row in (cursor.fetchall() or [])]
            return [TrackedPosition(**r) for r in rows]

    def close_manual_position(
        self,
        position_id: int,
        exit_price: float,
        realized_pnl: Optional[float] = None,
        status: str = "CLOSED",
        exit_reason: Optional[str] = None,
    ) -> None:
        """Mark a monitored position as closed (manual exit, stop-loss, or take-profit)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if realized_pnl is None:
                cursor.execute("SELECT action, quantity, entry_price FROM manual_positions WHERE id = ?", (position_id,))
                row = cursor.fetchone()
                if row:
                    act, qty, ep = row["action"], row["quantity"], row["entry_price"]
                    if act == "BUY":
                        realized_pnl = round((exit_price - ep) * qty, 2)
                    else:
                        realized_pnl = round((ep - exit_price) * qty, 2)
                else:
                    realized_pnl = 0.0

            reason = exit_reason or status or "MANUAL"
            cursor.execute(
                """
                UPDATE manual_positions
                SET status = 'CLOSED', exit_price = ?, realized_pnl = ?, exit_reason = ?, closed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (exit_price, realized_pnl, reason, position_id),
            )
            conn.commit()

    def get_all_manual_positions(self, limit: int = 100) -> List[Any]:
        """Retrieve historical manual positions for audit and performance reviews."""
        from superkraken.state import TrackedPosition
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM manual_positions ORDER BY created_at DESC LIMIT ?", (limit,))
            rows = [dict(row) for row in (cursor.fetchall() or [])]
            return [TrackedPosition(**r) for r in rows]

    def create_price_alert(
        self,
        symbol: str,
        target_price: float,
        condition: str = "CROSS",
        note: str = "",
    ) -> int:
        """Create custom operator price alert."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO price_alerts (symbol, target_price, condition, note) VALUES (?, ?, ?, ?)",
                (symbol, target_price, condition, note),
            )
            conn.commit()
            return cursor.lastrowid

    def get_active_price_alerts(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get untriggered price alerts."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if symbol:
                cursor.execute(
                    "SELECT * FROM price_alerts WHERE triggered = 0 AND symbol = ? ORDER BY created_at ASC",
                    (symbol,),
                )
            else:
                cursor.execute("SELECT * FROM price_alerts WHERE triggered = 0 ORDER BY created_at ASC")
            return [dict(row) for row in (cursor.fetchall() or [])]

    def trigger_price_alert(self, alert_id: int) -> None:
        """Mark a price alert as triggered."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE price_alerts SET triggered = 1 WHERE id = ?", (alert_id,))
            conn.commit()

    def get_copilot_performance_stats(self) -> Dict[str, Any]:
        """Aggregate personal operator execution statistics vs raw signal accuracy."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Manual positions stats
            cursor.execute("SELECT * FROM manual_positions WHERE status != 'OPEN'")
            closed_manual = [dict(row) for row in (cursor.fetchall() or [])]

            total_placed = len(closed_manual)
            following_signal = sum(1 for p in closed_manual if p.get("signal_id"))
            
            wins = [p for p in closed_manual if (p.get("realized_pnl") or 0.0) > 0]
            losses = [p for p in closed_manual if (p.get("realized_pnl") or 0.0) <= 0]
            win_rate = (len(wins) / total_placed * 100.0) if total_placed > 0 else 0.0
            total_pnl = sum(p.get("realized_pnl", 0.0) or 0.0 for p in closed_manual)

            best_p = max(closed_manual, key=lambda x: x.get("realized_pnl") or 0.0) if closed_manual else None
            worst_p = min(closed_manual, key=lambda x: x.get("realized_pnl") or 0.0) if closed_manual else None

            # All signals stats
            cursor.execute("SELECT * FROM copilot_signals")
            signals = [dict(row) for row in (cursor.fetchall() or [])]
            total_signals = len(signals)
            skipped_signals = [s for s in signals if s.get("user_action") == "SKIPPED"]

            resolved_signals = [s for s in signals if s.get("theoretical_outcome") in ("WIN", "LOSS")]
            signal_wins = sum(1 for s in resolved_signals if s.get("theoretical_outcome") == "WIN")
            signal_win_rate = (signal_wins / len(resolved_signals) * 100.0) if resolved_signals else 0.0

            # Human judgment evaluation
            correctly_skipped = sum(1 for s in skipped_signals if s.get("theoretical_outcome") == "LOSS")
            incorrectly_skipped = sum(1 for s in skipped_signals if s.get("theoretical_outcome") == "WIN")

            return {
                "total_trades_placed": total_placed,
                "total_user_trades": total_placed,
                "trades_following_signal": following_signal,
                "trades_skipped": len(skipped_signals),
                "total_skipped_signals": len(skipped_signals),
                "manual_win_rate": win_rate,
                "user_win_rate_pct": win_rate,
                "user_wins": len(wins),
                "user_losses": len(losses),
                "total_pnl_usd": total_pnl,
                "total_realized_pnl": total_pnl,
                "best_trade": best_p,
                "worst_trade": worst_p,
                "total_signals": total_signals,
                "signal_wins": signal_wins,
                "signal_losses": len(resolved_signals) - signal_wins,
                "signal_win_rate": signal_win_rate,
                "signal_win_rate_pct": signal_win_rate,
                "correctly_skipped_losses": correctly_skipped,
                "good_skips": correctly_skipped,
                "missed_opportunities": incorrectly_skipped,
                "incorrectly_skipped_wins": incorrectly_skipped,
                "beat_signal": (win_rate > signal_win_rate) if total_placed > 0 and resolved_signals else None,
                "alpha_delta": (win_rate - signal_win_rate) if total_placed > 0 and resolved_signals else 0.0,
            }


db = Database()
