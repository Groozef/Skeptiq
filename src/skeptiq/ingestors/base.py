import abc
import asyncio
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from skeptiq.core.db import session_scope
from skeptiq.core.logging import get_logger
from skeptiq.core.models import IngestedItem

log = get_logger(__name__)


@dataclass(slots=True, kw_only=True)
class RawItem:
    source: str
    external_id: str
    url: str
    title: str
    content: str
    published_at: datetime  # tz-aware UTC


class BaseIngestor(abc.ABC):
    name: str

    def __init__(self, *, poll_interval_sec: int) -> None:
        self.poll_interval_sec = poll_interval_sec

    @abc.abstractmethod
    async def fetch_once(self) -> list[RawItem]:
        """Return all items found in one polling cycle.
        Persistence dedups by UNIQUE(source, external_id), so duplicates
        across cycles are harmless."""

    async def run(self) -> None:
        log.info(
            "ingestor_started",
            name=self.name,
            interval_sec=self.poll_interval_sec,
        )
        while True:
            try:
                await self._cycle()
            except asyncio.CancelledError:
                log.info("ingestor_cancelled", name=self.name)
                raise
            except Exception as exc:
                log.exception(
                    "ingestor_cycle_error",
                    name=self.name,
                    error=str(exc),
                )
            await asyncio.sleep(self.poll_interval_sec)

    async def _cycle(self) -> None:
        items = await self.fetch_once()
        if not items:
            log.debug("ingestor_cycle_empty", name=self.name)
            return

        new_count = 0
        async with session_scope() as session:
            for raw in items:
                stmt = (
                    sqlite_insert(IngestedItem)
                    .values(
                        source=raw.source,
                        external_id=raw.external_id,
                        url=raw.url,
                        title=raw.title,
                        content=raw.content,
                        published_at=raw.published_at,
                    )
                    .on_conflict_do_nothing(
                        index_elements=["source", "external_id"],
                    )
                )
                result = await session.execute(stmt)
                rowcount = getattr(result, "rowcount", 0) or 0
                if rowcount > 0:
                    new_count += 1

        log.info(
            "ingestor_cycle_complete",
            name=self.name,
            seen=len(items),
            new=new_count,
        )

    async def aclose(self) -> None:  # noqa: B027  (default no-op; subclass may override)
        """Override to release client resources (HTTP, etc.)."""
