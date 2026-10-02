# superKraken 🐙⚡

Autonomous AI Day Trading Desk CLI modeled directly after the **TradingAgents** framework by TauricResearch on GitHub. Powered by the **Kraken CLI** execution engine, **OpenRouter** as the unified multi-model LLM backbone, and an institutional terminal UI built with **Textual** and **Rich**.

## Features

- 🤖 **Multi-Agent Trading Desk (LangGraph)**:
  - 📊 **Technical Analyst**: RSI, MACD, Bollinger Bands, ATR, regime detection.
  - 📰 **Sentiment Analyst**: Social sentiment, fear & greed, news catalysts.
  - 📈 **Fundamental Analyst**: Volume profiles, order book depth, trend strength.
  - 🐂 **Bullish Researcher**: High-conviction upside catalysts, breakout levels.
  - 🐻 **Bearish Researcher**: Risk exposure, liquidity traps, downside indicators.
  - 🤝 **Debate & Consensus Agent**: Adversarial debate producing confidence scores.
  - ⚡ **Execution Trader**: Synthesizes reports into optimal order timing & sizing.
  - 🛡️ **Risk Manager**: Position sizing enforcement (20-30%), 3-5% stop loss, 10% daily drawdown circuit breaker.
- 🔌 **OpenRouter LLM Backbone**: Multi-model routing tailored per role (DeepSeek R1, Claude Sonnet, GPT-4o, Gemini Flash, Claude Opus).
- ⚙️ **Kraken Execution Engine**: Direct support for Kraken CLI (151+ tools, MCP server, `kraken spot cancel-after` dead man's switch), plus high-fidelity paper trading engine and fallback REST/WS client.
- 🖥️ **Stunning Terminal UI**: Built with Textual and Rich for live streaming debates, real-time tickers, portfolio P&L, and risk gauges.

## Installation

```bash
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -e .
```

## Quick Start

```bash
# Setup environment
cp .env.example .env
# Edit OPENROUTER_API_KEY in .env

# Run paper trading sandbox mode
trader paper

# Watch live agent debate on a pair
trader debate BTC/USD

# View portfolio status
trader status
```
