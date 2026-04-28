from datetime import UTC, datetime

import feedparser
import httpx
import pytest
import respx
from sqlalchemy import select

from skeptiq.core.config import Settings
from skeptiq.core.db import session_scope
from skeptiq.core.models import IngestedItem
from skeptiq.ingestors.rss import RssFeedConfig, RssIngestor, _entry_datetime, _hash

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>T</title><link>http://x</link><description>d</description>
<item>
  <title>BTC ETF approved</title>
  <link>https://example.com/article-1</link>
  <guid>guid-1</guid>
  <pubDate>Mon, 28 Apr 2026 10:00:00 GMT</pubDate>
  <description>SEC approved spot BTC ETF.</description>
</item>
<item>
  <title>ETH upgrade live</title>
  <link>https://example.com/article-2</link>
  <guid>guid-2</guid>
  <pubDate>Mon, 28 Apr 2026 11:00:00 GMT</pubDate>
  <description>ETH upgrade activated successfully.</description>
</item>
</channel></rss>"""


def test_entry_datetime_parses_pubdate() -> None:
    parsed = feedparser.parse(SAMPLE_RSS)
    dt = _entry_datetime(parsed.entries[0])
    assert dt == datetime(2026, 4, 28, 10, 0, 0, tzinfo=UTC)


def test_hash_is_stable() -> None:
    assert _hash("a||b") == _hash("a||b")
    assert _hash("a||b") != _hash("a||c")


@pytest.mark.asyncio
async def test_rss_ingestor_fetch_and_dedup(temp_db: Settings) -> None:
    feed = RssFeedConfig(name="testfeed", url="https://feed.test/rss")

    async with httpx.AsyncClient() as client, respx.mock(
        assert_all_called=False
    ) as router:
        router.get("https://feed.test/rss").mock(
            return_value=httpx.Response(200, content=SAMPLE_RSS.encode("utf-8"))
        )
        ing = RssIngestor(feed=feed, poll_interval_sec=60, http_client=client)

        items = await ing.fetch_once()
        assert len(items) == 2
        assert items[0].external_id == "guid-1"
        assert items[0].source == "testfeed"
        assert items[0].title.startswith("BTC")

        # Run cycle twice — second cycle should insert 0 new rows due to dedup.
        await ing._cycle()
        await ing._cycle()

    async with session_scope() as session:
        rows = (await session.execute(select(IngestedItem))).scalars().all()
        assert len(rows) == 2
        sources = {r.source for r in rows}
        assert sources == {"testfeed"}
