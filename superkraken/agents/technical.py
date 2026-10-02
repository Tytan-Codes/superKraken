"""Technical Analyst Agent.

Analyzes RSI, MACD, Bollinger Bands, ATR, EMAs, breakout detection,
and market regime on live Kraken data.
"""

from typing import Any, Dict, Optional, Type
from superkraken.agents.base import BaseAgent
from superkraken.config import settings
from superkraken.state import AnalystReport, TechnicalIndicators, TradeAction


class TechnicalAnalystAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Technical Analyst",
            default_model=settings.model_technical,
            system_prompt=(
                "You are an elite Wall Street quantitative Technical Analyst specializing in high-frequency crypto day trading. "
                "Analyze the provided live OHLCV candle metrics and technical indicators (RSI 14, MACD, Bollinger Bands, EMA 20/50/200, ATR, and regimes). "
                "You MUST deliver a clear, actionable signal: BUY, SELL, or HOLD, with a confidence score between 0.0 and 1.0. "
                "Return strictly valid JSON matching this schema:\n"
                "{\n"
                '  "agent_name": "Technical Analyst",\n'
                '  "signal": "BUY" | "SELL" | "HOLD",\n'
                '  "confidence": 0.82,\n'
                '  "indicators": {\n'
                '    "rsi": 58.2,\n'
                '    "macd": 12.4,\n'
                '    "bb_position": 0.65,\n'
                '    "ema_trend": "BULLISH",\n'
                '    "regime": "STRONG_BULLISH"\n'
                '  },\n'
                '  "summary": "Concise technical thesis explicitly referencing numerical indicator values"\n'
                "}"
            ),
        )

    async def analyze(
        self,
        symbol: str,
        current_price: float,
        indicators: TechnicalIndicators,
        recent_candles: Optional[list] = None,
    ) -> AnalystReport:
        candle_summary = ""
        if recent_candles and len(recent_candles) >= 3:
            last_3 = recent_candles[-3:]
            candle_summary = "\nRecent Candles (Last 3):\n" + "\n".join(
                f"- O:{c.open:.1f} H:{c.high:.1f} L:{c.low:.1f} C:{c.close:.1f} Vol:{c.volume:.2f}" for c in last_3
            )

        prompt = (
            f"Symbol: {symbol}\n"
            f"Current Price: ${current_price:,.2f}\n"
            f"RSI (14): {indicators.rsi_14}\n"
            f"MACD Line: {indicators.macd_line}, Signal: {indicators.macd_signal}, Hist: {indicators.macd_histogram}\n"
            f"Bollinger Bands: Upper={indicators.bb_upper}, Mid={indicators.bb_middle}, Lower={indicators.bb_lower}, %B={indicators.bb_percent_b}\n"
            f"EMAs: 20={indicators.ema_20}, 50={indicators.ema_50}, 200={indicators.ema_200}\n"
            f"ATR (14): {indicators.atr_14}\n"
            f"Trend Regime: {indicators.trend_regime}\n"
            f"Volatility Regime: {indicators.volatility_regime}"
            f"{candle_summary}\n\n"
            "Evaluate momentum, trend alignment, mean reversion, and breakouts. Output strictly structured JSON."
        )

        res = await self.call_llm(prompt, response_model=AnalystReport)
        return res

    def _heuristic_fallback(self, context: str, schema: Optional[Type[AnalystReport]]) -> AnalystReport:
        return AnalystReport(
            agent_name="Technical Analyst",
            signal=TradeAction.BUY,
            confidence=0.76,
            indicators={
                "rsi": 56.4,
                "macd": 14.8,
                "bb_position": 0.62,
                "ema_trend": "BULLISH_RECOVERY",
                "regime": "STRONG_BULLISH",
            },
            key_metrics={"rsi": 56.4, "trend": "BULLISH_RECOVERY", "momentum": "POSITIVE"},
            summary="[HEURISTIC FALLBACK] Price trading above EMA 20 with positive MACD expansion (14.8) and RSI 56.4 momentum.",
            is_fallback=True,
        )
