import argparse
import asyncio
import contextlib
from zoneinfo import ZoneInfo

import httpx

from skeptiq.brain.analyzer import NewsAnalyzer
from skeptiq.cli.journal import run_journal_skeleton, run_journal_sync
from skeptiq.cli.stats import run_stats
from skeptiq.core.config import get_settings
from skeptiq.core.db import dispose_engine, init_db
from skeptiq.core.llm import LlmClient
from skeptiq.core.logging import configure_logging, get_logger
from skeptiq.delivery.telegram import TelegramSender
from skeptiq.ingestors.rss import DEFAULT_FEEDS, RssIngestor
from skeptiq.market.binance import BinanceClient
from skeptiq.market.macro import MacroProvider
from skeptiq.recommender.builder import RecommendationBuilder
from skeptiq.tracking.hit_rate import HitRateTracker

PROCESSOR_INTERVAL_SEC = 5
PENDING_BATCH_SIZE = 10


async def _processor_loop(
    *,
    analyzer: NewsAnalyzer,
    builder: RecommendationBuilder,
    sender: TelegramSender,
) -> None:
    log = get_logger("processor")
    log.info("processor_started")
    while True:
        try:
            items = await analyzer.fetch_pending(limit=PENDING_BATCH_SIZE)
            for item in items:
                analysis, analysis_id = await analyzer.analyze_item(item)
                recs = await builder.build(analysis=analysis, item=item)
                if not recs:
                    continue
                # All recs share an analysis -> one Telegram message,
                # but each rec is persisted separately for hit-rate tracking.
                msg_id: int | None = None
                try:
                    msg_id = await sender.send_grouped(recs)
                except Exception as exc:
                    log.exception(
                        "telegram_send_failed",
                        tickers=[r.ticker for r in recs],
                        error=str(exc),
                    )
                for rec in recs:
                    await builder.persist(
                        recommendation=rec,
                        analysis_id=analysis_id,
                        telegram_message_id=msg_id,
                    )
        except asyncio.CancelledError:
            log.info("processor_cancelled")
            raise
        except Exception as exc:
            log.exception("processor_error", error=str(exc))
        await asyncio.sleep(PROCESSOR_INTERVAL_SEC)


async def run() -> None:
    settings = get_settings()
    configure_logging(settings)
    log = get_logger("main")
    log.info(
        "startup",
        model=settings.llm_model,
        watchlist_size=len(settings.watchlist),
        rss_interval_sec=settings.rss_poll_interval_sec,
        message_language=settings.message_language,
    )

    await init_db(settings)

    tz = ZoneInfo(settings.my_timezone)
    from skeptiq.ingestors.rss import ACCEPT_HEADER, USER_AGENT

    rss_http = httpx.AsyncClient(
        timeout=httpx.Timeout(20.0),
        headers={"User-Agent": USER_AGENT, "Accept": ACCEPT_HEADER},
        follow_redirects=True,
    )
    binance_http = httpx.AsyncClient(timeout=httpx.Timeout(15.0))

    llm = LlmClient(settings)
    binance = BinanceClient(http_client=binance_http)
    macro = MacroProvider()
    analyzer = NewsAnalyzer(llm)
    builder = RecommendationBuilder(settings=settings, binance=binance, macro=macro)
    sender = TelegramSender(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.my_telegram_chat_id,
        tz=tz,
        language=settings.message_language,
    )
    tracker = HitRateTracker(binance=binance)

    ingestors = [
        RssIngestor(
            feed=feed,
            poll_interval_sec=settings.rss_poll_interval_sec,
            http_client=rss_http,
        )
        for feed in DEFAULT_FEEDS
    ]

    try:
        async with asyncio.TaskGroup() as tg:
            for ing in ingestors:
                tg.create_task(ing.run(), name=f"ingestor.{ing.name}")
            tg.create_task(
                _processor_loop(
                    analyzer=analyzer,
                    builder=builder,
                    sender=sender,
                ),
                name="processor",
            )
            tg.create_task(tracker.run(), name="tracker.hit_rate")
    finally:
        log.info("shutdown_starting")
        await sender.aclose()
        await llm.aclose()
        await binance.aclose()
        await rss_http.aclose()
        await binance_http.aclose()
        await dispose_engine()
        log.info("shutdown_complete")


def cli() -> None:
    parser = argparse.ArgumentParser(prog="skeptiq")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("run", help="Run the orchestrator (default if no command given)")

    stats_p = sub.add_parser("stats", help="Print real win-rate stats from the DB")
    stats_p.add_argument(
        "--recent",
        type=int,
        default=10,
        help="How many most-recent signals to include in the table (default: 10)",
    )

    sub.add_parser(
        "journal-skeleton",
        help="Append PENDING entries to SIGNALS_JOURNAL.md for any DB "
        "signals not yet logged",
    )
    sub.add_parser(
        "journal-sync",
        help="Refresh outcome blocks in SIGNALS_JOURNAL.md from DB hit-rate columns",
    )

    args = parser.parse_args()
    cmd = args.command or "run"

    if cmd == "run":
        with contextlib.suppress(KeyboardInterrupt):
            asyncio.run(run())
    elif cmd == "stats":
        raise SystemExit(asyncio.run(run_stats(recent=args.recent)))
    elif cmd == "journal-skeleton":
        raise SystemExit(asyncio.run(run_journal_skeleton()))
    elif cmd == "journal-sync":
        raise SystemExit(asyncio.run(run_journal_sync()))
    else:  # pragma: no cover — argparse will reject unknown subcommands
        parser.error(f"unknown command: {cmd}")


if __name__ == "__main__":
    cli()
