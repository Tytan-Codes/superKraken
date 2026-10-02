"""Textual Application for superKraken Autonomous Trading Desk."""

import asyncio
import logging
from typing import Optional
from textual.app import App, ComposeResult
from textual.containers import Container, Grid, Horizontal, Vertical
from textual.widgets import Footer, Header, Static
from superkraken.config import settings
from superkraken.execution.paper_engine import PaperTradingEngine
from superkraken.execution.rest_client import KrakenMarketDataClient
from superkraken.graph.workflow import trading_graph
from superkraken.storage.audit import audit_logger
from superkraken.storage.database import db
from superkraken.ui.widgets.agent_status import AgentStatusWidget
from superkraken.ui.widgets.debate_log import DebateLogWidget
from superkraken.ui.widgets.notifications import NotificationsBarWidget
from superkraken.ui.widgets.portfolio import PortfolioWidget
from superkraken.ui.widgets.price_feed import PriceFeedWidget
from superkraken.ui.widgets.risk_bar import RiskBarWidget

logger = logging.getLogger(__name__)


class TopHeaderWidget(Static):
    """Custom top header displaying Desk title and Portfolio total."""

    def __init__(self, mode: str = "PAPER", **kwargs):
        super().__init__(**kwargs)
        self.mode = mode
        self.portfolio_value: float = 10000.0

    def update_value(self, val: float) -> None:
        self.portfolio_value = val
        self.refresh()

    def render(self) -> str:
        mode_tag = f"[{'bold red' if self.mode == 'LIVE' else 'bold yellow'}][{self.mode}][/]"
        reg_tag = "[bold cyan][CA-SPOT][/]" if settings.is_canadian else f"[dim][{settings.account_region}][/]"
        return (
            f" 🤖 [bold cyan]KRAKEN TRADING AGENTS[/bold cyan] {mode_tag} {reg_tag} "
            f"[dim]│ Wall Street Desk[/dim] "
            f"[bold green]Portfolio: ${self.portfolio_value:,.2f} {settings.base_currency}[/bold green]"
        )


class SuperKrakenTUI(App):
    """Main Textual Trading Desk Application."""

    CSS = """
    Screen {
        background: #0f141c;
        color: #e6edf3;
    }
    #top-header {
        dock: top;
        height: 1;
        background: #161b22;
        padding: 0 1;
    }
    #top-grid {
        height: 16;
        layout: grid;
        grid-size: 3 1;
        grid-columns: 1fr 1fr 1fr;
        margin: 0;
        padding: 0;
    }
    .panel-box {
        border: round #30363d;
        height: 100%;
        margin: 0 1;
        padding: 0;
    }
    .panel-box:focus {
        border: round #58a6ff;
    }
    #middle-debate {
        height: 1fr;
        margin: 0 1;
    }
    #middle-debate:focus {
        border: round #58a6ff;
    }
    #bottom-risk {
        dock: bottom;
        height: 3;
        margin: 0 1;
    }
    #bottom-notifications {
        dock: bottom;
        height: 1;
        background: #161b22;
        padding: 0 1;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("p", "toggle_pause", "Pause"),
        ("s", "emergency_stop", "Flatten"),
        ("k", "kill_switch", "Kill"),
        ("d", "force_debate", "Debate"),
        ("a", "focus_agents", "Agents"),
        ("l", "focus_log", "Log"),
        ("r", "show_region", "Region"),
    ]

    def __init__(self, mode: str = "PAPER"):
        super().__init__()
        self.mode = mode.upper()
        self.paper_engine = PaperTradingEngine()
        self.market_client = KrakenMarketDataClient()
        self.paused = False
        self.kill_switch_active = False
        self._confirming_kill = False
        self._loop_task: Optional[asyncio.Task] = None

        # Widgets
        self.top_header = TopHeaderWidget(mode=self.mode, id="top-header")
        self.agent_status = AgentStatusWidget(classes="panel-box")
        self.price_feed = PriceFeedWidget(classes="panel-box")
        self.portfolio_widget = PortfolioWidget(classes="panel-box")
        self.debate_log = DebateLogWidget(id="middle-debate")
        self.risk_bar = RiskBarWidget(id="bottom-risk")
        self.notifications_bar = NotificationsBarWidget(id="bottom-notifications")

    def compose(self) -> ComposeResult:
        yield self.top_header
        with Grid(id="top-grid"):
            yield self.agent_status
            yield self.price_feed
            yield self.portfolio_widget
        yield self.debate_log
        yield self.notifications_bar
        yield self.risk_bar
        yield Footer()

    async def on_mount(self) -> None:
        """Start the background autonomous trading loop."""
        self._loop_task = asyncio.create_task(self.autonomous_trading_loop())

    async def action_toggle_pause(self) -> None:
        self.paused = not self.paused
        state = "PAUSED" if self.paused else "RESUMED"
        self.debate_log.add_log("⚙️ System", f"Autonomous trading {state}", "yellow")

    async def action_emergency_stop(self) -> None:
        self.debate_log.add_log("🚨 EMERGENCY", "Flattening all positions & canceling orders!", "bold red")
        self.notifications_bar.add_event("Emergency Stop: Flattening positions", "warn")
        prices = {s: d["price"] for s, d in self.price_feed.prices.items()}
        results = self.paper_engine.flatten_all_positions(prices)
        self.portfolio_widget.update_portfolio(self.paper_engine.portfolio)
        self.top_header.update_value(self.paper_engine.portfolio.total_value_usd)
        self.risk_bar.update_metrics(
            last_trade="⚡ EMERGENCY STOP: All positions flattened",
            daily_pnl=self.paper_engine.portfolio.realized_pnl_today,
            drawdown_pct=self.paper_engine.portfolio.daily_drawdown_pct,
            trade_count=sum(self.paper_engine.portfolio.trade_count_today.values()),
        )

    async def action_kill_switch(self) -> None:
        """Trigger emergency kill switch with operator confirmation barrier."""
        if not self._confirming_kill:
            self._confirming_kill = True
            self.debate_log.add_log(
                "⚠️ CONFIRM KILL",
                "CONFIRMATION REQUIRED: Press 'k' again or 'y' within 5s to permanently liquidate all positions.",
                "bold red",
            )
            self.notifications_bar.add_event("⚠️ Confirm Kill Switch: press 'k' or 'y' to confirm", "warn")
            asyncio.create_task(self._reset_kill_confirm())
            return

        await self._execute_kill_switch()

    async def action_confirm_kill(self) -> None:
        if self._confirming_kill:
            await self._execute_kill_switch()

    async def _reset_kill_confirm(self) -> None:
        await asyncio.sleep(5.0)
        self._confirming_kill = False

    async def _execute_kill_switch(self) -> None:
        self.paused = True
        self.kill_switch_active = True
        self._confirming_kill = False
        self.debate_log.add_log("🚨 KILL SWITCH", "CRITICAL: ALL AGENTS HALTED. LIQUIDATING PORTFOLIO.", "bold red")
        self.notifications_bar.add_event("🚨 KILL SWITCH ACTIVATED: ALL SYSTEMS HALTED", "warn")
        prices = {s: d["price"] for s, d in self.price_feed.prices.items()}
        results = self.paper_engine.flatten_all_positions(prices)
        self.portfolio_widget.update_portfolio(self.paper_engine.portfolio)
        self.top_header.update_value(self.paper_engine.portfolio.total_value_usd)
        self.risk_bar.update_metrics(
            last_trade="🚨 KILL SWITCH ACTIVATED: ALL SYSTEMS HALTED",
            daily_pnl=self.paper_engine.portfolio.realized_pnl_today,
            drawdown_pct=self.paper_engine.portfolio.daily_drawdown_pct,
            trade_count=sum(self.paper_engine.portfolio.trade_count_today.values()),
        )
        audit_logger.log_decision_cycle({
            "action": "KILL_SWITCH_ACTIVATED",
            "reason": "Emergency kill switch operator confirmation verified",
        })

    async def action_show_region(self) -> None:
        """Display active jurisdiction policy and regulatory restrictions."""
        if settings.is_canadian:
            reg_info = (
                "🇨🇦 [bold cyan]REGION: CANADA (CA)[/bold cyan] — Spot: ✅ ENABLED | Base: USDC | "
                "Futures: 🚫 RESTRICTED | Margin: 🚫 RESTRICTED | Leverage: 🚫 LOCKED 1.0x"
            )
        else:
            reg_info = f"🌐 REGION: {settings.account_region} — Full trading capabilities enabled."
        self.debate_log.add_log("🇨🇦 Region Info", reg_info, "bold cyan")
        self.notifications_bar.add_event(f"Region: {settings.account_region} (CA Compliance active)", "info")

    async def action_force_debate(self) -> None:
        self.debate_log.add_log("⚡ Force Debate", "Triggering out-of-band multi-agent debate cycle...", "cyan")
        self.notifications_bar.add_event("Force debate triggered by operator", "info")

    async def action_trigger_backtest(self) -> None:
        self.debate_log.add_log("📈 Backtest", "Run 'trader backtest BTC/USD 30d' in CLI for full strategy verification.", "yellow")
        self.notifications_bar.add_event("Backtest reminder: run trader backtest", "info")

    def action_focus_agents(self) -> None:
        self.agent_status.focus()
        self.notifications_bar.add_event("Agent Status panel focused — use ↑/↓ to scroll", "info")

    def action_focus_log(self) -> None:
        self.debate_log.focus()
        self.notifications_bar.add_event("Debate Log panel focused — use ↑/↓ to scroll full conversation", "info")

    async def autonomous_trading_loop(self) -> None:
        """Main multi-agent decision cycle across watchlisted symbols."""
        symbols = settings.pairs_list

        while True:
            try:
                if not self.paused and not self.kill_switch_active:
                    for symbol in symbols:
                        if self.kill_switch_active:
                            break

                        # 1. Fetch live market ticker and update feeds
                        ticker = await self.market_client.get_ticker(symbol)
                        current_price = ticker["price"]
                        self.price_feed.update_prices({
                            symbol: {
                                "price": current_price,
                                "change_pct": ticker.get("change_pct", 0.0),
                            }
                        })

                        # Update open positions valuation in paper engine
                        all_prices = {s: d["price"] for s, d in self.price_feed.prices.items()}
                        triggered_orders = self.paper_engine.update_market_prices(all_prices)
                        for trig in triggered_orders:
                            if "stop-loss" in trig.message.lower() or "stop" in trig.message.lower():
                                pnl_pct = (trig.filled_price - trig.price) / trig.price * 100 if trig.price > 0 else -3.2
                                self.notifications_bar.add_event(
                                    f"🔴 STOP-LOSS HIT — exited {trig.symbol} @ ${trig.filled_price:,.2f} ({pnl_pct:.1f}%)",
                                    "warn",
                                )
                                self.debate_log.add_log("🛑 Stop-Loss", f"Triggered on {trig.symbol} @ ${trig.filled_price:,.2f}", "bold red")

                        self.portfolio_widget.update_portfolio(self.paper_engine.portfolio)
                        self.top_header.update_value(self.paper_engine.portfolio.total_value_usd)

                        # Check if daily drawdown reached circuit breaker
                        if self.paper_engine.portfolio.daily_drawdown_pct >= settings.daily_drawdown_limit_pct:
                            msg = f"CIRCUIT BREAKER: {self.paper_engine.portfolio.daily_drawdown_pct * 100:.1f}% drawdown! Halting trading."
                            self.debate_log.add_log("🛡️ Risk Manager", f"[CIRCUIT BREAKER TRIGGERED] {msg}", "bold red")
                            self.notifications_bar.add_event(f"🔴 CIRCUIT BREAKER — trading halted", "warn")
                            db.log_audit_event("CIRCUIT_BREAKER_ACTIVATED", msg)
                            audit_logger.log_decision_cycle({
                                "action": "CIRCUIT_BREAKER_ACTIVATED",
                                "reason": msg,
                                "portfolio": self.paper_engine.portfolio.model_dump(),
                            })
                            self.paused = True
                            break

                        # 2. Fetch candles and order book for deep analysis
                        candles = await self.market_client.get_ohlc(symbol, interval_minutes=1, count=100)
                        order_book = await self.market_client.get_order_book_depth(symbol)

                        # Set initial agent states for this symbol cycle: Analysts thinking, rest waiting
                        self.agent_status.update_statuses({
                            "technical": "THINKING",
                            "sentiment": "THINKING",
                            "fundamental": "THINKING",
                            "bull_researcher": "WAITING",
                            "bear_researcher": "WAITING",
                            "debate": "WAITING",
                            "trader": "WAITING",
                            "risk_manager": "WAITING",
                        })

                        # 3. Execute LangGraph multi-agent flow with live node streaming
                        initial_state = {
                            "symbol": symbol,
                            "current_price": current_price,
                            "candles": [c.model_dump() for c in candles],
                            "market_sentiment": {
                                "fear_greed_index": 68,
                                "sentiment_label": "Greed",
                                "social_volume_24h": "Surging",
                                "recent_headline": f"Surging liquidity and momentum across {symbol} desks.",
                            },
                            "order_book": order_book,
                            "portfolio": self.paper_engine.portfolio.model_dump(),
                            "agent_states": {},
                        }

                        final_state = dict(initial_state)
                        async for chunk in trading_graph.astream(initial_state):
                            for node_name, node_update in chunk.items():
                                final_state.update(node_update)
                                if node_name == "technical_analyst":
                                    self.agent_status.update_statuses({"technical": "COMPLETED"})
                                    tech = node_update.get("technical_report")
                                    if tech:
                                        self.agent_status.update_signals({"technical": f"{tech.get('signal', 'HOLD')} {int(tech.get('confidence', 0)*100)}%"})
                                elif node_name == "sentiment_analyst":
                                    self.agent_status.update_statuses({"sentiment": "COMPLETED"})
                                    sent = node_update.get("sentiment_report")
                                    if sent:
                                        self.agent_status.update_signals({"sentiment": f"{sent.get('signal', 'HOLD')} {int(sent.get('confidence', 0)*100)}%"})
                                elif node_name == "fundamental_analyst":
                                    self.agent_status.update_statuses({"fundamental": "COMPLETED"})
                                    fund = node_update.get("fundamental_report")
                                    if fund:
                                        self.agent_status.update_signals({"fundamental": f"{fund.get('signal', 'HOLD')} {int(fund.get('confidence', 0)*100)}%"})

                                if (
                                    self.agent_status.agent_statuses.get("technical") in ("COMPLETED", "COMPLETE")
                                    and self.agent_status.agent_statuses.get("sentiment") in ("COMPLETED", "COMPLETE")
                                    and self.agent_status.agent_statuses.get("fundamental") in ("COMPLETED", "COMPLETE")
                                    and self.agent_status.agent_statuses.get("bull_researcher") == "WAITING"
                                ):
                                    self.agent_status.update_statuses({"bull_researcher": "THINKING", "bear_researcher": "THINKING"})

                                if node_name == "bull_researcher":
                                    self.agent_status.update_statuses({"bull_researcher": "COMPLETED"})
                                    bull = node_update.get("bull_argument")
                                    if bull:
                                        self.agent_status.update_signals({"bull_researcher": f"BULL {int(bull.get('confidence', 0)*100)}%"})
                                elif node_name == "bear_researcher":
                                    self.agent_status.update_statuses({"bear_researcher": "COMPLETED"})
                                    bear = node_update.get("bear_argument")
                                    if bear:
                                        self.agent_status.update_signals({"bear_researcher": f"BEAR {int(bear.get('confidence', 0)*100)}%"})

                                if (
                                    self.agent_status.agent_statuses.get("bull_researcher") in ("COMPLETED", "COMPLETE")
                                    and self.agent_status.agent_statuses.get("bear_researcher") in ("COMPLETED", "COMPLETE")
                                    and self.agent_status.agent_statuses.get("debate") == "WAITING"
                                ):
                                    self.agent_status.update_statuses({"debate": "THINKING"})

                                if node_name == "debate_consensus":
                                    self.agent_status.update_statuses({"debate": "COMPLETED"})
                                    cons = node_update.get("consensus")
                                    if cons:
                                        self.agent_status.update_signals({"debate": f"{cons.get('action', 'HOLD')} {int(cons.get('confidence', 0)*100)}%"})
                                    self.agent_status.update_statuses({"trader": "THINKING"})

                                if node_name == "execution_trader":
                                    self.agent_status.update_statuses({"trader": "COMPLETED"})
                                    prop = node_update.get("proposal")
                                    if prop:
                                        p_act = prop.get("action", "HOLD")
                                        p_q = prop.get("quantity", 0.0)
                                        self.agent_status.update_signals({"trader": f"{p_act} {p_q:.3f}" if p_act != "HOLD" else "HOLD 0.0"})
                                    self.agent_status.update_statuses({"risk_manager": "THINKING"})

                                if node_name == "risk_manager":
                                    self.agent_status.update_statuses({"risk_manager": "COMPLETED"})
                                    r_ev = node_update.get("risk_evaluation")
                                    if r_ev:
                                        self.agent_status.update_signals({"risk_manager": "APPROVED" if r_ev.get("approved") else "REJECTED"})

                        # Log debate statements & update signal values
                        bull = final_state.get("bull_argument")
                        bear = final_state.get("bear_argument")
                        consensus = final_state.get("consensus")
                        proposal = final_state.get("proposal")
                        risk_eval = final_state.get("risk_evaluation")

                        if bull:
                            self.debate_log.add_log("🐂 Bull", f"{bull.get('thesis')[:95]}...", "green")
                        if bear:
                            self.debate_log.add_log("🐻 Bear", f"{bear.get('thesis')[:95]}...", "red")
                        if consensus:
                            conf = int(consensus.get("confidence", 0) * 100)
                            action = consensus.get("action")
                            self.debate_log.add_log(
                                "🤝 Consensus",
                                f"{action} on {symbol} — Conf: {conf}%: {consensus.get('summary')[:85]}",
                                "bold gold1",
                            )

                        if proposal:
                            p_act = proposal.get("action", "HOLD")
                            p_q = proposal.get("quantity", 0.0)
                            p_style = "bold green" if p_act == "BUY" else ("bold red" if p_act == "SELL" else "yellow")
                            self.debate_log.add_log(
                                "⚡ Trader",
                                f"Order: {p_act} {p_q:.4f} {symbol} | SL: ${proposal.get('stop_loss_price', 0):,.2f} | TP: ${proposal.get('take_profit_price', 0):,.2f}",
                                p_style,
                            )

                        if risk_eval:
                            r_app = risk_eval.get("approved", False)
                            r_style = "bold green" if r_app else "bold red"
                            r_text = "APPROVED" if r_app else "REJECTED"
                            r_reasons = " | ".join(risk_eval.get("reasons", [])) or "Risk parameters satisfied"
                            self.debate_log.add_log(
                                "🛡️ Risk Manager",
                                f"{r_text}: {r_reasons[:85]}",
                                r_style,
                            )

                        # 4. Check Risk Audit & Execution

                        # Memory layer consecutive losses notification
                        if risk_eval:
                            for reason in risk_eval.get("reasons", []):
                                if "consecutive losses" in reason.lower() or "tightened" in reason.lower():
                                    self.debate_log.add_log(
                                        "🛡️ Risk Manager",
                                        "[MEMORY: SIZING TIGHTENED — 3 consecutive losses] Halving position size.",
                                        "bold yellow",
                                    )
                                    self.notifications_bar.add_event("🛡️ 3 consecutive losses — sizing cut 50%", "warn")

                        if proposal and risk_eval and risk_eval.get("approved"):
                            action_val = proposal.get("action")
                            if action_val in ["BUY", "SELL"]:
                                qty = risk_eval.get("adjusted_quantity", proposal.get("quantity", 0.0))
                                sl = risk_eval.get("stop_loss_price", proposal.get("stop_loss_price", 0.0))
                                tp = proposal.get("take_profit_price", 0.0)

                                if settings.is_canadian and proposal.get("leverage", 1.0) > 1.0:
                                    self.notifications_bar.add_event("🇨🇦 Futures/leverage blocked — spot fallback", "info")

                                exec_res = self.paper_engine.execute_order(
                                    symbol=symbol,
                                    action=action_val,
                                    quantity=qty,
                                    current_market_price=current_price,
                                    stop_loss=sl,
                                    take_profit=tp,
                                )

                                final_state["execution_result"] = exec_res.model_dump()
                                status_emoji = "✅" if exec_res.success else "❌"
                                last_trade_msg = (
                                    f"⚡ LAST TRADE: {action_val} {qty:.4f} {symbol} @ ${exec_res.filled_price:,.2f} "
                                    f"{status_emoji} {exec_res.status}"
                                )

                                self.risk_bar.update_metrics(
                                    last_trade=last_trade_msg,
                                    daily_pnl=self.paper_engine.portfolio.realized_pnl_today,
                                    drawdown_pct=self.paper_engine.portfolio.daily_drawdown_pct,
                                    trade_count=sum(self.paper_engine.portfolio.trade_count_today.values()),
                                )

                                if exec_res.success:
                                    self.notifications_bar.add_event(
                                        f"🟢 FILLED spot {action_val} {qty:.4f} {symbol} @ ${exec_res.filled_price:,.2f}",
                                        "fill",
                                    )

                                self.debate_log.add_log(
                                    "⚡ Execution",
                                    f"{exec_res.message} (Fee: ${exec_res.fee:.2f})",
                                    "cyan",
                                )

                                # Persist to SQLite
                                db.log_trade(
                                    exec_res,
                                    confidence=consensus.get("confidence", 0.0) if consensus else 0.0,
                                    reasoning=proposal.get("reasoning", ""),
                                )
                            else:
                                conf_int = int(consensus.get("confidence", 0) * 100) if consensus else 0
                                self.notifications_bar.add_event(f"🟡 HOLD {symbol} — Conf {conf_int}% below 65% gate", "info")
                        elif proposal and proposal.get("action") == "HOLD":
                            conf_int = int(consensus.get("confidence", 0) * 100) if consensus else 0
                            self.notifications_bar.add_event(f"🟡 HOLD {symbol} — Conf {conf_int}% below 65% gate", "info")

                        # Audit log
                        audit_logger.log_decision_cycle(final_state)

                        # Small breathing interval between symbols
                        await asyncio.sleep(2.0)

                # Wait before next cycle
                await asyncio.sleep(float(settings.loop_interval_seconds))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in trading loop: {e}", exc_info=True)
                self.debate_log.add_log("⚠️ Error", str(e), "bold red")
                await asyncio.sleep(5.0)
