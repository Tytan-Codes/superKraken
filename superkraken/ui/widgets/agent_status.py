"""Textual widget for agent status overview with thinking spinners and scrollable compact layout."""

from typing import Dict, List, Optional
from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual.binding import Binding
from textual.widgets import Static
from superkraken.config import settings


def short_model_name(model_id: str) -> str:
    """Return concise model alias that fits cleanly on a single row."""
    m = model_id.lower()
    if "v4.1-flash" in m:
        return "v4.1-flash"
    elif "v4-flash" in m:
        return "v4-flash"
    elif "glm-5.3" in m:
        return "glm-5.3"
    elif "/" in model_id:
        return model_id.split("/")[-1][:12]
    return model_id[:12]


class AgentStatusWidget(Static):
    """Renders the real-time status of each specialized agent in a scrollable compact format."""

    DEFAULT_CSS = """
    AgentStatusWidget {
        height: 100%;
    }
    AgentStatusWidget:focus {
        border: round #58a6ff;
    }
    """
    can_focus = True

    BINDINGS = [
        Binding("up", "scroll_up", "Scroll Up", show=False),
        Binding("down", "scroll_down", "Scroll Down", show=False),
        Binding("k", "scroll_up", "Scroll Up", show=False),
        Binding("j", "scroll_down", "Scroll Down", show=False),
    ]

    SPINNERS = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    AGENTS_CONFIG = [
        ("technical", "📊 Technical", settings.model_technical),
        ("sentiment", "📰 Sentiment", settings.model_sentiment),
        ("fundamental", "📈 Fundamental", settings.model_fundamental),
        ("bull_researcher", "🐂 Bull", settings.model_bull),
        ("bear_researcher", "🐻 Bear", settings.model_bear),
        ("debate", "🤝 Debate", settings.model_debate),
        ("trader", "⚡ Trader", settings.model_trader),
        ("risk_manager", "🛡️ Risk", settings.model_risk),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.spinner_idx = 0
        self.agent_scroll_offset = 0
        self.max_display_rows = 8  # Full 8 agents visible in standard terminal
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
        self.agent_signals: Dict[str, str] = {
            "technical": "BUY  72%",
            "sentiment": "BUY  68%",
            "fundamental": "BULL 71%",
            "bull_researcher": "BULL 80%",
            "bear_researcher": "BEAR 45%",
            "debate": "BUY  78%",
            "trader": "BUY  0.029",
            "risk_manager": "APPROVED",
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

    def update_signals(self, new_signals: Dict[str, str]) -> None:
        for k, v in new_signals.items():
            if k in self.agent_signals:
                self.agent_signals[k] = v
        self.refresh()

    def action_scroll_up(self) -> None:
        if self.agent_scroll_offset > 0:
            self.agent_scroll_offset -= 1
            self.refresh()

    def action_scroll_down(self) -> None:
        max_offset = max(0, len(self.AGENTS_CONFIG) - self.max_display_rows)
        if self.agent_scroll_offset < max_offset:
            self.agent_scroll_offset += 1
            self.refresh()

    def render(self) -> Group:
        # Determine available row height
        widget_height = self.size.height if self.size.height > 0 else 12
        # Deduct title, padding, and potential scroll indicators
        visible_rows = max(4, widget_height - 3)
        self.max_display_rows = min(len(self.AGENTS_CONFIG), visible_rows)

        total_agents = len(self.AGENTS_CONFIG)
        end_idx = min(total_agents, self.agent_scroll_offset + self.max_display_rows)
        displayed_agents = self.AGENTS_CONFIG[self.agent_scroll_offset:end_idx]

        table = Table(
            title="🤖 AGENT COGNITION & STATUS [dim]([A] to focus)[/dim]",
            expand=True,
            box=None,
            padding=(0, 1),
            show_header=False,
        )
        table.add_column("Agent", style="bold cyan", no_wrap=True, width=15)
        table.add_column("Status & Model", no_wrap=True)
        table.add_column("Signal / Action", justify="right", no_wrap=True, width=12)

        spinner_char = self.SPINNERS[self.spinner_idx]

        for key, name, model_full in displayed_agents:
            model_short = short_model_name(model_full)
            state = self.agent_statuses.get(key, "IDLE").upper()
            sig_text = self.agent_signals.get(key, "-")

            # Format status text
            if state in ("RUNNING", "THINKING"):
                status_text = Text(f"{spinner_char} THINKING [{model_short}]...", style="bold yellow")
            elif state in ("COMPLETED", "COMPLETE", "READY"):
                status_text = Text(f"✅ COMPLETE [{model_short}]", style="bold green")
            elif state in ("FAILED", "ERROR"):
                status_text = Text(f"❌ ERROR [{model_short}]", style="bold red")
            elif state == "WAITING":
                status_text = Text("⏳ WAITING", style="dim cyan")
            else:
                status_text = Text(f"⚪ IDLE [{model_short}]", style="dim white")

            # Format signal text
            if state == "WAITING":
                signal_rich = Text("-", style="dim")
            elif "BUY" in sig_text or "APPROVED" in sig_text or "BULL" in sig_text:
                signal_rich = Text(sig_text, style="bold green")
            elif "SELL" in sig_text or "REJECTED" in sig_text or "BEAR" in sig_text:
                signal_rich = Text(sig_text, style="bold red")
            elif "HOLD" in sig_text:
                signal_rich = Text(sig_text, style="bold yellow")
            elif "HEURISTIC FALLBACK" in sig_text:
                signal_rich = Text(sig_text, style="bold magenta")
            elif "RESTRICTED" in sig_text:
                signal_rich = Text(sig_text, style="bold dark_orange")
            else:
                signal_rich = Text(sig_text, style="white")

            table.add_row(name, status_text, signal_rich)

        renderables = []
        if self.agent_scroll_offset > 0:
            renderables.append(Text(f"▲ {self.agent_scroll_offset} more above", style="bold cyan justify=center"))

        renderables.append(table)

        remaining_below = total_agents - end_idx
        if remaining_below > 0:
            renderables.append(Text(f"▼ {remaining_below} more below (press [A] then ↓)", style="bold yellow justify=center"))

        return Group(*renderables)
