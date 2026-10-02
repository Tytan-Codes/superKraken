"""Textual widget for live agent debate streaming."""

from collections import deque
from datetime import datetime
from typing import List, Tuple
from rich.panel import Panel
from rich.text import Text
from textual.widgets import Static


class DebateLogWidget(Static):
    """Renders scrolling live adversarial debate and consensus commentary."""

    def __init__(self, max_lines: int = 15, **kwargs):
        super().__init__(**kwargs)
        self.max_lines = max_lines
        self.logs: deque = deque(maxlen=max_lines)

        # Initial placeholder logs
        self.add_log("🐂 Bull", "BTC breaking above 200 EMA, RSI 58, momentum strong.", "green")
        self.add_log("🐻 Bear", "Volume declining on higher timeframes; watching resistance @ $68,200.", "red")
        self.add_log("🤝 Consensus", "BUY 0.05 BTC @ market — Confidence: 78%", "bold gold1")

    def add_log(self, speaker: str, message: str, style: str = "white") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.logs.append((ts, speaker, message, style))
        self.refresh()

    def render(self) -> Panel:
        content = Text()
        for ts, speaker, msg, style in self.logs:
            content.append(f"[{ts}] ", style="dim")
            content.append(f"{speaker}: ", style=f"bold {style}")
            content.append(f"{msg}\n", style="white")

        return Panel(
            content,
            title="🗣️ AGENT DEBATE LOG",
            border_style="bright_blue",
            expand=True,
        )
