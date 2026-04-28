from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from skeptiq.schemas.analysis import ImpactMagnitude, TimeHorizon
from skeptiq.schemas.technical import TechnicalContext

Direction = Literal["long", "short"]
TechnicalAlignment = Literal["confirms", "neutral", "contradicts"]


class Recommendation(BaseModel):
    ticker: str
    direction: Direction
    confidence: float = Field(ge=0.0, le=1.0)
    impact: ImpactMagnitude
    horizon: TimeHorizon
    summary: str
    directional_arguments: list[str] = Field(
        description="Bulletized arguments supporting the directional call. "
        "Rendered as 'Why bullish' for long, 'Why bearish' for short.",
    )
    counter_signals: list[str] = Field(min_length=1)
    technical_context: TechnicalContext
    technical_alignment: TechnicalAlignment
    source_url: str
    source_name: str
    detected_at: datetime
