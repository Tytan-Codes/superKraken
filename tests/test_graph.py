"""Unit tests for LangGraph multi-agent trading workflow."""

import pytest
from superkraken.graph.workflow import trading_graph
from superkraken.state import Candle, PortfolioState


@pytest.mark.asyncio
async def test_trading_graph_full_cycle():
    # Synthetic test candles
    candles = [
        Candle(
            timestamp=float(i * 60),
            open=67000.0 + i,
            high=67100.0 + i,
            low=66900.0 + i,
            close=67050.0 + i,
            volume=25.0,
        )
        for i in range(50)
    ]

    initial_state = {
        "symbol": "BTC/USD",
        "current_price": 67100.0,
        "candles": [c.model_dump() for c in candles],
        "market_sentiment": {
            "fear_greed_index": 70,
            "sentiment_label": "Greed",
            "social_volume_24h": "High",
            "recent_headline": "Bitcoin surges past key moving averages.",
        },
        "order_book": {"bid_volume": 120.0, "ask_volume": 80.0, "imbalance": 0.20},
        "portfolio": PortfolioState(total_value_usd=10000.0, cash_usd=10000.0).model_dump(),
        "agent_states": {},
    }

    final_state = await trading_graph.ainvoke(initial_state)

    # Verify all layers executed and contributed to state
    assert "technical_report" in final_state
    assert "sentiment_report" in final_state
    assert "fundamental_report" in final_state
    assert "bull_argument" in final_state
    assert "bear_argument" in final_state
    assert "consensus" in final_state
    assert "proposal" in final_state
    assert "risk_evaluation" in final_state

    # Verify consensus and proposal schemas
    assert final_state["consensus"]["action"] in ["BUY", "SELL", "HOLD"]
    assert 0.0 <= final_state["consensus"]["confidence"] <= 1.0
    assert final_state["risk_evaluation"]["approved"] is True


@pytest.mark.asyncio
async def test_confidence_threshold_gate():
    from superkraken.agents.trader import ExecutionTraderAgent
    from superkraken.state import ConsensusResult, TradeAction

    trader = ExecutionTraderAgent()
    low_conf_consensus = ConsensusResult(
        action=TradeAction.BUY,
        confidence=0.58,  # Below 65% threshold
        summary="Weak consensus",
        bull_score=0.6,
        bear_score=0.55,
        recommended_position_pct=0.1,
    )
    portfolio = PortfolioState(total_value_usd=10000.0, cash_usd=10000.0)

    proposal = await trader.propose_trade("BTC/USD", 67000.0, low_conf_consensus, portfolio)
    assert proposal.action == TradeAction.HOLD
    assert "below the mandatory 65.0% conviction threshold" in proposal.reasoning

