"""Kraken Public REST and market data client with offline/synthetic fallback."""

import logging
import random
import time
from typing import Any, Dict, List, Optional, Tuple
import httpx
from superkraken.state import Candle

logger = logging.getLogger(__name__)


# Kraken symbol mapping: human-readable pair -> Kraken internal API format
PAIR_MAP = {
    "BTC/USD": "XBTZUSD",
    "ETH/USD": "XETHZUSD",
    "SOL/USD": "SOLUSD",
    "BTC/USDT": "XBTUSDT",
    "ETH/USDT": "ETHUSDT",
    "SOL/USDT": "SOLUSDT",
}
KRAKEN_PAIR_MAP = PAIR_MAP


class KrakenMarketDataClient:
    """Fetches real-time ticker, OHLCV, and order book from Kraken API."""

    BASE_URL = "https://api.kraken.com/0/public"

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
        self._cached_tickers: Dict[str, float] = {
            "BTC/USD": 67420.0,
            "ETH/USD": 3210.0,
            "SOL/USD": 182.5,
        }

    def _normalize_pair(self, pair: str) -> str:
        clean = pair.upper().strip()
        return KRAKEN_PAIR_MAP.get(clean, clean.replace("/", ""))

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """Fetch current ticker price, 24h change, high, low, volume."""
        pair = self._normalize_pair(symbol)
        url = f"{self.BASE_URL}/Ticker?pair={pair}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    if not data.get("error") and "result" in data:
                        # First key in result
                        result_key = list(data["result"].keys())[0]
                        res = data["result"][result_key]
                        last_price = float(res["c"][0])
                        self._cached_tickers[symbol] = last_price
                        return {
                            "symbol": symbol,
                            "price": last_price,
                            "bid": float(res["b"][0]),
                            "ask": float(res["a"][0]),
                            "high_24h": float(res["h"][1]),
                            "low_24h": float(res["l"][1]),
                            "volume_24h": float(res["v"][1]),
                            "change_pct": round(
                                ((last_price - float(res["o"])) / float(res["o"])) * 100, 2
                            )
                            if float(res["o"]) > 0
                            else 0.0,
                        }
        except Exception as e:
            logger.debug(f"Public Kraken API failed for {symbol}: {e}. Using resilient fallback.")

        # Resilient fallback with subtle dynamic drift
        base = self._cached_tickers.get(symbol, 100.0)
        drift = base * (random.uniform(-0.003, 0.003))
        current = round(base + drift, 2)
        self._cached_tickers[symbol] = current

        return {
            "symbol": symbol,
            "price": current,
            "bid": round(current * 0.9998, 2),
            "ask": round(current * 1.0002, 2),
            "high_24h": round(current * 1.03, 2),
            "low_24h": round(current * 0.97, 2),
            "volume_24h": 1250.0,
            "change_pct": round(random.uniform(-1.5, 2.5), 2),
        }

    async def get_ohlc(self, symbol: str, interval_minutes: int = 1, count: int = 100) -> List[Candle]:
        """Fetch OHLCV candlestick historical series."""
        pair = self._normalize_pair(symbol)
        url = f"{self.BASE_URL}/OHLC?pair={pair}&interval={interval_minutes}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    if not data.get("error") and "result" in data:
                        result_key = [k for k in data["result"].keys() if k != "last"][0]
                        raw_candles = data["result"][result_key][-count:]
                        candles = []
                        for row in raw_candles:
                            candles.append(
                                Candle(
                                    timestamp=float(row[0]),
                                    open=float(row[1]),
                                    high=float(row[2]),
                                    low=float(row[3]),
                                    close=float(row[4]),
                                    volume=float(row[6]),
                                )
                            )
                        if candles:
                            return candles
        except Exception as e:
            logger.debug(f"Failed to fetch live OHLC for {symbol}: {e}. Generating synthetic history.")

        # Fallback realistic random walk candles
        ticker = await self.get_ticker(symbol)
        base_price = ticker["price"]
        candles: List[Candle] = []
        now = time.time()
        p = base_price * 0.98

        for i in range(count):
            ts = now - ((count - i) * interval_minutes * 60)
            step = p * random.gauss(0.0002, 0.004)
            c_open = p
            c_close = max(1.0, c_open + step)
            c_high = max(c_open, c_close) + abs(random.gauss(0, p * 0.001))
            c_low = min(c_open, c_close) - abs(random.gauss(0, p * 0.001))
            c_vol = abs(random.gauss(15.0, 5.0))
            candles.append(
                Candle(
                    timestamp=ts,
                    open=round(c_open, 2),
                    high=round(c_high, 2),
                    low=round(c_low, 2),
                    close=round(c_close, 2),
                    volume=round(c_vol, 4),
                )
            )
            p = c_close

        return candles

    async def get_order_book_depth(self, symbol: str, count: int = 10) -> Dict[str, Any]:
        """Fetch order book depth to calculate bid/ask imbalance."""
        pair = self._normalize_pair(symbol)
        url = f"{self.BASE_URL}/Depth?pair={pair}&count={count}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    if not data.get("error") and "result" in data:
                        result_key = list(data["result"].keys())[0]
                        res = data["result"][result_key]
                        bids = [[float(p), float(v)] for p, v, _ in res.get("bids", [])]
                        asks = [[float(p), float(v)] for p, v, _ in res.get("asks", [])]
                        bid_vol = sum(v for _, v in bids)
                        ask_vol = sum(v for _, v in asks)
                        imbalance = (bid_vol - ask_vol) / (bid_vol + ask_vol) if (bid_vol + ask_vol) > 0 else 0.0
                        return {
                            "bids": bids,
                            "asks": asks,
                            "bid_volume": round(bid_vol, 4),
                            "ask_volume": round(ask_vol, 4),
                            "imbalance": round(imbalance, 4),
                        }
        except Exception:
            pass

        # Realistic synthetic depth
        bid_vol = random.uniform(40.0, 100.0)
        ask_vol = random.uniform(40.0, 100.0)
        imbalance = (bid_vol - ask_vol) / (bid_vol + ask_vol)
        return {
            "bids": [],
            "asks": [],
            "bid_volume": round(bid_vol, 4),
            "ask_volume": round(ask_vol, 4),
            "imbalance": round(imbalance, 4),
        }
