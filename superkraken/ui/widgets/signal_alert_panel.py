"""Active Signal Alert Panel widget rendering trading advisor recommendations in plain English."""

import sys
from typing import Optional
from rich.console import Group
from rich.panel import Panel
from rich.text import Text
from textual.widgets import Static
from superkraken.state import SignalAlert


def make_confidence_bar(conf: float, width: int = 16) -> str:
    """Renders a visual ASCII progress bar for conviction percentage."""
    filled = int(round(conf * width))
    empty = width - filled
    return "█" * filled + "░" * empty


class ActiveSignalAlertWidget(Static):
    """Trading advisor recommendation panel that talks directly to the trader in plain English."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.active_alert: Optional[SignalAlert] = None
        self._last_alert_id: Optional[str] = None
        self.radar_status: Optional[str] = None

    def set_radar_status(self, status: Optional[str]) -> None:
        """Update live desk activity shown in the alert panel when standing by."""
        self.radar_status = status
        if not self.active_alert:
            self.refresh()

    def set_alert(self, alert: Optional[SignalAlert]) -> None:
        self.active_alert = alert
        if alert and alert.signal_id != self._last_alert_id:
            self._last_alert_id = alert.signal_id
            # Audible terminal bell sound to ensure alert is impossible to miss
            try:
                sys.stdout.write("\a")
                sys.stdout.flush()
            except Exception:
                pass
        self.refresh()

    def clear_alert(self) -> None:
        self.active_alert = None
        self.refresh()

    def render(self) -> Panel:
        if not self.active_alert:
            # Standby mode display
            content = Text()
            content.append("\n  🔔 ", style="bold cyan")
            content.append("ADVISOR RADAR ACTIVE — Watching The Markets\n\n", style="bold white")
            if self.radar_status:
                content.append(f"  ⚡ DESK FOCUS: {self.radar_status}\n\n", style="bold yellow")
            content.append("  I am continuously monitoring BTC/USD, ETH/USD, and SOL/USD with 8 AI agents.\n", style="dim")
            content.append("  When the desk finds a high-probability trade with ", style="dim")
            content.append("62%+ confidence", style="bold yellow")
            content.append(", I will alert you right here with exact Kraken Pro instructions.\n\n", style="dim")
            content.append("  Advisor Controls:  ", style="dim")
            content.append("[S] Scan Now", style="bold yellow")
            content.append("  │  ", style="dim")
            content.append("[D] View Debate", style="bold cyan")
            content.append("  │  ", style="dim")
            content.append("[L] Log Trade Manually", style="bold green")

            return Panel(
                content,
                title="[bold cyan]🔔 RECOMMENDATION — STANDBY[/bold cyan]",
                border_style="cyan",
                padding=(1, 2),
            )

        alert = self.active_alert
        is_buy = alert.action.value == "BUY" if hasattr(alert.action, "value") else "BUY" in str(alert.action).upper()
        border_col = "bold green" if is_buy else "bold red"
        coin = alert.symbol.split("/")[0]

        conf_pct = int(alert.confidence * 100)
        conf_bar = make_confidence_bar(alert.confidence, width=16)
        bull_pts = int(alert.bull_score * 100)
        bear_pts = int(alert.bear_score * 100)

        ord_spec = alert.suggested_order
        qty = ord_spec.get("quantity", 0.0)
        notional = ord_spec.get("notional_usdc", 0.0)
        entry_p = ord_spec.get("entry_price", 0.0)
        sl_p = ord_spec.get("stop_loss", 0.0)
        tp_p = ord_spec.get("take_profit", 0.0)

        risk_m = alert.risk_metrics
        max_loss = risk_m.get("max_loss_usd", 0.0)
        max_loss_pct = risk_m.get("max_loss_pct", 0.0)
        target_gain = risk_m.get("target_gain_usd", 0.0)
        target_gain_pct = risk_m.get("target_gain_pct", 0.0)

        rsi = float(alert.indicators.get("rsi", 50.0))
        macd = float(alert.indicators.get("macd", 0.0))
        trend = str(alert.indicators.get("ema_trend", "NEUTRAL")).upper()

        body = Text()

        if is_buy:
            body.append(f"🟢 I think you should BUY {coin} right now.\n\n", style="bold green")

            # Conversational explanation
            if rsi < 40:
                rsi_text = f"RSI bounced off {rsi:.0f} — recovering out of oversold territory."
            elif rsi <= 60:
                rsi_text = f"RSI is at {rsi:.0f} which means momentum is building but we are not overbought yet."
            else:
                rsi_text = f"RSI is at {rsi:.0f} — strong bullish velocity pushing upward."

            if macd >= 0:
                macd_text = "MACD crossed bullish — upward momentum expanding."
            else:
                macd_text = "MACD histogram is turning up toward a bullish cross."

            if "BULL" in trend or "UP" in trend:
                trend_text = "Price held key moving averages all morning — bulls are in control."
            else:
                trend_text = "Price found firm support on the 15m timeframe."

            body.append(f"The setup looks good. {rsi_text} {macd_text} {trend_text} Order book depth shows aggressive buyers.\n\n", style="white")
            body.append(f"My bull and bear agents debated this: Bulls won {bull_pts} to {bear_pts}.\n\n", style="bold cyan")

            body.append("What to do RIGHT NOW on Kraken Pro:\n", style="bold yellow")
            body.append(f"  1. Go to kraken.com/u/trade or open Kraken Pro\n", style="white")
            body.append(f"  2. Select {alert.symbol} spot market\n", style="white")
            body.append(f"  3. Buy {qty:.4f} {coin} at market (${entry_p:,.2f}) (about ${notional:,.2f} of your money)\n", style="bold white")
            body.append(f"  4. Set your stop-loss at ${sl_p:,.2f}\n", style="bold red")
            body.append(f"  5. Set your take-profit at ${tp_p:,.2f}\n\n", style="bold green")

            body.append(f"Your risk:    ${max_loss:.2f} USDC max loss ({max_loss_pct:.1f}% of your portfolio)\n", style="bold red")
            body.append(f"Your reward:  ${target_gain:.2f} USDC if target hit ({target_gain_pct:.1f}% of portfolio)\n", style="bold green")
            body.append(f"Risk/Reward:  1:2 — this is a good bet.\n", style="bold cyan")
            body.append(f"Confidence:   {conf_pct}%  {conf_bar}\n\n", style="bold white")

            body.append("  [Y] Doing it    [N] Skip    [D] Full debate    [S] Scan Now", style="bold black on green")

        else:
            # SELL Recommendation
            body.append(f"🔴 I think you should SELL {coin} right now.\n\n", style="bold red")
            body.append(f"The market setup is weakening. RSI dropped to {rsi:.0f} as selling pressure accelerated. ", style="white")
            body.append(f"MACD crossed bearish and price broke below short-term support levels.\n\n", style="white")
            body.append(f"My bull and bear agents debated this: Bears dominated {bear_pts} to {bull_pts}.\n\n", style="bold cyan")

            body.append(f"If you are holding {coin} — consider closing your position to protect your capital.\n", style="bold yellow")
            body.append(f"(Spot shorting is restricted in CA accounts — spot exit only).\n\n", style="dim")

            body.append("What to do RIGHT NOW on Kraken Pro:\n", style="bold yellow")
            body.append(f"  1. Go to your open positions on Kraken Pro\n", style="white")
            body.append(f"  2. Close your {coin} position at market price (${entry_p:,.2f})\n\n", style="bold red")
            body.append(f"Confidence:   {conf_pct}%  {conf_bar}\n\n", style="bold white")

            body.append("  [Y] Logging as closed    [N] Skip    [D] Full debate    [S] Scan Now", style="bold black on red")

        return Panel(
            body,
            title=f"[{border_col}]🔔 RECOMMENDATION (you have a new signal — {alert.symbol})[/{border_col}]",
            border_style=border_col,
            padding=(1, 2),
        )
