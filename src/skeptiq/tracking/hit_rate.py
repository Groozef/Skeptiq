import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from skeptiq.core.db import session_scope
from skeptiq.core.logging import get_logger
from skeptiq.core.models import Recommendation as RecommendationORM
from skeptiq.market.binance import BinanceClient

log = get_logger(__name__)

DEFAULT_INTERVAL_SEC = 300  # check every 5 min — tiers have 1/6/24h granularity


@dataclass(slots=True, kw_only=True, frozen=True)
class _Tier:
    hours: int
    price_column: str        # ORM attribute name
    is_outcome_tier: bool    # the 24h tier also writes pct_move + direction_correct


_TIERS: tuple[_Tier, ...] = (
    _Tier(hours=1, price_column="price_after_1h", is_outcome_tier=False),
    _Tier(hours=6, price_column="price_after_6h", is_outcome_tier=False),
    _Tier(hours=24, price_column="price_after_24h", is_outcome_tier=True),
)


def _ensure_utc(dt: datetime) -> datetime:
    """SQLite drops tzinfo on read; we write UTC, so re-attach UTC on read."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


class HitRateTracker:
    """Backfills price_after_{1h,6h,24h} on Recommendation rows once enough
    time has passed, plus pct_move_24h and direction_correct_24h on the 24h
    tier. Drives v0.2's first attempt at measuring real signal quality.

    Runs as a sibling task in main's TaskGroup — failures inside _cycle are
    logged and the loop continues so transient Binance issues never kill it.
    """

    def __init__(
        self,
        *,
        binance: BinanceClient,
        interval_sec: int = DEFAULT_INTERVAL_SEC,
    ) -> None:
        self._binance = binance
        self._interval_sec = interval_sec

    async def run(self) -> None:
        log.info("hit_rate_tracker_started", interval_sec=self._interval_sec)
        while True:
            try:
                await self._cycle()
            except asyncio.CancelledError:
                log.info("hit_rate_tracker_cancelled")
                raise
            except Exception as exc:
                log.exception("hit_rate_cycle_error", error=str(exc))
            await asyncio.sleep(self._interval_sec)

    async def _cycle(self) -> None:
        now = datetime.now(UTC)
        for tier in _TIERS:
            await self._fill_tier(now=now, tier=tier)

    async def _fill_tier(self, *, now: datetime, tier: _Tier) -> None:
        threshold = now - timedelta(hours=tier.hours)

        async with session_scope() as session:
            select_stmt = select(RecommendationORM).where(
                RecommendationORM.sent_at <= threshold,
                getattr(RecommendationORM, tier.price_column).is_(None),
            )
            recs = list((await session.execute(select_stmt)).scalars().all())

        if not recs:
            return

        log.debug("hit_rate_tier_pending", hours=tier.hours, count=len(recs))

        for rec in recs:
            sent_at = _ensure_utc(rec.sent_at)
            target_dt = sent_at + timedelta(hours=tier.hours)

            try:
                kline = await self._binance.fetch_kline_at(rec.ticker, target_dt)
            except Exception as exc:
                log.warning(
                    "hit_rate_fetch_failed",
                    rec_id=rec.id,
                    ticker=rec.ticker,
                    tier_hours=tier.hours,
                    error=str(exc),
                )
                continue

            if kline is None:
                # Binance has no kline yet — either earlier than data history
                # or there's a slight clock skew. Try again next cycle.
                continue

            close = kline.close
            pct_move: float | None = None
            direction_correct: bool | None = None

            if tier.is_outcome_tier and rec.price_at_send:
                pct_move = (close - rec.price_at_send) / rec.price_at_send * 100.0
                if rec.direction == "long":
                    direction_correct = pct_move > 0
                elif rec.direction == "short":
                    direction_correct = pct_move < 0

            async with session_scope() as session:
                update_stmt = update(RecommendationORM).where(
                    RecommendationORM.id == rec.id
                )
                if tier.is_outcome_tier:
                    await session.execute(
                        update_stmt.values(
                            **{tier.price_column: close},
                            pct_move_24h=pct_move,
                            direction_correct_24h=direction_correct,
                        )
                    )
                else:
                    await session.execute(
                        update_stmt.values(**{tier.price_column: close})
                    )

            extras = (
                {
                    "pct_move_24h": round(pct_move, 3) if pct_move is not None else None,
                    "direction_correct_24h": direction_correct,
                }
                if tier.is_outcome_tier
                else {}
            )
            log.info(
                "hit_rate_filled",
                rec_id=rec.id,
                ticker=rec.ticker,
                tier_hours=tier.hours,
                close=round(close, 4),
                **extras,
            )
