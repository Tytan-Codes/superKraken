"""Textual widget for scrolling notifications and system alerts ticker."""

from collections import deque
from datetime import datetime
from typing import List, Tuple
from rich.text import Text
from textual.widgets import Static


class NotificationsBarWidget(Static):
    """Scrolling notifications bar showing last 5 trading and desk events."""

    def __init__(self, max_items: int = 5, **kwargs):
        super().__init__(**kwargs)
        self.max_items = max_items
        self.events: deque = deque(maxlen=max_items)
        # Default starting events
        self.add_event("superKraken Desk armed and online", "info")
        self.add_event("Risk Manager: 10% daily drawdown circuit breaker active", "info")

    def add_event(self, message: str, level: str = "info") -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.events.append((ts, message, level))
        self.refresh()

    def render(self) -> Text:
        ticker = Text()
        ticker.append(" 🔔 EVENTS: ", style="bold gold1")
        if not self.events:
            ticker.append("Desk monitoring live market feeds...", style="dim")
            return ticker

        items = []
        for ts, msg, lvl in list(self.events)[-self.max_items:]:
            if lvl == "warn" or "circuit" in msg.lower() or "stop" in msg.lower():
                style = "bold red"
            elif lvl == "fill" or "executed" in msg.lower() or "buy" in msg.lower():
                style = "bold green"
            else:
                style = "white"
            item = Text()
            item.append(f"[{ts}] ", style="dim")
            item.append(msg, style=style)
            items.append(item)

        for i, it in enumerate(items):
            if i > 0:
                ticker.append(" │ ", style="dim cyan")
            ticker.append_text(it)

        return ticker
