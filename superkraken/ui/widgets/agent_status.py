"""Textual widget for agent status overview."""

from typing import Dict
from rich.table import Table
from rich.text import Text
from textual.widgets import Static


class AgentStatusWidget(Static):
    """Renders the real-time status of each specialized agent."""

    MODEL_MAP = {
        "Technical Analyst": "v4.1-flash",
        "Sentiment Analyst": "v4-flash",
        "Fundamental Analyst": "v4-flash",
        "Bullish Researcher": "v4.1-flash",
        "Bearish Researcher": "v4.1-flash",
        "Debate & Consensus": "v4.1-flash",
        "Execution Trader": "glm-5.3",
        "Risk Manager": "v4.1-flash",
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.agent_statuses: Dict[str, str] = {
            "Technical Analyst": "IDLE",
            "Sentiment Analyst": "IDLE",
            "Fundamental Analyst": "IDLE",
            "Bullish Researcher": "IDLE",
            "Bearish Researcher": "IDLE",
            "Debate & Consensus": "IDLE",
            "Execution Trader": "IDLE",
            "Risk Manager": "IDLE",
        }

    def update_statuses(self, new_statuses: Dict[str, str]) -> None:
        name_mapping = {
            "technical": "Technical Analyst",
            "sentiment": "Sentiment Analyst",
            "fundamental": "Fundamental Analyst",
            "bull_researcher": "Bullish Researcher",
            "bear_researcher": "Bearish Researcher",
            "debate": "Debate & Consensus",
            "trader": "Execution Trader",
            "risk_manager": "Risk Manager",
        }
        for k, v in new_statuses.items():
            mapped = name_mapping.get(k, k)
            if mapped in self.agent_statuses:
                self.agent_statuses[mapped] = v
        self.refresh()

    def render(self) -> Table:
        table = Table(title="🤖 AGENT STATUS & MODELS", expand=True, box=None, padding=(0, 1))
        table.add_column("Agent", style="bold cyan")
        table.add_column("Model", style="dim cyan", justify="center")
        table.add_column("State", justify="right")

        icon_map = {
            "IDLE": ("⚪ IDLE", "dim white"),
            "RUNNING": ("⟳ [THINKING...]", "bold yellow"),
            "COMPLETED": ("✅ READY", "bold green"),
            "FAILED": ("❌ ERROR", "bold red"),
        }

        for agent, state in self.agent_statuses.items():
            label, style = icon_map.get(state, ("⚪ IDLE", "dim white"))
            model_tag = self.MODEL_MAP.get(agent, "llm")
            table.add_row(
                agent,
                Text(f"[{model_tag}]", style="dim magenta"),
                Text(label, style=style),
            )

        return table
