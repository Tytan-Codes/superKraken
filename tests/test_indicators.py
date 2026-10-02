"""Unit tests for quantitative technical indicators and regimes."""

import pytest
from superkraken.indicators.technical import (
    calculate_atr,
    calculate_bollinger_bands,
    calculate_ema,
    calculate_macd,
    calculate_rsi,
    compute_all_indicators,
    detect_trend_regime,
    detect_volatility_regime,
)
from superkraken.state import Candle


def test_calculate_rsi():
    # Constant prices -> RSI 50
    flat_prices = [100.0] * 30
    assert calculate_rsi(flat_prices) == 50.0

    # Strictly rising prices -> RSI 100
    rising_prices = [100.0 + i for i in range(30)]
    assert calculate_rsi(rising_prices) == 100.0

    # Falling prices -> RSI near 0
    falling_prices = [200.0 - i for i in range(30)]
    rsi_down = calculate_rsi(falling_prices)
    assert 0.0 <= rsi_down < 5.0


def test_calculate_macd():
    # Test on sequence of 40 closes
    closes = [100.0 + (i * 0.5) for i in range(40)]
    macd, signal, hist = calculate_macd(closes)
    assert isinstance(macd, float)
    assert isinstance(signal, float)
    assert isinstance(hist, float)
    assert round(hist, 4) == round(macd - signal, 4)


def test_calculate_bollinger_bands():
    closes = [100.0 + (i % 5) for i in range(30)]
    upper, mid, lower, pct_b = calculate_bollinger_bands(closes, period=20, num_std_dev=2.0)
    assert upper > mid > lower
    assert 0.0 <= pct_b <= 1.0


def test_calculate_atr():
    candles = [
        Candle(timestamp=i, open=100.0, high=105.0, low=95.0, close=102.0, volume=10.0)
        for i in range(25)
    ]
    atr = calculate_atr(candles, period=14)
    assert atr > 0.0


def test_detect_regimes():
    trend = detect_trend_regime([110.0], ema_20=105.0, ema_50=100.0, ema_200=90.0)
    assert trend == "STRONG_BULLISH"

    trend_bear = detect_trend_regime([80.0], ema_20=90.0, ema_50=95.0, ema_200=100.0)
    assert trend_bear == "STRONG_BEARISH"

    vol_high = detect_volatility_regime(atr=5.0, current_price=100.0)
    assert vol_high == "HIGH_VOLATILITY"


def test_compute_all_indicators():
    candles = [
        Candle(
            timestamp=float(i),
            open=100.0 + i,
            high=102.0 + i,
            low=99.0 + i,
            close=101.0 + i,
            volume=50.0,
        )
        for i in range(50)
    ]
    indicators = compute_all_indicators(candles)
    assert indicators.rsi_14 > 0
    assert indicators.bb_upper > indicators.bb_lower
    assert indicators.trend_regime != ""
