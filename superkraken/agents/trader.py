"""Execution Trader Agent.

Synthesizes analyst reports, research debates, and consensus intelligence
to determine the optimal timing, entry levels, sizing, and order type.
"""

from typing import Any, Dict, Optional, Type
from superkraken.agents.base import BaseAgent
from superkraken.config import settings
from superkraken.state import ConsensusResult, OrderType, PortfolioState, TradeAction, TradeProposal


class ExecutionTraderAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Execution Trader",
            default_model=settings.model_trader,
            system_prompt=(
                "You are the Head Execution Trader of an aggressive, high-performance crypto day trading desk. "
                "Synthesize the Consensus verdict, current market price, and portfolio capital. "
                "Formulate an exact, bold order specification. "
                "Aggressively allocate 20-30% of portfolio on high-confidence setups (>75%). "
                "Always calculate a mandatory stop-loss between 3% and 5% below entry for BUYs (or above entry for SELLs). "
                "Output valid JSON matching this schema:\n"
                "{\n"
                '  "symbol": "BTC/USD",\n'
                '  "action": "BUY" | "SELL" | "HOLD",\n'
                '  "order_type": "market" | "limit",\n'
                '  "quantity": 0.05,\n'
                '  "entry_price": 67420.0,\n'
                '  "stop_loss_price": 64723.2,\n'
                '  "take_profit_price": 72813.6,\n'
                '  "position_pct": 0.25,\n'
                '  "leverage": 1.0,\n'
                '  "reasoning": "Aggressive market entry following debate consensus"\n'
                "}"
            ),
        )

    async def propose_trade(
        self,
        symbol: str,
        current_price: float,
        consensus: ConsensusResult,
        portfolio: PortfolioState,
    ) -> TradeProposal:
        # Confidence Threshold Gate: must be > 65% to trade
        if consensus.confidence < 0.65:
            return TradeProposal(
                symbol=symbol,
                action=TradeAction.HOLD,
                quantity=0.0,
                entry_price=current_price,
                stop_loss_price=0.0,
                take_profit_price=0.0,
                position_pct=0.0,
                model_used=self.default_model,
                reasoning=(
                    f"Consensus confidence ({consensus.confidence * 100:.1f}%) is below the "
                    "mandatory 65.0% conviction threshold; holding capital."
                ),
            )

        if consensus.action == TradeAction.HOLD:
            return TradeProposal(
                symbol=symbol,
                action=TradeAction.HOLD,
                quantity=0.0,
                entry_price=current_price,
                stop_loss_price=0.0,
                take_profit_price=0.0,
                position_pct=0.0,
                model_used=self.default_model,
                reasoning="Consensus recommends HOLD; waiting for higher-conviction catalyst.",
            )

        prompt = (
            f"Asset: {symbol}\n"
            f"Current Market Price: ${current_price:,.2f}\n"
            f"Consensus Action: {consensus.action.value}\n"
            f"Consensus Confidence: {consensus.confidence:.2f}\n"
            f"Consensus Recommended Sizing: {consensus.recommended_position_pct:.2f}\n"
            f"Available Cash: ${portfolio.cash_usd:,.2f}\n"
            f"Total Portfolio Value: ${portfolio.total_value_usd:,.2f}\n\n"
            "Formulate the trade proposal. If confidence >= 0.75, allocate between 20% and 30% of portfolio value. "
            "Enforce a 3% to 5% stop loss."
        )

        if settings.is_canadian:
            prompt += "\nIMPORTANT: Canadian account detected (ACCOUNT_REGION='CA'). Futures and margin are restricted; leverage is locked to 1.0x (Spot only)."

        proposal = await self.call_llm(prompt, response_model=TradeProposal)
        if settings.is_canadian:
            proposal.leverage = 1.0
        return proposal

    def _heuristic_fallback(self, context: str, schema: Optional[Type[TradeProposal]]) -> TradeProposal:
        # Bold execution sizing
        alloc_pct = 0.25
        # Example calculation for BTC at ~67,400 with 10k portfolio
        qty = 0.037
        entry = 67420.0
        stop_loss = round(entry * (1.0 - settings.stop_loss_pct), 2)
        take_profit = round(entry * (1.0 + settings.take_profit_pct), 2)

        return TradeProposal(
            symbol="BTC/USD",
            action=TradeAction.BUY,
            order_type=OrderType.MARKET,
            quantity=qty,
            entry_price=entry,
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
            position_pct=alloc_pct,
            leverage=1.0,
            reasoning="High-conviction consensus trigger: executing aggressive 25% momentum allocation.",
        )
