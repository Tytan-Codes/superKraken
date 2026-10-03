"""Active Signal Alert Panel widget rendering high-conviction copilot recommendations."""

import sys
from typing import Any, Dict, Optional
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.widgets import Static
from superkraken.state import SignalAlert


def make_confidence_bar(conf: float, width: int = 16) -> str:
    """Renders a visual ASCII progress bar for conviction percentage."""
    filled = int(round(conf * width))
    empty = width - filled
    return "█" * filled + "░" * empty


class ActiveSignalAlertWidget(Static):
    """High-visibility signal alert panel that commands attention when an alert triggers."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.active_alert: Optional[SignalAlert] = None
        self._last_alert_id: Optional[str] = None

    def set_alert(self, alert: Optional[SignalAlert]) -> None:
        self.active_alert = alert
        if alert and alert.signal_id != self._last_alert_id:
            self._last_alert_id = alert.signal_id
            # Audible terminal bell sound to ensure alert is impossible to miss
            try:
                sys.stdout.write("\a")
                sys.stdout.flush()
            except Exception:
                pass
        self.refresh()

    def clear_alert(self) -> None:
        self.active_alert = None
        self.refresh()

    def render(self) -> Panel:
        if not self.active_alert:
            # Standby mode display
            content = Text()
            content.append("\n  📡 ", style="bold cyan")
            content.append("COPILOT RADAR ACTIVE — Standby Mode\n\n", style="bold white")
            content.append("  Continuous 8-agent market scans running across BTC/USD, ETH/USD, and SOL/USD.\n", style="dim")
            content.append("  When conviction reaches ", style="dim")
            content.append("62%+ confidence", style="bold yellow")
            content.append(", an active signal alert with exact order spec will appear here.\n\n", style="dim")
            content.append("  Quick Actions:  ", style="dim")
            content.append("[S] Scan Now   ", style="bold yellow")
            content.append("│   ", style="dim")
            content.append("[D] Full Debate   ", style="bold cyan")
            content.append("│   ", style="dim")
            content.append("[L] Manually Log Placed Trade   ", style="bold green")
            content.append("│   ", style="dim")
            content.append("[P] Performance", style="bold magenta")

            return Panel(
                content,
                title="[bold cyan]🔔 COPILOT RADAR — STANDBY[/bold cyan]",
                border_style="cyan",
                padding=(1, 2),
            )

        alert = self.active_alert
        is_buy = alert.action.value == "BUY" if hasattr(alert.action, "value") else "BUY" in str(alert.action).upper()
        border_col = "bold green" if is_buy else "bold red"
        act_col = "bold green" if is_buy else "bold red"
        act_label = "🟢 BUY" if is_buy else "🔴 SELL"

        # 1. Header & Conviction
        conf_pct = int(alert.confidence * 100)
        conf_bar = make_confidence_bar(alert.confidence, width=16)
        bull_pct = int(alert.bull_score * 100)
        bear_pct = int(alert.bear_score * 100)

        header_tbl = Table(box=None, expand=True, padding=(0, 1))
        header_tbl.add_column("Decision", style=act_col)
        header_tbl.add_column("Confidence & Conviction", justify="right")
        header_tbl.add_row(
            Text(f"Decision: {act_label}", style=f"bold {act_col}"),
            Text(f"Confidence: {conf_pct}%  {conf_bar}  (Bull: {bull_pct}% vs Bear: {bear_pct}%)", style="bold white"),
        )

        # 2. Key Indicators Summary Table
        ind_tbl = Table(title="📊 Key Indicators", box=None, expand=True, padding=(0, 1))
        ind_tbl.add_column("Indicator", style="bold cyan", width=12)
        ind_tbl.add_column("Value & Interpretation", style="bold white")

        rsi = float(alert.indicators.get("rsi", 50.0))
        rsi_tag = "(Bullish — above 50)" if rsi >= 50 else "(Bearish — below 50)"
        ind_tbl.add_row("RSI (14)", f"{rsi:.1f}  {rsi_tag}")

        macd = float(alert.indicators.get("macd", 0.0))
        macd_tag = "(Bullish momentum)" if macd >= 0 else "(Bearish pressure)"
        ind_tbl.add_row("MACD Hist", f"{macd:+.2f}  {macd_tag}")

        bb_pb = float(alert.indicators.get("bb_percent_b", 0.5))
        bb_tag = "(Mid-band — room to run)" if 0.2 <= bb_pb <= 0.8 else ("(Overbought)" if bb_pb > 0.8 else "(Oversold)")
        ind_tbl.add_row("Bollinger %B", f"{bb_pb:.2f}  {bb_tag}")

        ema = alert.indicators.get("ema_trend", "NEUTRAL")
        ind_tbl.add_row("EMA Trend", f"{ema} regime")

        # 3. Suggested Order Spec
        ord_spec = alert.suggested_order
        qty = ord_spec.get("quantity", 0.0)
        notional = ord_spec.get("notional_usdc", 0.0)
        pos_pct = ord_spec.get("position_pct", 0.0)
        entry_p = ord_spec.get("entry_price", 0.0)
        lim_p = ord_spec.get("limit_entry_price", entry_p)
        sl_p = ord_spec.get("stop_loss", 0.0)
        sl_pct = ord_spec.get("stop_loss_pct", 0.0)
        tp_p = ord_spec.get("take_profit", 0.0)
        tp_pct = ord_spec.get("take_profit_pct", 0.0)

        ord_tbl = Table(title="📋 Suggested Order (YOU decide whether to place it)", box=None, expand=True, padding=(0, 1))
        ord_tbl.add_column("Parameter", style="bold yellow", width=14)
        ord_tbl.add_column("Recommendation", style="bold white")

        coin = alert.symbol.split("/")[0]
        ord_tbl.add_row("Action", Text(f"{alert.action.value if hasattr(alert.action, 'value') else alert.action}", style=act_col))
        ord_tbl.add_row("Amount", f"{qty:.4f} {coin}  (${notional:,.2f} USDC — {pos_pct:.0f}% of portfolio)")
        ord_tbl.add_row("Entry Price", f"${entry_p:,.2f} market  OR  limit at ${lim_p:,.2f}")
        ord_tbl.add_row("Stop-Loss", Text(f"${sl_p:,.2f}  (-{sl_pct:.1f}% │ ATR-based risk anchor)", style="bold red"))
        ord_tbl.add_row("Take-Profit", Text(f"${tp_p:,.2f}  (+{tp_pct:.1f}% │ 2:1 Reward:Risk)", style="bold green"))

        # 4. Exact Dollar Risk Box
        risk_m = alert.risk_metrics
        max_loss = risk_m.get("max_loss_usd", 0.0)
        max_loss_pct = risk_m.get("max_loss_pct", 0.0)
        target_gain = risk_m.get("target_gain_usd", 0.0)
        target_gain_pct = risk_m.get("target_gain_pct", 0.0)
        rr = risk_m.get("risk_reward_ratio", "1:2")
        port_val = risk_m.get("portfolio_usdc", 10000.0)

        risk_tbl = Table(title="💰 Risk Calculator (based on your live USDC balance)", box=None, expand=True, padding=(0, 1))
        risk_tbl.add_column("Dimension", style="bold magenta", width=14)
        risk_tbl.add_column("Value in Real Dollars", style="bold white")

        risk_tbl.add_row("Portfolio Base", f"${port_val:,.2f} USDC")
        risk_tbl.add_row("Max Loss Risk", Text(f"${max_loss:,.2f} USDC  ({max_loss_pct:.1f}% of portfolio max)", style="bold red"))
        risk_tbl.add_row("Target Profit", Text(f"${target_gain:,.2f} USDC  ({target_gain_pct:.1f}% of portfolio)", style="bold green"))
        risk_tbl.add_row("Reward/Risk", f"{rr}")

        # 5. Bull vs Bear Theses
        theses = Text()
        theses.append("🐂 Bull: ", style="bold green")
        theses.append(f"{alert.bull_thesis[:110]}...\n", style="white")
        theses.append("🐻 Bear: ", style="bold red")
        theses.append(f"{alert.bear_thesis[:110]}...", style="white")

        # 6. Action Bar
        action_bar = Text()
        action_bar.append("\n  ➡️  Your Move: ", style="bold white")
        action_bar.append("[Y] Log Trade as Placed on Kraken Pro   ", style="bold black on green")
        action_bar.append("  ")
        action_bar.append("[D] View Full Debate   ", style="bold black on cyan")
        action_bar.append("  ")
        action_bar.append("[N] Skip / Dismiss Signal", style="bold black on yellow")

        group = Group(
            header_tbl,
            Text("─" * 65, style="dim"),
            ind_tbl,
            Text("─" * 65, style="dim"),
            ord_tbl,
            Text("─" * 65, style="dim"),
            risk_tbl,
            Text("─" * 65, style="dim"),
            theses,
            action_bar,
        )

        ts_str = alert.timestamp.strftime("%H:%M:%S")
        return Panel(
            group,
            title=f"[{border_col}]🔔 NEW SIGNAL — {alert.symbol} — {ts_str}[/{border_col}]",
            border_style=border_col,
            padding=(0, 1),
        )
