from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from skeptiq.core.config import Settings
from skeptiq.core.logging import get_logger

log = get_logger(__name__)


class Base(DeclarativeBase):
    pass


def _add_missing_columns(sync_conn: Any) -> None:
    """Lightweight forward-only migration: ALTER TABLE ADD COLUMN for any
    column declared on an ORM model but missing from the live SQLite table.

    Limitations (acceptable for v0.2):
    - SQLite-only DDL (`ALTER TABLE ADD COLUMN`).
    - Only adds columns; never drops, renames, or changes types.
    - Adds columns as nullable regardless of the ORM's nullable= setting,
      so existing rows can stay NULL. New INSERTs go through SQLAlchemy
      and will satisfy the ORM-level constraints.

    For any non-trivial migration (drop/rename/type change) you will need
    to either accept losing skeptiq.db or pull in alembic.
    """
    inspector = inspect(sync_conn)
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue  # create_all will have made this; nothing to migrate.
        existing = {col["name"] for col in inspector.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing:
                continue
            col_type_sql = col.type.compile(dialect=sync_conn.dialect)
            ddl = (
                f'ALTER TABLE "{table.name}" '
                f'ADD COLUMN "{col.name}" {col_type_sql}'
            )
            sync_conn.exec_driver_sql(ddl)
            log.info(
                "schema_column_added",
                table=table.name,
                column=col.name,
                sql=ddl,
            )


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _build_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
        future=True,
    )


async def init_db(settings: Settings) -> AsyncEngine:
    global _engine, _sessionmaker

    _engine = _build_engine(settings)
    _sessionmaker = async_sessionmaker(
        _engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    # Import ORM models so they attach to Base.metadata before create_all.
    from skeptiq.core import models  # noqa: F401

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)
    return _engine


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("DB not initialized. Call init_db(settings) first.")
    async with _sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
