"""Full-screen Modal Overlay for Stop-Loss and Take-Profit Alerts."""

import sys
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class PositionAlertModal(ModalScreen[bool]):
    """Full-screen high-priority alert overlay for Stop-Loss and Take-Profit triggers."""

    DEFAULT_CSS = """
    PositionAlertModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.90);
    }

    #alert-dialog {
        width: 80%;
        max-width: 90;
        height: auto;
        padding: 2 3;
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
        ("c", "confirm_close", "Mark as closed"),
        ("enter", "confirm_close", "Mark as closed"),
        ("i", "dismiss_modal", "Keep monitoring"),
        ("escape", "dismiss_modal", "Keep monitoring"),
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
        coin = self.symbol.split("/")[0]

        if is_sl:
            title_text = f"🚨 YOUR POSITION NEEDS ATTENTION — {self.symbol}"
            title_style = "bold red"
            dialog_body = (
                f"[bold red]{coin} just hit your STOP-LOSS level.[/bold red]\n\n"
                f"You bought {coin} at ${self.entry_price:,.2f}.\n"
                f"Your stop was at ${self.target_price:,.2f}.\n"
                f"Price is now at [bold red]${self.current_price:,.2f}[/bold red] — below your stop.\n\n"
                f"[bold yellow]You should close this trade RIGHT NOW on Kraken Pro.[/bold yellow]\n"
                f"If you close now your loss is about [bold red]${abs(self.pnl_usd):,.2f} USDC[/bold red] ({self.pnl_pct:+.2f}%).\n"
                f"That is exactly what you planned for — this is fine.\n\n"
                f"[bold white]Go to Kraken Pro → Positions → Close {coin}[/bold white]"
            )
        else:
            title_text = f"🎯 TARGET HIT — LOCK IN GAINS — {self.symbol}"
            title_style = "bold green"
            dialog_body = (
                f"[bold green]{coin} just hit your TAKE-PROFIT target![/bold green]\n\n"
                f"You bought {coin} at ${self.entry_price:,.2f}.\n"
                f"Your target was at ${self.target_price:,.2f}.\n"
                f"Price reached [bold green]${self.current_price:,.2f}[/bold green] — target reached.\n\n"
                f"[bold yellow]You should close this trade RIGHT NOW on Kraken Pro to lock in profit.[/bold yellow]\n"
                f"If you close now your gain is about [bold green]+${abs(self.pnl_usd):,.2f} USDC[/bold green] ({self.pnl_pct:+.2f}%).\n"
                f"Great trade — take your profit off the table.\n\n"
                f"[bold white]Go to Kraken Pro → Positions → Close {coin}[/bold white]"
            )

        with Container(id="alert-dialog", classes=border_class):
            yield Static(f"[{title_style}]{title_text}[/{title_style}]", id="alert-title")
            yield Static(dialog_body, id="alert-details")

            with Horizontal(id="btn-container"):
                yield Button("Mark as closed [C]", variant="success", id="btn-close")
                yield Button("Keep monitoring (risky) [I]", variant="error", id="btn-dismiss")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-close":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_confirm_close(self) -> None:
        self.dismiss(True)

    def action_dismiss_modal(self) -> None:
        self.dismiss(False)
