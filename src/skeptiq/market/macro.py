"""Macro context for confidence calibration.

Pulls SPX (^GSPC), DXY (DX=F), and VIX (^VIX) from Yahoo Finance via yfinance.
The bot's news+tech analysis runs blind to the broader risk-on/risk-off
environment, which in 2024-2026 has been the dominant driver for BTC/ETH.

A "regime score" combines the three indicators:

  SPX 24h: > +1% -> +1 (risk-on);  < -1% -> -1 (risk-off);   else 0
  DXY 24h: < -0.5% -> +1 (USD weak/risk-on);  > +0.5% -> -1; else 0
  VIX level: < 20 -> +1 (calm);    > 28 -> -1 (panic);        else 0

Score range: -3 (extreme risk-off) to +3 (extreme risk-on).

Confidence calibration:
  long signal + macro <= -2  -> -0.10 (longing into risk-off)
  long signal + macro >= +2  -> +0.05 (longing with risk-on tailwind)
  short signal + macro >= +2 -> -0.10 (shorting into risk-on)
  short signal + macro <= -2 -> +0.05 (shorting with risk-off tailwind)

Cached 1h: macro doesn't move minute-to-minute, and yfinance is rate-limited.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Literal

from skeptiq.core.logging import get_logger
from skeptiq.schemas.recommendation import Direction

log = get_logger(__name__)

CACHE_TTL_SEC = 3600  # 1h — macro moves slow

SPX_TICKER = "^GSPC"
# DX-Y.NYB is the ICE Dollar Index — DX=F (futures) and ^DXY both 404 on Yahoo.
DXY_TICKER = "DX-Y.NYB"
VIX_TICKER = "^VIX"

SPX_THRESHOLD_PCT = 1.0
DXY_THRESHOLD_PCT = 0.5
VIX_CALM = 20.0
VIX_PANIC = 28.0

MacroAlignment = Literal["support", "neutral", "conflict", "unavailable"]


@dataclass(slots=True, kw_only=True, frozen=True)
class MacroContext:
    spx_change_24h_pct: float
    dxy_change_24h_pct: float
    vix_level: float
    score: int                      # -3 to +3, positive = risk-on
    available: bool                 # False if yfinance failed to fetch


def _macro_score(spx_pct: float, dxy_pct: float, vix: float) -> int:
    score = 0
    if spx_pct > SPX_THRESHOLD_PCT:
        score += 1
    elif spx_pct < -SPX_THRESHOLD_PCT:
        score -= 1
    # DXY inverse to risk: stronger USD = risk-off
    if dxy_pct < -DXY_THRESHOLD_PCT:
        score += 1
    elif dxy_pct > DXY_THRESHOLD_PCT:
        score -= 1
    if vix < VIX_CALM:
        score += 1
    elif vix > VIX_PANIC:
        score -= 1
    return score


def alignment_for_direction(
    macro: MacroContext, direction: Direction
) -> MacroAlignment:
    if not macro.available:
        return "unavailable"
    if direction == "long":
        if macro.score >= 2:
            return "support"
        if macro.score <= -2:
            return "conflict"
        return "neutral"
    # short: mirror
    if macro.score <= -2:
        return "support"
    if macro.score >= 2:
        return "conflict"
    return "neutral"


def _fetch_macro_blocking() -> MacroContext:
    """Synchronous fetch — runs in thread pool. yfinance is blocking and
    rate-limited; one call per ticker per cache window is fine."""
    import yfinance as yf  # heavy import, kept local

    try:
        spx_hist = yf.Ticker(SPX_TICKER).history(period="3d", interval="1h")
        dxy_hist = yf.Ticker(DXY_TICKER).history(period="3d", interval="1h")
        vix_hist = yf.Ticker(VIX_TICKER).history(period="2d", interval="1h")

        if spx_hist.empty or dxy_hist.empty or vix_hist.empty:
            log.warning("macro_empty_history")
            return MacroContext(
                spx_change_24h_pct=0.0,
                dxy_change_24h_pct=0.0,
                vix_level=0.0,
                score=0,
                available=False,
            )

        # 24h ago = ~24 hourly bars back. Markets close on weekends so this
        # is approximate, but good enough for a regime-level read.
        def _change_pct(hist: Any, bars_back: int = 24) -> float:
            closes = hist["Close"].dropna()
            if len(closes) < bars_back + 1:
                bars_back = len(closes) - 1
            if bars_back < 1:
                return 0.0
            return float((closes.iloc[-1] - closes.iloc[-bars_back - 1])
                         / closes.iloc[-bars_back - 1] * 100.0)

        spx_pct = _change_pct(spx_hist)
        dxy_pct = _change_pct(dxy_hist)
        vix_level = float(vix_hist["Close"].dropna().iloc[-1])

        score = _macro_score(spx_pct, dxy_pct, vix_level)

        return MacroContext(
            spx_change_24h_pct=spx_pct,
            dxy_change_24h_pct=dxy_pct,
            vix_level=vix_level,
            score=score,
            available=True,
        )
    except Exception as exc:
        log.warning("macro_fetch_failed", error=str(exc))
        return MacroContext(
            spx_change_24h_pct=0.0,
            dxy_change_24h_pct=0.0,
            vix_level=0.0,
            score=0,
            available=False,
        )


class MacroProvider:
    """1h-cached MacroContext provider. Single instance shared across the
    builder loop. Call get_context() — it handles caching and threading."""

    def __init__(self, *, cache_ttl_sec: float = CACHE_TTL_SEC) -> None:
        self._ttl = cache_ttl_sec
        self._cache: MacroContext | None = None
        self._cache_at_monotonic: float = 0.0
        self._lock = asyncio.Lock()

    async def get_context(self) -> MacroContext:
        now = time.monotonic()
        async with self._lock:
            if self._cache is not None and (now - self._cache_at_monotonic) < self._ttl:
                return self._cache

        # Fetch outside the lock — yfinance call is slow.
        ctx = await asyncio.to_thread(_fetch_macro_blocking)

        async with self._lock:
            self._cache = ctx
            self._cache_at_monotonic = now

        log.info(
            "macro_context_refreshed",
            spx_pct=round(ctx.spx_change_24h_pct, 2),
            dxy_pct=round(ctx.dxy_change_24h_pct, 2),
            vix=round(ctx.vix_level, 1),
            score=ctx.score,
            available=ctx.available,
        )
        return ctx
