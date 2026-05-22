"""Event-level deduplication for the recommender.

Two articles about the same underlying event (e.g. the Kelp DAO exploit and
its $300M recovery plan) produce nearly-identical NewsAnalysis structures
with overlapping `event_subject`, `event_key_numbers`, and
`event_related_projects`. Without dedup the bot fires three signals on the
same news in 10 minutes — sometimes contradicting each other.

This module checks whether a candidate (ticker, direction, event-fingerprint)
matches a recent (within 24h) Recommendation that already covers the same
event for the same ticker.

Returns:
  - None              -> no recent duplicate, candidate is unique
  - ("dup_same_dir", id) -> same ticker, same direction; new signal redundant
  - ("dup_conflict", id) -> same ticker, opposite direction; bot is
                            contradicting itself, drop with a loud log
"""

import json
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select

from skeptiq.core.db import session_scope
from skeptiq.core.logging import get_logger
from skeptiq.core.models import Analysis
from skeptiq.core.models import Recommendation as RecommendationORM
from skeptiq.schemas.recommendation import Direction

log = get_logger(__name__)

DedupKind = Literal["dup_same_dir", "dup_conflict"]
DEDUP_WINDOW_HOURS = 24
SUBJECT_TOKEN_JACCARD_MIN = 0.5
NUMBERS_OR_PROJECTS_JACCARD_MIN = 0.5


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / max(len(a | b), 1)


def _tokens(text: str) -> set[str]:
    """Coarse tokenization: lowercase + drop short tokens like 'a', 'of', 'the'."""
    stop = {"a", "an", "and", "of", "the", "to", "in", "on", "for", "from", "by"}
    return {tok for tok in text.lower().split() if tok and tok not in stop}


def _normalize_set(values: Iterable[str]) -> set[str]:
    return {v.strip().lower() for v in values if v and v.strip()}


async def find_recent_duplicate(
    *,
    ticker: str,
    direction: Direction,
    event_subject: str,
    event_key_numbers: list[str],
    event_related_projects: list[str],
) -> tuple[DedupKind, int] | None:
    """Look for a recent (24h) Recommendation on the same ticker whose
    underlying analysis matches the candidate event-fingerprint."""
    if not event_subject:
        return None  # no fingerprint to compare against

    cutoff = datetime.now(UTC) - timedelta(hours=DEDUP_WINDOW_HOURS)
    cur_subj_tokens = _tokens(event_subject)
    cur_numbers = _normalize_set(event_key_numbers)
    cur_projects = _normalize_set(event_related_projects)

    async with session_scope() as session:
        stmt = (
            select(Analysis, RecommendationORM)
            .join(
                RecommendationORM,
                RecommendationORM.analysis_id == Analysis.id,
            )
            .where(
                RecommendationORM.ticker == ticker,
                Analysis.event_subject.isnot(None),
            )
            .order_by(RecommendationORM.sent_at.desc())
        )
        rows = list((await session.execute(stmt)).all())

    for prev_analysis, prev_rec in rows:
        # Filter by sent_at after we have the row (SQLite naive datetimes — see
        # core/db notes). Skip rows older than 24h.
        sent_at = prev_rec.sent_at
        if sent_at is None:
            continue
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=UTC)
        if sent_at < cutoff:
            continue

        prev_subj_tokens = _tokens(prev_analysis.event_subject or "")
        prev_numbers = _normalize_set(
            json.loads(prev_analysis.event_key_numbers_json or "[]")
        )
        prev_projects = _normalize_set(
            json.loads(prev_analysis.event_related_projects_json or "[]")
        )

        subj_jaccard = _jaccard(cur_subj_tokens, prev_subj_tokens)
        num_jaccard = _jaccard(cur_numbers, prev_numbers)
        proj_jaccard = _jaccard(cur_projects, prev_projects)

        is_dup = subj_jaccard >= SUBJECT_TOKEN_JACCARD_MIN and (
            num_jaccard >= NUMBERS_OR_PROJECTS_JACCARD_MIN
            or proj_jaccard >= NUMBERS_OR_PROJECTS_JACCARD_MIN
        )

        if not is_dup:
            continue

        kind: DedupKind = (
            "dup_same_dir" if prev_rec.direction == direction else "dup_conflict"
        )
        log.info(
            "dedup_match",
            ticker=ticker,
            direction=direction,
            kind=kind,
            prev_rec_id=prev_rec.id,
            prev_event=prev_analysis.event_subject,
            cur_event=event_subject,
            subj_jaccard=round(subj_jaccard, 2),
            num_jaccard=round(num_jaccard, 2),
            proj_jaccard=round(proj_jaccard, 2),
        )
        return (kind, prev_rec.id)

    return None
