"""Node implementations for LangGraph multi-agent trading workflow."""

import logging
from typing import Any, Dict, List
from superkraken.agents.bear_researcher import BearishResearcherAgent
from superkraken.agents.bull_researcher import BullishResearcherAgent
from superkraken.agents.debate import DebateConsensusAgent
from superkraken.agents.fundamental import FundamentalAnalystAgent
from superkraken.agents.risk_manager import RiskManagerAgent
from superkraken.agents.sentiment import SentimentAnalystAgent
from superkraken.agents.technical import TechnicalAnalystAgent
from superkraken.agents.trader import ExecutionTraderAgent
from superkraken.indicators.technical import compute_all_indicators
from superkraken.state import (
    AnalystReport,
    Candle,
    ConsensusResult,
    PortfolioState,
    ResearcherArgument,
    TechnicalIndicators,
    TradeAction,
    TradeProposal,
    TradingDeskState,
)

logger = logging.getLogger(__name__)

# Initialize agent singletons
technical_agent = TechnicalAnalystAgent()
sentiment_agent = SentimentAnalystAgent()
fundamental_agent = FundamentalAnalystAgent()
bull_agent = BullishResearcherAgent()
bear_agent = BearishResearcherAgent()
debate_agent = DebateConsensusAgent()
trader_agent = ExecutionTraderAgent()
risk_agent = RiskManagerAgent()


async def technical_analyst_node(state: TradingDeskState) -> Dict[str, Any]:
    symbol = state["symbol"]
    current_price = state["current_price"]
    candles = [Candle.model_validate(c) for c in (state.get("candles") or [])]
    indicators = compute_all_indicators(candles)

    report = await technical_agent.analyze(symbol, current_price, indicators, recent_candles=candles)
    return {
        "technical_report": report.model_dump(mode="json"),
        "indicators": indicators.model_dump(mode="json"),
        "agent_states": {"technical": "COMPLETED"},
    }


async def sentiment_analyst_node(state: TradingDeskState) -> Dict[str, Any]:
    symbol = state["symbol"]
    current_price = state["current_price"]
    sentiment_ctx = state.get("market_sentiment") or {}

    report = await sentiment_agent.analyze(symbol, current_price, sentiment_ctx)
    return {
        "sentiment_report": report.model_dump(mode="json"),
        "agent_states": {"sentiment": "COMPLETED"},
    }


async def fundamental_analyst_node(state: TradingDeskState) -> Dict[str, Any]:
    symbol = state["symbol"]
    current_price = state["current_price"]
    order_book = state.get("order_book") or {}

    report = await fundamental_agent.analyze(symbol, current_price, order_book)
    return {
        "fundamental_report": report.model_dump(mode="json"),
        "agent_states": {"fundamental": "COMPLETED"},
    }


async def bull_researcher_node(state: TradingDeskState) -> Dict[str, Any]:
    symbol = state["symbol"]
    current_price = state["current_price"]

    reports = []
    for key in ["technical_report", "sentiment_report", "fundamental_report"]:
        val = state.get(key)
        if val is not None:
            reports.append(AnalystReport.model_validate(val))

    argument = await bull_agent.research(symbol, current_price, reports)
    return {
        "bull_argument": argument.model_dump(mode="json"),
        "agent_states": {"bull_researcher": "COMPLETED"},
    }


async def bear_researcher_node(state: TradingDeskState) -> Dict[str, Any]:
    symbol = state["symbol"]
    current_price = state["current_price"]

    reports = []
    for key in ["technical_report", "sentiment_report", "fundamental_report"]:
        val = state.get(key)
        if val is not None:
            reports.append(AnalystReport.model_validate(val))

    argument = await bear_agent.research(symbol, current_price, reports)
    return {
        "bear_argument": argument.model_dump(mode="json"),
        "agent_states": {"bear_researcher": "COMPLETED"},
    }


async def debate_consensus_node(state: TradingDeskState) -> Dict[str, Any]:
    symbol = state["symbol"]
    current_price = state["current_price"]

    bull = ResearcherArgument.model_validate(state["bull_argument"])
    bear = ResearcherArgument.model_validate(state["bear_argument"])

    consensus, rounds = await debate_agent.adjudicate(symbol, current_price, bull, bear)
    return {
        "consensus": consensus.model_dump(mode="json"),
        "debate_rounds": [r.model_dump(mode="json") for r in (rounds or [])],
        "agent_states": {"debate": "COMPLETED"},
    }


async def execution_trader_node(state: TradingDeskState) -> Dict[str, Any]:
    symbol = state["symbol"]
    current_price = state["current_price"]
    consensus = ConsensusResult.model_validate(state["consensus"])
    portfolio = PortfolioState.model_validate(state.get("portfolio") or {})

    proposal = await trader_agent.propose_trade(symbol, current_price, consensus, portfolio)
    return {
        "proposal": proposal.model_dump(mode="json"),
        "agent_states": {"trader": "COMPLETED"},
    }


async def risk_manager_node(state: TradingDeskState) -> Dict[str, Any]:
    proposal = TradeProposal.model_validate(state["proposal"])
    portfolio = PortfolioState.model_validate(state.get("portfolio") or {})

    evaluation = await risk_agent.audit_trade(proposal, portfolio)
    return {
        "risk_evaluation": evaluation.model_dump(mode="json"),
        "agent_states": {"risk_manager": "COMPLETED"},
    }
