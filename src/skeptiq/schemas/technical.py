from typing import Literal

from pydantic import BaseModel, Field

RsiState = Literal["oversold", "neutral", "overbought"]


class TechnicalContext(BaseModel):
    ticker: str
    price: float = Field(gt=0)
    rsi_14: float = Field(ge=0.0, le=100.0)
    rsi_state: RsiState
    volume_spike: bool
    above_ema20: bool
    change_24h_pct: float
    volume_ratio: float = Field(
        gt=0,
        description="current_volume / avg(last 20). volume_spike = ratio > 2.0.",
    )


def classify_rsi(rsi: float) -> RsiState:
    if rsi < 30:
        return "oversold"
    if rsi > 70:
        return "overbought"
    return "neutral"
