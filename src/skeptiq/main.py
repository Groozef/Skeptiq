import asyncio
from zoneinfo import ZoneInfo

import httpx

from skeptiq.brain.analyzer import NewsAnalyzer
from skeptiq.core.config import get_settings
from skeptiq.core.db import dispose_engine, init_db
from skeptiq.core.llm import LlmClient
from skeptiq.core.logging import configure_logging, get_logger
from skeptiq.delivery.telegram import TelegramSender
from skeptiq.ingestors.rss import DEFAULT_FEEDS, RssIngestor
from skeptiq.market.binance import BinanceClient
from skeptiq.recommender.builder import RecommendationBuilder

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
                for rec in recs:
                    msg_id: int | None = None
                    try:
                        msg_id = await sender.send(rec)
                    except Exception as exc:
                        log.exception(
                            "telegram_send_failed",
                            ticker=rec.ticker,
                            error=str(exc),
                        )
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
    )

    await init_db(settings)

    tz = ZoneInfo(settings.my_timezone)
    rss_http = httpx.AsyncClient(
        timeout=httpx.Timeout(20.0),
        headers={"User-Agent": "Skeptiq/0.1"},
    )
    binance_http = httpx.AsyncClient(timeout=httpx.Timeout(15.0))

    llm = LlmClient(settings)
    binance = BinanceClient(http_client=binance_http)
    analyzer = NewsAnalyzer(llm)
    builder = RecommendationBuilder(settings=settings, binance=binance)
    sender = TelegramSender(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.my_telegram_chat_id,
        tz=tz,
    )

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
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cli()
