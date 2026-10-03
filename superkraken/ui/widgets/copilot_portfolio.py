"""Portfolio widget for Copilot displaying live USDC, tracked holdings, and day's P&L."""

from typing import Any, Dict, List, Optional
from rich.table import Table
from rich.text import Text
from textual.widgets import Static
from superkraken.config import settings


class CopilotPortfolioWidget(Static):
    """Displays real Kraken balances and manual position tracking stats."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.usdc_cash: float = 10000.0
        self.pnl_today: float = 0.0
        self.open_positions: List[Dict[str, Any]] = []

    def update_portfolio(
        self,
        usdc_cash: float,
        pnl_today: float = 0.0,
        open_positions: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self.usdc_cash = usdc_cash
        self.pnl_today = pnl_today
        if open_positions is not None:
            self.open_positions = open_positions
        self.refresh()

    def render(self) -> Table:
        table = Table(title="📊 MY PORTFOLIO", expand=True, box=None, padding=(0, 1))
        table.add_column("Asset / Item", style="bold magenta", width=12)
        table.add_column("Holding / Size", justify="right")

        table.add_row(f"{settings.base_currency} Cash", f"${self.usdc_cash:,.2f}")

        # Track active holdings
        holdings = {"BTC": 0.0, "ETH": 0.0, "SOL": 0.0}
        for pos in self.open_positions:
            sym = pos.get("symbol", "")
            qty = float(pos.get("quantity") or 0.0)
            if "BTC" in sym:
                holdings["BTC"] += qty
            elif "ETH" in sym:
                holdings["ETH"] += qty
            elif "SOL" in sym:
                holdings["SOL"] += qty

        for coin, amt in holdings.items():
            style = "bold white" if amt > 0 else "dim"
            table.add_row(f"{coin}", Text(f"{amt:.4f}", style=style))

        # P&L Row
        pnl_style = "bold green" if self.pnl_today >= 0 else "bold red"
        pnl_sign = "+" if self.pnl_today >= 0 else ""
        table.add_row("", "")
        table.add_row("P&L Today", Text(f"{pnl_sign}${self.pnl_today:,.2f}", style=pnl_style))

        open_cnt = len(self.open_positions)
        pos_badge = Text(f"{open_cnt} Active", style="bold green" if open_cnt > 0 else "dim")
        table.add_row("Positions", pos_badge)

        return table
