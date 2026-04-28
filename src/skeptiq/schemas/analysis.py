from typing import Literal

from pydantic import BaseModel, Field

Sentiment = Literal["very_bullish", "bullish", "neutral", "bearish", "very_bearish"]
ImpactMagnitude = Literal["low", "medium", "high", "critical"]
TimeHorizon = Literal["immediate", "hours", "days", "weeks"]

IMPACT_ORDER: dict[ImpactMagnitude, int] = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "critical": 3,
}


class NewsAnalysis(BaseModel):
    is_relevant: bool = Field(
        description="True only if the item concerns crypto markets, tokens, protocols, "
        "crypto-native institutions, or macro events with immediate crypto impact.",
    )
    affected_tickers: list[str] = Field(
        default_factory=list,
        description="Uppercase ticker symbols, no $ prefix, no exchange suffixes. "
        "Empty if no specific token implicated.",
    )
    sentiment: Sentiment = Field(
        description="Directional view. Use 'neutral' aggressively when in doubt.",
    )
    impact_magnitude: ImpactMagnitude = Field(
        description="Strict rubric: critical/high/medium/low. Choose the lower tier when torn.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Calibrated probability the call looks correct in 24h. "
        "Bulk of calls 0.40-0.80.",
    )
    time_horizon: TimeHorizon = Field(
        description="When the price effect, if any, is most likely to play out.",
    )
    summary: str = Field(
        description="1-2 sentences. State what happened. No interpretation.",
    )
    key_points: list[str] = Field(
        min_length=2,
        max_length=5,
        description="2-5 specific bullet points supporting the directional call. "
        "Each must be concrete (cite a fact from the news, a precedent, a mechanism). "
        "These are rendered as the 'Why bullish/bearish' section to the user.",
    )
    reasoning: str = Field(
        description="3-5 sentences. How sentiment AND impact were derived. "
        "Reference the rubric tier used. Cite the strongest evidence.",
    )
    counter_signals: list[str] = Field(
        min_length=1,
        description="At least one specific counter-argument or risk. "
        "Mandatory even for very_bullish/very_bearish. No boilerplate.",
    )
