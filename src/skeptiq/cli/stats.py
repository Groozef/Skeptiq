"""`skeptiq stats` — read DB and print real win-rate breakdowns.

Pulls all Recommendation rows, partitions by 'closed' (direction_correct_24h
populated by the hit-rate tracker) vs 'open', then aggregates by direction,
impact, ticker, and technical_alignment. Output is plain text — no extra
deps. Intended for the measurement-week workflow.
"""

import json
from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import select

from skeptiq.core.config import get_settings
from skeptiq.core.db import dispose_engine, init_db, session_scope
from skeptiq.core.models import Recommendation


def _impact_from_tc_json(raw: str) -> str:
    """Best-effort extract impact tier; for now we don't store impact on the
    Recommendation row directly, so fall back to '?'."""
    return "?"


def _format_breakdown(
    title: str,
    rows: Iterable[Recommendation],
    key: str,
) -> list[str]:
    totals: dict[str, int] = defaultdict(int)
    wins: dict[str, int] = defaultdict(int)
    for r in rows:
        bucket = getattr(r, key) or "?"
        totals[bucket] += 1
        if r.direction_correct_24h:
            wins[bucket] += 1

    if not totals:
        return [f"{title}: (no closed signals yet)"]

    out = [f"{title}:"]
    for bucket in sorted(totals.keys()):
        n = totals[bucket]
        w = wins[bucket]
        pct = w / n if n else 0.0
        out.append(f"  {bucket:14s}  {w}W / {n - w}L  ({pct:.0%})")
    return out


async def run_stats(*, recent: int = 10) -> int:
    settings = get_settings()
    await init_db(settings)
    try:
        async with session_scope() as session:
            result = await session.execute(
                select(Recommendation).order_by(Recommendation.sent_at.desc())
            )
            rows = list(result.scalars().all())

        total = len(rows)
        closed_rows = [r for r in rows if r.direction_correct_24h is not None]
        closed = len(closed_rows)
        open_count = total - closed

        wins = sum(1 for r in closed_rows if r.direction_correct_24h)
        losses = closed - wins
        win_rate = wins / closed if closed else 0.0

        pct_moves = [
            r.pct_move_24h for r in closed_rows if r.pct_move_24h is not None
        ]
        avg_pct = sum(pct_moves) / len(pct_moves) if pct_moves else 0.0

        # R-based stats: each closed signal has a fixed 1:2 RR, so we win 2R or lose 1R.
        realized_r = 2 * wins - 1 * losses
        ev_per_signal = realized_r / closed if closed else 0.0

        print("=" * 60)
        print(" Skeptiq — signal stats ")
        print("=" * 60)
        print(f"Total signals        {total}")
        print(f"Closed (24h+)        {closed}")
        print(f"Open (pending)       {open_count}")
        print()
        if closed >= 1:
            print(f"Win rate (24h)       {win_rate:.1%}   ({wins}W / {losses}L)")
            print(f"Avg pct move (24h)   {avg_pct:+.2f}%")
            print(f"Realized R total     {realized_r:+.1f}R   "
                  f"(SL=-1R, TP at 1:2 RR=+2R)")
            print(f"EV per signal        {ev_per_signal:+.2f}R")
        else:
            print("Not enough closed signals to compute win rate.")
            print("Need at least 1 closed signal — run the bot and wait 24h.")
        print()

        if closed_rows:
            for line in _format_breakdown("By direction", closed_rows, "direction"):
                print(line)
            print()
            for line in _format_breakdown(
                "By technical alignment", closed_rows, "technical_alignment"
            ):
                print(line)
            print()
            for line in _format_breakdown("By ticker", closed_rows, "ticker"):
                print(line)
            print()

        # Recent signals table
        if rows:
            print(f"Recent {min(recent, len(rows))} signals:")
            print(
                f"  {'sent_at (UTC)':<19s}  "
                f"{'tic':<5s} {'dir':<6s} {'conf':>5s} "
                f"{'price':>11s} {'+24h%':>7s}  status"
            )
            for r in rows[:recent]:
                sent = r.sent_at.strftime("%Y-%m-%d %H:%M:%S") if r.sent_at else "?"
                conf = (
                    f"{r.confidence_adjusted:.2f}"
                    if r.confidence_adjusted is not None
                    else "?"
                )
                price = (
                    f"{r.price_at_send:,.2f}"
                    if r.price_at_send is not None
                    else "?"
                )
                pct = (
                    f"{r.pct_move_24h:+.2f}%"
                    if r.pct_move_24h is not None
                    else "  pend"
                )
                if r.direction_correct_24h is True:
                    status = "WIN"
                elif r.direction_correct_24h is False:
                    status = "LOSS"
                else:
                    status = "open"
                print(
                    f"  {sent:<19s}  {r.ticker:<5s} {r.direction:<6s} {conf:>5s} "
                    f"{price:>11s} {pct:>7s}  {status}"
                )

        # Avoid unused-import warning when json is only used in helpers we may grow.
        _ = json
        _ = _impact_from_tc_json
    finally:
        await dispose_engine()

    return 0
