import asyncio
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import httpx

from skeptiq.core.logging import get_logger
from skeptiq.ingestors.base import BaseIngestor, RawItem

log = get_logger(__name__)

USER_AGENT = "Skeptiq/0.1 (+https://github.com/Groozef/Skeptiq)"


@dataclass(slots=True, kw_only=True, frozen=True)
class RssFeedConfig:
    name: str  # short id, e.g. "coindesk"
    url: str


DEFAULT_FEEDS: tuple[RssFeedConfig, ...] = (
    RssFeedConfig(name="coindesk", url="https://www.coindesk.com/arc/outboundfeeds/rss/"),
    RssFeedConfig(name="cointelegraph", url="https://cointelegraph.com/rss"),
    RssFeedConfig(name="theblock", url="https://www.theblock.co/rss.xml"),
    RssFeedConfig(name="decrypt", url="https://decrypt.co/feed"),
    RssFeedConfig(name="bitcoinmagazine", url="https://bitcoinmagazine.com/.rss/full/"),
)


class RssIngestor(BaseIngestor):
    def __init__(
        self,
        *,
        feed: RssFeedConfig,
        poll_interval_sec: int,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(poll_interval_sec=poll_interval_sec)
        self.name = feed.name
        self._feed = feed
        self._http = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(20.0),
            headers={"User-Agent": USER_AGENT},
        )
        self._owns_http = http_client is None

    async def fetch_once(self) -> list[RawItem]:
        try:
            resp = await self._http.get(self._feed.url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("rss_fetch_failed", source=self.name, error=str(exc))
            return []

        parsed = await asyncio.to_thread(feedparser.parse, resp.content)
        if parsed.bozo and not parsed.entries:
            log.warning(
                "rss_parse_bozo",
                source=self.name,
                error=str(parsed.bozo_exception),
            )
            return []

        items: list[RawItem] = []
        for entry in parsed.entries:
            try:
                items.append(self._entry_to_item(entry))
            except Exception as exc:
                log.debug(
                    "rss_entry_skipped",
                    source=self.name,
                    error=str(exc),
                )
        return items

    def _entry_to_item(self, entry: Any) -> RawItem:
        url = entry.get("link") or ""
        title = (entry.get("title") or "").strip()
        external_id = (
            entry.get("id") or entry.get("guid") or _hash(f"{url}||{title}")
        )

        content = ""
        if entry.get("content"):
            content = entry.content[0].get("value", "") or ""
        if not content:
            content = entry.get("summary", "") or ""
        if not content:
            content = title

        return RawItem(
            source=self.name,
            external_id=str(external_id),
            url=url,
            title=title,
            content=content,
            published_at=_entry_datetime(entry),
        )

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()


def _entry_datetime(entry: Any) -> datetime:
    for key in ("published_parsed", "updated_parsed"):
        st = entry.get(key)
        if st is not None:
            return datetime(*st[:6], tzinfo=UTC)
    for key in ("published", "updated"):
        raw = entry.get(key)
        if raw:
            try:
                dt = parsedate_to_datetime(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                return dt.astimezone(UTC)
            except (TypeError, ValueError):
                continue
    return datetime.now(UTC)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
