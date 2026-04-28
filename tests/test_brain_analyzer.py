from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select

from skeptiq.brain.analyzer import NewsAnalyzer
from skeptiq.core.config import Settings
from skeptiq.core.db import session_scope
from skeptiq.core.llm import LlmCallResult
from skeptiq.core.models import Analysis, IngestedItem
from skeptiq.schemas import NewsAnalysis


class _FakeLlm:
    model = "claude-test-model"

    def __init__(self, payload: NewsAnalysis) -> None:
        self._payload = payload

    async def analyze(self, **_kwargs: Any) -> LlmCallResult[NewsAnalysis]:
        return LlmCallResult(
            parsed=self._payload,
            tokens_input=1500,
            tokens_output=400,
            cache_creation_tokens=200,
            cache_read_tokens=1300,
            cost_usd=0.01164,
        )


@pytest.mark.asyncio
async def test_analyze_item_persists_and_marks_processed(
    temp_db: Settings,
) -> None:
    payload = NewsAnalysis(
        is_relevant=True,
        affected_tickers=["BTC"],
        sentiment="bullish",
        impact_magnitude="high",
        confidence=0.72,
        time_horizon="hours",
        summary="ETF inflows hit $1B.",
        key_points=["Institutional demand confirmed", "Coincides with FOMC"],
        reasoning="Inflows of this size are historically directional. " * 2,
        counter_signals=["Resistance at $73k", "Sell-the-news risk"],
        event_subject="ETF inflow milestone",
        event_key_numbers=["$1B"],
        event_related_projects=[],
    )

    async with session_scope() as session:
        item = IngestedItem(
            source="coindesk",
            external_id="x1",
            url="https://example.com/x",
            title="Big inflow",
            content="...",
            published_at=datetime.now(UTC),
        )
        session.add(item)
        await session.flush()
        item_id = item.id
        session.expunge(item)

    analyzer = NewsAnalyzer(_FakeLlm(payload))  # type: ignore[arg-type]
    parsed, analysis_id = await analyzer.analyze_item(item)

    assert parsed.sentiment == "bullish"
    assert analysis_id > 0

    async with session_scope() as session:
        a = (await session.execute(select(Analysis))).scalar_one()
        assert a.confidence == pytest.approx(0.72)
        assert a.affected_tickers == "BTC"
        assert a.cache_read_tokens == 1300
        assert a.model_used == "claude-test-model"

        refreshed = await session.get(IngestedItem, item_id)
        assert refreshed is not None
        assert refreshed.processed_at is not None
