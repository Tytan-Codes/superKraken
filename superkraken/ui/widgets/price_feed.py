"""Textual widget for real-time price feed and ticker updates."""

from typing import Dict, List
from rich.table import Table
from rich.text import Text
from textual.widgets import Static


class PriceFeedWidget(Static):
    """Renders live prices, 24h changes, and directional markers."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.prices: Dict[str, Dict[str, float]] = {
            "BTC/USD": {"price": 67420.0, "change_pct": 3.8},
            "ETH/USD": {"price": 3210.0, "change_pct": 2.1},
            "SOL/USD": {"price": 182.5, "change_pct": -0.8},
        }

    def update_prices(self, price_data: Dict[str, Dict[str, float]]) -> None:
        self.prices.update(price_data)
        self.refresh()

    def render(self) -> Table:
        table = Table(title="📈 PRICE FEED", expand=True, box=None, padding=(0, 1))
        table.add_column("Symbol", style="bold yellow")
        table.add_column("Price", justify="right", style="bold white")
        table.add_column("24h %", justify="right")

        for symbol, data in self.prices.items():
            price = data.get("price", 0.0)
            chg = data.get("change_pct", 0.0)
            arrow = "▲" if chg >= 0 else "▼"
            style = "bold green" if chg >= 0 else "bold red"
            chg_text = f"{arrow} {abs(chg):.2f}%"

            table.add_row(
                symbol,
                f"${price:,.2f}",
                Text(chg_text, style=style),
            )

        return table
