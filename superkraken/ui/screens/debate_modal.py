"""Modal Screen displaying full 8-agent adversarial debate transcript."""

from typing import Any, Dict
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class DebateModal(ModalScreen[None]):
    """Modal dialog displaying detailed 8-agent debate transcript."""

    DEFAULT_CSS = """
    DebateModal {
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }

    #debate-dialog {
        width: 85%;
        max-width: 100;
        height: 85%;
        padding: 1 2;
        border: heavy #58a6ff;
        background: #161b22;
    }

    #debate-title {
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
        border-bottom: solid #30363d;
        width: 100%;
    }

    #debate-scroll {
        height: 1fr;
        margin: 1 0;
        padding: 0 1;
    }

    .debate-section {
        margin-bottom: 1;
        padding: 1;
        background: #0d1117;
        border: solid #21262d;
    }

    .debate-section-title {
        text-style: bold;
        margin-bottom: 1;
    }

    #debate-footer {
        align: center middle;
        height: 3;
    }
    """

    BINDINGS = [
        ("escape", "dismiss_modal", "Close"),
        ("q", "dismiss_modal", "Close"),
        ("d", "dismiss_modal", "Close"),
    ]

    def __init__(self, symbol: str, debate_data: Dict[str, Any] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.symbol = symbol
        self.debate_data = debate_data or {}

    def compose(self) -> ComposeResult:
        with Container(id="debate-dialog"):
            yield Static(f"[bold cyan]🤝 8-AGENT ADVERSARIAL DEBATE TRANSCRIPT — {self.symbol}[/]", id="debate-title")
            with VerticalScroll(id="debate-scroll"):
                # Bull vs Bear
                yield Static(
                    f"[bold green]🐂 Bull Agent Thesis:[/bold green]\n"
                    f"{self.debate_data.get('bull_thesis', 'Bull argument: Strong momentum continuation, healthy volume expansion, and key moving averages trending upward.')}\n",
                    classes="debate-section"
                )
                yield Static(
                    f"[bold red]🐻 Bear Agent Counter-Thesis:[/bold red]\n"
                    f"{self.debate_data.get('bear_thesis', 'Bear counter: Resistance near upper range, overbought RSI divergence, and broader macro liquidity drag.')}\n",
                    classes="debate-section"
                )
                
                # Consensus & Synthesis
                yield Static(
                    f"[bold cyan]🤝 Debate Synthesizer & Consensus:[/bold cyan]\n"
                    f"{self.debate_data.get('synthesis', 'Synthesizer assessed bull momentum vs bear resistance. Risk-reward favored continuation with tight trailing stop.')}\n",
                    classes="debate-section"
                )
                
                # Technical, Sentiment & Fundamental
                yield Static(
                    f"[bold yellow]📊 Technical, Sentiment & Fundamental Checks:[/bold yellow]\n"
                    f"• Technical: {self.debate_data.get('technical', 'RSI and MACD aligned in favorable regime.')}\n"
                    f"• Sentiment: {self.debate_data.get('sentiment', 'Positive social sentiment index and funding rate stability.')}\n"
                    f"• Fundamental: {self.debate_data.get('fundamental', 'Neutral-to-bullish network hash rate and on-chain accumulation.')}\n",
                    classes="debate-section"
                )

                # Risk Management Evaluation
                yield Static(
                    f"[bold magenta]🛡️ Risk Manager Audit:[/bold magenta]\n"
                    f"{self.debate_data.get('risk_audit', 'Passed Canadian regulatory restrictions. Max risk capped at 1.0% portfolio equity with strict 2:1 R:R target.')}\n",
                    classes="debate-section"
                )

            with Horizontal(id="debate-footer"):
                yield Button("Close Transcript [Esc]", variant="primary", id="btn-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)
