"""Agent signals summary widget displaying current signal per pair and scan countdown timer."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from rich.table import Table
from rich.text import Text
from textual.widgets import Static


class AgentSignalsWidget(Static):
    """Displays multi-pair agent signals and live next scan countdown."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.signals: Dict[str, Dict[str, Any]] = {
            "BTC/USD": {"action": "HOLD", "confidence": 0.50, "time": "--:--"},
            "ETH/USD": {"action": "HOLD", "confidence": 0.50, "time": "--:--"},
            "SOL/USD": {"action": "HOLD", "confidence": 0.50, "time": "--:--"},
        }
        self.seconds_until_next_scan: int = 300
        self.is_scanning: bool = False

    def update_signal(self, symbol: str, action: str, confidence: float) -> None:
        short_sym = symbol.replace("XXBTZUSD", "BTC/USD").replace("XETHZUSD", "ETH/USD")
        now_str = datetime.now().strftime("%H:%M")
        self.signals[short_sym] = {
            "action": action.upper(),
            "confidence": confidence,
            "time": now_str,
        }
        self.refresh()

    def update_signals(self, results: List[Dict[str, Any]]) -> None:
        for r in results:
            sym = r.get("symbol", "")
            act = r.get("action", "HOLD")
            conf = float(r.get("confidence", 0.50))
            self.update_signal(sym, act, conf)
        self.refresh()

    def update_scan_timer(self, seconds_left: int) -> None:
        self.seconds_until_next_scan = max(0, seconds_left)
        self.refresh()

    def set_scanning(self, is_scanning: bool) -> None:
        self.is_scanning = is_scanning
        self.refresh()

    def update_countdown(self, seconds_left: int, is_scanning: bool = False) -> None:
        self.seconds_until_next_scan = max(0, seconds_left)
        self.is_scanning = is_scanning
        self.refresh()

    def render(self) -> Table:
        table = Table(title="🤖 AGENT SIGNALS", expand=True, box=None, padding=(0, 1))
        table.add_column("Pair", style="bold white", width=6)
        table.add_column("Signal", width=10)
        table.add_column("Conviction", justify="right")

        for sym, d in self.signals.items():
            short_label = sym.split("/")[0]
            act = d.get("action", "HOLD")
            conf = int(d.get("confidence", 0.50) * 100)

            if act == "BUY":
                sig_text = Text(f"🟢 BUY", style="bold green")
            elif act == "SELL":
                sig_text = Text(f"🔴 SELL", style="bold red")
            else:
                sig_text = Text(f"🟡 HOLD", style="bold yellow")

            table.add_row(short_label, sig_text, f"{conf}% conf")

        # Countdown row
        mins = self.seconds_until_next_scan // 60
        secs = self.seconds_until_next_scan % 60
        if self.is_scanning:
            status_text = Text("⠸ Scanning agents...", style="bold cyan")
        else:
            status_text = Text(f"⏱️ Next scan: {mins}:{secs:02d}", style="dim cyan")

        table.add_row("", "", "")
        table.add_row("Status", status_text, Text("[S] Scan Now", style="dim yellow"))

        return table
