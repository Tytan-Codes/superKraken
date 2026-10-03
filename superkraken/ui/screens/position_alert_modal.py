"""Full-screen Modal Overlay for Stop-Loss and Take-Profit Alerts."""

import sys
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class PositionAlertModal(ModalScreen[bool]):
    """Full-screen high-priority alert overlay for Stop-Loss and Take-Profit triggers."""

    DEFAULT_CSS = """
    PositionAlertModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }

    #alert-dialog {
        width: 80%;
        max-width: 90;
        height: auto;
        padding: 2 3;
        border: heavy $error;
        background: #161b22;
    }

    .stop-loss-border {
        border: heavy red;
    }

    .take-profit-border {
        border: heavy green;
    }

    #alert-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        width: 100%;
    }

    #alert-details {
        margin: 1 0;
        padding: 1 2;
        background: #0d1117;
        border: solid #30363d;
        height: auto;
    }

    #alert-action {
        text-align: center;
        margin: 1 0;
        text-style: bold;
    }

    #btn-container {
        align: center middle;
        margin-top: 1;
        height: 3;
    }

    Button {
        margin: 0 2;
    }
    """

    BINDINGS = [
        ("escape", "dismiss_modal", "Dismiss"),
        ("c", "confirm_close", "Confirm Closed"),
        ("enter", "confirm_close", "Confirm Closed"),
    ]

    def __init__(
        self,
        symbol: str,
        alert_type: str,  # 'STOP_LOSS' or 'TAKE_PROFIT'
        current_price: float,
        entry_price: float,
        target_price: float,
        position_size: float,
        pnl_usd: float,
        pnl_pct: float,
        position_id: int | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.symbol = symbol
        self.alert_type = alert_type.upper()
        self.current_price = current_price
        self.entry_price = entry_price
        self.target_price = target_price
        self.position_size = position_size
        self.pnl_usd = pnl_usd
        self.pnl_pct = pnl_pct
        self.position_id = position_id

    def on_mount(self) -> None:
        """Trigger audible bell when alert is shown."""
        try:
            sys.stdout.write("\a")
            sys.stdout.flush()
        except Exception:
            pass

    def compose(self) -> ComposeResult:
        is_sl = "STOP" in self.alert_type
        border_class = "stop-loss-border" if is_sl else "take-profit-border"
        title_color = "bold red" if is_sl else "bold green"
        title_icon = "🛑" if is_sl else "🎯"
        title_text = "STOP-LOSS HIT — ACTION REQUIRED" if is_sl else "TAKE-PROFIT TARGET HIT — LOCK IN GAINS"

        with Container(id="alert-dialog", classes=border_class):
            yield Static(f"[{title_color}]{title_icon}  {title_text}  {title_icon}[/]", id="alert-title")
            
            details_text = (
                f"[bold cyan]Asset:[/bold cyan] {self.symbol}     "
                f"[bold cyan]Size:[/bold cyan] {self.position_size:,.4f} units\n"
                f"[bold]Entry Price:[/bold]  ${self.entry_price:,.2f}\n"
                f"[bold]Trigger Price:[/bold] ${self.target_price:,.2f}\n"
                f"[bold]Current Price:[/bold] ${self.current_price:,.2f}\n"
                f"[bold]Unrealized P&L:[/bold] [{'red' if self.pnl_usd < 0 else 'green'}]"
                f"${self.pnl_usd:+,.2f} ({self.pnl_pct:+.2f}%)[/]\n\n"
                f"[bold yellow]INSTRUCTIONS FOR KRAKEN PRO:[/bold yellow]\n"
                f"1. Open Kraken Pro terminal or mobile app immediately.\n"
                f"2. Navigate to [bold]{self.symbol}[/bold] spot market.\n"
                f"3. Place a [bold]{'MARKET SELL' if is_sl else 'LIMIT SELL'}[/bold] order for {self.position_size:,.4f} {self.symbol.split('/')[0]}.\n"
                f"4. Press [bold green][Enter][/bold green] or click [bold green]'Mark as Closed'[/bold green] below once executed."
            )
            yield Static(details_text, id="alert-details")

            with Horizontal(id="btn-container"):
                yield Button("Mark Position Closed [Enter]", variant="success", id="btn-close")
                yield Button("Dismiss Warning [Esc]", variant="error", id="btn-dismiss")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-close":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_confirm_close(self) -> None:
        self.dismiss(True)

    def action_dismiss_modal(self) -> None:
        self.dismiss(False)
