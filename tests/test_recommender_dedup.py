"""Event-level deduplication: same event, same ticker -> drop or conflict."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from skeptiq.core.config import Settings
from skeptiq.core.db import session_scope
from skeptiq.core.models import Analysis, IngestedItem
from skeptiq.core.models import Recommendation as RecommendationORM
from skeptiq.recommender.dedup import find_recent_duplicate


async def _seed_signal(
    *,
    ticker: str,
    direction: str,
    sent_at: datetime,
    event_subject: str,
    key_numbers: list[str],
    related_projects: list[str],
) -> int:
    async with session_scope() as session:
        item = IngestedItem(
            source="test",
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
            time_horizon="days",
            summary="s",
            reasoning="r",
            key_points_json="[]",
            counter_signals_json="[]",
            event_subject=event_subject,
            event_key_numbers_json=json.dumps(key_numbers),
            event_related_projects_json=json.dumps(related_projects),
            analyzed_at=sent_at,
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
            price_at_send=100.0,
        )
        session.add(rec)
        await session.flush()
        return rec.id


@pytest.mark.asyncio
async def test_same_ticker_same_direction_returns_dup_same_dir(
    temp_db: Settings,
) -> None:
    now = datetime.now(UTC)
    prev_id = await _seed_signal(
        ticker="AAVE",
        direction="long",
        sent_at=now - timedelta(hours=1),
        event_subject="Kelp DAO exploit and recovery",
        key_numbers=["$293M", "$300M"],
        related_projects=["Aave", "DeFi United", "rsETH"],
    )

    result = await find_recent_duplicate(
        ticker="AAVE",
        direction="long",
        event_subject="Kelp exploit recovery effort",
        event_key_numbers=["$293M", "$300M"],
        event_related_projects=["Aave", "rsETH"],
    )
    assert result == ("dup_same_dir", prev_id)


@pytest.mark.asyncio
async def test_same_ticker_opposite_direction_returns_dup_conflict(
    temp_db: Settings,
) -> None:
    now = datetime.now(UTC)
    prev_id = await _seed_signal(
        ticker="AAVE",
        direction="long",
        sent_at=now - timedelta(minutes=10),
        event_subject="Kelp DAO exploit and recovery",
        key_numbers=["$293M"],
        related_projects=["Aave", "rsETH"],
    )

    result = await find_recent_duplicate(
        ticker="AAVE",
        direction="short",
        event_subject="Kelp DAO recovery plan",
        event_key_numbers=["$300M"],
        event_related_projects=["Aave", "rsETH"],
    )
    assert result == ("dup_conflict", prev_id)


@pytest.mark.asyncio
async def test_different_event_returns_none(temp_db: Settings) -> None:
    now = datetime.now(UTC)
    await _seed_signal(
        ticker="BTC",
        direction="long",
        sent_at=now - timedelta(hours=2),
        event_subject="Block treasury 9000 BTC milestone",
        key_numbers=["9000 BTC"],
        related_projects=["Block", "Square"],
    )

    result = await find_recent_duplicate(
        ticker="BTC",
        direction="long",
        event_subject="BlackRock spot ETF inflow",
        event_key_numbers=["$1.2B"],
        event_related_projects=["BlackRock", "CoinShares"],
    )
    assert result is None


@pytest.mark.asyncio
async def test_different_ticker_same_event_returns_none(
    temp_db: Settings,
) -> None:
    """Multi-asset news (e.g. CoinShares inflows for BTC + ETH) — separate
    per-ticker bets, not a dup. Multi-asset merging is fix #6, not dedup."""
    now = datetime.now(UTC)
    await _seed_signal(
        ticker="BTC",
        direction="long",
        sent_at=now - timedelta(minutes=5),
        event_subject="CoinShares weekly inflows report",
        key_numbers=["$1.2B"],
        related_projects=["CoinShares", "BlackRock"],
    )

    result = await find_recent_duplicate(
        ticker="ETH",
        direction="long",
        event_subject="CoinShares weekly inflows report",
        event_key_numbers=["$1.2B"],
        event_related_projects=["CoinShares", "BlackRock"],
    )
    assert result is None


@pytest.mark.asyncio
async def test_outside_24h_window_returns_none(temp_db: Settings) -> None:
    now = datetime.now(UTC)
    await _seed_signal(
        ticker="BTC",
        direction="long",
        sent_at=now - timedelta(hours=30),  # outside 24h
        event_subject="Same event subject",
        key_numbers=["$1B"],
        related_projects=["X"],
    )

    result = await find_recent_duplicate(
        ticker="BTC",
        direction="long",
        event_subject="Same event subject",
        event_key_numbers=["$1B"],
        event_related_projects=["X"],
    )
    assert result is None


@pytest.mark.asyncio
async def test_empty_event_subject_returns_none(temp_db: Settings) -> None:
    """Legacy v0.1 rows have NULL event_subject; can't dedup against them."""
    result = await find_recent_duplicate(
        ticker="BTC",
        direction="long",
        event_subject="",  # empty current
        event_key_numbers=["$1B"],
        event_related_projects=["X"],
    )
    assert result is None


@pytest.mark.asyncio
async def test_subject_match_but_no_number_or_project_overlap_returns_none(
    temp_db: Settings,
) -> None:
    """Subject tokens overlap but key_numbers and projects are entirely
    different — these are not the same event."""
    now = datetime.now(UTC)
    await _seed_signal(
        ticker="BTC",
        direction="long",
        sent_at=now - timedelta(hours=1),
        event_subject="ETF approval news",
        key_numbers=["$5B"],
        related_projects=["BlackRock"],
    )
    result = await find_recent_duplicate(
        ticker="BTC",
        direction="long",
        event_subject="ETF approval news",  # subject matches
        event_key_numbers=["$0.1M"],         # but numbers don't
        event_related_projects=["Grayscale"],  # and projects don't
    )
    assert result is None
