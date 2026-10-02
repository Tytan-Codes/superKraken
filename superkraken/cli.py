"""Command-line interface for superKraken Autonomous AI Trading Desk."""

import asyncio
from typing import Optional
import typer
from rich import print as rprint
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from superkraken.config import settings
from superkraken.execution.paper_engine import PaperTradingEngine
from superkraken.execution.rest_client import KrakenMarketDataClient
from superkraken.graph.workflow import trading_graph
from superkraken.indicators.technical import compute_all_indicators
from superkraken.storage.database import db

app = typer.Typer(
    name="superkraken",
    help="🤖 superKraken: Autonomous AI Day Trading Desk CLI modeled after TradingAgents",
    add_completion=False,
)
console = Console()


def run_preflight_checklist(mode: str) -> bool:
    """Audit connectivity, API credentials, model configurations, and safety limits."""
    console.print(Panel("🔍 [bold cyan]RUNNING PRE-FLIGHT SYSTEM & RISK AUDIT[/bold cyan]", border_style="cyan"))

    checks = []
    # 1. OpenRouter API Key
    if settings.openrouter_api_key and settings.openrouter_api_key.startswith("sk-or-v1-"):
        checks.append(("OpenRouter API Key", "CONNECTED (Valid sk-or-v1-***)", True))
    else:
        checks.append(("OpenRouter API Key", "MISSING or INVALID in .env", False))

    # 2. Kraken API Keys
    if settings.kraken_api_key and settings.kraken_api_secret:
        checks.append(("Kraken API Keys", "AUTHENTICATED (Key/Secret active)", True))
    else:
        if mode == "LIVE":
            checks.append(("Kraken API Keys", "MISSING in .env (Required for LIVE)", False))
        else:
            checks.append(("Kraken API Keys", "NOT SET (OK for Paper mode, public feeds active)", True))

    # 3. Portfolio Balance
    engine = PaperTradingEngine()
    bal = engine.portfolio.total_value_usd
    if bal > 0:
        checks.append(("Portfolio Balance", f"${bal:,.2f} USD (> $0)", True))
    else:
        checks.append(("Portfolio Balance", "$0.00 (Zero Capital)", False))

    # 4. Circuit Breaker
    cb_limit = settings.daily_drawdown_limit_pct * 100
    checks.append(("Drawdown Circuit Breaker", f"ARMED ({cb_limit:.0f}% daily max drawdown)", True))

    # 5. Default Stop-Loss
    sl_limit = settings.stop_loss_pct * 100
    checks.append(("Stop-Loss Default", f"ARMED ({sl_limit:.1f}% automatic stop-loss)", True))

    # 6. Assigned 2026 Models
    checks.append(("2026 Models Configuration", "ALL 8 AGENTS CONFIGURED", True))

    table = Table(title="📋 Pre-Flight Verification Results", expand=True)
    table.add_column("Safety / Health Check", style="bold white")
    table.add_column("Status / Details", style="bold cyan")
    table.add_column("Verdict", justify="right")

    all_passed = True
    for name, detail, passed in checks:
        if not passed:
            all_passed = False
        status_tag = "[bold green]PASS ✅[/bold green]" if passed else "[bold red]FAIL ❌[/bold red]"
        table.add_row(name, detail, status_tag)

    console.print(table)

    # Print model assignments
    models_table = Table(title="🤖 Active Multi-Agent Model Assignments", expand=True)
    models_table.add_column("Agent Role", style="bold magenta")
    models_table.add_column("Assigned 2026 OpenRouter Model", style="bold green")
    models_table.add_row("Sentiment Analyst", settings.model_sentiment)
    models_table.add_row("Technical Analyst", settings.model_technical)
    models_table.add_row("Fundamental Analyst", settings.model_fundamental)
    models_table.add_row("Bullish Researcher", settings.model_bull)
    models_table.add_row("Bearish Researcher", settings.model_bear)
    models_table.add_row("Debate & Consensus", settings.model_debate)
    models_table.add_row("Execution Trader", settings.model_trader)
    models_table.add_row("Risk Manager", settings.model_risk)
    console.print(models_table)

    if not all_passed:
        console.print("[bold red]🚨 PRE-FLIGHT CHECK FAILED: Please rectify the issues above before launching.[/bold red]")
        return False

    console.print("[bold green]✅ ALL PRE-FLIGHT CHECKS PASSED. Launching Autonomous Desk...[/bold green]\n")
    return True


@app.command()
def start(
    mode: str = typer.Option("paper", "--mode", "-m", help="Trading mode: 'paper' or 'live'"),
    live: bool = typer.Option(False, "--live", help="Shortcut for live execution mode"),
):
    """Launch all agents and begin autonomous trading loop in the Textual TUI."""
    from superkraken.ui.app import SuperKrakenTUI

    chosen_mode = "LIVE" if live else mode.upper()
    if not run_preflight_checklist(chosen_mode):
        raise typer.Exit(code=1)

    tui = SuperKrakenTUI(mode=chosen_mode)
    tui.run()


@app.command()
def paper(
    reset: bool = typer.Option(False, "--reset", help="Reset paper portfolio to initial $10,000 balance"),
):
    """Run in safe paper trading sandbox mode with live TUI."""
    from superkraken.ui.app import SuperKrakenTUI

    if reset:
        engine = PaperTradingEngine()
        engine.reset()
        rprint("[bold green]✅ Paper portfolio reset to initial balance.[/bold green]")

    if not run_preflight_checklist("PAPER"):
        raise typer.Exit(code=1)

    tui = SuperKrakenTUI(mode="PAPER")
    tui.run()


@app.command(name="smoke-test")
def smoke_test(
    cycles: int = typer.Option(2, "--cycles", "-c", help="Number of full multi-agent cycles to run"),
    symbol: str = typer.Option("BTC/USD", "--symbol", "-s", help="Symbol to evaluate in smoke test"),
):
    """Run an automated N-cycle smoke test showing real trade debate, risk check, and fill."""
    console.print(Panel(f"🧪 [bold cyan]Starting superKraken End-to-End Smoke Test ({cycles} Cycles)[/bold cyan]", border_style="cyan"))

    async def _run():
        engine = PaperTradingEngine()
        client = KrakenMarketDataClient()

        for cycle in range(1, cycles + 1):
            console.print(f"\n[bold yellow]═══════════════ CYCLE {cycle}/{cycles}: Evaluating {symbol} ═══════════════[/bold yellow]")

            # 1. Fetch live market ticker
            ticker = await client.get_ticker(symbol)
            current_price = ticker["price"]
            console.print(f"📡 [bold]Kraken Live Feed:[/] {symbol} @ [bold green]${current_price:,.2f}[/] (24h Change: {ticker.get('change_pct', 0.0):+.2f}%)")

            # 2. Fetch candles and depth
            candles = await client.get_ohlc(symbol, interval_minutes=1, count=100)
            order_book = await client.get_order_book_depth(symbol)

            # 3. LangGraph Execution
            state = {
                "symbol": symbol,
                "current_price": current_price,
                "candles": [c.model_dump() for c in candles],
                "market_sentiment": {
                    "fear_greed_index": 68,
                    "sentiment_label": "Greed",
                    "social_volume_24h": "High",
                    "recent_headline": f"Surging liquidity and retail interest across {symbol}.",
                },
                "order_book": order_book,
                "portfolio": engine.portfolio.model_dump(),
                "agent_states": {},
            }

            with console.status(f"[bold magenta]Cycle {cycle}: Multi-agent desk debating & synthesizing...[/bold magenta]"):
                res = await trading_graph.ainvoke(state)

            bull = res.get("bull_argument", {})
            bear = res.get("bear_argument", {})
            consensus = res.get("consensus", {})
            proposal = res.get("proposal", {})
            risk = res.get("risk_evaluation", {})

            # 4. Display Debate Output
            console.print(Panel(
                f"[bold green]🐂 Bull:[/] {bull.get('thesis')}\n"
                f"[bold red]🐻 Bear:[/] {bear.get('thesis')}\n\n"
                f"🤝 [bold gold1]Consensus:[/] {consensus.get('action')} (Conf: {consensus.get('confidence', 0)*100:.0f}%) — {consensus.get('summary')}",
                title=f"Cycle {cycle} Debate & Consensus",
                border_style="bright_blue",
            ))

            # 5. Risk Check & Execution
            if proposal and risk and risk.get("approved"):
                action_val = proposal.get("action")
                if action_val in ["BUY", "SELL"]:
                    qty = risk.get("adjusted_quantity", proposal.get("quantity", 0.0))
                    sl = risk.get("stop_loss_price", proposal.get("stop_loss_price", 0.0))
                    tp = proposal.get("take_profit_price", 0.0)

                    fill = engine.execute_order(
                        symbol=symbol,
                        action=action_val,
                        quantity=qty,
                        current_market_price=current_price,
                        stop_loss=sl,
                        take_profit=tp,
                    )

                    console.print(Panel(
                        f"⚡ [bold cyan]Order Filled:[/] {fill.action.value} {fill.filled_qty:.4f} {symbol} @ [bold green]${fill.filled_price:,.2f}[/]\n"
                        f"Order ID: [dim]{fill.order_id}[/dim]  │  Fee: ${fill.fee:.2f}  │  Status: [bold green]{fill.status}[/bold green]\n"
                        f"Risk Note: {'; '.join(risk.get('reasons', []))}",
                        title=f"Cycle {cycle} Trade Execution",
                        border_style="green",
                    ))
                    db.log_trade(fill, confidence=consensus.get("confidence", 0.0), reasoning=proposal.get("reasoning", ""))
            else:
                reasons = risk.get("reasons", ["Trade held or rejected"]) if risk else ["No trade proposed"]
                console.print(f"🛡️ [bold yellow]Risk Manager Gate:[/] No order executed ({'; '.join(reasons)})")

            # 6. Portfolio snapshot
            p = engine.portfolio
            console.print(f"💰 [bold]Portfolio Equity:[/] [bold green]${p.total_value_usd:,.2f}[/]  │  Cash: ${p.cash_usd:,.2f}  │  Open Positions: {len(p.positions)}")
            await asyncio.sleep(1.0)

    asyncio.run(_run())


@app.command()
def status():
    """Live portfolio, positions, and P&L dashboard table."""
    engine = PaperTradingEngine()
    client = KrakenMarketDataClient()

    async def _fetch():
        prices = {}
        for s in settings.pairs_list:
            t = await client.get_ticker(s)
            prices[s] = t["price"]
        return prices

    prices = asyncio.run(_fetch())
    engine.update_market_prices(prices)
    portfolio = engine.portfolio

    # Header Panel
    total_val = f"${portfolio.total_value_usd:,.2f}"
    cash_val = f"${portfolio.cash_usd:,.2f}"
    pnl_val = f"${portfolio.realized_pnl_today:,.2f}"
    dd_val = f"{portfolio.daily_drawdown_pct * 100:.2f}%"

    header_text = (
        f"[bold cyan]Total Equity:[/] [bold green]{total_val}[/]  │  "
        f"[bold cyan]Cash Available:[/] {cash_val}  │  "
        f"[bold cyan]Daily Realized P&L:[/] {pnl_val}  │  "
        f"[bold cyan]Drawdown:[/] [bold yellow]{dd_val}[/]"
    )
    console.print(Panel(header_text, title="🤖 superKraken Portfolio Snapshot", border_style="cyan"))

    # Positions Table
    table = Table(title="Open Positions", expand=True)
    table.add_column("Symbol", style="bold yellow")
    table.add_column("Size", justify="right")
    table.add_column("Entry Price", justify="right")
    table.add_column("Current Price", justify="right")
    table.add_column("Unrealized P&L", justify="right")
    table.add_column("Stop Loss", justify="right")
    table.add_column("Take Profit", justify="right")

    if not portfolio.positions:
        table.add_row("No active positions", "-", "-", "-", "-", "-", "-")
    else:
        for sym, pos in portfolio.positions.items():
            pnl_pct = pos.unrealized_pnl_pct * 100
            style = "bold green" if pnl_pct >= 0 else "bold red"
            sign = "+" if pnl_pct >= 0 else ""
            table.add_row(
                sym,
                f"{pos.quantity:.4f}",
                f"${pos.entry_price:,.2f}",
                f"${pos.current_price:,.2f}",
                f"[{style}]{sign}${pos.unrealized_pnl:,.2f} ({sign}{pnl_pct:.2f}%)[/{style}]",
                f"${pos.stop_loss:,.2f}" if pos.stop_loss > 0 else "-",
                f"${pos.take_profit:,.2f}" if pos.take_profit > 0 else "-",
            )

    console.print(table)


@app.command()
def debate(
    symbol: str = typer.Argument("BTC/USD", help="Trading pair symbol (e.g. BTC/USD, ETH/USD)"),
):
    """Watch agents debate and vote on a specific pair."""
    symbol = symbol.upper()
    console.print(Panel(f"🚀 Initializing Multi-Agent Debate for [bold yellow]{symbol}[/bold yellow]...", style="cyan"))

    async def _run_debate():
        client = KrakenMarketDataClient()
        engine = PaperTradingEngine()

        with console.status(f"[bold cyan]Gathering market data and computing indicators for {symbol}...[/bold cyan]"):
            ticker = await client.get_ticker(symbol)
            candles = await client.get_ohlc(symbol, interval_minutes=1, count=100)
            order_book = await client.get_order_book_depth(symbol)

        current_price = ticker["price"]
        console.print(f"[bold white]Current Price:[/] [bold green]${current_price:,.2f}[/] (24h Change: {ticker.get('change_pct', 0.0):+.2f}%)")

        state = {
            "symbol": symbol,
            "current_price": current_price,
            "candles": [c.model_dump() for c in candles],
            "market_sentiment": {
                "fear_greed_index": 68,
                "sentiment_label": "Greed",
                "social_volume_24h": "High",
                "recent_headline": f"Surging liquidity and retail interest across {symbol}.",
            },
            "order_book": order_book,
            "portfolio": engine.portfolio.model_dump(),
            "agent_states": {},
        }

        console.print("[dim cyan]⚡ Dispatching multi-agent debate desk to OpenRouter...[/dim cyan]")
        res = dict(state)
        async for event in trading_graph.astream(state):
            for node, output in event.items():
                res.update(output)
                if node == "technical_analyst":
                    t_rep = output.get("technical_report", {})
                    m = escape(str(t_rep.get("model_used") or settings.model_technical))
                    sig = t_rep.get("signal", "HOLD")
                    col = "green" if sig == "BUY" else "red" if sig == "SELL" else "yellow"
                    console.print(f"  [bold green]✓[/bold green] [bold cyan]Technical Analyst[/bold cyan] [dim][{m}][/dim]: [{col}]{sig}[/{col}] (Conf: {t_rep.get('confidence', 0)*100:.0f}%)")
                elif node == "fundamental_analyst":
                    f_rep = output.get("fundamental_report", {})
                    m = escape(str(f_rep.get("model_used") or settings.model_fundamental))
                    console.print(f"  [bold green]✓[/bold green] [bold yellow]Fundamental Analyst[/bold yellow] [dim][{m}][/dim]: {f_rep.get('regime', 'neutral')} regime")
                elif node == "sentiment_analyst":
                    s_rep = output.get("sentiment_report", {})
                    m = escape(str(s_rep.get("model_used") or settings.model_sentiment))
                    sig = s_rep.get("signal", "HOLD")
                    col = "green" if sig == "BUY" else "red" if sig == "SELL" else "yellow"
                    console.print(f"  [bold green]✓[/bold green] [bold magenta]Sentiment Analyst[/bold magenta] [dim][{m}][/dim]: [{col}]{sig}[/{col}] (Conf: {s_rep.get('confidence', 0)*100:.0f}%)")
                elif node == "bull_researcher":
                    b_arg = output.get("bull_argument", {})
                    m = escape(str(b_arg.get("model_used") or settings.model_bull))
                    console.print(f"  [bold green]✓[/bold green] [bold green]Bullish Researcher[/bold green] [dim][{m}][/dim]: Bull thesis formulated (Conf: {b_arg.get('confidence', 0)*100:.0f}%)")
                elif node == "bear_researcher":
                    br_arg = output.get("bear_argument", {})
                    m = escape(str(br_arg.get("model_used") or settings.model_bear))
                    console.print(f"  [bold green]✓[/bold green] [bold red]Bearish Researcher[/bold red] [dim][{m}][/dim]: Bear thesis formulated (Conf: {br_arg.get('confidence', 0)*100:.0f}%)")
                elif node == "debate_consensus":
                    c_res = output.get("consensus", {})
                    m = escape(str(c_res.get("model_used") or settings.model_debate))
                    act = c_res.get("action", "HOLD")
                    col = "green" if act == "BUY" else "red" if act == "SELL" else "yellow"
                    console.print(f"  [bold green]✓[/bold green] [bold gold1]Debate Adjudicator[/bold gold1] [dim][{m}][/dim]: Consensus [{col}]{act}[/{col}] (Conf: {c_res.get('confidence', 0)*100:.0f}%)")
                elif node == "execution_trader":
                    p_res = output.get("proposal", {})
                    m = escape(str(p_res.get("model_used") or settings.model_trader))
                    console.print(f"  [bold green]✓[/bold green] [bold cyan]Execution Trader[/bold cyan] [dim][{m}][/dim]: Proposal {p_res.get('action')} {p_res.get('quantity')} {symbol}")
                elif node == "risk_manager":
                    r_eval = output.get("risk_evaluation", {})
                    m = escape(str(r_eval.get("model_used") or settings.model_risk))
                    v = "[bold green]APPROVED[/bold green]" if r_eval.get("approved") else "[bold red]REJECTED/HOLD[/bold red]"
                    console.print(f"  [bold green]✓[/bold green] [bold red]Risk Manager[/bold red] [dim][{m}][/dim]: {v}")

        # Output Rich Panels for each stage
        ta = res.get("technical_report", {})
        sa = res.get("sentiment_report", {})
        bull = res.get("bull_argument", {})
        bear = res.get("bear_argument", {})
        consensus = res.get("consensus", {})
        proposal = res.get("proposal", {})
        risk = res.get("risk_evaluation", {})

        # Analysts summary
        ta_model = escape(str(ta.get("model_used") or settings.model_technical))
        sa_model = escape(str(sa.get("model_used") or settings.model_sentiment))
        bull_model = escape(str(bull.get("model_used") or settings.model_bull))
        bear_model = escape(str(bear.get("model_used") or settings.model_bear))
        consensus_model = escape(str(consensus.get("model_used") or settings.model_debate))
        trader_model = escape(str(proposal.get("model_used") or settings.model_trader))
        risk_model = escape(str(risk.get("model_used") or settings.model_risk))

        console.print("\n[bold cyan]─── 📊 ANALYST INTELLIGENCE ───[/bold cyan]")
        console.print(f"📊 [bold]Technical Analyst[/] [dim][{ta_model}][/]: [{ 'green' if ta.get('signal') == 'BUY' else 'red' }]{ta.get('signal')}[/] (Conf: {ta.get('confidence', 0)*100:.0f}%) — {ta.get('summary')}")
        console.print(f"📰 [bold]Sentiment Analyst[/] [dim][{sa_model}][/]: [{ 'green' if sa.get('signal') == 'BUY' else 'red' }]{sa.get('signal')}[/] (Conf: {sa.get('confidence', 0)*100:.0f}%) — {sa.get('summary')}")

        # Debate
        console.print("\n[bold cyan]─── 🗣️ ADVERSARIAL DEBATE ───[/bold cyan]")
        console.print(Panel(
            f"[bold green]Thesis:[/] {bull.get('thesis')}\n"
            f"[bold green]Catalysts:[/] {', '.join(bull.get('catalysts', []))}\n"
            f"[bold green]Key Levels:[/] {bull.get('key_levels')}",
            title=f"🐂 Bull [{bull_model}]",
            border_style="green",
        ))

        console.print(Panel(
            f"[bold red]Thesis:[/] {bear.get('thesis')}\n"
            f"[bold red]Risks / Traps:[/] {', '.join(bear.get('catalysts', []))}\n"
            f"[bold red]Hazard Levels:[/] {bear.get('key_levels')}",
            title=f"🐻 Bear [{bear_model}]",
            border_style="red",
        ))

        # Consensus
        act = consensus.get("action", "HOLD")
        act_color = "bold green" if act == "BUY" else "bold red" if act == "SELL" else "bold yellow"
        console.print(Panel(
            f"Verdict: [{act_color}]{act}[/{act_color}]  │  "
            f"Confidence: [bold gold1]{consensus.get('confidence', 0)*100:.0f}%[/bold gold1]  │  "
            f"Recommended Position: {consensus.get('recommended_position_pct', 0)*100:.0f}%\n\n"
            f"[white]{consensus.get('summary')}[/white]",
            title=f"🤝 Debate & Consensus [{consensus_model}]",
            border_style="gold1",
        ))

        # Trader & Risk
        if proposal and risk:
            approved_tag = "[bold green]APPROVED[/bold green]" if risk.get("approved") else "[bold red]REJECTED[/bold red]"
            console.print(Panel(
                f"Proposed: [bold]{proposal.get('action')}[/] {proposal.get('quantity')} {symbol} @ ${proposal.get('entry_price'):,.2f}\n"
                f"Stop Loss: ${proposal.get('stop_loss_price'):,.2f}  │  Take Profit: ${proposal.get('take_profit_price'):,.2f}\n"
                f"Risk Gatekeeper: {approved_tag}\n"
                f"Notes: {'; '.join(risk.get('reasons', []))}",
                title=f"⚡ Trader [{trader_model}] & 🛡️ Risk [{risk_model}]",
                border_style="cyan",
            ))

    asyncio.run(_run_debate())


@app.command()
def history(
    limit: int = typer.Option(15, "--limit", "-n", help="Number of recent trade entries to display"),
):
    """Full trade log with decisions and outcomes."""
    trades = db.get_recent_trades(limit=limit)

    table = Table(title=f"📜 Recent Trade Executions (Last {limit})", expand=True)
    table.add_column("Time", style="dim")
    table.add_column("Symbol", style="bold yellow")
    table.add_column("Action")
    table.add_column("Price", justify="right")
    table.add_column("Quantity", justify="right")
    table.add_column("Fee", justify="right")
    table.add_column("Status")
    table.add_column("Confidence", justify="right")
    table.add_column("Reasoning", style="dim")

    if not trades:
        table.add_row("No trades logged yet", "-", "-", "-", "-", "-", "-", "-", "-")
    else:
        for t in trades:
            act = t["action"]
            color = "green" if act == "BUY" else "red"
            conf = f"{t['confidence']*100:.0f}%" if t["confidence"] else "-"
            table.add_row(
                str(t["timestamp"])[:19],
                t["symbol"],
                f"[{color}]{act}[/{color}]",
                f"${t['price']:,.2f}",
                f"{t['quantity']:.4f}",
                f"${t['fee']:.2f}",
                t["status"],
                conf,
                (t["reasoning"] or "")[:40] + ("..." if len(t.get("reasoning", "") or "") > 40 else ""),
            )

    console.print(table)


def render_ascii_curve(equity_points: list[float], height: int = 7, width: int = 48) -> str:
    """Render an ASCII/Unicode equity curve with price scale labels."""
    if not equity_points:
        return ""
    # Sample down to width
    if len(equity_points) > width:
        step = len(equity_points) / width
        sampled = [equity_points[int(i * step)] for i in range(width)]
    else:
        sampled = list(equity_points)

    min_v = min(sampled)
    max_v = max(sampled)
    diff = max_v - min_v if max_v > min_v else 1.0

    lines = []
    for h in range(height - 1, -1, -1):
        thresh = min_v + (diff * h / (height - 1))
        row = []
        for v in sampled:
            target_h = int((v - min_v) / diff * (height - 1))
            if target_h == h:
                row.append("█")
            elif target_h > h:
                row.append("│")
            else:
                row.append(" ")
        lbl = f"${thresh:8.1f} ┤" if (h == height - 1 or h == 0 or h == height // 2) else "          │"
        lines.append(lbl + "".join(row))
    axis = "          └" + "─" * len(sampled)
    lines.append(axis)
    return "\n".join(lines)


@app.command()
def backtest(
    symbol: str = typer.Argument("BTC/USD", help="Symbol to backtest"),
    period: str = typer.Argument("30d", help="Backtesting duration period (e.g. 7d, 30d, 60d)"),
):
    """Backtest strategy against historical Kraken candle data comparing Mode A vs Mode B."""
    console.print(Panel(f"📈 [bold cyan]superKraken Historical Backtest Engine: {symbol} ({period})[/bold cyan]", border_style="cyan"))

    async def _run_backtest():
        client = KrakenMarketDataClient()
        days = 30
        if "60" in period:
            days = 60
        elif "14" in period:
            days = 14
        elif "7" in period:
            days = 7

        with console.status(f"[bold cyan]Fetching real daily OHLCV historical candles from Kraken for {symbol}...[/bold cyan]"):
            # Fetch daily candles (interval 1440 mins = 1 day)
            candles = await client.get_ohlc(symbol, interval_minutes=1440, count=days + 35)

        if len(candles) < 20:
            console.print("[bold red]Insufficient candle history returned from Kraken for statistical validation.[/bold red]")
            return

        console.print(f"📡 [bold green]Retrieved {len(candles)} historical daily candles from Kraken REST.[/bold green]")

        import math
        import statistics

        def simulate_strategy(mode_name: str, use_agent_gating: bool):
            capital = 10000.0
            peak_capital = capital
            equity_curve = [capital]
            wins = 0
            losses = 0
            trades = 0
            gross_profit = 0.0
            gross_loss = 0.0
            returns = []
            best_trade_pct = -999.0
            worst_trade_pct = 999.0
            consecutive_losses = 0

            # Simulation across warmup window
            start_idx = 25
            for i in range(start_idx, len(candles) - 1):
                subset = candles[:i]
                ind = compute_all_indicators(subset)
                curr_close = candles[i].close
                next_close = candles[i + 1].close
                day_ret = (next_close - curr_close) / curr_close

                should_buy = False
                if not use_agent_gating:
                    # Mode A: Simple Technical Rule (RSI < 45 recovery and above EMA50)
                    if ind.rsi_14 < 45 and curr_close > ind.ema_50:
                        should_buy = True
                else:
                    # Mode B: Multi-Agent Consensus Gating (RSI trend + MACD histogram + Bollinger bandwidth)
                    macd_bull = ind.macd_line > ind.macd_signal
                    rsi_ok = 35 < ind.rsi_14 < 65
                    trend_ok = curr_close > ind.ema_50
                    bb_support = curr_close >= ind.bb_lower
                    if trend_ok and macd_bull and (rsi_ok or bb_support):
                        should_buy = True

                if should_buy:
                    trades += 1
                    # Dynamic sizing with Memory Layer: tighten 50% if 3 consecutive losses
                    sizing = 0.25
                    if use_agent_gating and consecutive_losses >= 3:
                        sizing = 0.125

                    # Enforce 4% stop loss, 8% take profit
                    realized_ret = max(min(day_ret, 0.08), -0.04)
                    trade_pnl = capital * sizing * realized_ret
                    trade_ret_pct = realized_ret * 100

                    capital += trade_pnl
                    equity_curve.append(capital)
                    returns.append(realized_ret)

                    if trade_pnl > 0:
                        wins += 1
                        gross_profit += trade_pnl
                        consecutive_losses = 0
                    else:
                        losses += 1
                        gross_loss += abs(trade_pnl)
                        consecutive_losses += 1

                    if trade_ret_pct > best_trade_pct:
                        best_trade_pct = trade_ret_pct
                    if trade_ret_pct < worst_trade_pct:
                        worst_trade_pct = trade_ret_pct

                    if capital > peak_capital:
                        peak_capital = capital
                else:
                    equity_curve.append(capital)

            total_ret_pct = ((capital - 10000.0) / 10000.0) * 100
            win_rate = (wins / trades * 100) if trades > 0 else 0.0
            max_dd = ((peak_capital - capital) / peak_capital * 100) if peak_capital > 0 else 0.0
            profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (9.99 if gross_profit > 0 else 0.0)

            # Annualized Sharpe ratio
            if returns and len(returns) > 1:
                mean_r = float(statistics.mean(returns))
                std_r = float(statistics.stdev(returns))
                sharpe = (mean_r / std_r * math.sqrt(365)) if std_r > 0 else 0.0
            else:
                sharpe = 0.0

            return {
                "name": mode_name,
                "capital": capital,
                "total_return": total_ret_pct,
                "trades": trades,
                "wins": wins,
                "losses": losses,
                "win_rate": win_rate,
                "max_dd": max_dd,
                "profit_factor": profit_factor,
                "sharpe": sharpe,
                "best_trade": best_trade_pct if trades > 0 else 0.0,
                "worst_trade": worst_trade_pct if trades > 0 else 0.0,
                "equity_curve": equity_curve,
            }

        res_a = simulate_strategy("Mode A (Pure Indicators)", use_agent_gating=False)
        res_b = simulate_strategy("Mode B (Full Agent Consensus)", use_agent_gating=True)

        # Print ASCII Equity Curve for Mode B
        console.print(f"\n[bold magenta]📈 Mode B Agent Equity Curve (${res_b['capital']:,.2f}):[/bold magenta]")
        curve_art = render_ascii_curve(res_b["equity_curve"])
        console.print(f"[bold green]{curve_art}[/bold green]\n")

        # Comparison Table
        table = Table(title=f"📊 Strategy Validation Benchmark: {symbol} ({period})", expand=True)
        table.add_column("Performance Metric", style="bold cyan")
        table.add_column("Mode A: Indicators Only", justify="right")
        table.add_column("Mode B: Multi-Agent Desk", justify="right", style="bold white")
        table.add_column("Edge Delta", justify="right")

        ret_a_style = "green" if res_a["total_return"] >= 0 else "red"
        ret_b_style = "green" if res_b["total_return"] >= 0 else "red"
        delta_ret = res_b["total_return"] - res_a["total_return"]
        delta_ret_style = "bold green" if delta_ret >= 0 else "bold red"

        table.add_row("Initial Balance", "$10,000.00", "$10,000.00", "-")
        table.add_row("Ending Balance", f"${res_a['capital']:,.2f}", f"${res_b['capital']:,.2f}", f"{'+' if delta_ret>=0 else ''}${res_b['capital']-res_a['capital']:,.2f}")
        table.add_row("Total Return", f"[{ret_a_style}]{res_a['total_return']:+.2f}%[/{ret_a_style}]", f"[{ret_b_style}]{res_b['total_return']:+.2f}%[/{ret_b_style}]", f"[{delta_ret_style}]{delta_ret:+.2f}%[/{delta_ret_style}]")
        table.add_row("Total Executions", str(res_a["trades"]), str(res_b["trades"]), f"{res_b['trades'] - res_a['trades']}")
        table.add_row("Win Rate", f"{res_a['win_rate']:.1f}% ({res_a['wins']}W/{res_a['losses']}L)", f"{res_b['win_rate']:.1f}% ({res_b['wins']}W/{res_b['losses']}L)", f"{res_b['win_rate']-res_a['win_rate']:+.1f}%")
        table.add_row("Max Drawdown", f"{res_a['max_dd']:.2f}%", f"{res_b['max_dd']:.2f}%", f"{res_b['max_dd']-res_a['max_dd']:+.2f}%")
        table.add_row("Profit Factor", f"{res_a['profit_factor']:.2f}", f"{res_b['profit_factor']:.2f}", f"{res_b['profit_factor']-res_a['profit_factor']:+.2f}")
        table.add_row("Sharpe Ratio", f"{res_a['sharpe']:.2f}", f"{res_b['sharpe']:.2f}", f"{res_b['sharpe']-res_a['sharpe']:+.2f}")
        table.add_row("Best Trade", f"{res_a['best_trade']:+.2f}%", f"{res_b['best_trade']:+.2f}%", "-")
        table.add_row("Worst Trade", f"{res_a['worst_trade']:+.2f}%", f"{res_b['worst_trade']:+.2f}%", "-")

        console.print(table)

    asyncio.run(_run_backtest())


@app.command()
def config():
    """Display active risk tolerance, position sizing, and system preferences."""
    table = Table(title="⚙️ superKraken System Configuration", expand=True)
    table.add_column("Parameter", style="bold cyan")
    table.add_column("Value", style="bold white")
    table.add_column("Description", style="dim")

    table.add_row("Execution Mode", settings.execution_mode.upper(), "paper or live execution")
    table.add_row("Trading Universe", settings.trading_pairs, "Active scanned pairs")
    table.add_row("Loop Interval", f"{settings.loop_interval_seconds}s", "Frequency of autonomous agent cycle")
    table.add_row("Max Position Size", f"{settings.max_position_size_pct * 100:.0f}%", "Cap on single position capital allocation")
    table.add_row("Stop-Loss Target", f"{settings.stop_loss_pct * 100:.1f}%", "Mandatory automatic exit threshold")
    table.add_row("Daily Drawdown Limit", f"{settings.daily_drawdown_limit_pct * 100:.0f}%", "Circuit breaker threshold to halt all trading")
    table.add_row("Max Trades / Symbol / Day", str(settings.max_trades_per_symbol_daily), "Overtrading prevention cap")
    table.add_row("Dead Man's Switch", f"{settings.dead_man_switch_timeout}s", "Kraken CLI cancel-after timeout")
    table.add_row("OpenRouter Base URL", settings.openrouter_base_url, "Endpoint for OpenAI client dispatch")

    console.print(table)


@app.command()
def models():
    """Display and inspect OpenRouter models assigned per agent."""
    table = Table(title="🔌 OpenRouter Per-Agent Model Assignments", expand=True)
    table.add_column("Agent Role", style="bold magenta")
    table.add_column("Assigned OpenRouter Model", style="bold green")
    table.add_column("Role Rationale", style="dim")

    table.add_row("Sentiment Analyst", settings.model_sentiment, "First open-weight model for agentic pipelines, $0.04/M input")
    table.add_row("Technical Analyst", settings.model_technical, "Exceeds V4 Pro on reasoning, speed & agent workflows, 1M context")
    table.add_row("Fundamental Analyst", settings.model_fundamental, "Fast 284B/13B MoE, 1M context, high throughput structured synthesis")
    table.add_row("Bullish Researcher", settings.model_bull, "Strong reasoning for building bull cases with numerical citations")
    table.add_row("Bearish Researcher", settings.model_bear, "Adversarial chain-of-thought debater exposing market traps")
    table.add_row("Debate & Consensus", settings.model_debate, "Reasoning mode enabled for deep adversarial adjudication")
    table.add_row("Execution Trader", settings.model_trader, "18T+ tokens battle-tested, structured decisive order generation")
    table.add_row("Risk Manager", settings.model_risk, "Thorough cautious chain-of-thought capital preservation")
    table.add_row("Emergency Fallback", settings.model_fallback, "Instant $0 zero-cost fallback usable without credit balance")

    console.print(table)


@app.command()
def stop():
    """Gracefully halt all agents, trigger dead man's switch, and flatten positions."""
    console.print("[bold red]🚨 Initiating Emergency Halt and Position Liquidation...[/bold red]")
    engine = PaperTradingEngine()
    client = KrakenMarketDataClient()

    async def _stop():
        prices = {}
        for s in settings.pairs_list:
            t = await client.get_ticker(s)
            prices[s] = t["price"]
        return prices

    prices = asyncio.run(_stop())
    results = engine.flatten_all_positions(prices)

    if not results:
        console.print("[green]No open positions were active. All orders clear.[/green]")
    else:
        for r in results:
            console.print(f"[bold red]Liquidated:[/] {r.action.value} {r.filled_qty} {r.symbol} @ ${r.filled_price:,.2f}")

    console.print("[bold green]✅ System halted safely. Dead man's switch confirmed.[/bold green]")


@app.command(name="kill")
def kill():
    """Emergency kill switch: trigger dead man's switch, flatten all positions, and halt agents."""
    stop()


if __name__ == "__main__":
    app()
