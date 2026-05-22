"""Per-ticker funding-rate context for confidence calibration.

Pulls current 8h funding rate from Binance Futures public API (no auth).
Funding rate is the cleanest derivatives-market signal of crowdedness:

  - Positive funding (longs pay shorts) = market positioned long
  - Negative funding (shorts pay longs) = market positioned short
  - Extreme magnitude either way = blow-off / capitulation territory

Trading interpretation: a fresh signal in the SAME direction as funding-
crowdedness is late entry / squeeze-vulnerable; a signal AGAINST crowded
funding is the structural contrarian play.

Calibration impact:
  long signal + funding > +0.05%/8h  -> -0.05 (joining crowded long)
  long signal + funding < -0.05%/8h  -> +0.05 (taking other side of crowded short)
  short signal + funding > +0.05%/8h -> +0.05 (taking other side of crowded long)
  short signal + funding < -0.05%/8h -> -0.05 (joining crowded short)

Cached 30 min: funding updates once per 8h on Binance, no need to poll often.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Literal

import httpx

from skeptiq.core.logging import get_logger
from skeptiq.schemas.recommendation import Direction

log = get_logger(__name__)

BINANCE_PREMIUM_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
CACHE_TTL_SEC = 1800  # 30 min — funding only updates every 8h
EXTREME_FUNDING_THRESHOLD = 0.0005  # 0.05% per 8h ~ 55% APR — clearly elevated

FundingAlignment = Literal["support", "neutral", "conflict", "unavailable"]


@dataclass(slots=True, kw_only=True, frozen=True)
class FundingContext:
    ticker: str
    funding_rate_8h: float | None     # None if symbol not on Binance perps
    next_funding_time_ms: int | None
    available: bool


def alignment_for_direction(
    funding: FundingContext, direction: Direction
) -> FundingAlignment:
    if not funding.available or funding.funding_rate_8h is None:
        return "unavailable"
    fr = funding.funding_rate_8h
    if abs(fr) < EXTREME_FUNDING_THRESHOLD:
        return "neutral"
    crowded_side: Direction = "long" if fr > 0 else "short"
    if direction == crowded_side:
        # joining crowded trade — late entry, squeeze risk
        return "conflict"
    # taking the other side of crowded positioning — structural contrarian
    return "support"


@dataclass(slots=True)
class _CacheEntry:
    fetched_at_monotonic: float
    ctx: FundingContext


class FundingProvider:
    """Per-ticker funding-rate cache backed by Binance Futures public API.
    Shared across the recommender loop; each fetch is ~50ms but we cache
    30min so steady-state overhead is near zero."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        cache_ttl_sec: float = CACHE_TTL_SEC,
        quote_asset: str = "USDT",
    ) -> None:
        self._http = http_client or httpx.AsyncClient(timeout=httpx.Timeout(10.0))
        self._owns_http = http_client is None
        self._ttl = cache_ttl_sec
        self._quote = quote_asset
        self._cache: dict[str, _CacheEntry] = {}
        self._lock = asyncio.Lock()

    def _symbol(self, ticker: str) -> str:
        return f"{ticker.upper()}{self._quote}"

    async def get_context(self, ticker: str) -> FundingContext:
        symbol = self._symbol(ticker)
        now = time.monotonic()
        async with self._lock:
            cached = self._cache.get(symbol)
            if cached and (now - cached.fetched_at_monotonic) < self._ttl:
                return cached.ctx

        ctx = await self._fetch(ticker, symbol)

        async with self._lock:
            self._cache[symbol] = _CacheEntry(fetched_at_monotonic=now, ctx=ctx)
        return ctx

    async def _fetch(self, ticker: str, symbol: str) -> FundingContext:
        try:
            resp = await self._http.get(
                BINANCE_PREMIUM_URL,
                params={"symbol": symbol},
            )
        except httpx.HTTPError as exc:
            log.warning("funding_fetch_failed", symbol=symbol, error=str(exc))
            return FundingContext(
                ticker=ticker.upper(),
                funding_rate_8h=None,
                next_funding_time_ms=None,
                available=False,
            )

        if resp.status_code == 400:
            # Symbol not listed on Binance perps (e.g. some small-cap alts).
            log.debug("funding_symbol_not_on_perps", symbol=symbol)
            return FundingContext(
                ticker=ticker.upper(),
                funding_rate_8h=None,
                next_funding_time_ms=None,
                available=False,
            )
        try:
            resp.raise_for_status()
            data = resp.json()
            return FundingContext(
                ticker=ticker.upper(),
                funding_rate_8h=float(data["lastFundingRate"]),
                next_funding_time_ms=int(data.get("nextFundingTime", 0)) or None,
                available=True,
            )
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            log.warning("funding_parse_failed", symbol=symbol, error=str(exc))
            return FundingContext(
                ticker=ticker.upper(),
                funding_rate_8h=None,
                next_funding_time_ms=None,
                available=False,
            )

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()
