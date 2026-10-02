"""Textual widget for portfolio balances, open positions, and equity curve sparkline."""

from typing import Any, Dict, List
from rich.table import Table
from rich.text import Text
from textual.widgets import Static
from superkraken.state import PortfolioState


def render_sparkline(values: List[float], width: int = 18) -> str:
    """Render a unicode sparkline curve from a series of floats."""
    if not values:
        return "─" * width
    pts = values[-width:]
    min_v = min(pts)
    max_v = max(pts)
    if max_v == min_v:
        return "▄" * len(pts)
    bars = [" ", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
    curve = []
    for v in pts:
        norm = (v - min_v) / (max_v - min_v)
        idx = min(int(norm * (len(bars) - 1)), len(bars) - 1)
        curve.append(bars[idx])
    return "".join(curve)


class PortfolioWidget(Static):
    """Renders active positions, allocation %, unrealized P&L, and equity sparkline."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.portfolio: PortfolioState = PortfolioState(
            total_value_usd=10000.0,
            cash_usd=10000.0,
        )
        self.equity_history: List[float] = [10000.0]

    def update_portfolio(self, portfolio: PortfolioState) -> None:
        self.portfolio = portfolio
        self.equity_history.append(portfolio.total_value_usd)
        if len(self.equity_history) > 60:
            self.equity_history.pop(0)
        self.refresh()

    def render(self) -> Table:
        table = Table(title="💰 PORTFOLIO & EQUITY CURVE", expand=True, box=None, padding=(0, 1))
        table.add_column("Asset", style="bold magenta")
        table.add_column("Size", justify="right")
        table.add_column("Unrealized P&L", justify="right")

        table.add_row(
            "USD Cash",
            f"${self.portfolio.cash_usd:,.2f}",
            Text("0.00%", style="dim"),
        )

        for sym, pos in self.portfolio.positions.items():
            pnl_pct = pos.unrealized_pnl_pct * 100
            pnl_usd = pos.unrealized_pnl
            style = "bold green" if pnl_pct >= 0 else "bold red"
            sign = "+" if pnl_pct >= 0 else ""
            pnl_text = f"{sign}${pnl_usd:,.2f} ({sign}{pnl_pct:.1f}%)"

            table.add_row(
                sym,
                f"{pos.quantity:.4f}",
                Text(pnl_text, style=style),
            )

        # Sparkline row
        spark = render_sparkline(self.equity_history, width=18)
        initial_val = self.equity_history[0] if self.equity_history else 10000.0
        current_val = self.portfolio.total_value_usd
        spark_style = "bold green" if current_val >= initial_val else "bold red"
        table.add_row(
            Text("Curve (20c)", style="dim cyan"),
            Text(f"${current_val:,.1f}", style="bold white"),
            Text(spark, style=spark_style),
        )

        return table
