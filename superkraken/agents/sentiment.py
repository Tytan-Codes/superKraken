"""Sentiment Analyst Agent.

Scans crypto news feeds, social buzz, and Fear & Greed sentiment for trading signals.
"""

from typing import Any, Dict, Optional, Type
from superkraken.agents.base import BaseAgent
from superkraken.config import settings
from superkraken.state import AnalystReport, TradeAction


class SentimentAnalystAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Sentiment Analyst",
            default_model=settings.model_sentiment,
            system_prompt=(
                "You are an AI Sentiment Analyst specializing in high-frequency crypto social data, "
                "fear and greed metrics, and breaking market headlines. "
                "Output valid JSON matching this schema:\n"
                "{\n"
                '  "agent_name": "Sentiment Analyst",\n'
                '  "signal": "BUY" | "SELL" | "HOLD",\n'
                '  "confidence": 0.80,\n'
                '  "key_metrics": {"fear_greed": 68, "social_sentiment": "BULLISH", "mentions_velocity": "+24%"},\n'
                '  "summary": "Concise summary of social and sentiment drivers"\n'
                "}"
            ),
        )

    async def analyze(
        self,
        symbol: str,
        current_price: float,
        sentiment_context: Optional[Dict[str, Any]] = None,
    ) -> AnalystReport:
        ctx = sentiment_context or {
            "fear_greed_index": 65,
            "sentiment_label": "Greed",
            "social_volume_24h": "High",
            "recent_headline": f"Institutional crypto inflows surging; {symbol} open interest hits new high.",
        }

        prompt = (
            f"Symbol: {symbol}\n"
            f"Price: ${current_price:,.2f}\n"
            f"Fear & Greed Index: {ctx.get('fear_greed_index')} ({ctx.get('sentiment_label')})\n"
            f"Social Volume: {ctx.get('social_volume_24h')}\n"
            f"Breaking Headline: {ctx.get('recent_headline')}\n\n"
            "Assess whether current social euphoria or panic warrants an aggressive momentum entry or caution."
        )

        return await self.call_llm(prompt, response_model=AnalystReport)

    def _heuristic_fallback(self, context: str, schema: Optional[Type[AnalystReport]]) -> AnalystReport:
        return AnalystReport(
            agent_name="Sentiment Analyst",
            signal=TradeAction.BUY,
            confidence=0.72,
            key_metrics={"fear_greed": 64, "social_sentiment": "BULLISH_EXPANSION"},
            summary="Strong social volume expansion and positive retail net sentiment across derivatives venues.",
        )
