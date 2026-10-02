"""Textual widget for live agent debate streaming with color-coded signals."""

from collections import deque
from datetime import datetime
import re
from typing import List, Tuple
from rich.panel import Panel
from rich.text import Text
from textual.widgets import Static


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


class DebateLogWidget(Static):
    """Renders scrolling live adversarial debate and consensus commentary."""

    def __init__(self, max_lines: int = 20, **kwargs):
        super().__init__(**kwargs)
        self.max_lines = max_lines
        self.logs: deque = deque(maxlen=max_lines)

        # Initial placeholder logs
        self.add_log("🐂 Bull", "BTC breaking above 200 EMA, RSI 58, BUY pressure strong.", "green")
        self.add_log("🐻 Bear", "Volume declining on higher timeframes; resistance @ $68,200, HOLD recommended.", "red")
        self.add_log("🤝 Consensus", "Consensus verdict: BUY 0.05 BTC @ market — Confidence: 78%", "bold gold1")

    def add_log(self, speaker: str, message: str, style: str = "white") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.logs.append((ts, speaker, message, style))
        self.refresh()

    def render(self) -> Panel:
        content = Text()
        for ts, speaker, msg, style in self.logs:
            content.append(f"[{ts}] ", style="dim")
            content.append(f"{speaker}: ", style=f"bold {style}")
            highlighted = highlight_trading_signals(msg)
            content.append_text(highlighted)
            content.append("\n")

        return Panel(
            content,
            title="🗣️ AGENT DEBATE LOG",
            border_style="bright_blue",
            expand=True,
        )
