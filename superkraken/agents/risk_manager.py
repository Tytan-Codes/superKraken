"""Risk Manager Agent.

Enforces strict position sizing limits, mandatory stop-losses,
daily drawdown circuit breakers, and overtrading caps.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from superkraken.agents.base import BaseAgent
from superkraken.config import settings
from superkraken.state import PortfolioState, RiskEvaluation, TradeAction, TradeProposal

logger = logging.getLogger(__name__)


class RiskManagerAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Risk Manager",
            default_model=settings.model_risk,
            system_prompt=(
                "You are the Chief Risk Officer of an institutional crypto proprietary trading firm. "
                "Your word is absolute law. Audit trade proposals against strict capital preservation rules:\n"
                "1. Maximum 30% position size per trade.\n"
                "2. Mandatory stop-loss strictly between 3% and 5% of entry price.\n"
                "3. 10% daily drawdown circuit breaker: halt all trading if breached.\n"
                "4. Max 10 trades per symbol per day.\n"
                "Approve, adjust, or reject the trade proposal."
            ),
        )

    def evaluate_mathematical_rules(
        self,
        proposal: TradeProposal,
        portfolio: PortfolioState,
        recent_trades: Optional[List[Dict[str, Any]]] = None,
    ) -> RiskEvaluation:
        """Deterministic safety check that cannot be bypassed by LLM hallucination."""
        reasons: List[str] = []
        approved = True
        circuit_breaker = False

        trades_today = portfolio.trade_count_today.get(proposal.symbol, 0)
        drawdown_pct = portfolio.daily_drawdown_pct

        # 1. Circuit Breaker Check: 10% daily drawdown
        if drawdown_pct >= settings.daily_drawdown_limit_pct:
            approved = False
            circuit_breaker = True
            reasons.append(
                f"CIRCUIT BREAKER TRIGGERED: Daily drawdown ({drawdown_pct * 100:.1f}%) "
                f"exceeds limit ({settings.daily_drawdown_limit_pct * 100:.1f}%). Halting all trades."
            )
            return RiskEvaluation(
                approved=False,
                adjusted_quantity=0.0,
                adjusted_position_pct=0.0,
                stop_loss_price=proposal.stop_loss_price,
                reasons=reasons,
                drawdown_pct=drawdown_pct,
                trades_today=trades_today,
                circuit_breaker_triggered=True,
            )

        # 2. Overtrading Check: Max 10 trades per symbol daily
        if trades_today >= settings.max_trades_per_symbol_daily:
            approved = False
            reasons.append(
                f"Overtrading limit reached: {trades_today}/{settings.max_trades_per_symbol_daily} trades today for {proposal.symbol}."
            )
            return RiskEvaluation(
                approved=False,
                adjusted_quantity=0.0,
                adjusted_position_pct=0.0,
                stop_loss_price=proposal.stop_loss_price,
                reasons=reasons,
                drawdown_pct=drawdown_pct,
                trades_today=trades_today,
            )

        if proposal.action == TradeAction.HOLD:
            return RiskEvaluation(
                approved=True,
                adjusted_quantity=0.0,
                adjusted_position_pct=0.0,
                stop_loss_price=0.0,
                reasons=["HOLD proposal acknowledged."],
                drawdown_pct=drawdown_pct,
                trades_today=trades_today,
            )

        # 3. Position Sizing Cap: Max 30% of total portfolio value
        max_capital = portfolio.total_value_usd * settings.max_position_size_pct
        proposed_notional = proposal.quantity * proposal.entry_price
        adjusted_qty = proposal.quantity
        adjusted_pct = proposal.position_pct

        if proposed_notional > max_capital:
            adjusted_qty = max_capital / proposal.entry_price if proposal.entry_price > 0 else 0.0
            adjusted_pct = settings.max_position_size_pct
            reasons.append(
                f"Position size scaled down to max allowed {settings.max_position_size_pct * 100:.0f}% (${max_capital:,.2f})."
            )

        # 3b. Memory Layer: Check last 5 trades for consecutive losses
        from superkraken.storage.database import db
        history = recent_trades if recent_trades is not None else db.get_recent_trades(limit=5)
        consecutive_losses = 0
        for t in history:
            msg = (t.get("message") or "").lower()
            reason = (t.get("reasoning") or "").lower()
            status = (t.get("status") or "").lower()
            if "loss" in msg or "stop" in msg or "loss" in reason or "loss" in status:
                consecutive_losses += 1
            elif "profit" in msg or "win" in reason or "profit" in reason:
                break

        if consecutive_losses >= 3:
            adjusted_qty *= 0.5
            adjusted_pct *= 0.5
            reasons.append(
                f"[CONSECUTIVE LOSSES DETECTED] Last {consecutive_losses} trades were losses. "
                f"Automatically tightened position sizing by 50% for risk preservation."
            )

        # 3c. Leverage Gate
        if settings.is_canadian:
            # Canadian account: skip leverage approval step entirely, locked to 1.0x spot
            proposal.leverage = 1.0
        else:
            # US/GLOBAL: Full leverage check
            if proposal.leverage > settings.max_allowed_leverage:
                reasons.append(
                    f"Leverage reduced from {proposal.leverage:.1f}x to maximum allowed {settings.max_allowed_leverage:.1f}x."
                )
                proposal.leverage = settings.max_allowed_leverage

        # 4. Mandatory Stop-Loss Validation (3% to 5%)
        entry = proposal.entry_price
        sl = proposal.stop_loss_price
        if entry > 0:
            actual_sl_pct = abs(entry - sl) / entry
            if sl <= 0 or actual_sl_pct > 0.051 or actual_sl_pct < 0.029:
                target_sl_pct = settings.stop_loss_pct  # e.g. 0.04 (4%)
                if proposal.action == TradeAction.BUY:
                    sl = round(entry * (1.0 - target_sl_pct), 2)
                else:
                    sl = round(entry * (1.0 + target_sl_pct), 2)
                reasons.append(f"Adjusted stop-loss to strict {target_sl_pct * 100:.1f}% (${sl:,.2f}).")

        # 5. Cash Availability Check
        if proposal.action == TradeAction.BUY:
            required_cash = adjusted_qty * entry
            if required_cash > portfolio.cash_usd:
                adjusted_qty = (portfolio.cash_usd * 0.95) / entry if entry > 0 else 0.0
                adjusted_pct = (adjusted_qty * entry) / portfolio.total_value_usd if portfolio.total_value_usd > 0 else 0.0
                reasons.append(f"Adjusted for available cash: ${portfolio.cash_usd:,.2f}.")

        if adjusted_qty <= 0:
            approved = False
            reasons.append("Insufficient remaining purchasing power for minimum trade size.")

        if not reasons:
            reasons.append("Risk parameters strictly validated and approved.")

        return RiskEvaluation(
            approved=approved,
            adjusted_quantity=round(adjusted_qty, 6),
            adjusted_position_pct=round(adjusted_pct, 4),
            stop_loss_price=sl,
            reasons=reasons,
            drawdown_pct=drawdown_pct,
            trades_today=trades_today,
            circuit_breaker_triggered=circuit_breaker,
        )

    async def audit_trade(
        self,
        proposal: TradeProposal,
        portfolio: PortfolioState,
        recent_trades: Optional[List[Dict[str, Any]]] = None,
    ) -> RiskEvaluation:
        """Run deterministic mathematical audit followed by qualitative assessment."""
        # Always run deterministic mathematical enforcement first
        math_eval = self.evaluate_mathematical_rules(proposal, portfolio, recent_trades=recent_trades)
        math_eval.model_used = self.default_model

        if math_eval.approved and proposal.action != TradeAction.HOLD:
            prompt = (
                f"AUDIT PROPOSAL: {proposal.action.value} {math_eval.adjusted_quantity} {proposal.symbol} @ ${proposal.entry_price:,.2f}\n"
                f"Stop Loss: ${math_eval.stop_loss_price:,.2f} | Portfolio Drawdown: {math_eval.drawdown_pct*100:.1f}%\n"
                f"Provide a 1-sentence risk officer confirmation or condition."
            )
            try:
                commentary = await self.call_llm(prompt)
                if commentary:
                    cleaned_comment = commentary.strip().replace("\n", " ")[:160]
                    math_eval.reasons.append(f"CRO Sign-off: {cleaned_comment}")
            except Exception as e:
                logger.warning(f"Qualitative risk audit call failed: {e}")
        return math_eval

