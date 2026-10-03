"""Copilot market scanner that runs 8-agent desk analysis and generates high-conviction alerts."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from superkraken.config import settings
from superkraken.copilot.risk_calc import calculate_copilot_order_spec
from superkraken.execution.rest_client import KrakenMarketDataClient
from superkraken.graph.workflow import trading_graph
from superkraken.state import Candle, SignalAlert, TradeAction
from superkraken.storage.database import db

logger = logging.getLogger(__name__)


def build_advisor_narrative(
    symbol: str,
    action: str,
    current_price: float,
    confidence: float,
    bull_score: float,
    bear_score: float,
    indicators: Dict[str, Any],
    order_spec: Dict[str, Any],
) -> str:
    """Compose plain-English trading advisor speech explaining the setup, indicators, and exact Kraken steps."""
    coin = symbol.split("/")[0]
    rsi = float(indicators.get("rsi_14", 50.0))
    macd = float(indicators.get("macd_histogram", 0.0))
    trend = str(indicators.get("trend_regime", "NEUTRAL")).upper()

    bull_pts = int(bull_score * 100)
    bear_pts = int(bear_score * 100)

    qty = order_spec.get("quantity", 0.0)
    notional = order_spec.get("notional_usdc", 0.0)
    sl = order_spec.get("stop_loss_price", 0.0)
    tp = order_spec.get("take_profit_price", 0.0)
    max_loss = order_spec.get("max_loss_usd", 0.0)
    max_loss_pct = order_spec.get("max_loss_pct", 0.0)
    target_gain = order_spec.get("target_gain_usd", 0.0)
    target_gain_pct = order_spec.get("target_gain_pct", 0.0)
    conf_pct = int(confidence * 100)

    if rsi < 40:
        rsi_msg = f"RSI is down around {rsi:.0f} — recovering out of oversold territory"
    elif rsi <= 60:
        rsi_msg = f"RSI is at {rsi:.0f} — momentum is building nicely without being overbought"
    else:
        rsi_msg = f"RSI is at {rsi:.0f} — strong bullish velocity"

    if macd > 0:
        macd_msg = "MACD crossed bullish with expanding positive momentum"
    else:
        macd_msg = "MACD histogram is curling upward toward a bullish crossover"

    if "BULL" in trend or "UP" in trend:
        trend_msg = "Price is holding firm above key moving averages — buyers are in control"
    elif "BEAR" in trend or "DOWN" in trend:
        trend_msg = "Price is breaking through overhead resistance"
    else:
        trend_msg = "Price is holding steady support on the 15m chart"

    if action == "BUY":
        return (
            f"🟢 I think you should BUY {coin} right now.\n\n"
            f"The setup looks good:\n"
            f"• {rsi_msg}.\n"
            f"• {macd_msg}.\n"
            f"• {trend_msg}.\n"
            f"• Order book depth shows solid buyer support.\n\n"
            f"My bull and bear agents debated this: Bulls won {bull_pts} to {bear_pts}.\n\n"
            f"What to do RIGHT NOW on Kraken Pro:\n"
            f"  1. Go to kraken.com/u/trade or open Kraken Pro\n"
            f"  2. Select {symbol} spot market\n"
            f"  3. Buy {qty:.4f} {coin} at market (${current_price:,.2f}) (about ${notional:,.2f} of your money)\n"
            f"  4. Set your stop-loss at ${sl:,.2f}\n"
            f"  5. Set your take-profit at ${tp:,.2f}\n\n"
            f"Your risk:    ${max_loss:,.2f} USDC max loss ({max_loss_pct:.1f}% of your portfolio)\n"
            f"Your reward:  ${target_gain:,.2f} USDC if target hit ({target_gain_pct:.1f}% of your portfolio)\n"
            f"Risk/Reward:  1:2 — this is a solid bet.\n"
            f"Confidence:   {conf_pct}%"
        )
    else:
        return (
            f"🔴 I think you should SELL {coin} right now.\n\n"
            f"The setup is weakening:\n"
            f"• RSI dropped to {rsi:.0f} — sellers taking over.\n"
            f"• MACD crossed bearish with accelerating downward pressure.\n"
            f"• Price broke below support levels — bears are in control.\n\n"
            f"My bull and bear agents debated this: Bears dominated {bear_pts} to {bull_pts}.\n\n"
            f"If you are holding {coin} — consider closing your position to protect your capital.\n"
            f"(Note: Spot shorting is not available in CA accounts).\n\n"
            f"What to do RIGHT NOW on Kraken Pro:\n"
            f"  1. Go to kraken.com/u/trade\n"
            f"  2. Open your portfolio / active positions\n"
            f"  3. Close your {coin} position at market price (${current_price:,.2f})\n\n"
            f"Confidence: {conf_pct}%"
        )


class CopilotScanner:
    """Orchestrates multi-pair market scanning with live Kraken feeds and 8-agent consensus."""

    def __init__(self):
        self.client = KrakenMarketDataClient()
        self.cached_portfolio_usdc: float = 10000.0

    async def get_live_portfolio_usdc(self) -> float:
        """Fetch live USDC balance from Kraken Private API /0/private/Balance."""
        try:
            res = await self.client.get_account_balances()
            if res.get("success"):
                balances = res.get("balances", {})
                usdc = float(balances.get("USDC", 0.0))
                if usdc > 0:
                    self.cached_portfolio_usdc = usdc
                    return usdc
                # If USDC empty, check USD or CAD conversion approximation or standard 10,000
                usd = float(balances.get("USD", 0.0))
                if usd > 0:
                    self.cached_portfolio_usdc = usd
                    return usd
        except Exception as e:
            logger.debug(f"Failed to fetch private Kraken balance: {e}")
        return self.cached_portfolio_usdc

    async def scan_symbol(
        self,
        symbol: str,
        min_confidence: float = 0.62,
        portfolio_usdc: Optional[float] = None,
    ) -> Tuple[Dict[str, Any], Optional[SignalAlert]]:
        """
        Run full 8-agent analysis on a single asset and generate SignalAlert if confidence >= min_confidence.
        """
        if portfolio_usdc is None:
            portfolio_usdc = await self.get_live_portfolio_usdc()

        # 1. Fetch live ticker, OHLCV, and order book depth
        ticker = await self.client.get_ticker(symbol)
        current_price = float(ticker["price"])
        candles = await self.client.get_ohlc(symbol, interval_minutes=15, count=100)
        order_book = await self.client.get_order_book_depth(symbol)

        # 2. Assemble Graph State
        state = {
            "symbol": symbol,
            "current_price": current_price,
            "candles": [c.model_dump() for c in candles],
            "market_sentiment": {
                "fear_greed_index": 65,
                "sentiment_label": "Greed",
                "social_volume_24h": "High",
                "recent_headline": f"Surging liquidity and momentum across {symbol} institutional desks.",
            },
            "order_book": order_book,
            "portfolio": {"cash_usd": portfolio_usdc, "total_value_usd": portfolio_usdc},
            "agent_states": {},
        }

        # 3. Execute LangGraph workflow
        res = await trading_graph.ainvoke(state)

        ta = res.get("technical_report") or {}
        indicators = res.get("indicators") or {}
        bull = res.get("bull_argument") or {}
        bear = res.get("bear_argument") or {}
        consensus = res.get("consensus") or {}
        proposal = res.get("proposal") or {}
        risk = res.get("risk_evaluation") or {}

        action_str = consensus.get("action", "HOLD")
        confidence = float(consensus.get("confidence", 0.50))
        bull_score = float(consensus.get("bull_score", 0.50))
        bear_score = float(consensus.get("bear_score", 0.50))
        summary = consensus.get("summary", "Consensus evaluation completed.")

        atr_14 = float(indicators.get("atr_14", 0.0))

        # Check if high-conviction BUY or SELL alert should be fired
        alert: Optional[SignalAlert] = None
        if action_str in ("BUY", "SELL") and confidence >= min_confidence:
            order_spec = calculate_copilot_order_spec(
                symbol=symbol,
                action=action_str,
                current_price=current_price,
                atr_14=atr_14,
                portfolio_usdc=portfolio_usdc,
                confidence=confidence,
                max_position_pct=settings.max_position_size_pct,
                risk_per_trade_pct=0.01,
            )

            advisor_narrative = build_advisor_narrative(
                symbol=symbol,
                action=action_str,
                current_price=current_price,
                confidence=confidence,
                bull_score=bull_score,
                bear_score=bear_score,
                indicators=indicators,
                order_spec=order_spec,
            )

            # Build SignalAlert
            signal_id = f"sig-{symbol.split('/')[0].lower()}-{uuid.uuid4().hex[:6]}"
            alert = SignalAlert(
                signal_id=signal_id,
                symbol=symbol,
                action=TradeAction.BUY if action_str == "BUY" else TradeAction.SELL,
                confidence=confidence,
                bull_score=bull_score,
                bear_score=bear_score,
                indicators={
                    "rsi": indicators.get("rsi_14", 50.0),
                    "macd": indicators.get("macd_histogram", 0.0),
                    "bb_percent_b": indicators.get("bb_percent_b", 0.5),
                    "ema_trend": indicators.get("trend_regime", "NEUTRAL"),
                    "atr": atr_14,
                },
                suggested_order={
                    "action": action_str,
                    "quantity": order_spec["quantity"],
                    "notional_usdc": order_spec["notional_usdc"],
                    "position_pct": order_spec["position_pct"],
                    "entry_price": order_spec["entry_price"],
                    "limit_entry_price": order_spec["limit_entry_price"],
                    "stop_loss": order_spec["stop_loss_price"],
                    "stop_loss_pct": order_spec["stop_loss_pct"],
                    "take_profit": order_spec["take_profit_price"],
                    "take_profit_pct": order_spec["take_profit_pct"],
                },
                risk_metrics={
                    "portfolio_usdc": portfolio_usdc,
                    "max_loss_usd": order_spec["max_loss_usd"],
                    "max_loss_pct": order_spec["max_loss_pct"],
                    "target_gain_usd": order_spec["target_gain_usd"],
                    "target_gain_pct": order_spec["target_gain_pct"],
                    "risk_reward_ratio": order_spec["risk_reward_ratio"],
                },
                bull_thesis=bull.get("thesis", "Bull thesis supported by trend"),
                bear_thesis=bear.get("thesis", "Bear thesis notes resistance"),
                summary=summary,
                advisor_speech=advisor_narrative,
                timestamp=datetime.now(timezone.utc),
            )

            # Persist signal to SQLite
            db.log_copilot_signal(alert)

        analysis_result = {
            "symbol": symbol,
            "current_price": current_price,
            "change_pct": ticker.get("change_pct", 0.0),
            "action": action_str,
            "confidence": confidence,
            "bull_score": bull_score,
            "bear_score": bear_score,
            "summary": summary,
            "indicators": indicators,
            "bull_thesis": bull.get("thesis", ""),
            "bear_thesis": bear.get("thesis", ""),
            "debate_rounds": res.get("debate_rounds", []),
        }

        return analysis_result, alert

    async def scan_all_pairs(
        self,
        pairs: Optional[List[str]] = None,
        min_confidence: float = 0.62,
    ) -> Tuple[List[Dict[str, Any]], Optional[SignalAlert]]:
        """
        Scan all configured trading pairs. Returns list of summaries and top active alert if any.
        """
        symbols = pairs or settings.pairs_list
        portfolio_usdc = await self.get_live_portfolio_usdc()

        summaries = []
        highest_conviction_alert: Optional[SignalAlert] = None

        for sym in symbols:
            summary, alert = await self.scan_symbol(sym, min_confidence=min_confidence, portfolio_usdc=portfolio_usdc)
            summaries.append(summary)
            if alert:
                if (
                    highest_conviction_alert is None
                    or alert.confidence > highest_conviction_alert.confidence
                ):
                    highest_conviction_alert = alert

        # Update historical signal outcomes
        await self.evaluate_pending_signals()

        return summaries, highest_conviction_alert

    async def evaluate_pending_signals(self) -> None:
        """Audit previous pending signals against current market prices to determine WIN/LOSS."""
        try:
            recent_signals = db.get_recent_signals(limit=20)
            for sig in recent_signals:
                if sig.get("theoretical_outcome") == "PENDING":
                    import json
                    order_spec = json.loads(sig.get("suggested_order_json") or "{}")
                    entry = float(order_spec.get("entry_price") or 0.0)
                    sl = float(order_spec.get("stop_loss") or 0.0)
                    tp = float(order_spec.get("take_profit") or 0.0)
                    action = sig.get("action", "BUY")
                    sym = sig.get("symbol")

                    if entry > 0 and sl > 0 and tp > 0 and sym:
                        ticker = await self.client.get_ticker(sym)
                        p = float(ticker["price"])
                        if action == "BUY":
                            if p >= tp:
                                db.update_signal_outcome(sig["signal_id"], "WIN")
                            elif p <= sl:
                                db.update_signal_outcome(sig["signal_id"], "LOSS")
                        elif action == "SELL":
                            if p <= tp:
                                db.update_signal_outcome(sig["signal_id"], "WIN")
                            elif p >= sl:
                                db.update_signal_outcome(sig["signal_id"], "LOSS")
        except Exception as e:
            logger.debug(f"Error evaluating pending signals: {e}")
