from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from skeptiq.core.config import Settings
from skeptiq.core.db import session_scope
from skeptiq.core.models import Analysis, IngestedItem
from skeptiq.core.models import Recommendation as RecommendationORM
from skeptiq.market.binance import Kline
from skeptiq.tracking.hit_rate import _TIERS, HitRateTracker


class _FakeBinance:
    def __init__(self, by_offset_hours: dict[int, float]) -> None:
        # Map: hours-after-sent_at -> close price
        self._prices = by_offset_hours
        self.calls: list[tuple[str, datetime]] = []

    async def fetch_kline_at(
        self, ticker: str, target_dt: datetime, **_kw: Any
    ) -> Kline | None:
        self.calls.append((ticker, target_dt))
        # Decide offset by comparing with the seeded sent_at; tests pass that
        # via closure. We just round to hours and look up.
        offset_h = round((target_dt - _SENT_AT).total_seconds() / 3600)
        price = self._prices.get(offset_h)
        if price is None:
            return None
        ts_ms = int(target_dt.timestamp() * 1000)
        return Kline(
            open_time_ms=ts_ms,
            open=price - 1,
            high=price + 1,
            low=price - 2,
            close=price,
            volume=10.0,
            close_time_ms=ts_ms + 3_600_000 - 1,
        )


_SENT_AT = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)  # 25h before "now" below


async def _seed_recommendation(
    *, sent_at: datetime, direction: str, price_at_send: float
) -> int:
    async with session_scope() as session:
        item = IngestedItem(
            source="x",
            external_id="x1",
            url="http://x",
            title="t",
            content="c",
            published_at=sent_at,
        )
        session.add(item)
        await session.flush()

        analysis = Analysis(
            item_id=item.id,
            raw_response_json="{}",
            is_relevant=True,
            affected_tickers="BTC",
            sentiment="bullish",
            impact_magnitude="high",
            confidence=0.7,
            time_horizon="hours",
            summary="s",
            reasoning="r",
            key_points_json="[]",
            counter_signals_json="[]",
            model_used="test",
        )
        session.add(analysis)
        await session.flush()

        rec = RecommendationORM(
            analysis_id=analysis.id,
            ticker="BTC",
            direction=direction,
            technical_context_json="{}",
            technical_alignment="neutral",
            sent_at=sent_at,
            price_at_send=price_at_send,
        )
        session.add(rec)
        await session.flush()
        return rec.id


@pytest.mark.asyncio
async def test_hit_rate_fills_all_three_tiers_and_24h_outcome(
    temp_db: Settings,
) -> None:
    rec_id = await _seed_recommendation(
        sent_at=_SENT_AT, direction="long", price_at_send=70_000.0
    )

    # Long signal: price rose 5% over 24h -> direction_correct_24h = True.
    fake = _FakeBinance({1: 70_350.0, 6: 71_000.0, 24: 73_500.0})
    tracker = HitRateTracker(binance=fake, interval_sec=1)  # type: ignore[arg-type]

    # Force 'now' to be 25h after sent_at so all three tiers are mature.
    now = _SENT_AT + timedelta(hours=25)
    for tier in _TIERS:
        await tracker._fill_tier(now=now, tier=tier)

    async with session_scope() as session:
        rec = await session.get(RecommendationORM, rec_id)
        assert rec is not None
        assert rec.price_after_1h == pytest.approx(70_350.0)
        assert rec.price_after_6h == pytest.approx(71_000.0)
        assert rec.price_after_24h == pytest.approx(73_500.0)
        assert rec.pct_move_24h == pytest.approx(5.0)
        assert rec.direction_correct_24h is True


@pytest.mark.asyncio
async def test_hit_rate_marks_short_correct_when_price_falls(
    temp_db: Settings,
) -> None:
    rec_id = await _seed_recommendation(
        sent_at=_SENT_AT, direction="short", price_at_send=70_000.0
    )

    # Short signal: price fell 3% over 24h -> direction_correct_24h = True.
    fake = _FakeBinance({24: 67_900.0})
    tracker = HitRateTracker(binance=fake, interval_sec=1)  # type: ignore[arg-type]

    now = _SENT_AT + timedelta(hours=25)
    tier_24h = next(t for t in _TIERS if t.hours == 24)
    await tracker._fill_tier(now=now, tier=tier_24h)

    async with session_scope() as session:
        rec = await session.get(RecommendationORM, rec_id)
        assert rec is not None
        assert rec.pct_move_24h == pytest.approx(-3.0)
        assert rec.direction_correct_24h is True


@pytest.mark.asyncio
async def test_hit_rate_skips_immature_rows(temp_db: Settings) -> None:
    """A recommendation sent only 30 min ago should NOT have any tier filled."""
    just_now = datetime.now(UTC) - timedelta(minutes=30)
    rec_id = await _seed_recommendation(
        sent_at=just_now, direction="long", price_at_send=70_000.0
    )

    fake = _FakeBinance({1: 70_500.0})  # would-be 1h price, not yet due
    tracker = HitRateTracker(binance=fake, interval_sec=1)  # type: ignore[arg-type]

    await tracker._cycle()

    async with session_scope() as session:
        rec = await session.get(RecommendationORM, rec_id)
        assert rec is not None
        assert rec.price_after_1h is None
        assert fake.calls == []
