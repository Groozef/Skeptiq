from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from skeptiq.schemas.analysis import ImpactMagnitude, NewsClass, TimeHorizon
from skeptiq.schemas.technical import TechnicalContext

Direction = Literal["long", "short"]
# v0.2.1: "mixed" replaces "neutral" as the middle category to better describe
# the multi-factor scoring (some factors confirm, some don't). Legacy v0.2.0
# rows in the DB still carry "neutral" — display paths handle both.
TechnicalAlignment = Literal["confirms", "mixed", "contradicts", "neutral"]
InvalidationKind = Literal["swing_low", "swing_high", "atr"]


class Recommendation(BaseModel):
    ticker: str
    direction: Direction
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Calibrated confidence after technical adjustments.",
    )
    base_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Raw confidence from the LLM analysis, before tech adjustments.",
    )
    confidence_adjustments: list[str] = Field(
        description="Audit trail of penalties/bonuses applied to base_confidence "
        "(e.g. 'alignment_neutral_-0.08', 'rsi_oversold_for_short_-0.10').",
    )
    impact: ImpactMagnitude
    horizon: TimeHorizon
    news_class: NewsClass = Field(
        description="Magnitude class set by the LLM analyzer. Affects ATR-multiplier "
        "on the stop-loss distance and adds a small confidence bonus when "
        "impulsive. Only impulsive/trend reach this point — baseline is "
        "dropped earlier in passes_pre_filter.",
    )
    summary: str
    directional_arguments: list[str] = Field(
        description="Bulletized arguments supporting the directional call. "
        "Rendered as 'Why bullish' for long, 'Why bearish' for short.",
    )
    counter_signals: list[str] = Field(min_length=1)
    technical_context: TechnicalContext
    technical_alignment: TechnicalAlignment
    invalidation_level: float = Field(
        gt=0,
        description="Price level that would invalidate the directional thesis. "
        "For longs: lower bound; for shorts: upper bound.",
    )
    invalidation_kind: InvalidationKind = Field(
        description="Which constraint produced the invalidation level: "
        "swing_low/high (price-action) or atr_2_5x (volatility-based).",
    )
    stop_loss: float = Field(
        gt=0,
        description="Suggested stop-loss level (= invalidation_level). "
        "Beyond it, the directional thesis is no longer supported.",
    )
    take_profit: float = Field(
        gt=0,
        description="Suggested take-profit level at fixed 1:2 risk-reward "
        "(distance from entry to TP = 2x distance from entry to SL).",
    )
    source_url: str
    source_name: str
    detected_at: datetime
