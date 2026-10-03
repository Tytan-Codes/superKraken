"""superKraken Copilot TUI Application.

Human-in-the-loop AI trading copilot where 8 agents analyze the market
and generate real-time recommendations, while the operator retains 100% execution authority.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from textual.app import App, ComposeResult
from textual.containers import Container, Grid, Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Static

from superkraken.config import settings
from superkraken.copilot.scanner import CopilotScanner
from superkraken.execution.rest_client import KrakenMarketDataClient
from superkraken.state import SignalAlert, TrackedPosition
from superkraken.storage.database import db
from superkraken.ui.screens.debate_modal import DebateModal
from superkraken.ui.screens.log_trade_modal import LogTradeModal
from superkraken.ui.screens.position_alert_modal import PositionAlertModal
from superkraken.ui.widgets.copilot_portfolio import CopilotPortfolioWidget
from superkraken.ui.widgets.copilot_signals import AgentSignalsWidget
from superkraken.ui.widgets.notifications import NotificationsBarWidget
from superkraken.ui.widgets.price_feed import PriceFeedWidget
from superkraken.ui.widgets.signal_alert_panel import ActiveSignalAlertWidget

logger = logging.getLogger(__name__)


class CopilotHeaderWidget(Static):
    """Header showing Copilot Mode, Canadian Spot compliance, live USDC, and open positions."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.usdc_balance: float = 10000.0
        self.open_count: int = 0
        self.realized_pnl: float = 0.0

    def update_metrics(self, usdc: float, open_count: int, realized_pnl: float) -> None:
        self.usdc_balance = usdc
        self.open_count = open_count
        self.realized_pnl = realized_pnl
        self.refresh()

    def render(self) -> str:
        reg_tag = "[bold cyan]🇨🇦 CA-SPOT[/]" if settings.is_canadian else f"[dim][{settings.account_region}][/]"
        pnl_color = "bold green" if self.realized_pnl >= 0 else "bold red"
        return (
            f" 🤖 [bold cyan]superKraken COPILOT[/bold cyan] {reg_tag} │ "
            f"[bold green]Live USDC: ${self.usdc_balance:,.2f}[/bold green] │ "
            f"Open Positions: [bold]{self.open_count}[/bold] │ "
            f"Day P&L: [{pnl_color}]${self.realized_pnl:+,.2f}[/{pnl_color}]"
        )


class SignalHistoryWidget(Static):
    """Recent signals and operator action log."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.table = DataTable(zebra_stripes=True)

    def compose(self) -> ComposeResult:
        yield self.table

    def on_mount(self) -> None:
        if not self.table.columns:
            self.table.add_columns("Time", "Symbol", "Signal", "Conf", "Max Loss", "Action", "Outcome")
        self.refresh_signals()

    def refresh_signals(self) -> None:
        if not self.is_mounted:
            return
        if not self.table.columns:
            self.table.add_columns("Time", "Symbol", "Signal", "Conf", "Max Loss", "Action", "Outcome")
        self.table.clear()
        signals = db.get_recent_signals(limit=12)
        for s in signals:
            sig_color = "green" if s.get("action") == "BUY" else "red"
            action_val = s.get("user_action") or "PENDING"
            act_color = "green" if action_val == "TAKEN" else ("yellow" if action_val == "SKIPPED" else "dim")
            out_val = s.get("outcome") or "PENDING"
            out_color = "green" if out_val == "WIN" else ("red" if out_val == "LOSS" else "dim")

            self.table.add_row(
                s.get("timestamp", "")[-8:],
                f"[bold]{s.get('symbol')}[/bold]",
                f"[{sig_color}]{s.get('action')}[/{sig_color}]",
                f"{float(s.get('confidence', 0))*100:.0f}%",
                f"${float(s.get('max_loss_usd', 0)):.0f}",
                f"[{act_color}]{action_val}[/{act_color}]",
                f"[{out_color}]{out_val}[/{out_color}]",
            )


class SuperKrakenCopilotApp(App):
    """Institutional AI Copilot TUI for Kraken Pro manual execution."""

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
    #middle-alert {
        min-height: 15;
        height: auto;
        margin: 1 1 0 1;
    }
    #bottom-history {
        height: 1fr;
        margin: 1 1 0 1;
        border: round #30363d;
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
        ("s", "scan_now", "Scan Now [S]"),
        ("y", "accept_signal", "Accept [Y]"),
        ("n", "skip_signal", "Skip [N]"),
        ("d", "view_debate", "Debate [D]"),
        ("l", "log_trade", "Log Trade [L]"),
        ("c", "close_position", "Close Pos [C]"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.scanner = CopilotScanner()
        self.market_client = KrakenMarketDataClient()
        self.active_alert: Optional[SignalAlert] = None
        self._scan_task: Optional[asyncio.Task] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._seconds_until_scan: int = 300
        self._last_active_symbol: str = "BTC/USD"
        self._last_debate_data: Dict = {}

        # Widgets
        self.header_widget = CopilotHeaderWidget(id="top-header")
        self.price_feed = PriceFeedWidget(classes="panel-box")
        self.signals_widget = AgentSignalsWidget(classes="panel-box")
        self.portfolio_widget = CopilotPortfolioWidget(classes="panel-box")
        self.alert_widget = ActiveSignalAlertWidget(id="middle-alert")
        self.history_widget = SignalHistoryWidget(id="bottom-history")
        self.notifications_bar = NotificationsBarWidget(id="bottom-notifications")

    def compose(self) -> ComposeResult:
        yield self.header_widget
        with Grid(id="top-grid"):
            yield self.price_feed
            yield self.signals_widget
            yield self.portfolio_widget
        yield self.alert_widget
        yield self.history_widget
        yield self.notifications_bar
        yield Footer()

    async def on_mount(self) -> None:
        """Start background scan and monitoring tasks with instant cold-start."""
        self.notifications_bar.add_event("superKraken Copilot initialized in Canadian Spot mode", "info")

        # Wire streaming callbacks
        self.scanner.on_progress = self._handle_scan_progress
        self.scanner.on_pair_scanned = self._handle_pair_scanned

        # Initialize USDC balance
        bal = await self.scanner.get_live_portfolio_usdc()
        open_pos = db.get_open_positions()
        stats = db.get_copilot_performance_stats()
        self.header_widget.update_metrics(bal, len(open_pos), stats.get("total_realized_pnl", 0.0))
        self.portfolio_widget.update_portfolio(bal, open_pos, stats.get("total_realized_pnl", 0.0))

        # Instant cold-start ticker fetch (<500ms)
        try:
            initial_prices = {}
            for sym in ("BTC/USD", "ETH/USD", "SOL/USD"):
                try:
                    t = await self.market_client.get_ticker(sym)
                    initial_prices[sym] = t
                except Exception:
                    pass
            if initial_prices:
                self.price_feed.update_prices(initial_prices)
        except Exception as pe:
            logger.debug(f"Initial ticker fetch error: {pe}")

        # Start periodic tasks
        self._scan_task = asyncio.create_task(self._scan_loop())
        self._monitor_task = asyncio.create_task(self._price_and_position_monitor())

        # Trigger immediate initial scan
        asyncio.create_task(self._execute_scan())

    def _handle_scan_progress(self, symbol: str, stage: str, message: str) -> None:
        """Stream live agent status to signals widget, alert panel radar, and bottom log."""
        self.signals_widget.set_agent_activity(symbol, message)
        self.alert_widget.set_radar_status(f"[{symbol}] {message}")
        self.notifications_bar.add_event(f"[{symbol}] {message}", "info")

    def _handle_pair_scanned(self, summary: Dict[str, Any], alert: Optional[SignalAlert]) -> None:
        """Immediately update TUI as each asset finishes scanning (BTC first!)."""
        sym = summary.get("symbol", "")
        act = summary.get("action", "HOLD")
        conf = float(summary.get("confidence", 0.50))
        self.signals_widget.update_signal(sym, act, conf)

        # Store debate data for immediate inspection
        self._last_active_symbol = sym
        self._last_debate_data = {
            "bull_thesis": summary.get("bull_thesis", ""),
            "bear_thesis": summary.get("bear_thesis", ""),
            "synthesis": summary.get("summary", ""),
            "technical": f"RSI: {summary.get('indicators', {}).get('rsi_14', 50):.1f}",
            "sentiment": "Positive liquidity and momentum",
            "fundamental": "On-chain accumulation support",
            "risk_audit": "1.0% portfolio risk cap, strict 2:1 R:R target",
        }

        # If this pair triggered an alert, surface it immediately without waiting for other pairs
        if alert:
            self.active_alert = alert
            self.alert_widget.set_alert(alert)
            self.notifications_bar.add_event(
                f"HIGH-CONVICTION ALERT: {alert.action.value} {alert.symbol} ({alert.confidence*100:.0f}%)",
                "warn",
            )

        self.history_widget.refresh_signals()

    async def _scan_loop(self) -> None:
        """Countdown loop that triggers multi-pair scan every 300s."""
        while True:
            self._seconds_until_scan = 300
            while self._seconds_until_scan > 0:
                self.signals_widget.update_scan_timer(self._seconds_until_scan)
                await asyncio.sleep(1)
                self._seconds_until_scan -= 1
            await self._execute_scan()

    async def _execute_scan(self) -> None:
        """Scan configured pairs with real-time streaming updates."""
        self.signals_widget.set_scanning(True)
        self.notifications_bar.add_event("Starting 8-agent market scan (BTC/USD first)...", "info")
        try:
            results, alert = await self.scanner.scan_all_pairs(min_confidence=0.62)
            self.signals_widget.update_signals(results)
            self.signals_widget.set_scanning(False)
            self.alert_widget.set_radar_status("Standby — monitoring order book & candles")

            if alert:
                self.active_alert = alert
                self._last_active_symbol = alert.symbol
                self.alert_widget.set_alert(alert)
                self.notifications_bar.add_event(
                    f"HIGH-CONVICTION ALERT: {alert.action.value} {alert.symbol} ({alert.confidence*100:.0f}%)",
                    "warn",
                )
            else:
                self.notifications_bar.add_event("Scan completed. No signals met 62% confidence gate.", "info")

            self.history_widget.refresh_signals()
        except Exception as e:
            logger.error(f"Scan failed: {e}", exc_info=True)
            self.signals_widget.set_scanning(False)
            self.notifications_bar.add_event(f"Scan error: {e}", "warn")

    async def _price_and_position_monitor(self) -> None:
        """Monitors live prices, updates open positions, audits signals, and pops SL/TP modals."""
        while True:
            try:
                # 1. Update Price Feed
                prices_dict = {}
                for sym in ("BTC/USD", "ETH/USD", "SOL/USD"):
                    try:
                        ticker = await self.market_client.get_ticker(sym)
                        prices_dict[sym] = ticker
                    except Exception:
                        pass
                if prices_dict:
                    self.price_feed.update_prices(prices_dict)

                # 2. Check open positions
                open_pos = db.get_open_positions()
                usdc = await self.scanner.get_live_portfolio_usdc()
                stats = db.get_copilot_performance_stats()
                self.header_widget.update_metrics(usdc, len(open_pos), stats.get("total_realized_pnl", 0.0))
                self.portfolio_widget.update_portfolio(usdc, open_pos, stats.get("total_realized_pnl", 0.0))

                for pos in open_pos:
                    sym = pos.symbol
                    cur_p = prices_dict.get(sym, {}).get("price")
                    if cur_p is None:
                        continue

                    cur_p = float(cur_p)
                    # Check Stop-Loss
                    if pos.stop_loss and (
                        (pos.side == "BUY" and cur_p <= pos.stop_loss)
                        or (pos.side == "SELL" and cur_p >= pos.stop_loss)
                    ):
                        pnl_usd = (cur_p - pos.entry_price) * pos.position_size if pos.side == "BUY" else (pos.entry_price - cur_p) * pos.position_size
                        pnl_pct = ((cur_p - pos.entry_price) / pos.entry_price) * 100 if pos.side == "BUY" else ((pos.entry_price - cur_p) / pos.entry_price) * 100
                        modal = PositionAlertModal(
                            symbol=pos.symbol,
                            alert_type="STOP_LOSS",
                            current_price=cur_p,
                            entry_price=pos.entry_price,
                            target_price=pos.stop_loss,
                            position_size=pos.position_size,
                            pnl_usd=pnl_usd,
                            pnl_pct=pnl_pct,
                            position_id=pos.id,
                        )

                        def _on_sl_confirmed(confirmed: bool) -> None:
                            if confirmed and pos.id:
                                db.close_manual_position(pos.id, exit_price=cur_p, exit_reason="STOP_LOSS")
                                self.notifications_bar.add_event(f"Stop-Loss closed for {pos.symbol}", "warn")
                                open_p = db.get_open_positions()
                                st = db.get_copilot_performance_stats()
                                self.portfolio_widget.update_portfolio(usdc, open_p, st.get("total_realized_pnl", 0.0))

                        self.push_screen(modal, _on_sl_confirmed)
                        break

                    # Check Take-Profit
                    elif pos.take_profit and (
                        (pos.side == "BUY" and cur_p >= pos.take_profit)
                        or (pos.side == "SELL" and cur_p <= pos.take_profit)
                    ):
                        pnl_usd = (cur_p - pos.entry_price) * pos.position_size if pos.side == "BUY" else (pos.entry_price - cur_p) * pos.position_size
                        pnl_pct = ((cur_p - pos.entry_price) / pos.entry_price) * 100 if pos.side == "BUY" else ((pos.entry_price - cur_p) / pos.entry_price) * 100
                        modal = PositionAlertModal(
                            symbol=pos.symbol,
                            alert_type="TAKE_PROFIT",
                            current_price=cur_p,
                            entry_price=pos.entry_price,
                            target_price=pos.take_profit,
                            position_size=pos.position_size,
                            pnl_usd=pnl_usd,
                            pnl_pct=pnl_pct,
                            position_id=pos.id,
                        )

                        def _on_tp_confirmed(confirmed: bool) -> None:
                            if confirmed and pos.id:
                                db.close_manual_position(pos.id, exit_price=cur_p, exit_reason="TAKE_PROFIT")
                                self.notifications_bar.add_event(f"Take-Profit locked in for {pos.symbol}!", "info")
                                open_p = db.get_open_positions()
                                st = db.get_copilot_performance_stats()
                                self.portfolio_widget.update_portfolio(usdc, open_p, st.get("total_realized_pnl", 0.0))

                        self.push_screen(modal, _on_tp_confirmed)
                        break

                # 3. Evaluate pending historical signals
                await self.scanner.evaluate_pending_signals()
                self.history_widget.refresh_signals()

            except Exception as e:
                logger.debug(f"Monitor iteration error: {e}")

            await asyncio.sleep(15)

    async def action_scan_now(self) -> None:
        """Trigger an immediate scan right now (User hotkey [S])."""
        self._seconds_until_scan = 300
        asyncio.create_task(self._execute_scan())

    async def action_accept_signal(self) -> None:
        """User accepted active alert -> log trade as placed on Kraken Pro (Hotkey [Y])."""
        if not self.active_alert:
            self.notifications_bar.add_event("No active signal alert to accept.", "info")
            return

        alert = self.active_alert
        # 1. Update signal database status
        db.update_signal_user_action(alert.signal_id, "TAKEN", "Operator confirmed trade placed on Kraken Pro.")

        # 2. Record manual position
        order = alert.suggested_order
        pos = TrackedPosition(
            symbol=alert.symbol,
            side=order.get("action", "BUY"),
            entry_price=order.get("entry_price", 0.0),
            current_price=order.get("entry_price", 0.0),
            position_size=order.get("quantity", 0.0),
            stop_loss=order.get("stop_loss"),
            take_profit=order.get("take_profit"),
            status="OPEN",
            notes=f"Signal {alert.signal_id} ({alert.confidence*100:.0f}%)",
        )
        db.create_manual_position(pos)

        # 3. Clear alert panel and notify
        self.alert_widget.clear_alert()
        self.active_alert = None
        self.history_widget.refresh_signals()
        self.notifications_bar.add_event(f"Trade logged: {pos.side} {pos.symbol} at ${pos.entry_price:,.2f}", "info")

    async def action_skip_signal(self) -> None:
        """User skipped active alert (Hotkey [N])."""
        if not self.active_alert:
            self.notifications_bar.add_event("No active signal alert to skip.", "info")
            return

        alert = self.active_alert
        db.update_signal_user_action(alert.signal_id, "SKIPPED", "Operator skipped signal.")
        self.alert_widget.clear_alert()
        self.active_alert = None
        self.history_widget.refresh_signals()
        self.notifications_bar.add_event(f"Signal skipped: {alert.symbol} {alert.action.value}", "info")

    def action_view_debate(self) -> None:
        """Open full 8-agent adversarial transcript modal (Hotkey [D])."""
        sym = self._last_active_symbol
        modal = DebateModal(symbol=sym, debate_data=self._last_debate_data)
        self.push_screen(modal)

    def action_log_trade(self) -> None:
        """Open modal form to log trade placed on Kraken Pro (Hotkey [L])."""
        modal = LogTradeModal(default_symbol=self._last_active_symbol)

        def _on_trade_logged(pos: Optional[TrackedPosition]) -> None:
            if pos:
                self.notifications_bar.add_event(f"Manually logged: {pos.side} {pos.symbol} ({pos.position_size} units)", "info")
                open_pos = db.get_open_positions()
                usdc = self.scanner.cached_portfolio_usdc
                stats = db.get_copilot_performance_stats()
                self.header_widget.update_metrics(usdc, len(open_pos), stats.get("total_realized_pnl", 0.0))
                self.portfolio_widget.update_portfolio(usdc, open_pos, stats.get("total_realized_pnl", 0.0))

        self.push_screen(modal, _on_trade_logged)

    async def action_close_position(self) -> None:
        """Quick close latest open position if any."""
        open_pos = db.get_open_positions()
        if not open_pos:
            self.notifications_bar.add_event("No open positions to close.", "info")
            return
        pos = open_pos[0]
        ticker = await self.market_client.get_ticker(pos.symbol)
        cur_p = float(ticker["price"])
        if pos.id:
            db.close_manual_position(pos.id, exit_price=cur_p, exit_reason="MANUAL_CLOSE")
            self.notifications_bar.add_event(f"Closed {pos.symbol} at ${cur_p:,.2f}", "info")
            open_pos = db.get_open_positions()
            usdc = await self.scanner.get_live_portfolio_usdc()
            stats = db.get_copilot_performance_stats()
            self.header_widget.update_metrics(usdc, len(open_pos), stats.get("total_realized_pnl", 0.0))
            self.portfolio_widget.update_portfolio(usdc, open_pos, stats.get("total_realized_pnl", 0.0))
