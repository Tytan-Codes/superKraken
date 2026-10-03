"""Modal Screen to manually log an executed Kraken Pro trade."""

from typing import Optional
from textual.app import ComposeResult
from textual.containers import Container, Grid, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static
from superkraken.state import TrackedPosition
from superkraken.storage.database import db


class LogTradeModal(ModalScreen[Optional[TrackedPosition]]):
    """Modal dialog for logging a manually placed Kraken Pro trade."""

    DEFAULT_CSS = """
    LogTradeModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }

    #form-dialog {
        width: 70;
        height: auto;
        padding: 1 2;
        border: heavy #58a6ff;
        background: #161b22;
    }

    #form-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        width: 100%;
    }

    .form-row {
        height: 3;
        margin-bottom: 1;
    }

    .field-label {
        width: 16;
        padding-top: 1;
        text-style: bold;
    }

    .field-input {
        width: 1fr;
    }

    #button-bar {
        align: center middle;
        margin-top: 1;
        height: 3;
    }

    Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        ("escape", "cancel_form", "Cancel"),
    ]

    def __init__(
        self,
        default_symbol: str = "BTC/USD",
        default_side: str = "BUY",
        default_size: float = 0.0,
        default_price: float = 0.0,
        default_sl: float = 0.0,
        default_tp: float = 0.0,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.default_symbol = default_symbol
        self.default_side = default_side
        self.default_size = default_size
        self.default_price = default_price
        self.default_sl = default_sl
        self.default_tp = default_tp

    def compose(self) -> ComposeResult:
        with Container(id="form-dialog"):
            yield Static("[bold cyan]📝 LOG EXECUTED KRAKEN PRO TRADE[/bold cyan]", id="form-title")

            with Horizontal(classes="form-row"):
                yield Label("Pair Symbol:", classes="field-label")
                yield Input(value=self.default_symbol, id="inp-symbol", classes="field-input")

            with Horizontal(classes="form-row"):
                yield Label("Order Side:", classes="field-label")
                yield Input(value=self.default_side, placeholder="BUY or SELL", id="inp-side", classes="field-input")

            with Horizontal(classes="form-row"):
                yield Label("Fill Price ($):", classes="field-label")
                yield Input(value=str(self.default_price) if self.default_price > 0 else "", placeholder="e.g. 68250.00", id="inp-price", classes="field-input")

            with Horizontal(classes="form-row"):
                yield Label("Size (Units):", classes="field-label")
                yield Input(value=str(self.default_size) if self.default_size > 0 else "", placeholder="e.g. 0.015", id="inp-size", classes="field-input")

            with Horizontal(classes="form-row"):
                yield Label("Stop-Loss ($):", classes="field-label")
                yield Input(value=str(self.default_sl) if self.default_sl > 0 else "", placeholder="e.g. 67500.00", id="inp-sl", classes="field-input")

            with Horizontal(classes="form-row"):
                yield Label("Target ($):", classes="field-label")
                yield Input(value=str(self.default_tp) if self.default_tp > 0 else "", placeholder="e.g. 69750.00", id="inp-tp", classes="field-input")

            with Horizontal(id="button-bar"):
                yield Button("Save Position [Enter]", variant="success", id="btn-save")
                yield Button("Cancel [Esc]", variant="error", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save":
            self.submit_form()
        else:
            self.dismiss(None)

    def submit_form(self) -> None:
        try:
            symbol = self.query_one("#inp-symbol", Input).value.strip().upper()
            side = self.query_one("#inp-side", Input).value.strip().upper()
            price = float(self.query_one("#inp-price", Input).value.strip() or 0.0)
            size = float(self.query_one("#inp-size", Input).value.strip() or 0.0)
            sl_val = self.query_one("#inp-sl", Input).value.strip()
            tp_val = self.query_one("#inp-tp", Input).value.strip()
            sl = float(sl_val) if sl_val else None
            tp = float(tp_val) if tp_val else None

            if not symbol or side not in ("BUY", "SELL") or price <= 0 or size <= 0:
                return

            pos = TrackedPosition(
                symbol=symbol,
                side=side,
                entry_price=price,
                current_price=price,
                position_size=size,
                stop_loss=sl,
                take_profit=tp,
                status="OPEN",
            )
            pos_id = db.create_manual_position(pos)
            pos.id = pos_id
            self.dismiss(pos)
        except Exception:
            self.dismiss(None)

    def action_cancel_form(self) -> None:
        self.dismiss(None)
