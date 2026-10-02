"""Bullish Researcher Agent.

Focuses aggressively on identifying potential gains, upside momentum, breakout levels,
and positive market catalysts.
"""

from typing import Any, Dict, List, Optional, Type
from superkraken.agents.base import BaseAgent
from superkraken.config import settings
from superkraken.state import AnalystReport, ResearcherArgument


class BullishResearcherAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Bullish Researcher",
            default_model=settings.model_bull,
            system_prompt=(
                "You are the Bullish Researcher of a quantitative Wall Street day trading desk. "
                "Your role is to formulate the strongest possible long thesis. "
                "CRITICAL REQUIREMENT: You MUST explicitly cite actual numerical indicator values in your arguments "
                "(e.g., 'RSI is at 58.2 showing strong expansion' or 'Price ($86,534) is holding 1.8% above the 50 EMA ($85,020)'). "
                "Never make vague or generic claims without citing exact data points. "
                "Output strictly valid JSON matching this schema:\n"
                "{\n"
                '  "perspective": "BULLISH",\n'
                '  "agent_name": "Bullish Researcher",\n'
                '  "thesis": "Detailed bullish thesis explicitly quoting exact RSI, MACD, and EMA numbers",\n'
                '  "catalysts": ["RSI 58.2 expanding above midpoint", "MACD histogram +14.8 expanding", "Price holding above 20 EMA"],\n'
                '  "key_levels": {"entry": 86500.0, "target": 89200.0, "invalidation": 84800.0},\n'
                '  "confidence": 0.85\n'
                "}"
            ),
        )

    async def research(
        self,
        symbol: str,
        current_price: float,
        analyst_reports: List[AnalystReport],
    ) -> ResearcherArgument:
        reports_summary = []
        for r in (analyst_reports or []):
            if not r:
                continue
            ind_text = f" Indicators: {r.indicators}" if getattr(r, "indicators", None) else ""
            reports_summary.append(
                f"- {r.agent_name}: Signal={r.signal.value}, Conf={r.confidence:.2f},{ind_text} Summary: {r.summary}"
            )
        summary_str = "\n".join(reports_summary)

        prompt = (
            f"Asset: {symbol} at ${current_price:,.2f}\n"
            f"Analyst Reports & Indicators:\n{summary_str}\n\n"
            "Build the most compelling Bullish thesis. Cite specific RSI, MACD, EMA, and level numbers. Output JSON."
        )

        return await self.call_llm(prompt, response_model=ResearcherArgument)

    def _heuristic_fallback(self, context: str, schema: Optional[Type[ResearcherArgument]]) -> ResearcherArgument:
        return ResearcherArgument(
            perspective="BULLISH",
            agent_name="Bullish Researcher",
            thesis="[HEURISTIC FALLBACK] RSI at 56.4 maintains bullish momentum above the 50 median while MACD histogram (+14.8) confirms positive momentum above the 20 EMA.",
            catalysts=[
                "RSI 56.4 momentum confirmation",
                "MACD histogram expanding (+14.8)",
                "Spot price maintaining support above EMA 20",
            ],
            key_levels={"entry": 86530.0, "target": 89200.0, "invalidation": 84900.0},
            confidence=0.82,
            is_fallback=True,
        )
