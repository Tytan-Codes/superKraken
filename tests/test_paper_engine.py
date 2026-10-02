"""Unit tests for Paper Trading Execution Engine."""

import pytest
from superkraken.execution.paper_engine import PaperTradingEngine
from superkraken.state import OrderType, TradeAction


@pytest.fixture
def temp_engine(tmp_path):
    state_file = tmp_path / "paper_test.json"
    engine = PaperTradingEngine(state_file=state_file, initial_balance=10000.0)
    return engine


def test_buy_execution_and_fees(temp_engine):
    # Buy 0.1 BTC at $60,000 market price ($6,000 notional)
    res = temp_engine.execute_order(
        symbol="BTC/USD",
        action=TradeAction.BUY,
        quantity=0.1,
        current_market_price=60000.0,
        stop_loss=57600.0,
        take_profit=64800.0,
    )

    assert res.success is True
    assert res.status == "FILLED"
    # Price had slight upward slippage
    assert res.filled_price > 60000.0
    assert res.fee > 0.0

    # Portfolio checks
    assert "BTC/USD" in temp_engine.portfolio.positions
    pos = temp_engine.portfolio.positions["BTC/USD"]
    assert pos.quantity == 0.1
    assert temp_engine.portfolio.cash_usd < 4000.0


def test_stop_loss_trigger(temp_engine):
    # Buy 0.1 BTC with SL at $58,000
    temp_engine.execute_order(
        symbol="BTC/USD",
        action=TradeAction.BUY,
        quantity=0.1,
        current_market_price=60000.0,
        stop_loss=58000.0,
    )
    assert "BTC/USD" in temp_engine.portfolio.positions

    # Market price drops to $57,500 (below SL)
    temp_engine.update_market_prices({"BTC/USD": 57500.0})

    # Position should be closed out by stop-loss
    assert "BTC/USD" not in temp_engine.portfolio.positions
    assert temp_engine.portfolio.realized_pnl_today < 0.0


def test_flatten_all_positions(temp_engine):
    temp_engine.execute_order(
        symbol="ETH/USD",
        action=TradeAction.BUY,
        quantity=1.0,
        current_market_price=3000.0,
    )
    assert len(temp_engine.portfolio.positions) == 1

    results = temp_engine.flatten_all_positions({"ETH/USD": 3100.0})
    assert len(results) == 1
    assert results[0].action == TradeAction.SELL
    assert len(temp_engine.portfolio.positions) == 0
