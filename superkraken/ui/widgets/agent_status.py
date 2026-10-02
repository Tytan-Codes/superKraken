"""Textual widget for agent status overview with thinking spinners."""

from typing import Dict
from rich.table import Table
from rich.text import Text
from textual.widgets import Static
from superkraken.config import settings


class AgentStatusWidget(Static):
    """Renders the real-time status of each specialized agent with live spinners."""

    SPINNERS = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.spinner_idx = 0
        self.agent_statuses: Dict[str, str] = {
            "technical": "IDLE",
            "sentiment": "IDLE",
            "fundamental": "IDLE",
            "bull_researcher": "IDLE",
            "bear_researcher": "IDLE",
            "debate": "IDLE",
            "trader": "IDLE",
            "risk_manager": "IDLE",
        }

    def on_mount(self) -> None:
        self.set_interval(0.12, self._tick_spinner)

    def _tick_spinner(self) -> None:
        if any(s in ("RUNNING", "THINKING") for s in self.agent_statuses.values()):
            self.spinner_idx = (self.spinner_idx + 1) % len(self.SPINNERS)
            self.refresh()

    def update_statuses(self, new_statuses: Dict[str, str]) -> None:
        for k, v in new_statuses.items():
            if k in self.agent_statuses:
                self.agent_statuses[k] = v
        self.refresh()

    def render(self) -> Table:
        table = Table(title="🤖 AGENT COGNITION & STATUS", expand=True, box=None, padding=(0, 1))
        table.add_column("Agent", style="bold cyan")
        table.add_column("Status / Assigned OpenRouter Model", justify="right")

        agents_config = [
            ("technical", "📊 Technical Analyst", settings.model_technical),
            ("sentiment", "📰 Sentiment Analyst", settings.model_sentiment),
            ("fundamental", "📈 Fundamental Analyst", settings.model_fundamental),
            ("bull_researcher", "🐂 Bull Researcher", settings.model_bull),
            ("bear_researcher", "🐻 Bear Researcher", settings.model_bear),
            ("debate", "🤝 Debate & Consensus", settings.model_debate),
            ("trader", "⚡ Execution Trader", settings.model_trader),
            ("risk_manager", "🛡️ Risk Manager", settings.model_risk),
        ]

        spinner_char = self.SPINNERS[self.spinner_idx]

        for key, name, model in agents_config:
            state = self.agent_statuses.get(key, "IDLE").upper()
            if state in ("RUNNING", "THINKING"):
                status_text = Text(f"{spinner_char} THINKING [{model}]...", style="bold yellow")
            elif state in ("COMPLETED", "COMPLETE", "READY"):
                status_text = Text(f"✅ COMPLETE [{model}]", style="bold green")
            elif state in ("FAILED", "ERROR"):
                status_text = Text(f"❌ ERROR [{model}]", style="bold red")
            else:
                status_text = Text(f"⚪ IDLE [{model}]", style="dim white")

            table.add_row(name, status_text)

        return table
