"""Auto-expire path: HitRateTracker._close_expired writes final_outcome."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from skeptiq.core.config import Settings
from skeptiq.core.db import session_scope
from skeptiq.core.models import Analysis, IngestedItem
from skeptiq.core.models import Recommendation as RecommendationORM
from skeptiq.market.binance import Kline
from skeptiq.tracking.hit_rate import HitRateTracker, _scan_for_tp_sl


class _FakeBinanceRange:
    def __init__(self, klines: list[Kline]) -> None:
        self._klines = klines
        self.calls: list[tuple[str, datetime, datetime]] = []

    async def fetch_klines_range(
        self, ticker: str, start_dt: datetime, end_dt: datetime, **_kw: Any
    ) -> list[Kline]:
        self.calls.append((ticker, start_dt, end_dt))
        return list(self._klines)


def _kl(ts_ms: int, *, open_: float, high: float, low: float, close: float) -> Kline:
    return Kline(
        open_time_ms=ts_ms,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=1.0,
        close_time_ms=ts_ms + 3_600_000 - 1,
    )


async def _seed_open_rec(
    *,
    ticker: str,
    direction: str,
    entry: float,
    stop_loss: float,
    take_profit: float,
    sent_at: datetime,
    expires_at: datetime,
) -> int:
    async with session_scope() as session:
        item = IngestedItem(
            source="t",
            external_id=f"{ticker}-{sent_at.timestamp()}",
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
            affected_tickers=ticker,
            sentiment="bullish" if direction == "long" else "bearish",
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
            ticker=ticker,
            direction=direction,
            technical_context_json="{}",
            technical_alignment="confirms",
            sent_at=sent_at,
            price_at_send=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            expires_at=expires_at,
        )
        session.add(rec)
        await session.flush()
        return rec.id


def test_scan_long_tp_hit_first_bar() -> None:
    klines = [_kl(0, open_=100, high=110, low=99, close=108)]
    out, ts = _scan_for_tp_sl(
        klines, direction="long", stop_loss=95.0, take_profit=105.0
    )
    assert out == "tp_hit"
    assert ts == klines[0].close_time_ms


def test_scan_long_sl_hit() -> None:
    klines = [_kl(0, open_=100, high=101, low=94, close=96)]
    out, _ = _scan_for_tp_sl(
        klines, direction="long", stop_loss=95.0, take_profit=110.0
    )
    assert out == "sl_hit"


def test_scan_short_tp_hit() -> None:
    klines = [_kl(0, open_=100, high=101, low=94, close=96)]
    out, _ = _scan_for_tp_sl(
        klines, direction="short", stop_loss=110.0, take_profit=95.0
    )
    assert out == "tp_hit"


def test_scan_no_hit_returns_expired() -> None:
    klines = [
        _kl(0, open_=100, high=102, low=99, close=101),
        _kl(3600_000, open_=101, high=103, low=100, close=102),
    ]
    out, ts = _scan_for_tp_sl(
        klines, direction="long", stop_loss=90.0, take_profit=120.0
    )
    assert out == "expired"
    assert ts is None


@pytest.mark.asyncio
async def test_close_expired_writes_tp_hit(temp_db: Settings) -> None:
    sent = datetime(2026, 4, 27, 12, 0, tzinfo=UTC)
    expires = sent + timedelta(hours=12)
    rec_id = await _seed_open_rec(
        ticker="BTC",
        direction="long",
        entry=100.0,
        stop_loss=95.0,
        take_profit=105.0,
        sent_at=sent,
        expires_at=expires,
    )

    klines = [
        _kl(int(sent.timestamp() * 1000), open_=100, high=104, low=99, close=103),
        _kl(int((sent + timedelta(hours=2)).timestamp() * 1000),
            open_=103, high=106, low=102, close=105),
    ]
    fake = _FakeBinanceRange(klines)
    tracker = HitRateTracker(binance=fake, interval_sec=1)  # type: ignore[arg-type]

    now = expires + timedelta(minutes=5)  # past expiry
    await tracker._close_expired(now=now)

    async with session_scope() as session:
        rec = await session.get(RecommendationORM, rec_id)
        assert rec is not None
        assert rec.final_outcome == "tp_hit"
        assert rec.final_outcome_pct is not None
        assert rec.final_outcome_at is not None


@pytest.mark.asyncio
async def test_close_expired_writes_expired_when_no_hit(temp_db: Settings) -> None:
    sent = datetime(2026, 4, 27, 12, 0, tzinfo=UTC)
    expires = sent + timedelta(hours=12)
    rec_id = await _seed_open_rec(
        ticker="ETH",
        direction="long",
        entry=2000.0,
        stop_loss=1900.0,
        take_profit=2200.0,
        sent_at=sent,
        expires_at=expires,
    )

    klines = [
        _kl(int(sent.timestamp() * 1000), open_=2000, high=2050, low=1980, close=2010),
        _kl(int((sent + timedelta(hours=6)).timestamp() * 1000),
            open_=2010, high=2030, low=1990, close=2005),
    ]
    fake = _FakeBinanceRange(klines)
    tracker = HitRateTracker(binance=fake, interval_sec=1)  # type: ignore[arg-type]

    await tracker._close_expired(now=expires + timedelta(minutes=5))

    async with session_scope() as session:
        rec = await session.get(RecommendationORM, rec_id)
        assert rec is not None
        assert rec.final_outcome == "expired"
        # pct from entry 2000 to last close 2005 -> +0.25%
        assert rec.final_outcome_pct == pytest.approx(0.25)


@pytest.mark.asyncio
async def test_close_expired_skips_not_yet_expired(temp_db: Settings) -> None:
    sent = datetime.now(UTC) - timedelta(minutes=30)
    expires = sent + timedelta(hours=12)  # 11.5h in the future
    rec_id = await _seed_open_rec(
        ticker="BTC",
        direction="long",
        entry=100.0,
        stop_loss=95.0,
        take_profit=105.0,
        sent_at=sent,
        expires_at=expires,
    )

    fake = _FakeBinanceRange([])
    tracker = HitRateTracker(binance=fake, interval_sec=1)  # type: ignore[arg-type]
    await tracker._close_expired(now=datetime.now(UTC))

    async with session_scope() as session:
        rec = await session.get(RecommendationORM, rec_id)
        assert rec is not None
        assert rec.final_outcome is None
    assert fake.calls == []


@pytest.mark.asyncio
async def test_close_expired_skips_already_closed(temp_db: Settings) -> None:
    sent = datetime(2026, 4, 27, 12, 0, tzinfo=UTC)
    expires = sent + timedelta(hours=12)
    rec_id = await _seed_open_rec(
        ticker="BTC",
        direction="long",
        entry=100.0,
        stop_loss=95.0,
        take_profit=105.0,
        sent_at=sent,
        expires_at=expires,
    )
    # Pretend a previous tracker pass already wrote outcome.
    async with session_scope() as session:
        rec = await session.get(RecommendationORM, rec_id)
        assert rec is not None
        rec.final_outcome = "tp_hit"
        rec.final_outcome_pct = 5.0

    fake = _FakeBinanceRange([])
    tracker = HitRateTracker(binance=fake, interval_sec=1)  # type: ignore[arg-type]
    await tracker._close_expired(now=expires + timedelta(hours=1))

    assert fake.calls == []
