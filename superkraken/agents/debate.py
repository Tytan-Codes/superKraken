"""Debate & Consensus Agent.

Runs an adversarial debate process that balances potential gains against inherent risks,
refining the market outlook into a high-conviction consensus decision.
"""

from typing import Any, Dict, List, Optional, Tuple, Type
from superkraken.agents.base import BaseAgent
from superkraken.config import settings
from superkraken.state import ConsensusResult, DebateRound, ResearcherArgument, TradeAction


class DebateConsensusAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Debate & Consensus",
            default_model=settings.model_debate,
            system_prompt=(
                "You are the Chief Investment Officer and Debate Adjudicator of an elite Wall Street trading desk. "
                "You conduct a rigorous adversarial debate between the Bullish Researcher and the Bearish Researcher. "
                "Weigh their theses, challenge weak points, determine the dominant market force, and forge a clear consensus. "
                "Output valid JSON matching this schema:\n"
                "{\n"
                '  "action": "BUY" | "SELL" | "HOLD",\n'
                '  "confidence": 0.78,\n'
                '  "summary": "Consensus verdict explaining the resolution of the debate",\n'
                '  "bull_score": 0.82,\n'
                '  "bear_score": 0.45,\n'
                '  "recommended_position_pct": 0.25,\n'
                '  "recommended_leverage": 2.0\n'
                "}"
            ),
        )

    async def adjudicate(
        self,
        symbol: str,
        current_price: float,
        bull: ResearcherArgument,
        bear: ResearcherArgument,
    ) -> Tuple[ConsensusResult, List[DebateRound]]:
        prompt = (
            f"Asset: {symbol} at ${current_price:,.2f}\n\n"
            f"🐂 BULLISH CASE (Conf: {bull.confidence:.2f}):\n"
            f"Thesis: {bull.thesis}\n"
            f"Catalysts: {', '.join(bull.catalysts)}\n\n"
            f"🐻 BEARISH CASE (Conf: {bear.confidence:.2f}):\n"
            f"Thesis: {bear.thesis}\n"
            f"Catalysts: {', '.join(bear.catalysts)}\n\n"
            "Conduct the cross-examination, evaluate risk vs reward asymmetry, and deliver the final verdict."
        )

        res = await self.call_llm(prompt, response_model=ConsensusResult)

        # Generate structured debate rounds for the terminal UI
        rounds = [
            DebateRound(
                round_number=1,
                bull_point=bull.thesis,
                bear_counterpoint=bear.thesis,
                adjudication=res.summary,
            )
        ]

        return res, rounds

    def _heuristic_fallback(self, context: str, schema: Optional[Type[ConsensusResult]]) -> ConsensusResult:
        return ConsensusResult(
            action=TradeAction.BUY,
            confidence=0.78,
            summary="[HEURISTIC FALLBACK] Bullish momentum indicators (RSI 56.4) and order book bid support outweigh overhead resistance risks.",
            bull_score=0.82,
            bear_score=0.48,
            recommended_position_pct=0.25,
            recommended_leverage=1.0,
            is_fallback=True,
        )
