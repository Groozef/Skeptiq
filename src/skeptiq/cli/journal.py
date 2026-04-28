"""`skeptiq journal-skeleton` — append PENDING entries for new DB signals.
`skeptiq journal-sync` — refresh outcome blocks from DB hit-rate columns.

Journal entries are matched to DB rows via an HTML-comment marker injected
on creation:
  <!-- skeptiq:db_id=N sent_at=YYYY-MM-DDTHH:MM:SSZ -->

Pre-existing manual entries (#001, #002) lack the marker and are skipped by
sync — their outcomes are tracked manually in those blocks.
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from skeptiq.core.config import get_settings
from skeptiq.core.db import dispose_engine, init_db, session_scope
from skeptiq.core.models import Analysis, IngestedItem
from skeptiq.core.models import Recommendation as RecommendationORM

JOURNAL_PATH = Path("SIGNALS_JOURNAL.md")

_HEADER_RE = re.compile(r"^## #(\d{3}) — ", re.MULTILINE)
_DB_MARKER_RE = re.compile(
    r"<!--\s*skeptiq:db_id=(\d+)\s+sent_at=([^\s>]+)\s*-->"
)
_OUTCOME_BLOCK_RE = re.compile(
    r"<!--\s*outcome-block id=(\d{3}) start\s*-->.*?<!--\s*outcome-block end\s*-->",
    re.DOTALL,
)
_SENT_AT_LINE_RE = re.compile(r"\|\s*Sent \(UTC\)\s*\|\s*([\d\-: ]+?)\s*\|")


def _ensure_journal() -> str:
    if JOURNAL_PATH.exists():
        return JOURNAL_PATH.read_text(encoding="utf-8")
    return "# Skeptiq — Signals Journal\n\n"


def _existing_db_ids(content: str) -> set[int]:
    return {int(m.group(1)) for m in _DB_MARKER_RE.finditer(content)}


def _existing_sent_ats(content: str) -> set[str]:
    """Sent (UTC) strings parsed from any entry (marker or manual).
    Used to dedup pre-existing manual entries that lack DB markers."""
    return {m.group(1).strip() for m in _SENT_AT_LINE_RE.finditer(content)}


def _next_entry_number(content: str) -> int:
    nums = [int(m.group(1)) for m in _HEADER_RE.finditer(content)]
    return (max(nums) + 1) if nums else 1


def _format_entry(
    *,
    entry_num: int,
    rec: RecommendationORM,
    analysis: Analysis,
    item: IngestedItem,
) -> str:
    tc = json.loads(rec.technical_context_json) if rec.technical_context_json else {}
    sent = rec.sent_at.strftime("%Y-%m-%d %H:%M:%S") if rec.sent_at else "?"
    tag = f"{entry_num:03d}"

    def _f(v: float | None, fmt: str = ",.2f", suffix: str = "") -> str:
        if v is None:
            return "—"
        return f"{v:{fmt}}{suffix}"

    confidence_str = (
        f"{(rec.confidence_adjusted or 0):.2f} (base {(rec.base_confidence or 0):.2f})"
    )
    rsi = tc.get("rsi_14")
    above = tc.get("above_ema20")
    spike = tc.get("volume_spike")
    chg = tc.get("change_24h_pct")

    return f"""
## #{tag} — {rec.ticker} {rec.direction.upper()}
<!-- skeptiq:db_id={rec.id} sent_at={rec.sent_at.isoformat() if rec.sent_at else "?"} -->

**Status:** OPEN

| Field | Value |
|---|---|
| Sent (UTC) | {sent} |
| Source | {item.source} |
| Title | {item.title} |
| URL | {item.url} |
| Entry | ${_f(rec.price_at_send)} |
| RSI(14) | {rsi if rsi is None else f"{rsi:.1f}"} |
| Above EMA20 | {"YES" if above else "no"} |
| Volume spike | {"YES" if spike else "no"} |
| 24h change | {chg if chg is None else f"{chg:+.2f}%"} |
| Tech alignment | {rec.technical_alignment} |
| Confidence | {confidence_str} |
| Impact / Horizon | {analysis.impact_magnitude} / {analysis.time_horizon} |
| SL / TP | ${_f(rec.stop_loss)} / ${_f(rec.take_profit)} |
| Invalidation kind | {rec.invalidation_kind} |

### LLM thesis
{analysis.summary}

### Manual review (Claude as trader)
_Pending — ping Claude in chat to fill in this block._

<!-- outcome-block id={tag} start -->
### Outcome (auto-synced from hit-rate tracker)

| Mark | Price | PnL | Notes |
|---|---|---|---|
| +1h | PENDING | — | — |
| +6h | PENDING | — | — |
| +24h | PENDING | — | — |
| TP hit (${_f(rec.take_profit)})? | PENDING | — | — |
| SL hit (${_f(rec.stop_loss)})? | PENDING | — | — |
| Final verdict | PENDING | — | — |
<!-- outcome-block end -->

---
"""


async def run_journal_skeleton() -> int:
    settings = get_settings()
    await init_db(settings)
    try:
        async with session_scope() as session:
            stmt = (
                select(RecommendationORM)
                .options(
                    joinedload(RecommendationORM.analysis).joinedload(Analysis.item)
                )
                .order_by(RecommendationORM.sent_at.asc())
            )
            recs = list((await session.execute(stmt)).scalars().all())
    finally:
        await dispose_engine()

    if not recs:
        print("No recommendations in DB yet.")
        return 0

    content = _ensure_journal()
    existing_ids = _existing_db_ids(content)
    existing_sent_ats = _existing_sent_ats(content)
    new_recs = []
    for r in recs:
        if r.id in existing_ids:
            continue
        sent_str = r.sent_at.strftime("%Y-%m-%d %H:%M:%S") if r.sent_at else ""
        if sent_str and sent_str in existing_sent_ats:
            continue
        new_recs.append(r)

    if not new_recs:
        print(f"Journal already up to date ({len(recs)} signals in DB, all logged).")
        return 0

    next_num = _next_entry_number(content)
    appended = []
    for rec in new_recs:
        entry = _format_entry(
            entry_num=next_num,
            rec=rec,
            analysis=rec.analysis,
            item=rec.analysis.item,
        )
        content = content.rstrip() + "\n" + entry
        appended.append((next_num, rec.ticker, rec.direction, rec.id))
        next_num += 1

    JOURNAL_PATH.write_text(content, encoding="utf-8")
    print(f"Appended {len(appended)} entries to {JOURNAL_PATH}:")
    for num, ticker, direction, db_id in appended:
        print(f"  #{num:03d}  {ticker} {direction}  (db_id={db_id})")
    return 0


def _sync_outcome_block(
    *,
    tag: str,
    rec: RecommendationORM,
) -> str:
    """Render the outcome-block contents (between markers, exclusive)."""

    def _row(label: str, price: float | None, pct_or_note: str = "—") -> str:
        if price is None:
            return f"| {label} | PENDING | — | — |"
        price_str = f"${price:,.2f}"
        return f"| {label} | {price_str} | {pct_or_note} | — |"

    rows = [
        "### Outcome (auto-synced from hit-rate tracker)",
        "",
        "| Mark | Price | PnL | Notes |",
        "|---|---|---|---|",
        _row("+1h", rec.price_after_1h),
        _row("+6h", rec.price_after_6h),
    ]

    if rec.pct_move_24h is None:
        rows.append(_row("+24h", rec.price_after_24h))
    else:
        rows.append(
            f"| +24h | ${rec.price_after_24h:,.2f} | "
            f"{rec.pct_move_24h:+.2f}% | — |"
        )

    if rec.direction_correct_24h is None:
        verdict = "PENDING"
    elif rec.direction_correct_24h:
        verdict = "WIN (direction correct at +24h)"
    else:
        verdict = "LOSS (direction wrong at +24h)"

    tp_label = (
        f"TP hit (${rec.take_profit:,.2f})?"
        if rec.take_profit is not None
        else "TP hit?"
    )
    sl_label = (
        f"SL hit (${rec.stop_loss:,.2f})?"
        if rec.stop_loss is not None
        else "SL hit?"
    )
    rows.append(f"| {tp_label} | (manual check) | — | — |")
    rows.append(f"| {sl_label} | (manual check) | — | — |")
    rows.append(f"| Final verdict | {verdict} | — | — |")

    body = "\n".join(rows)
    return f"<!-- outcome-block id={tag} start -->\n{body}\n<!-- outcome-block end -->"


async def run_journal_sync() -> int:
    if not JOURNAL_PATH.exists():
        print(f"{JOURNAL_PATH} does not exist; nothing to sync.")
        return 0

    settings = get_settings()
    await init_db(settings)
    try:
        async with session_scope() as session:
            recs_q = await session.execute(select(RecommendationORM))
            by_id = {r.id: r for r in recs_q.scalars().all()}
    finally:
        await dispose_engine()

    content = JOURNAL_PATH.read_text(encoding="utf-8")
    db_id_for_tag: dict[str, int] = {}

    # Walk each entry header to map tag -> db_id (via the marker that follows).
    for header_match in _HEADER_RE.finditer(content):
        tag = header_match.group(1)
        # Search for the db marker in a small window after the header.
        window = content[header_match.start() : header_match.start() + 600]
        marker = _DB_MARKER_RE.search(window)
        if marker:
            db_id_for_tag[tag] = int(marker.group(1))

    if not db_id_for_tag:
        print("No auto-synced entries found in journal "
              "(only manual entries — no markers).")
        return 0

    updated = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal updated
        tag = match.group(1)
        db_id = db_id_for_tag.get(tag)
        if db_id is None or db_id not in by_id:
            return match.group(0)
        new_block = _sync_outcome_block(tag=tag, rec=by_id[db_id])
        updated += 1
        return new_block

    new_content = _OUTCOME_BLOCK_RE.sub(_replace, content)
    JOURNAL_PATH.write_text(new_content, encoding="utf-8")
    print(f"Synced {updated} outcome blocks from DB ({datetime.now(UTC).isoformat()}).")
    return 0
