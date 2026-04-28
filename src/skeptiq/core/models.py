from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from skeptiq.core.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class IngestedItem(Base):
    __tablename__ = "ingested_items"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_source_external"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str] = mapped_column(String(512))
    url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str] = mapped_column(String(1024))
    content: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    analyses: Mapped[list["Analysis"]] = relationship(back_populates="item")


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("ingested_items.id"),
        index=True,
    )
    raw_response_json: Mapped[str] = mapped_column(Text)
    is_relevant: Mapped[bool] = mapped_column(Boolean)
    affected_tickers: Mapped[str] = mapped_column(String(256))
    sentiment: Mapped[str] = mapped_column(String(32))
    impact_magnitude: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[float] = mapped_column(Float)
    time_horizon: Mapped[str] = mapped_column(String(16))
    summary: Mapped[str] = mapped_column(Text)
    reasoning: Mapped[str] = mapped_column(Text)
    key_points_json: Mapped[str] = mapped_column(Text)
    counter_signals_json: Mapped[str] = mapped_column(Text)
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
    )
    model_used: Mapped[str] = mapped_column(String(64))
    tokens_input: Mapped[int] = mapped_column(Integer, default=0)
    tokens_output: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    item: Mapped[IngestedItem] = relationship(back_populates="analyses")
    recommendations: Mapped[list["Recommendation"]] = relationship(
        back_populates="analysis"
    )


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    analysis_id: Mapped[int] = mapped_column(
        ForeignKey("analyses.id"),
        index=True,
    )
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    direction: Mapped[str] = mapped_column(String(8))
    technical_context_json: Mapped[str] = mapped_column(Text)
    technical_alignment: Mapped[str] = mapped_column(String(16))
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
    )
    telegram_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    # v0.2 hit-rate tracking — left NULL on send, backfilled later.
    price_at_send: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_after_1h: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_after_6h: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_after_24h: Mapped[float | None] = mapped_column(Float, nullable=True)
    pct_move_24h: Mapped[float | None] = mapped_column(Float, nullable=True)
    direction_correct_24h: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )

    analysis: Mapped[Analysis] = relationship(back_populates="recommendations")
