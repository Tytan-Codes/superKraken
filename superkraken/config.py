"""Configuration module for superKraken trading system."""

from pathlib import Path
from typing import Dict, List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # OpenRouter API Configuration
    openrouter_api_key: str = Field(
        default="",
        description="OpenRouter API Key for multi-model LLM access",
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter API base URL",
    )

    # Account & Region Configuration
    account_region: str = Field(
        default="CA",
        description="Account region: 'CA' = Canada, 'US' = USA, 'GLOBAL' = unrestricted",
    )
    base_currency: str = Field(
        default="USDC",
        description="Base settlement currency: USDC for CA spot trading, USD for US/GLOBAL",
    )

    # Kraken CLI & API Configuration
    kraken_api_key: str = Field(default="", description="Kraken API Key")
    kraken_api_secret: str = Field(default="", description="Kraken API Secret")
    kraken_cli_path: str = Field(
        default="kraken",
        description="Path or binary name for Kraken CLI",
    )
    execution_mode: str = Field(
        default="paper",
        description="Execution mode: 'paper' or 'live'",
    )
    initial_paper_balance: float = Field(
        default=10000.0,
        description="Initial balance in USD for paper trading",
    )

    # Trading Universe
    trading_pairs: str = Field(
        default="BTC/USD,ETH/USD,SOL/USD",
        description="Comma-separated trading symbols",
    )
    loop_interval_seconds: int = Field(
        default=60,
        description="Main trading loop interval in seconds",
    )

    # Per-Agent Model Assignments (OpenRouter Model IDs)
    model_sentiment: str = Field(
        default="deepseek/deepseek-v4-flash-0731",
        description="Model for Sentiment Analyst",
    )
    model_technical: str = Field(
        default="deepseek/deepseek-v4.1-flash",
        description="Model for Technical Analyst",
    )
    model_fundamental: str = Field(
        default="deepseek/deepseek-v4-flash-0731",
        description="Model for Fundamental Analyst",
    )
    model_bull: str = Field(
        default="deepseek/deepseek-v4.1-flash",
        description="Model for Bullish Researcher",
    )
    model_bear: str = Field(
        default="deepseek/deepseek-v4.1-flash",
        description="Model for Bearish Researcher",
    )
    model_debate: str = Field(
        default="deepseek/deepseek-v4.1-flash",
        description="Model for Adversarial Debate and Consensus (reasoning mode)",
    )
    model_trader: str = Field(
        default="z-ai/glm-5.3-flash",
        description="Model for Execution Trader",
    )
    model_risk: str = Field(
        default="deepseek/deepseek-v4.1-flash",
        description="Model for Risk Manager",
    )
    model_fallback: str = Field(
        default="deepseek/deepseek-v4-flash-latest:free",
        description="Fallback model if primary model fails",
    )

    # Risk Parameters
    max_position_size_pct: float = Field(
        default=0.30,
        description="Maximum position size as fraction of portfolio (e.g. 0.30 = 30%)",
    )
    min_position_size_pct: float = Field(
        default=0.05,
        description="Minimum position size as fraction of portfolio",
    )
    stop_loss_pct: float = Field(
        default=0.04,
        description="Mandatory stop loss percentage (e.g. 0.04 = 4%)",
    )
    take_profit_pct: float = Field(
        default=0.08,
        description="Default target take profit percentage (e.g. 0.08 = 8%)",
    )
    daily_drawdown_limit_pct: float = Field(
        default=0.10,
        description="Circuit breaker daily drawdown limit (e.g. 0.10 = 10%)",
    )
    max_trades_per_symbol_daily: int = Field(
        default=10,
        description="Maximum trades per symbol allowed per day to prevent overtrading",
    )
    dead_man_switch_timeout: int = Field(
        default=60,
        description="Dead man's switch timeout in seconds for kraken cancel-after",
    )

    # Storage Paths
    data_dir: Path = Field(
        default_factory=lambda: Path.home() / ".superkraken",
        description="Directory for local state, databases, and logs",
    )

    @property
    def is_canadian(self) -> bool:
        return self.account_region.upper() == "CA"

    @property
    def futures_enabled(self) -> bool:
        return not self.is_canadian

    @property
    def margin_enabled(self) -> bool:
        return not self.is_canadian

    @property
    def max_allowed_leverage(self) -> float:
        return 1.0 if self.is_canadian else 5.0

    @property
    def pairs_list(self) -> List[str]:
        return [p.strip().upper() for p in self.trading_pairs.split(",") if p.strip()]

    @property
    def model_map(self) -> Dict[str, str]:
        return {
            "sentiment": self.model_sentiment,
            "technical": self.model_technical,
            "fundamental": self.model_fundamental,
            "bull_researcher": self.model_bull,
            "bear_researcher": self.model_bear,
            "debate": self.model_debate,
            "trader": self.model_trader,
            "risk_manager": self.model_risk,
        }


# Global settings instance
settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
