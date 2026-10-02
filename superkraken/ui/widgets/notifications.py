"""Textual widget for scrolling notifications and system alerts ticker."""

from collections import deque
from datetime import datetime
from typing import List, Tuple
from rich.text import Text
from textual.widgets import Static


class NotificationsBarWidget(Static):
    """Scrolling notifications bar showing last 5 trading and desk events in real time."""

    def __init__(self, max_items: int = 5, **kwargs):
        super().__init__(**kwargs)
        self.max_items = max_items
        self.events: deque = deque(maxlen=max_items)
        # Default starting events
        self.add_event("superKraken Desk armed and online", "info")
        self.add_event("Risk rules active (max 25% │ 3% stop-loss │ 10% drawdown)", "info")
        self.add_event("🇨🇦 Canadian account detected — spot only", "info")

    def add_event(self, message: str, level: str = "info") -> None:
        clean = message.strip()
        # Ensure contextual status emoji prefix
        if not any(clean.startswith(e) for e in ("🟢", "🔴", "🟡", "🇨🇦", "🛡️", "🚨", "⚡")):
            if "filled" in clean.lower() or "fill" in clean.lower() or "buy" in clean.lower():
                clean = f"🟢 {clean}"
            elif "hold" in clean.lower():
                clean = f"🟡 {clean}"
            elif "sell" in clean.lower():
                clean = f"🔴 {clean}"
            elif "futures" in clean.lower() or "margin" in clean.lower() or "restricted" in clean.lower():
                clean = f"🇨🇦 {clean}"
            elif "loss" in clean.lower() or "tightened" in clean.lower() or "risk" in clean.lower():
                clean = f"🛡️ {clean}"
            elif "circuit" in clean.lower():
                clean = f"🚨 {clean}"

        self.events.append(clean)
        self.refresh()

    def render(self) -> Text:
        ticker = Text()
        ticker.append(" 🔔 ", style="bold gold1")
        if not self.events:
            ticker.append("Desk monitoring live market feeds...", style="dim")
            return ticker

        items = []
        for msg in list(self.events)[-self.max_items:]:
            if "🚨" in msg or "circuit" in msg.lower() or "stop" in msg.lower():
                style = "bold red"
            elif "🟢" in msg or "filled" in msg.lower() or "buy" in msg.lower():
                style = "bold green"
            elif "🟡" in msg or "hold" in msg.lower():
                style = "bold yellow"
            elif "🇨🇦" in msg or "restricted" in msg.lower():
                style = "bold dark_orange"
            elif "🛡️" in msg:
                style = "cyan"
            else:
                style = "white"

            items.append(Text(msg, style=style))

        for i, it in enumerate(items):
            if i > 0:
                ticker.append("  │  ", style="dim cyan")
            ticker.append_text(it)

        return ticker
