"""Textual widget for bottom risk status and last trade banner."""

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.widgets import Static


class RiskBarWidget(Static):
    """Renders the execution ticker and risk telemetry footer."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.last_trade_text: str = "⚡ LAST TRADE: None yet | Standby"
        self.daily_pnl: float = 0.0
        self.drawdown_pct: float = 0.0
        self.trade_count: int = 0
        self.max_trades: int = 10

    def update_metrics(
        self,
        last_trade: str,
        daily_pnl: float,
        drawdown_pct: float,
        trade_count: int,
    ) -> None:
        self.last_trade_text = last_trade
        self.daily_pnl = daily_pnl
        self.drawdown_pct = drawdown_pct
        self.trade_count = trade_count
        self.refresh()

    def render(self) -> Panel:
        table = Table.grid(expand=True)
        table.add_column(ratio=6)
        table.add_column(ratio=6, justify="right")

        # Last Trade info
        trade_content = Text.from_markup(f"[bold cyan]{self.last_trade_text}[/bold cyan]")

        # Risk Telemetry
        pnl_style = "bold green" if self.daily_pnl >= 0 else "bold red"
        pnl_sign = "+" if self.daily_pnl >= 0 else ""
        dd_style = "bold red" if self.drawdown_pct > 0.07 else "bold yellow" if self.drawdown_pct > 0.03 else "green"

        risk_text = Text()
        risk_text.append("🛡️ Risk: Daily P&L ")
        risk_text.append(f"{pnl_sign}${self.daily_pnl:,.2f}", style=pnl_style)
        risk_text.append(" | Drawdown: ")
        risk_text.append(f"{self.drawdown_pct * 100:.1f}%", style=dd_style)
        risk_text.append(f" | Trades: {self.trade_count}/{self.max_trades}")

        table.add_row(trade_content, risk_text)

        return Panel(table, border_style="grey35", expand=True)
