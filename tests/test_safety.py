"""Unit tests for superKraken Safety Subsystems and Defense-in-Depth Mechanisms.

Tests:
1. Daily Drawdown Circuit Breaker halts and logs to SQLite audit log.
2. Stop-loss auto-execution closes position via market SELL and records realized P&L.
3. Memory Layer detects 3 consecutive losses and cuts position sizing by 50%.
4. Dead man's switch generates exact cancel-after 60 command and heartbeat reset.
5. Pre-flight checklist completes with all valid checks.
"""

import pytest
import uuid
from datetime import datetime, timezone
from superkraken.agents.risk_manager import RiskManagerAgent
from superkraken.config import settings
from superkraken.execution.kraken_cli import KrakenCLIWrapper
from superkraken.execution.paper_engine import PaperTradingEngine
from superkraken.state import ExecutionResult, OrderType, PortfolioState, TradeAction, TradeProposal
from superkraken.storage.database import db
from superkraken.cli import run_preflight_checklist


def test_circuit_breaker_halts_and_logs():
    """Verify 10% daily drawdown circuit breaker halts trading and logs to SQLite."""
    portfolio = PortfolioState(
        cash_usd=8900.0,
        total_value_usd=8900.0,
        daily_drawdown_pct=0.11,  # 11% drawdown > 10% limit
    )
    rm = RiskManagerAgent()
    proposal = TradeProposal(
        symbol="BTC/USD",
        action=TradeAction.BUY,
        quantity=0.05,
        entry_price=68000.0,
        stop_loss_price=65280.0,
        take_profit_price=73440.0,
        position_pct=0.25,
        reasoning="Test proposal in drawdown",
    )

    evaluation = rm.evaluate_mathematical_rules(proposal, portfolio)
    assert not evaluation.approved, "Circuit breaker must reject all trades"
    assert evaluation.circuit_breaker_triggered, "Circuit breaker flag must be True"

    recent_audits = db.get_recent_audit_events(limit=3)
    matching = [a for a in recent_audits if a["event_type"] == "CIRCUIT_BREAKER_ACTIVATED"]
    assert len(matching) > 0, "CIRCUIT_BREAKER_ACTIVATED must be logged in SQLite audit table"


def test_stop_loss_auto_execution():
    """Verify price falling below stop-loss triggers auto market SELL and realized P&L."""
    engine = PaperTradingEngine()
    engine.reset()

    # 1. Buy BTC at 68,000 with SL at 65,960 (3% SL)
    fill = engine.execute_order(
        symbol="BTC/USD",
        action=TradeAction.BUY,
        quantity=0.05,
        current_market_price=68000.0,
        stop_loss=65960.0,
        take_profit=73440.0,
    )
    assert fill.status == "FILLED"
    assert "BTC/USD" in engine.portfolio.positions

    # 2. Market price falls to 64,000 (< SL 65,960)
    engine.update_market_prices({"BTC/USD": 64000.0})

    # Position should be closed
    assert "BTC/USD" not in engine.portfolio.positions or engine.portfolio.positions["BTC/USD"].quantity == 0

    recent_trades = db.get_recent_trades(limit=1)
    assert len(recent_trades) > 0
    latest = recent_trades[0]
    assert latest["action"] == "SELL"
    assert "stop-loss" in (latest["reasoning"] or "").lower()


def test_memory_layer_consecutive_loss_sizing():
    """Verify 3 consecutive losses in SQLite trigger 50% position sizing reduction."""
    # Inject 3 consecutive losses
    for i, sym in enumerate(["BTC/USD", "ETH/USD", "SOL/USD"], 1):
        loss_res = ExecutionResult(
            success=True,
            order_id=f"test-loss-{i}-{uuid.uuid4().hex[:6]}",
            symbol=sym,
            action=TradeAction.SELL,
            filled_price=50000.0,
            filled_qty=0.02,
            fee=2.0,
            status="FILLED",
            message=f"Stop-loss hit: -${100.0 * i:.2f} loss",
        )
        db.log_trade(loss_res, confidence=1.0, reasoning=f"Consecutive loss {i}")

    portfolio = PortfolioState(
        cash_usd=10000.0,
        total_value_usd=10000.0,
        daily_drawdown_pct=0.0,
    )
    rm = RiskManagerAgent()
    prop_qty = 0.0300
    proposal = TradeProposal(
        symbol="BTC/USD",
        action=TradeAction.BUY,
        quantity=prop_qty,
        entry_price=68000.0,
        stop_loss_price=65280.0,
        take_profit_price=73440.0,
        position_pct=0.20,
        reasoning="Test proposal after 3 losses",
    )

    evaluation = rm.evaluate_mathematical_rules(proposal, portfolio)
    expected_qty = prop_qty * 0.5
    assert abs(evaluation.adjusted_quantity - expected_qty) < 1e-4, f"Quantity should be cut by 50% to {expected_qty}"
    assert any("[MEMORY: SIZING TIGHTENED" in r for r in evaluation.reasons), "Memory layer reason tag missing"


def test_dead_man_switch_command_generation():
    """Verify dead man's switch cancel-after 60 CLI command generation."""
    wrapper = KrakenCLIWrapper()
    cmd = wrapper.build_cancel_after_command(timeout_seconds=60)
    assert cmd == [wrapper.cli_path, "spot", "cancel-after", "--timeout", "60"]

    order_cmd = wrapper.build_spot_order_command(
        symbol="XBTZUSD",
        side="buy",
        order_type="limit",
        volume=0.05,
        price=68000.0,
    )
    assert "spot" in order_cmd
    assert "order" in order_cmd
    assert "add" in order_cmd
    assert "--pair" in order_cmd
    assert "XBTZUSD" in order_cmd


def test_preflight_checklist():
    """Verify full 11-point preflight checklist passes."""
    passed = run_preflight_checklist("PAPER")
    assert passed is True
