"""LangGraph workflow definition for superKraken multi-agent trading desk."""

import logging
from typing import Any, Dict
from langgraph.graph import END, START, StateGraph
from superkraken.graph.nodes import (
    bear_researcher_node,
    bull_researcher_node,
    debate_consensus_node,
    execution_trader_node,
    fundamental_analyst_node,
    risk_manager_node,
    sentiment_analyst_node,
    technical_analyst_node,
)
from superkraken.state import TradingDeskState

logger = logging.getLogger(__name__)


def build_trading_graph() -> StateGraph:
    """Build the compiled LangGraph workflow replicating TradingAgents."""
    builder = StateGraph(TradingDeskState)

    # 1. Add Analyst Nodes
    builder.add_node("technical_analyst", technical_analyst_node)
    builder.add_node("sentiment_analyst", sentiment_analyst_node)
    builder.add_node("fundamental_analyst", fundamental_analyst_node)

    # 2. Add Researcher Nodes
    builder.add_node("bull_researcher", bull_researcher_node)
    builder.add_node("bear_researcher", bear_researcher_node)

    # 3. Add Debate & Consensus Node
    builder.add_node("debate_consensus", debate_consensus_node)

    # 4. Add Execution Trader Node
    builder.add_node("execution_trader", execution_trader_node)

    # 5. Add Risk Manager Node
    builder.add_node("risk_manager", risk_manager_node)

    # Define Graph Edges:
    # Fan out from START to all 3 analysts
    builder.add_edge(START, "technical_analyst")
    builder.add_edge(START, "sentiment_analyst")
    builder.add_edge(START, "fundamental_analyst")

    # Connect analysts into researchers
    builder.add_edge("technical_analyst", "bull_researcher")
    builder.add_edge("sentiment_analyst", "bull_researcher")
    builder.add_edge("fundamental_analyst", "bull_researcher")

    builder.add_edge("technical_analyst", "bear_researcher")
    builder.add_edge("sentiment_analyst", "bear_researcher")
    builder.add_edge("fundamental_analyst", "bear_researcher")

    # Connect researchers into adversarial debate
    builder.add_edge("bull_researcher", "debate_consensus")
    builder.add_edge("bear_researcher", "debate_consensus")

    # Connect consensus into trader
    builder.add_edge("debate_consensus", "execution_trader")

    # Connect trader into risk manager
    builder.add_edge("execution_trader", "risk_manager")

    # Final edge to END
    builder.add_edge("risk_manager", END)

    return builder.compile()


# Compiled trading graph singleton
trading_graph = build_trading_graph()
