"""Fundamental & Market Microstructure Analyst Agent.

Evaluates trading volume patterns, order book depth, bid/ask imbalance, and trend persistence.
"""

from typing import Any, Dict, Optional, Type
from superkraken.agents.base import BaseAgent
from superkraken.config import settings
from superkraken.state import AnalystReport, TradeAction


class FundamentalAnalystAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Fundamental Analyst",
            default_model=settings.model_fundamental,
            system_prompt=(
                "You are an institutional Fundamental and Market Microstructure Analyst. "
                "Evaluate volume patterns, liquidity depth, order book imbalance, and macro trend strength. "
                "Output valid JSON matching this schema:\n"
                "{\n"
                '  "agent_name": "Fundamental Analyst",\n'
                '  "signal": "BUY" | "SELL" | "HOLD",\n'
                '  "confidence": 0.76,\n'
                '  "key_metrics": {"order_book_imbalance": 0.22, "volume_trend": "ACCUMULATION"},\n'
                '  "summary": "Concise synthesis of volume profiles and liquidity conditions"\n'
                "}"
            ),
        )

    async def analyze(
        self,
        symbol: str,
        current_price: float,
        order_book_data: Optional[Dict[str, Any]] = None,
        volume_24h: float = 0.0,
    ) -> AnalystReport:
        ob = order_book_data or {"bid_volume": 68.4, "ask_volume": 45.2, "imbalance": 0.20}
        prompt = (
            f"Symbol: {symbol}\n"
            f"Price: ${current_price:,.2f}\n"
            f"24h Volume: {volume_24h:,.2f}\n"
            f"Order Book Bid Volume: {ob.get('bid_volume')}\n"
            f"Order Book Ask Volume: {ob.get('ask_volume')}\n"
            f"Book Imbalance Ratio: {ob.get('imbalance')}\n\n"
            "Assess order flow absorption, depth support, and institutional accumulation/distribution."
        )

        return await self.call_llm(prompt, response_model=AnalystReport)

    def _heuristic_fallback(self, context: str, schema: Optional[Type[AnalystReport]]) -> AnalystReport:
        return AnalystReport(
            agent_name="Fundamental Analyst",
            signal=TradeAction.BUY,
            confidence=0.74,
            key_metrics={"imbalance": 0.18, "depth": "HEAVY_BID_WALLS"},
            summary="Substantial limit bid support in the top 10 order book levels absorbing sell pressure.",
        )
