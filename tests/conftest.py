from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio

from skeptiq.core.config import Settings
from skeptiq.core.db import dispose_engine, init_db


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("MY_TELEGRAM_CHAT_ID", "12345")
    monkeypatch.setenv("WATCHLIST", "BTC,ETH,SOL")
    monkeypatch.setenv("MIN_CONFIDENCE", "0.6")
    monkeypatch.setenv("MIN_IMPACT", "medium")
    monkeypatch.setenv("MY_TIMEZONE", "UTC")
    yield


@pytest.fixture
def settings(env: None) -> Settings:
    return Settings()  # type: ignore[call-arg]


@pytest_asyncio.fixture
async def temp_db(
    env: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[Settings]:
    db_path = tmp_path / "test.db"
    # SQLAlchemy on Windows wants forward slashes in the URL.
    monkeypatch.setenv(
        "DATABASE_URL", f"sqlite+aiosqlite:///{db_path.as_posix()}"
    )
    s = Settings()  # type: ignore[call-arg]
    await init_db(s)
    try:
        yield s
    finally:
        await dispose_engine()
