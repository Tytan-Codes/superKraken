"""Textual widget for portfolio balances, open positions, and ASCII equity curve."""

from typing import Any, Dict, List, Optional
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.widgets import Static
from superkraken.config import settings
from superkraken.state import PortfolioState


def render_ascii_curve(values: Optional[List[float]], height: int = 4, width: int = 24) -> str:
    if not values:
        return "Equity curve standby..."
    val_list = [v for v in (values or []) if v is not None]
    if not val_list:
        return "Equity curve standby..."
    if len(val_list) <= 1:
        v0 = val_list[0]
        return f"Equity Curve (cycle 1 standby):\n${v0:>6,.0f} ┼" + ("─" * (width - 2))

    pts = val_list[-width:]
    min_v = min(pts)
    max_v = max(pts)
    if min_v == max_v:
        max_v = min_v + 10.0
        min_v = min_v - 10.0

    step = (max_v - min_v) / (height - 1) if height > 1 else 1.0

    # Resample or pad points to match target width
    if len(pts) < width:
        pts = [pts[0]] * (width - len(pts)) + pts

    row_pts = [int(round((v - min_v) / (max_v - min_v) * (height - 1))) for v in pts]

    grid = [[" " for _ in range(width)] for _ in range(height)]

    for c in range(width):
        curr_r = max(0, min(height - 1, row_pts[c]))
        prev_r = max(0, min(height - 1, row_pts[c - 1])) if c > 0 else curr_r

        if curr_r == prev_r:
            grid[curr_r][c] = "─"
        elif curr_r > prev_r:
            grid[prev_r][c] = "╯"
            for inter in range(prev_r + 1, curr_r):
                grid[inter][c] = "│"
            grid[curr_r][c] = "╭"
        else:
            grid[prev_r][c] = "╮"
            for inter in range(curr_r + 1, prev_r):
                grid[inter][c] = "│"
            grid[curr_r][c] = "╰"

    lines = []
    for h in range(height - 1, -1, -1):
        thresh = min_v + h * step
        lbl = f"${thresh:>6,.0f} ┤" if h > 0 else f"${thresh:>6,.0f} ┼"
        lines.append(lbl + "".join(grid[h]))
    return "\n".join(lines)


class PortfolioWidget(Static):
    """Renders active positions, allocation %, unrealized P&L, and equity curve."""

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
        if len(self.equity_history) > 20:
            self.equity_history.pop(0)
        self.refresh()

    def render(self) -> Group:
        table = Table(title=f"💰 PORTFOLIO ({settings.base_currency})", expand=True, box=None, padding=(0, 1))
        table.add_column("Asset", style="bold magenta")
        table.add_column("Size", justify="right")
        table.add_column("P&L", justify="right")

        table.add_row(
            f"{settings.base_currency} Cash",
            f"${self.portfolio.cash_usd:,.2f}",
            Text("0.00%", style="dim"),
        )

        positions = getattr(self.portfolio, "positions", {}) or {}
        for sym, pos in positions.items():
            if not pos:
                continue
            pnl_pct = (pos.unrealized_pnl_pct or 0.0) * 100
            pnl_usd = pos.unrealized_pnl or 0.0
            style = "bold green" if pnl_pct >= 0 else "bold red"
            sign = "+" if pnl_pct >= 0 else ""
            pnl_text = f"{sign}${pnl_usd:,.2f} ({sign}{pnl_pct:.1f}%)"

            table.add_row(
                sym,
                f"{pos.quantity:.4f}",
                Text(pnl_text, style=style),
            )

        # Multi-row ASCII equity curve with delta calculation
        curve_str = render_ascii_curve(self.equity_history, height=4, width=22)
        initial_val = self.equity_history[0] if self.equity_history else 10000.0
        current_val = self.portfolio.total_value_usd
        delta = current_val - initial_val
        delta_pct = (delta / initial_val * 100) if initial_val > 0 else 0.0
        sign = "+" if delta >= 0 else ""
        delta_style = "bold green" if delta >= 0 else "bold red"

        hdr = Text("Equity Curve (last 20):", style="bold white")
        hdr.append(f" {sign}${delta:,.2f} ({sign}{delta_pct:.1f}%)", style=delta_style)

        curve_style = "bold green" if current_val >= initial_val else "bold red"
        curve_text = Text(curve_str, style=curve_style)

        return Group(table, hdr, curve_text)
