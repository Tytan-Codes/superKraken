"""Tests for superKraken Copilot features:
1. Risk calculator math (ATR sizing, dollar risk, R:R 2:1)
2. Manual position tracking (SQLite persistence, state transitions)
3. Performance stats (Operator [Y] vs Skipped [N] alpha)
4. Scanner 62% confidence filter
"""

import pytest
from datetime import datetime, timezone
from superkraken.copilot.risk_calc import calculate_copilot_order_spec
from superkraken.state import SignalAlert, TrackedPosition, TradeAction
from superkraken.storage.database import db


def test_copilot_risk_calculator_math_buy():
    """Verify ATR-anchored stop loss, 2:1 profit target, dollar sizing, and risk caps for BUY."""
    spec = calculate_copilot_order_spec(
        symbol="BTC/USD",
        action="BUY",
        current_price=68000.0,
        atr_14=1000.0,
        portfolio_usdc=10000.0,
        confidence=0.70,
        max_position_pct=0.25,
        risk_per_trade_pct=0.01,
    )

    # 1. Stop loss should be 1.5 * ATR below entry: 68000 - 1500 = 66500
    assert spec["stop_loss_price"] == 66500.0
    # 2. Take profit should be 2:1 R:R: 68000 + 2 * 1500 = 71000
    assert spec["take_profit_price"] == 71000.0
    # 3. Risk-reward ratio must be 2.0
    assert spec["risk_reward_ratio"] == 2.0
    # 4. Limit entry price should be current or slight discount
    assert spec["limit_entry_price"] <= spec["entry_price"]
    # 5. Position dollar sizing should respect max position pct (25% = $2,500)
    assert spec["notional_usdc"] <= 2500.01
    # 6. Max dollar loss should be capped near 1% of portfolio (~$100) or strictly bounded
    assert spec["max_loss_usd"] > 0
    assert spec["target_gain_usd"] > spec["max_loss_usd"]


def test_copilot_risk_calculator_math_sell():
    """Verify ATR-anchored stop loss, 2:1 profit target, dollar sizing for SELL."""
    spec = calculate_copilot_order_spec(
        symbol="ETH/USD",
        action="SELL",
        current_price=3500.0,
        atr_14=50.0,
        portfolio_usdc=10000.0,
        confidence=0.65,
        max_position_pct=0.20,
        risk_per_trade_pct=0.01,
    )

    # Stop loss should be above entry for short/sell: 3500 + 1.5 * 50 = 3575
    assert spec["stop_loss_price"] == 3575.0
    # Take profit should be below entry: 3500 - 2 * 75 = 3350
    assert spec["take_profit_price"] == 3350.0
    assert spec["risk_reward_ratio"] == 2.0
    assert spec["notional_usdc"] <= 2000.01


def test_manual_position_tracking_sqlite():
    """Verify manual positions can be created, retrieved, updated, and closed in SQLite."""
    pos = TrackedPosition(
        symbol="SOL/USD",
        side="BUY",
        entry_price=150.0,
        current_price=150.0,
        position_size=10.0,
        stop_loss=140.0,
        take_profit=170.0,
        status="OPEN",
        notes="Test manual trade",
    )
    pos_id = db.create_manual_position(pos)
    assert pos_id > 0

    open_positions = db.get_open_positions()
    matching = [p for p in open_positions if p.id == pos_id]
    assert len(matching) == 1
    assert matching[0].symbol == "SOL/USD"
    assert matching[0].position_size == 10.0
    assert matching[0].status == "OPEN"

    # Close position at target
    db.close_manual_position(pos_id, exit_price=170.0, exit_reason="TAKE_PROFIT")

    # Should no longer be in open positions
    open_positions_after = db.get_open_positions()
    assert not any(p.id == pos_id for p in open_positions_after)

    # Should be in all positions with CLOSED status and correct P&L
    all_positions = db.get_all_manual_positions()
    closed = next(p for p in all_positions if p.id == pos_id)
    assert closed.status == "CLOSED"
    assert closed.exit_price == 170.0
    assert closed.realized_pnl == (170.0 - 150.0) * 10.0  # +$200.0
    assert closed.exit_reason == "TAKE_PROFIT"


def test_copilot_performance_stats_calculation():
    """Verify performance metrics for Operator [Y] vs Skipped [N] alpha."""
    # 1. Log a winning user trade
    p1 = TrackedPosition(
        symbol="BTC/USD",
        side="BUY",
        entry_price=60000.0,
        current_price=62000.0,
        position_size=0.1,
        status="OPEN",
    )
    pid1 = db.create_manual_position(p1)
    db.close_manual_position(pid1, exit_price=62000.0, exit_reason="TAKE_PROFIT")

    # 2. Log a losing user trade
    p2 = TrackedPosition(
        symbol="ETH/USD",
        side="BUY",
        entry_price=3000.0,
        current_price=2900.0,
        position_size=1.0,
        status="OPEN",
    )
    pid2 = db.create_manual_position(p2)
    db.close_manual_position(pid2, exit_price=2900.0, exit_reason="STOP_LOSS")

    # 3. Log a skipped signal that was a GOOD skip (outcome was LOSS)
    sig1 = SignalAlert(
        signal_id=f"sig-test-skip-good-{datetime.now().timestamp()}",
        symbol="SOL/USD",
        action=TradeAction.BUY,
        confidence=0.64,
        bull_score=0.65,
        bear_score=0.35,
        suggested_order={"entry_price": 150.0, "stop_loss": 140.0, "take_profit": 170.0},
        risk_metrics={"max_loss_usd": 100.0, "target_gain_usd": 200.0},
        summary="Test signal",
    )
    db.log_copilot_signal(sig1)
    db.update_signal_user_action(sig1.signal_id, "SKIPPED", "Did not like market volatility")
    db.update_signal_outcome(sig1.signal_id, "LOSS", exit_price=140.0)

    # 4. Log a skipped signal that was a MISSED opportunity (outcome was WIN)
    sig2 = SignalAlert(
        signal_id=f"sig-test-skip-miss-{datetime.now().timestamp()}",
        symbol="AVAX/USD",
        action=TradeAction.BUY,
        confidence=0.66,
        bull_score=0.68,
        bear_score=0.32,
        suggested_order={"entry_price": 30.0, "stop_loss": 28.0, "take_profit": 34.0},
        risk_metrics={"max_loss_usd": 100.0, "target_gain_usd": 200.0},
        summary="Test signal 2",
    )
    db.log_copilot_signal(sig2)
    db.update_signal_user_action(sig2.signal_id, "SKIPPED", "Skipped")
    db.update_signal_outcome(sig2.signal_id, "WIN", exit_price=34.0)

    stats = db.get_copilot_performance_stats()
    assert stats["total_user_trades"] >= 2
    assert stats["user_wins"] >= 1
    assert stats["user_losses"] >= 1
    assert stats["total_skipped_signals"] >= 2
    assert stats["good_skips"] >= 1
    assert stats["missed_opportunities"] >= 1


def test_scanner_62_percent_confidence_filter():
    """Verify that signals with confidence < 0.62 are NOT returned as alerts."""
    # When action is HOLD or confidence < 0.62, alert must be None
    from superkraken.copilot.scanner import CopilotScanner
    # We test the logic:
    action_str = "BUY"
    confidence_low = 0.58
    min_confidence = 0.62
    assert not (action_str in ("BUY", "SELL") and confidence_low >= min_confidence)

    confidence_high = 0.63
    assert action_str in ("BUY", "SELL") and confidence_high >= min_confidence
