import json
from datetime import UTC, datetime

from sqlalchemy import select, update

from skeptiq.brain.prompts import SYSTEM_PROMPT
from skeptiq.core.db import session_scope
from skeptiq.core.llm import LlmClient
from skeptiq.core.logging import get_logger
from skeptiq.core.models import Analysis, IngestedItem
from skeptiq.schemas import NewsAnalysis

log = get_logger(__name__)


def _build_user_prompt(item: IngestedItem) -> str:
    return (
        f"Source: {item.source}\n"
        f"URL: {item.url}\n"
        f"Title: {item.title}\n\n"
        f"Body:\n{item.content}"
    )


class NewsAnalyzer:
    def __init__(self, llm: LlmClient) -> None:
        self._llm = llm

    async def fetch_pending(self, limit: int = 20) -> list[IngestedItem]:
        async with session_scope() as session:
            stmt = (
                select(IngestedItem)
                .where(IngestedItem.processed_at.is_(None))
                .order_by(IngestedItem.published_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            items = list(result.scalars().all())
            for item in items:
                session.expunge(item)
        return items

    async def analyze_item(
        self, item: IngestedItem
    ) -> tuple[NewsAnalysis, int]:
        """Run the LLM on one item, persist Analysis, mark item processed.
        Returns (parsed analysis, persisted analysis id)."""
        user_prompt = _build_user_prompt(item)
        result = await self._llm.analyze(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_model=NewsAnalysis,
            max_tokens=1500,
        )
        parsed = result.parsed

        analysis_orm = Analysis(
            item_id=item.id,
            raw_response_json=parsed.model_dump_json(),
            is_relevant=parsed.is_relevant,
            affected_tickers=",".join(parsed.affected_tickers),
            sentiment=parsed.sentiment,
            impact_magnitude=parsed.impact_magnitude,
            confidence=parsed.confidence,
            time_horizon=parsed.time_horizon,
            summary=parsed.summary,
            reasoning=parsed.reasoning,
            key_points_json=json.dumps(parsed.key_points),
            counter_signals_json=json.dumps(
                [cs.model_dump() for cs in parsed.counter_signals]
            ),
            event_subject=parsed.event_subject,
            event_key_numbers_json=json.dumps(parsed.event_key_numbers),
            event_related_projects_json=json.dumps(parsed.event_related_projects),
            model_used=self._llm.model,
            tokens_input=result.tokens_input,
            tokens_output=result.tokens_output,
            cache_read_tokens=result.cache_read_tokens,
            cost_usd=result.cost_usd,
        )

        async with session_scope() as session:
            session.add(analysis_orm)
            await session.flush()  # populate analysis_orm.id
            await session.execute(
                update(IngestedItem)
                .where(IngestedItem.id == item.id)
                .values(processed_at=datetime.now(UTC))
            )
            analysis_id = analysis_orm.id

        log.info(
            "analysis_persisted",
            item_id=item.id,
            analysis_id=analysis_id,
            relevant=parsed.is_relevant,
            sentiment=parsed.sentiment,
            impact=parsed.impact_magnitude,
            confidence=round(parsed.confidence, 2),
            tickers=parsed.affected_tickers,
            cost_usd=round(result.cost_usd, 6),
            cache_read_tokens=result.cache_read_tokens,
        )

        return parsed, analysis_id
