import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from skeptiq.core.db import session_scope
from skeptiq.core.logging import get_logger
from skeptiq.core.models import Recommendation as RecommendationORM
from skeptiq.market.binance import BinanceClient, Kline

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


def _scan_for_tp_sl(
    klines: list[Kline],
    *,
    direction: str,
    stop_loss: float,
    take_profit: float,
) -> tuple[str, int | None]:
    """Walk klines in order; the first bar to cross either level wins.
    For long: high >= TP -> tp_hit, low <= SL -> sl_hit.
    For short: low <= TP -> tp_hit (TP is below entry), high >= SL -> sl_hit.
    Returns ('tp_hit' | 'sl_hit' | 'expired', close_time_ms_or_None).
    """
    for k in klines:
        if direction == "long":
            if k.high >= take_profit:
                return "tp_hit", k.close_time_ms
            if k.low <= stop_loss:
                return "sl_hit", k.close_time_ms
        else:  # short
            if k.low <= take_profit:
                return "tp_hit", k.close_time_ms
            if k.high >= stop_loss:
                return "sl_hit", k.close_time_ms
    return "expired", None


class HitRateTracker:
    """Backfills price_after_{1h,6h,24h} on Recommendation rows once enough
    time has passed (plus pct_move_24h and direction_correct_24h), AND
    closes signals whose horizon-based expires_at has passed (writing
    final_outcome = tp_hit / sl_hit / expired).

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
        await self._close_expired(now=now)

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

    async def _close_expired(self, *, now: datetime) -> None:
        """For recs whose expires_at has passed and that don't yet have a
        final outcome, scan klines in [sent_at, expires_at] for the first
        TP/SL touch. If neither touched, mark outcome=expired and record
        pct move from entry to expiry close."""
        async with session_scope() as session:
            stmt = select(RecommendationORM).where(
                RecommendationORM.expires_at.isnot(None),
                RecommendationORM.expires_at <= now,
                RecommendationORM.final_outcome.is_(None),
            )
            recs = list((await session.execute(stmt)).scalars().all())

        if not recs:
            return

        log.debug("hit_rate_expired_pending", count=len(recs))

        for rec in recs:
            if (
                rec.stop_loss is None
                or rec.take_profit is None
                or rec.price_at_send is None
                or rec.sent_at is None
                or rec.expires_at is None
            ):
                continue
            sent_at = _ensure_utc(rec.sent_at)
            expires_at = _ensure_utc(rec.expires_at)

            try:
                klines = await self._binance.fetch_klines_range(
                    rec.ticker, sent_at, expires_at, interval="1h"
                )
            except Exception as exc:
                log.warning(
                    "hit_rate_expire_fetch_failed",
                    rec_id=rec.id,
                    ticker=rec.ticker,
                    error=str(exc),
                )
                continue

            outcome, hit_at_ms = _scan_for_tp_sl(
                klines,
                direction=rec.direction,
                stop_loss=rec.stop_loss,
                take_profit=rec.take_profit,
            )

            close_for_pct = klines[-1].close if klines else rec.price_at_send
            pct = (close_for_pct - rec.price_at_send) / rec.price_at_send * 100.0
            outcome_at = (
                datetime.fromtimestamp(hit_at_ms / 1000, tz=UTC) if hit_at_ms else None
            )

            async with session_scope() as session:
                await session.execute(
                    update(RecommendationORM)
                    .where(RecommendationORM.id == rec.id)
                    .values(
                        final_outcome=outcome,
                        final_outcome_pct=pct,
                        final_outcome_at=outcome_at,
                    )
                )

            log.info(
                "hit_rate_final_outcome",
                rec_id=rec.id,
                ticker=rec.ticker,
                outcome=outcome,
                pct=round(pct, 3),
                hit_at_ms=hit_at_ms,
            )
