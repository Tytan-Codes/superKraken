"""High-fidelity Paper Trading Execution Engine.

Simulates exchange matching, realistic slippage, maker/taker fees,
stop-loss and take-profit triggers, and position accounting.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Union
from superkraken.config import settings
from superkraken.state import ExecutionResult, OrderType, PortfolioState, Position, TradeAction

logger = logging.getLogger(__name__)


class PaperTradingEngine:
    """In-memory and file-persisted simulated exchange."""

    TAKER_FEE_PCT = 0.0026  # 0.26%
    MAKER_FEE_PCT = 0.0016  # 0.16%
    SLIPPAGE_PCT = 0.0005   # 0.05%

    def __init__(self, state_file: Optional[Path] = None, initial_balance: float = 10000.0):
        self.state_file = state_file or (settings.data_dir / "paper_portfolio.json")
        self.initial_balance = initial_balance
        self.portfolio = self._load_or_create_portfolio()
        self._dead_man_active: bool = False
        self._dead_man_timeout: int = 60

    def _load_or_create_portfolio(self) -> PortfolioState:
        if self.state_file.exists():
            try:
                with open(self.state_file, "r") as f:
                    data = json.load(f)
                    return PortfolioState.model_validate(data)
            except Exception as e:
                logger.warning(f"Failed to load paper portfolio from {self.state_file}: {e}")

        return PortfolioState(
            total_value_usd=self.initial_balance,
            cash_usd=self.initial_balance,
            realized_pnl_today=0.0,
            daily_drawdown_pct=0.0,
            trade_count_today={},
            positions={},
        )

    def save(self) -> None:
        """Persist portfolio state to disk."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, "w") as f:
                json.dump(self.portfolio.model_dump(mode="json"), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to persist paper portfolio: {e}")

    def reset(self, balance: Optional[float] = None) -> PortfolioState:
        """Reset paper portfolio to initial state."""
        bal = balance or self.initial_balance
        self.portfolio = PortfolioState(
            total_value_usd=bal,
            cash_usd=bal,
            realized_pnl_today=0.0,
            daily_drawdown_pct=0.0,
            trade_count_today={},
            positions={},
        )
        self.save()
        return self.portfolio

    def update_market_prices(self, price_map: Dict[str, float]) -> List[ExecutionResult]:
        """Update valuations and evaluate open position stop-loss / take-profits."""
        positions_value = 0.0
        triggered_results: List[ExecutionResult] = []

        for symbol, pos in list(self.portfolio.positions.items()):
            if symbol in price_map:
                current_price = price_map[symbol]
                pos.current_price = current_price
                pos.unrealized_pnl = (current_price - pos.entry_price) * pos.quantity
                if pos.entry_price > 0:
                    pos.unrealized_pnl_pct = (current_price - pos.entry_price) / pos.entry_price
                pos.updated_at = datetime.now(timezone.utc)

                # Check Stop-Loss Trigger
                if pos.stop_loss > 0 and current_price <= pos.stop_loss:
                    logger.warning(f"[STOP-LOSS HIT] {symbol} at ${current_price:.2f} <= SL ${pos.stop_loss:.2f}")
                    exec_res = self.execute_order(
                        symbol=symbol,
                        action=TradeAction.SELL,
                        quantity=pos.quantity,
                        current_market_price=current_price,
                        order_type=OrderType.MARKET,
                    )
                    from superkraken.storage.database import db
                    db.log_trade(
                        exec_res,
                        confidence=1.0,
                        reasoning=f"Automatic stop-loss trigger executed at ${current_price:,.2f}",
                    )
                    triggered_results.append(exec_res)
                    continue

                # Check Take-Profit Trigger
                if pos.take_profit > 0 and current_price >= pos.take_profit:
                    logger.info(f"[TAKE-PROFIT HIT] {symbol} at ${current_price:.2f} >= TP ${pos.take_profit:.2f}")
                    exec_res = self.execute_order(
                        symbol=symbol,
                        action=TradeAction.SELL,
                        quantity=pos.quantity,
                        current_market_price=current_price,
                        order_type=OrderType.MARKET,
                    )
                    from superkraken.storage.database import db
                    db.log_trade(
                        exec_res,
                        confidence=1.0,
                        reasoning=f"Automatic take-profit trigger executed at ${current_price:,.2f}",
                    )
                    triggered_results.append(exec_res)
                    continue

                positions_value += pos.quantity * current_price

        self.portfolio.total_value_usd = self.portfolio.cash_usd + positions_value

        # Calculate daily drawdown against peak initial balance
        if self.portfolio.total_value_usd < self.initial_balance:
            drawdown = (self.initial_balance - self.portfolio.total_value_usd) / self.initial_balance
            self.portfolio.daily_drawdown_pct = round(drawdown, 4)
        else:
            self.portfolio.daily_drawdown_pct = 0.0

        self.save()

    def execute_order(
        self,
        symbol: str,
        action: Union[TradeAction, str],
        quantity: float,
        current_market_price: float,
        order_type: Union[OrderType, str] = OrderType.MARKET,
        limit_price: Optional[float] = None,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        leverage: float = 1.0,
        order_category: str = "spot",
    ) -> ExecutionResult:
        """Execute simulated order with realistic slippage and fees."""
        if isinstance(action, str):
            action = TradeAction(action.upper())
        if isinstance(order_type, str):
            order_type = OrderType(order_type.lower())

        if settings.is_canadian:
            if leverage > 1.0:
                logger.warning(f"[RESTRICTED: CA] Leverage {leverage}x stripped — Canadian spot accounts locked to 1.0x.")
                leverage = 1.0
            if order_category.lower() in ("futures", "margin"):
                logger.warning(f"⚠️ [RESTRICTED: CA] {order_category.capitalize()} unavailable — falling back to spot order.")
                order_category = "spot"

        if quantity <= 0 or current_market_price <= 0:
            return ExecutionResult(
                success=False,
                symbol=symbol,
                action=action,
                status="REJECTED",
                message="Invalid quantity or price",
            )

        # Slippage model: buys pay slightly more, sells receive slightly less
        if action == TradeAction.BUY:
            fill_price = current_market_price * (1.0 + self.SLIPPAGE_PCT)
        else:
            fill_price = current_market_price * (1.0 - self.SLIPPAGE_PCT)

        if order_type == OrderType.LIMIT and limit_price is not None:
            if action == TradeAction.BUY and fill_price > limit_price:
                return ExecutionResult(
                    success=False,
                    symbol=symbol,
                    action=action,
                    status="UNFILLED",
                    message="Market above limit price",
                )
            if action == TradeAction.SELL and fill_price < limit_price:
                return ExecutionResult(
                    success=False,
                    symbol=symbol,
                    action=action,
                    status="UNFILLED",
                    message="Market below limit price",
                )
            fill_price = limit_price

        notional = fill_price * quantity
        fee = notional * (self.TAKER_FEE_PCT if order_type == OrderType.MARKET else self.MAKER_FEE_PCT)

        if action == TradeAction.BUY:
            total_cost = notional + fee
            if total_cost > self.portfolio.cash_usd:
                return ExecutionResult(
                    success=False,
                    symbol=symbol,
                    action=action,
                    status="INSUFFICIENT_FUNDS",
                    message=f"Required ${total_cost:.2f} > Cash ${self.portfolio.cash_usd:.2f}",
                )

            self.portfolio.cash_usd -= total_cost
            existing = self.portfolio.positions.get(symbol)
            if existing:
                # Weighted average entry price
                new_qty = existing.quantity + quantity
                existing.entry_price = ((existing.entry_price * existing.quantity) + notional) / new_qty
                existing.quantity = new_qty
                existing.current_price = fill_price
                existing.stop_loss = stop_loss or existing.stop_loss
                existing.take_profit = take_profit or existing.take_profit
                existing.updated_at = datetime.now(timezone.utc)
            else:
                self.portfolio.positions[symbol] = Position(
                    symbol=symbol,
                    quantity=quantity,
                    entry_price=fill_price,
                    current_price=fill_price,
                    unrealized_pnl=0.0,
                    unrealized_pnl_pct=0.0,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                )

        elif action == TradeAction.SELL:
            existing = self.portfolio.positions.get(symbol)
            if not existing or existing.quantity < quantity * 0.999:  # Floating tolerance
                return ExecutionResult(
                    success=False,
                    symbol=symbol,
                    action=action,
                    status="INSUFFICIENT_POSITION",
                    message=f"Holdings {existing.quantity if existing else 0.0:.6f} < Sell Qty {quantity:.6f}",
                )

            # Cap sell qty to existing position
            sell_qty = min(quantity, existing.quantity)
            revenue = (fill_price * sell_qty) - fee
            cost_basis = existing.entry_price * sell_qty
            realized = (fill_price * sell_qty) - cost_basis - fee

            self.portfolio.cash_usd += revenue
            self.portfolio.realized_pnl_today += realized

            existing.quantity -= sell_qty
            if existing.quantity <= 1e-6:
                del self.portfolio.positions[symbol]

        # Update daily trade counter
        self.portfolio.trade_count_today[symbol] = (
            self.portfolio.trade_count_today.get(symbol, 0) + 1
        )

        self.save()

        order_id = f"paper-{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        pnl_suffix = f" (Realized P&L: {'+' if realized >= 0 else ''}${realized:,.2f})" if action == TradeAction.SELL else ""
        return ExecutionResult(
            success=True,
            order_id=order_id,
            symbol=symbol,
            action=action,
            filled_price=round(fill_price, 4),
            filled_qty=round(quantity, 6),
            fee=round(fee, 4),
            status="FILLED",
            message=f"Filled {action.value} {quantity:.6f} @ ${fill_price:.2f}{pnl_suffix}",
        )

    def cancel_all_orders(self) -> int:
        """Simulate dead man's switch cancellation."""
        logger.info("Dead man's switch triggered: cancelled all pending orders.")
        return 0

    def flatten_all_positions(self, current_prices: Dict[str, float]) -> List[ExecutionResult]:
        """Emergency stop: market sell all open positions."""
        results = []
        for symbol, pos in list(self.portfolio.positions.items()):
            px = current_prices.get(symbol, pos.current_price)
            res = self.execute_order(
                symbol=symbol,
                action=TradeAction.SELL,
                quantity=pos.quantity,
                current_market_price=px,
                order_type=OrderType.MARKET,
            )
            results.append(res)
        return results
