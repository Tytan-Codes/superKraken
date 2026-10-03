"""State definitions and domain data models for superKraken multi-agent graph."""

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Dict, List, Optional
from typing_extensions import TypedDict
from pydantic import BaseModel, Field


class TradeAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class AgentStatus(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# Domain Models
class Candle(BaseModel):
    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float


class TechnicalIndicators(BaseModel):
    rsi_14: float = 50.0
    macd_line: float = 0.0
    macd_signal: float = 0.0
    macd_histogram: float = 0.0
    bb_upper: float = 0.0
    bb_middle: float = 0.0
    bb_lower: float = 0.0
    bb_percent_b: float = 0.5
    atr_14: float = 0.0
    ema_20: float = 0.0
    ema_50: float = 0.0
    ema_200: float = 0.0
    trend_regime: str = "NEUTRAL"
    volatility_regime: str = "NORMAL"


class AnalystReport(BaseModel):
    agent_name: str
    signal: TradeAction
    confidence: float = Field(ge=0.0, le=1.0)
    indicators: Dict[str, Any] = Field(default_factory=dict)
    key_metrics: Dict[str, Any] = Field(default_factory=dict)
    summary: str
    model_used: Optional[str] = None
    is_fallback: bool = False
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ResearcherArgument(BaseModel):
    perspective: str  # "BULLISH" or "BEARISH"
    agent_name: str
    thesis: str
    catalysts: List[str] = Field(default_factory=list)
    key_levels: Dict[str, float] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    model_used: Optional[str] = None
    is_fallback: bool = False


class DebateRound(BaseModel):
    round_number: int
    bull_point: str
    bear_counterpoint: str
    adjudication: str
    model_used: Optional[str] = None
    is_fallback: bool = False
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConsensusResult(BaseModel):
    action: TradeAction
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    bull_score: float
    bear_score: float
    recommended_position_pct: float
    recommended_leverage: float = 1.0
    model_used: Optional[str] = None
    is_fallback: bool = False


class TradeProposal(BaseModel):
    symbol: str
    action: TradeAction
    order_type: OrderType = OrderType.MARKET
    quantity: float
    entry_price: float
    stop_loss_price: float
    take_profit_price: float
    position_pct: float
    leverage: float = 1.0
    reasoning: str
    model_used: Optional[str] = None


class RiskEvaluation(BaseModel):
    approved: bool
    adjusted_quantity: float
    adjusted_position_pct: float
    stop_loss_price: float
    reasons: List[str] = Field(default_factory=list)
    drawdown_pct: float
    trades_today: int
    circuit_breaker_triggered: bool = False
    model_used: Optional[str] = None


class ExecutionResult(BaseModel):
    success: bool
    order_id: Optional[str] = None
    symbol: str
    action: TradeAction
    filled_price: float = 0.0
    filled_qty: float = 0.0
    fee: float = 0.0
    status: str
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Position(BaseModel):
    symbol: str
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    stop_loss: float
    take_profit: float
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PortfolioState(BaseModel):
    total_value_usd: float = 10000.0
    cash_usd: float = 10000.0
    realized_pnl_today: float = 0.0
    daily_drawdown_pct: float = 0.0
    trade_count_today: Dict[str, int] = Field(default_factory=dict)
    positions: Dict[str, Position] = Field(default_factory=dict)


def merge_dicts(left: Optional[Dict[str, Any]], right: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Reducer function to merge dictionaries from concurrent LangGraph nodes."""
    res = dict(left or {})
    if right:
        res.update(right)
    return res


# LangGraph State
class TradingDeskState(TypedDict, total=False):
    # Context
    symbol: str
    current_price: float
    candles: List[Dict[str, Any]]
    indicators: Dict[str, Any]
    market_sentiment: Dict[str, Any]
    order_book: Dict[str, Any]
    portfolio: Dict[str, Any]

    # Analyst outputs
    technical_report: Optional[Dict[str, Any]]
    sentiment_report: Optional[Dict[str, Any]]
    fundamental_report: Optional[Dict[str, Any]]

    # Researcher outputs
    bull_argument: Optional[Dict[str, Any]]
    bear_argument: Optional[Dict[str, Any]]

    # Debate & Consensus
    debate_rounds: List[Dict[str, Any]]
    consensus: Optional[Dict[str, Any]]

    # Decision Layer
    proposal: Optional[Dict[str, Any]]
    risk_evaluation: Optional[Dict[str, Any]]
    execution_result: Optional[Dict[str, Any]]

    # Metadata & UI state stream
    messages: List[Dict[str, str]]
    agent_states: Annotated[Dict[str, str], merge_dicts]
    error: Optional[str]


# Alias TradingState for backward compatibility with debug scripts
TradingState = TradingDeskState


class SignalAlert(BaseModel):
    """High-conviction trading recommendation generated by 8-agent desk."""
    signal_id: str
    symbol: str
    action: TradeAction
    confidence: float
    bull_score: float
    bear_score: float
    indicators: Dict[str, Any] = Field(default_factory=dict)
    suggested_order: Dict[str, Any] = Field(default_factory=dict)
    risk_metrics: Dict[str, Any] = Field(default_factory=dict)
    bull_thesis: str = ""
    bear_thesis: str = ""
    summary: str = ""
    advisor_speech: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    user_action: str = "PENDING"  # "PLACED", "SKIPPED", "PENDING"
    theoretical_outcome: str = "PENDING"  # "WIN", "LOSS", "PENDING"


class TrackedPosition(BaseModel):
    """Manual trade logged by human trader, actively monitored by copilot."""
    id: Optional[int] = None
    symbol: str
    action: str = "BUY"
    quantity: float = 0.0
    entry_price: float = 0.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    notes: str = ""
    status: str = "OPEN"  # "OPEN", "CLOSED", "STOPPED_OUT", "TARGET_HIT"
    signal_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: Optional[datetime] = None
    exit_price: Optional[float] = None
    realized_pnl: Optional[float] = None
    exit_reason: Optional[str] = None

    def __init__(self, **data: Any):
        # Support aliases
        if "side" in data and "action" not in data:
            data["action"] = data.pop("side")
        if "position_size" in data and "quantity" not in data:
            data["quantity"] = data.pop("position_size")
        super().__init__(**data)

    @property
    def side(self) -> str:
        return self.action

    @property
    def position_size(self) -> float:
        return self.quantity



class PriceAlert(BaseModel):
    """Custom price target alert configured by the operator."""
    id: Optional[int] = None
    symbol: str
    target_price: float
    condition: str = "CROSS"  # "ABOVE", "BELOW", "CROSS"
    note: str = ""
    triggered: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

