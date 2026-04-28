import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx

from skeptiq.core.logging import get_logger

log = get_logger(__name__)

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"


@dataclass(slots=True, kw_only=True, frozen=True)
class Kline:
    open_time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time_ms: int


@dataclass(slots=True)
class _CacheEntry:
    fetched_at_monotonic: float
    klines: list[Kline]


class BinanceClient:
    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        cache_ttl_sec: float = 300.0,
        quote_asset: str = "USDT",
    ) -> None:
        self._http = http_client or httpx.AsyncClient(timeout=httpx.Timeout(15.0))
        self._owns_http = http_client is None
        self._ttl = cache_ttl_sec
        self._quote = quote_asset
        self._cache: dict[tuple[str, str, int], _CacheEntry] = {}
        self._lock = asyncio.Lock()

    def _symbol(self, ticker: str) -> str:
        return f"{ticker.upper()}{self._quote}"

    async def fetch_klines(
        self,
        ticker: str,
        *,
        interval: str = "1h",
        limit: int = 100,
    ) -> list[Kline]:
        symbol = self._symbol(ticker)
        key = (symbol, interval, limit)
        now = time.monotonic()

        async with self._lock:
            entry = self._cache.get(key)
            if entry and (now - entry.fetched_at_monotonic) < self._ttl:
                return entry.klines

        try:
            resp = await self._http.get(
                BINANCE_KLINES_URL,
                params={"symbol": symbol, "interval": interval, "limit": limit},
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("binance_fetch_failed", symbol=symbol, error=str(exc))
            raise

        raw = resp.json()
        klines = [_parse_kline(row) for row in raw]

        async with self._lock:
            self._cache[key] = _CacheEntry(
                fetched_at_monotonic=now,
                klines=klines,
            )
        return klines

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()


def _parse_kline(row: list[Any]) -> Kline:
    return Kline(
        open_time_ms=int(row[0]),
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
        close_time_ms=int(row[6]),
    )
