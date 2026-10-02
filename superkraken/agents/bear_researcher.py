"""Bearish Researcher Agent.

Focuses relentlessly on identifying inherent risks, downside exposure,
liquidity traps, false breakouts, and negative catalysts.
"""

from typing import Any, Dict, List, Optional, Type
from superkraken.agents.base import BaseAgent
from superkraken.config import settings
from superkraken.state import AnalystReport, ResearcherArgument


class BearishResearcherAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Bearish Researcher",
            default_model=settings.model_bear,
            system_prompt=(
                "You are the Bearish Researcher of a quantitative Wall Street day trading desk. "
                "Your role is the Devil's Advocate. Challenge upside assumptions, uncover hidden risks, "
                "detect overextension, declining volume divergences, resistance barriers, and macro headwinds. "
                "CRITICAL REQUIREMENT: You MUST explicitly cite actual numerical indicator values in your arguments "
                "(e.g., 'RSI is at 56.4 approaching upper range' or 'Price is nearing upper Bollinger Band at $88,200'). "
                "Never make vague or generic claims without citing exact data points. "
                "Output strictly valid JSON matching this schema:\n"
                "{\n"
                '  "perspective": "BEARISH",\n'
                '  "agent_name": "Bearish Researcher",\n'
                '  "thesis": "Detailed bearish thesis quoting exact indicator levels and resistance barriers",\n'
                '  "catalysts": ["Volume divergence on ascending price action", "Overhead resistance at $88,000"],\n'
                '  "key_levels": {"resistance": 88000.0, "breakdown_target": 84200.0, "stop_risk": 88900.0},\n'
                '  "confidence": 0.65\n'
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
        for r in analyst_reports:
            ind_text = f" Indicators: {r.indicators}" if r.indicators else ""
            reports_summary.append(
                f"- {r.agent_name}: Signal={r.signal.value}, Conf={r.confidence:.2f},{ind_text} Summary: {r.summary}"
            )
        summary_str = "\n".join(reports_summary)

        prompt = (
            f"Asset: {symbol} at ${current_price:,.2f}\n"
            f"Analyst Reports & Indicators:\n{summary_str}\n\n"
            "Build the most rigorous Bearish argument. Cite specific indicator numbers and failure traps. Output JSON."
        )

        return await self.call_llm(prompt, response_model=ResearcherArgument)

    def _heuristic_fallback(self, context: str, schema: Optional[Type[ResearcherArgument]]) -> ResearcherArgument:
        return ResearcherArgument(
            perspective="BEARISH",
            agent_name="Bearish Researcher",
            thesis="[HEURISTIC FALLBACK] While RSI is at 56.4, upper Bollinger Band resistance near $88,200 and declining spot volume create an asymmetric risk of a liquidity squeeze.",
            catalysts=[
                "Upper Bollinger Band barrier approaching",
                "Volume divergence against ascending price action",
                "Risk of long liquidation sweeps below $85,000",
            ],
            key_levels={"resistance": 88200.0, "breakdown_target": 84800.0, "stop_risk": 88800.0},
            confidence=0.55,
            is_fallback=True,
        )
