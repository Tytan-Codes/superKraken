"""Technical indicators and regime calculation engine."""

import math
from typing import List, Tuple
from superkraken.state import Candle, TechnicalIndicators


def calculate_ema(values: List[float], period: int) -> List[float]:
    """Calculate Exponential Moving Average (EMA)."""
    if len(values) < period:
        return [values[-1]] * len(values) if values else []

    k = 2.0 / (period + 1)
    ema = [sum(values[:period]) / period]

    for val in values[period:]:
        next_ema = (val * k) + (ema[-1] * (1.0 - k))
        ema.append(next_ema)

    # Pad prefix to match length of values
    prefix = [ema[0]] * (period - 1)
    return prefix + ema


def calculate_rsi(closes: List[float], period: int = 14) -> float:
    """Calculate Relative Strength Index (RSI)."""
    if len(closes) <= period:
        return 50.0

    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [c if c > 0 else 0.0 for c in changes]
    losses = [-c if c < 0 else 0.0 for c in changes]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(changes)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0.0:
        if avg_gain == 0.0:
            return 50.0
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def calculate_macd(
    closes: List[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> Tuple[float, float, float]:
    """Calculate MACD line, signal line, and histogram."""
    if len(closes) < slow_period + signal_period:
        return 0.0, 0.0, 0.0

    fast_ema = calculate_ema(closes, fast_period)
    slow_ema = calculate_ema(closes, slow_period)

    macd_line = [f - s for f, s in zip(fast_ema, slow_ema)]
    signal_line = calculate_ema(macd_line, signal_period)

    current_macd = macd_line[-1]
    current_signal = signal_line[-1]
    current_hist = current_macd - current_signal
    return current_macd, current_signal, current_hist


def calculate_bollinger_bands(
    closes: List[float],
    period: int = 20,
    num_std_dev: float = 2.0,
) -> Tuple[float, float, float, float]:
    """Calculate Bollinger Bands: (Upper, Middle, Lower, %B)."""
    if len(closes) < period:
        latest = closes[-1] if closes else 0.0
        return latest, latest, latest, 0.5

    subset = closes[-period:]
    mean = sum(subset) / period
    variance = sum((x - mean) ** 2 for x in subset) / period
    std_dev = math.sqrt(variance)

    upper = mean + (num_std_dev * std_dev)
    lower = mean - (num_std_dev * std_dev)
    latest = closes[-1]

    percent_b = (latest - lower) / (upper - lower) if (upper - lower) > 0 else 0.5
    return upper, mean, lower, percent_b


def calculate_atr(candles: List[Candle], period: int = 14) -> float:
    """Calculate Average True Range (ATR)."""
    if len(candles) < 2:
        return 0.0

    true_ranges = []
    for i in range(1, len(candles)):
        c_curr = candles[i]
        c_prev = candles[i - 1]
        tr = max(
            c_curr.high - c_curr.low,
            abs(c_curr.high - c_prev.close),
            abs(c_curr.low - c_prev.close),
        )
        true_ranges.append(tr)

    if len(true_ranges) < period:
        return sum(true_ranges) / len(true_ranges) if true_ranges else 0.0

    atr = sum(true_ranges[:period]) / period
    for tr in true_ranges[period:]:
        atr = (atr * (period - 1) + tr) / period

    return atr


def detect_trend_regime(closes: List[float], ema_20: float, ema_50: float, ema_200: float) -> str:
    """Detect current macro/micro trend regime."""
    if not closes:
        return "NEUTRAL"
    current = closes[-1]

    if current > ema_20 > ema_50:
        if current > ema_200:
            return "STRONG_BULLISH"
        return "BULLISH_RECOVERY"
    elif current < ema_20 < ema_50:
        if current < ema_200:
            return "STRONG_BEARISH"
        return "BEARISH_PULLBACK"
    elif current > ema_50:
        return "MILD_BULLISH"
    elif current < ema_50:
        return "MILD_BEARISH"
    return "CHOPPY_RANGE"


def detect_volatility_regime(atr: float, current_price: float) -> str:
    """Detect volatility regime based on ATR percentage of price."""
    if current_price <= 0:
        return "NORMAL"
    atr_pct = (atr / current_price) * 100.0

    if atr_pct > 3.0:
        return "HIGH_VOLATILITY"
    elif atr_pct < 0.8:
        return "LOW_VOLATILITY"
    return "NORMAL_VOLATILITY"


def compute_all_indicators(candles: List[Candle]) -> TechnicalIndicators:
    """Compute complete suite of indicators from candlestick history."""
    if not candles:
        return TechnicalIndicators()

    closes = [c.close for c in candles]
    current_price = closes[-1]

    rsi = calculate_rsi(closes, period=14)
    macd_line, macd_signal, macd_hist = calculate_macd(closes, 12, 26, 9)
    bb_upper, bb_mid, bb_lower, percent_b = calculate_bollinger_bands(closes, 20, 2.0)
    atr = calculate_atr(candles, 14)

    ema_20_series = calculate_ema(closes, 20)
    ema_50_series = calculate_ema(closes, 50)
    ema_200_series = calculate_ema(closes, 200)

    ema_20 = ema_20_series[-1] if ema_20_series else current_price
    ema_50 = ema_50_series[-1] if ema_50_series else current_price
    ema_200 = ema_200_series[-1] if ema_200_series else current_price

    trend = detect_trend_regime(closes, ema_20, ema_50, ema_200)
    volatility = detect_volatility_regime(atr, current_price)

    return TechnicalIndicators(
        rsi_14=round(rsi, 2),
        macd_line=round(macd_line, 4),
        macd_signal=round(macd_signal, 4),
        macd_histogram=round(macd_hist, 4),
        bb_upper=round(bb_upper, 2),
        bb_middle=round(bb_mid, 2),
        bb_lower=round(bb_lower, 2),
        bb_percent_b=round(percent_b, 4),
        atr_14=round(atr, 2),
        ema_20=round(ema_20, 2),
        ema_50=round(ema_50, 2),
        ema_200=round(ema_200, 2),
        trend_regime=trend,
        volatility_regime=volatility,
    )
