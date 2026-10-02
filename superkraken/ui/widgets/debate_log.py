"""Textual widget for live agent debate streaming with color-coded signals and keyboard scrolling."""

from collections import deque
from datetime import datetime
import re
from typing import List, Tuple
from rich.console import Group
from rich.panel import Panel
from rich.text import Text
from textual.binding import Binding
from textual.widgets import Static


def highlight_trading_signals(message: str) -> Text:
    """Format and highlight trading signals and regulatory tags with explicit colors."""
    t = Text()
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
    """Renders scrolling live adversarial debate and consensus commentary with focus navigation."""

    DEFAULT_CSS = """
    DebateLogWidget {
        height: 1fr;
    }
    DebateLogWidget:focus {
        border: round #58a6ff;
    }
    """
    can_focus = True

    BINDINGS = [
        Binding("up", "scroll_up", "Scroll Up", show=False),
        Binding("down", "scroll_down", "Scroll Down", show=False),
        Binding("pageup", "page_up", "Page Up", show=False),
        Binding("pagedown", "page_down", "Page Down", show=False),
        Binding("k", "scroll_up", "Scroll Up", show=False),
        Binding("j", "scroll_down", "Scroll Down", show=False),
    ]

    def __init__(self, max_lines: int = 200, **kwargs):
        super().__init__(**kwargs)
        self.max_lines = max_lines
        self.logs: deque = deque(maxlen=max_lines)
        self.scroll_from_bottom: int = 0  # 0 means auto-scrolled to latest

        # Initial placeholder logs
        self.add_log("🐂 Bull", "BTC breaking above 200 EMA, RSI 58, BUY pressure strong.", "green")
        self.add_log("🐻 Bear", "Volume declining on higher timeframes; resistance @ $68,200, HOLD recommended.", "red")
        self.add_log("🤝 Consensus", "Consensus verdict: BUY 0.05 BTC @ market — Confidence: 78%", "bold gold1")

    def add_log(self, speaker: str, message: str, style: str = "white") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.logs.append((ts, speaker, message, style))
        self.refresh()

    def action_scroll_up(self) -> None:
        # Scroll up into history
        if self.scroll_from_bottom < len(self.logs) - 3:
            self.scroll_from_bottom += 1
            self.refresh()

    def action_scroll_down(self) -> None:
        # Scroll down towards latest
        if self.scroll_from_bottom > 0:
            self.scroll_from_bottom -= 1
            self.refresh()

    def action_page_up(self) -> None:
        self.scroll_from_bottom = min(len(self.logs) - 3, self.scroll_from_bottom + 5)
        self.refresh()

    def action_page_down(self) -> None:
        self.scroll_from_bottom = max(0, self.scroll_from_bottom - 5)
        self.refresh()

    def render(self) -> Panel:
        all_logs = list(self.logs)
        total_logs = len(all_logs)

        # Estimate visible capacity
        widget_height = self.size.height if self.size.height > 0 else 18
        visible_lines = max(5, widget_height - 4)

        if self.scroll_from_bottom == 0:
            display_logs = all_logs[-visible_lines:]
            hidden_above = max(0, total_logs - visible_lines)
            hidden_below = 0
        else:
            end_idx = total_logs - self.scroll_from_bottom
            start_idx = max(0, end_idx - visible_lines)
            display_logs = all_logs[start_idx:end_idx]
            hidden_above = start_idx
            hidden_below = self.scroll_from_bottom

        content = Text()
        if hidden_above > 0:
            content.append(f"▲ {hidden_above} older debate messages above (press [L] then ↑)\n", style="bold cyan")

        for ts, speaker, msg, style in display_logs:
            content.append(f"[{ts}] ", style="dim")
            content.append(f"{speaker}: ", style=f"bold {style}")
            highlighted = highlight_trading_signals(msg)
            content.append_text(highlighted)
            content.append("\n")

        if hidden_below > 0:
            content.append(f"▼ {hidden_below} newer debate messages below (press [L] then ↓)\n", style="bold yellow")

        return Panel(
            content,
            title="🗣️ AGENT DEBATE LOG [dim]([L] to focus & scroll)[/dim]",
            border_style="bright_blue",
            expand=True,
        )
