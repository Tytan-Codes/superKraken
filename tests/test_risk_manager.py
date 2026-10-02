"""Unit tests for Risk Manager safeguards and circuit breakers."""

import pytest
from superkraken.agents.risk_manager import RiskManagerAgent
from superkraken.state import OrderType, PortfolioState, TradeAction, TradeProposal


@pytest.fixture
def risk_agent():
    return RiskManagerAgent()


@pytest.fixture
def base_portfolio():
    return PortfolioState(
        total_value_usd=10000.0,
        cash_usd=10000.0,
        realized_pnl_today=0.0,
        daily_drawdown_pct=0.0,
        trade_count_today={},
        positions={},
    )


def test_position_sizing_cap(risk_agent, base_portfolio):
    # Propose 50% allocation ($5,000) -> must be capped to max 30% ($3,000)
    proposal = TradeProposal(
        symbol="BTC/USD",
        action=TradeAction.BUY,
        order_type=OrderType.MARKET,
        quantity=0.1,  # 0.1 * 50,000 = $5,000 (50% of portfolio)
        entry_price=50000.0,
        stop_loss_price=48000.0,
        take_profit_price=54000.0,
        position_pct=0.50,
        reasoning="Aggressive oversized test trade",
    )

    evaluation = risk_agent.evaluate_mathematical_rules(proposal, base_portfolio)
    assert evaluation.approved is True
    # Capital capped to 30% = $3,000 -> 3000 / 50000 = 0.06 qty
    assert evaluation.adjusted_quantity == pytest.approx(0.06, rel=1e-3)
    assert evaluation.adjusted_position_pct == 0.30


def test_mandatory_stop_loss_enforcement(risk_agent, base_portfolio):
    # Propose trade with NO stop loss -> Risk manager must force 4% stop loss
    proposal = TradeProposal(
        symbol="BTC/USD",
        action=TradeAction.BUY,
        order_type=OrderType.MARKET,
        quantity=0.05,
        entry_price=50000.0,
        stop_loss_price=0.0,  # Missing
        take_profit_price=54000.0,
        position_pct=0.25,
        reasoning="Test missing SL",
    )

    evaluation = risk_agent.evaluate_mathematical_rules(proposal, base_portfolio)
    assert evaluation.approved is True
    # 4% SL on 50,000 is 48,000
    assert evaluation.stop_loss_price == 48000.0


def test_circuit_breaker_drawdown(risk_agent, base_portfolio):
    # Breach 10% daily drawdown
    base_portfolio.daily_drawdown_pct = 0.11

    proposal = TradeProposal(
        symbol="BTC/USD",
        action=TradeAction.BUY,
        order_type=OrderType.MARKET,
        quantity=0.05,
        entry_price=50000.0,
        stop_loss_price=48000.0,
        take_profit_price=54000.0,
        position_pct=0.25,
        reasoning="Test circuit breaker",
    )

    evaluation = risk_agent.evaluate_mathematical_rules(proposal, base_portfolio)
    assert evaluation.approved is False
    assert evaluation.circuit_breaker_triggered is True
    assert "CIRCUIT BREAKER TRIGGERED" in evaluation.reasons[0]


def test_overtrading_limit(risk_agent, base_portfolio):
    # 10 trades already executed for BTC/USD today
    base_portfolio.trade_count_today["BTC/USD"] = 10

    proposal = TradeProposal(
        symbol="BTC/USD",
        action=TradeAction.BUY,
        order_type=OrderType.MARKET,
        quantity=0.05,
        entry_price=50000.0,
        stop_loss_price=48000.0,
        take_profit_price=54000.0,
        position_pct=0.25,
        reasoning="Test 11th trade",
    )

    evaluation = risk_agent.evaluate_mathematical_rules(proposal, base_portfolio)
    assert evaluation.approved is False
    assert "Overtrading limit reached" in evaluation.reasons[0]


def test_memory_layer_consecutive_losses(risk_agent, base_portfolio):
    # Simulate 3 previous consecutive loss trades in memory
    past_trades = [
        {"symbol": "BTC/USD", "message": "Stop-loss hit", "status": "STOP_LOSS", "reasoning": "Exit at loss"},
        {"symbol": "BTC/USD", "message": "Stop-loss hit", "status": "STOP_LOSS", "reasoning": "Exit at loss"},
        {"symbol": "BTC/USD", "message": "Stop-loss hit", "status": "STOP_LOSS", "reasoning": "Exit at loss"},
    ]

    proposal = TradeProposal(
        symbol="BTC/USD",
        action=TradeAction.BUY,
        order_type=OrderType.MARKET,
        quantity=0.04,  # $2,000 (20% of 10k)
        entry_price=50000.0,
        stop_loss_price=48000.0,
        take_profit_price=54000.0,
        position_pct=0.20,
        reasoning="Test memory tightening",
    )

    evaluation = risk_agent.evaluate_mathematical_rules(proposal, base_portfolio, recent_trades=past_trades)
    assert evaluation.approved is True
    # Quantity must be halved (0.04 -> 0.02)
    assert evaluation.adjusted_quantity == pytest.approx(0.02, rel=1e-3)
    assert evaluation.adjusted_position_pct == pytest.approx(0.10, rel=1e-3)
    assert any("CONSECUTIVE LOSSES DETECTED" in r for r in evaluation.reasons)

