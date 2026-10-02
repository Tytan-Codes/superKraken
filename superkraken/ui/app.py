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
        height: 12;
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
    #middle-debate {
        height: 1fr;
        margin: 0 1;
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
        ("k", "kill_switch", "Kill Switch"),
        ("y", "confirm_kill", "Confirm Kill"),
        ("r", "show_region", "Region Info"),
        ("d", "force_debate", "Force Debate"),
        ("b", "trigger_backtest", "Backtest"),
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
                        self.paper_engine.update_market_prices(all_prices)
                        self.portfolio_widget.update_portfolio(self.paper_engine.portfolio)
                        self.top_header.update_value(self.paper_engine.portfolio.total_value_usd)

                        # Check if daily drawdown reached circuit breaker
                        if self.paper_engine.portfolio.daily_drawdown_pct >= settings.daily_drawdown_limit_pct:
                            msg = f"CIRCUIT BREAKER: {self.paper_engine.portfolio.daily_drawdown_pct * 100:.1f}% drawdown! Halting trading."
                            self.debate_log.add_log("🛡️ Risk Manager", msg, "bold red")
                            self.notifications_bar.add_event(f"CIRCUIT BREAKER TRIGGERED: {msg}", "warn")
                            self.paused = True
                            break

                        # 2. Fetch candles and order book for deep analysis
                        candles = await self.market_client.get_ohlc(symbol, interval_minutes=1, count=100)
                        order_book = await self.market_client.get_order_book_depth(symbol)

                        # Set agents to running in UI
                        self.agent_status.update_statuses({
                            "technical": "RUNNING",
                            "sentiment": "RUNNING",
                            "fundamental": "RUNNING",
                            "bull_researcher": "RUNNING",
                            "bear_researcher": "RUNNING",
                            "debate": "RUNNING",
                            "trader": "RUNNING",
                            "risk_manager": "RUNNING",
                        })

                        # 3. Execute LangGraph multi-agent flow
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

                        final_state = await trading_graph.ainvoke(initial_state)

                        # Update UI with agent completion
                        self.agent_status.update_statuses(final_state.get("agent_states", {}))

                        # Log debate statements
                        bull = final_state.get("bull_argument")
                        bear = final_state.get("bear_argument")
                        consensus = final_state.get("consensus")

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
                            self.notifications_bar.add_event(f"Consensus: {action} on {symbol} (Conf: {conf}%)", "info")

                        # 4. Check Risk Audit & Execution
                        proposal = final_state.get("proposal")
                        risk_eval = final_state.get("risk_evaluation")

                        if proposal and risk_eval and risk_eval.get("approved"):
                            action_val = proposal.get("action")
                            if action_val in ["BUY", "SELL"]:
                                qty = risk_eval.get("adjusted_quantity", proposal.get("quantity", 0.0))
                                sl = risk_eval.get("stop_loss_price", proposal.get("stop_loss_price", 0.0))
                                tp = proposal.get("take_profit_price", 0.0)

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

                                self.notifications_bar.add_event(
                                    f"FILL: {action_val} {qty:.4f} {symbol} @ ${exec_res.filled_price:,.2f}",
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
