"""Textual widget for live agent debate streaming with color-coded signals."""

from collections import deque
from datetime import datetime
import re
from typing import List, Tuple
from rich.panel import Panel
from rich.text import Text
from textual.widgets import RichLog


def highlight_trading_signals(message: str) -> Text:
    """Format and highlight trading signals and regulatory tags with explicit colors."""
    t = Text()
    # Pattern to match signals and tags
    pattern = re.compile(
        r"(\[CIRCUIT BREAKER(?: TRIGGERED)?\]|\[HEURISTIC FALLBACK\]|\[RESTRICTED: CA\]|\bBUY\b|\bSELL\b|\bHOLD\b)"
    )

    last_idx = 0
    for match in pattern.finditer(message):
        start, end = match.span()
        if start > last_idx:
            t.append(message[last_idx:start], style="white")

        token = match.group(1)
        if "CIRCUIT BREAKER" in token:
            t.append(token, style="bold red blink")
        elif "HEURISTIC FALLBACK" in token:
            t.append(token, style="bold magenta")
        elif "RESTRICTED" in token:
            t.append(token, style="bold dark_orange")
        elif token == "BUY":
            t.append(token, style="bold green")
        elif token == "SELL":
            t.append(token, style="bold red")
        elif token == "HOLD":
            t.append(token, style="bold yellow")
        else:
            t.append(token, style="bold white")

        last_idx = end

    if last_idx < len(message):
        t.append(message[last_idx:], style="white")

    return t


class DebateLogWidget(RichLog):
    """Renders scrolling live adversarial debate and consensus commentary with full scroll support."""

    DEFAULT_CSS = """
    DebateLogWidget {
        background: #0f141c;
        color: #e6edf3;
        border: round #3b82f6;
        border-title-align: center;
        border-title-color: #60a5fa;
        overflow-y: scroll;
        scrollbar-size-vertical: 1;
        scrollbar-color: #3b82f6;
        scrollbar-background: #161b22;
        padding: 0 1;
    }
    DebateLogWidget:focus {
        border: round #93c5fd;
    }
    """

    def __init__(self, max_lines: int = 1000, **kwargs):
        super().__init__(
            max_lines=max_lines,
            wrap=True,
            highlight=False,
            markup=False,
            auto_scroll=True,
            **kwargs,
        )
        self.can_focus = True
        self.border_title = "🗣️ AGENT DEBATE LOG"
        self._initial_logs = [
            ("🐂 Bull", "BTC breaking above 200 EMA, RSI 58, BUY pressure strong.", "green"),
            ("🐻 Bear", "Volume declining on higher timeframes; resistance @ $68,200, HOLD recommended.", "red"),
            ("🤝 Consensus", "Consensus verdict: BUY 0.05 BTC @ market — Confidence: 78%", "bold gold1"),
        ]

    def on_mount(self) -> None:
        for speaker, msg, style in self._initial_logs:
            self.add_log(speaker, msg, style)

    def add_log(self, speaker: str, message: str, style: str = "white") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        line = Text()
        line.append(f"[{ts}] ", style="dim")
        line.append(f"{speaker}: ", style=f"bold {style}")
        highlighted = highlight_trading_signals(message)
        line.append_text(highlighted)
        self.write(line)
