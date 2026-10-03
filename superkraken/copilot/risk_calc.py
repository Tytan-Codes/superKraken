"""Institutional-grade dollar risk and position sizing calculator for Copilot."""

import math
from typing import Any, Dict, Optional


def calculate_copilot_order_spec(
    symbol: str,
    action: str,  # "BUY" or "SELL"
    current_price: float,
    atr_14: float,
    portfolio_usdc: float = 10000.0,
    confidence: float = 0.70,
    max_position_pct: float = 0.25,
    risk_per_trade_pct: float = 0.01,
    atr_multiplier: float = 1.5,
    reward_ratio: float = 2.0,
) -> Dict[str, Any]:
    """
    Computes exact trade specifications with plain dollar risk.

    - Stop loss is dynamically anchored by ATR (volatility-adjusted) or standard baseline.
    - Reward is strictly 2:1 relative to stop distance.
    - Sizing ensures max loss never exceeds 1.0% of portfolio (or configured risk per trade).
    - Capped at max allowed position percentage (e.g. 25% of portfolio).
    """
    action = action.upper()
    current_price = max(0.01, float(current_price))
    portfolio_usdc = max(10.0, float(portfolio_usdc))

    # 1. Determine stop distance
    if atr_14 > 0 and (atr_14 / current_price) >= 0.005:
        stop_dist = atr_14 * atr_multiplier
    else:
        # Fallback to standard 2.8% stop distance
        stop_dist = current_price * 0.028

    # Clamp stop distance between 1.5% and 5.0%
    min_dist = current_price * 0.015
    max_dist = current_price * 0.050
    stop_dist = max(min_dist, min(max_dist, stop_dist))

    target_dist = stop_dist * reward_ratio

    if action == "BUY":
        stop_loss_price = round(current_price - stop_dist, 2)
        take_profit_price = round(current_price + target_dist, 2)
        limit_entry_price = round(current_price * 0.997, 2)  # Limit entry slightly below market
    else:
        stop_loss_price = round(current_price + stop_dist, 2)
        take_profit_price = round(current_price - target_dist, 2)
        limit_entry_price = round(current_price * 1.003, 2)

    stop_loss_pct = round((stop_dist / current_price) * 100.0, 2)
    take_profit_pct = round((target_dist / current_price) * 100.0, 2)

    # 2. Risk budgeting: Max acceptable loss in USD (e.g. 1.0% of total portfolio)
    max_dollar_budget = portfolio_usdc * risk_per_trade_pct

    # Size based on risk budget: Quantity = RiskBudget / StopDistancePerUnit
    raw_qty = max_dollar_budget / stop_dist if stop_dist > 0 else 0.0

    # 3. Position cap budgeting (max 25% of portfolio)
    # Scale allocation slightly by conviction if confidence >= 0.75
    effective_max_pct = max_position_pct if confidence < 0.75 else min(0.30, max_position_pct * 1.2)
    max_capital_notional = portfolio_usdc * effective_max_pct
    max_capital_qty = max_capital_notional / current_price

    final_qty = min(raw_qty, max_capital_qty)

    # Clean crypto precision (BTC: 4 decimals, ETH: 3 decimals, SOL: 2 decimals, else 3)
    if "BTC" in symbol:
        final_qty = math.floor(final_qty * 10000) / 10000
        if final_qty < 0.0001:
            final_qty = 0.0010
    elif "ETH" in symbol:
        final_qty = math.floor(final_qty * 1000) / 1000
        if final_qty < 0.001:
            final_qty = 0.010
    elif "SOL" in symbol:
        final_qty = math.floor(final_qty * 100) / 100
        if final_qty < 0.01:
            final_qty = 0.10
    else:
        final_qty = math.floor(final_qty * 1000) / 1000

    notional_usd = round(final_qty * current_price, 2)
    pos_pct = round((notional_usd / portfolio_usdc) * 100.0, 1)

    # Exact dollar risk
    actual_max_loss_usd = round(final_qty * stop_dist, 2)
    actual_max_loss_pct = round((actual_max_loss_usd / portfolio_usdc) * 100.0, 2)
    actual_target_gain_usd = round(final_qty * target_dist, 2)
    actual_target_gain_pct = round((actual_target_gain_usd / portfolio_usdc) * 100.0, 2)

    return {
        "action": action,
        "symbol": symbol,
        "quantity": final_qty,
        "notional_usdc": notional_usd,
        "position_pct": pos_pct,
        "entry_price": current_price,
        "limit_entry_price": limit_entry_price,
        "stop_loss_price": stop_loss_price,
        "stop_loss_pct": stop_loss_pct,
        "take_profit_price": take_profit_price,
        "take_profit_pct": take_profit_pct,
        "max_loss_usd": actual_max_loss_usd,
        "max_loss_pct": actual_max_loss_pct,
        "target_gain_usd": actual_target_gain_usd,
        "risk_reward_ratio": float(reward_ratio),
        "risk_reward_display": f"1:{int(reward_ratio)}" if reward_ratio.is_integer() else f"1:{reward_ratio:.1f}",
        "portfolio_usdc": portfolio_usdc,
    }
