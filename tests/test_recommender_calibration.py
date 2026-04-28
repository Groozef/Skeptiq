"""adjust_confidence + the new pre-filter behavior introduced in v0.2."""

import pytest

from skeptiq.core.config import Settings
from skeptiq.recommender.builder import (
    BONUS_ALIGNMENT_CONFIRMS,
    PENALTY_ALIGNMENT_CONTRADICTS,
    PENALTY_ALIGNMENT_NEUTRAL,
    PENALTY_RSI_CONFLICT,
    adjust_confidence,
    passes_pre_filter,
)
from skeptiq.schemas import NewsAnalysis


def _analysis(**overrides: object) -> NewsAnalysis:
    base = {
        "is_relevant": True,
        "affected_tickers": ["BTC"],
        "sentiment": "bullish",
        "impact_magnitude": "high",
        "confidence": 0.7,
        "time_horizon": "hours",
        "summary": "x",
        "key_points": ["a", "b"],
        "reasoning": "r " * 5,
        "counter_signals": ["c"],
    }
    base.update(overrides)
    return NewsAnalysis.model_validate(base)


def test_adjust_short_against_oversold_rsi() -> None:
    """Live BTC short reproduction (raw 0.62, alignment=neutral, RSI 32.3)."""
    adjusted, reasons = adjust_confidence(
        0.62, direction="short", alignment="neutral", rsi=32.3
    )
    assert adjusted == pytest.approx(0.62 - PENALTY_ALIGNMENT_NEUTRAL - PENALTY_RSI_CONFLICT)
    assert any("alignment_neutral" in r for r in reasons)
    assert any("rsi_oversold_for_short" in r for r in reasons)


def test_adjust_long_with_confirms_and_healthy_rsi() -> None:
    adjusted, reasons = adjust_confidence(
        0.65, direction="long", alignment="confirms", rsi=55
    )
    assert adjusted == pytest.approx(0.65 + BONUS_ALIGNMENT_CONFIRMS)
    assert reasons == ["alignment_confirms_+0.05"]


def test_adjust_caps_at_0_95() -> None:
    adjusted, _ = adjust_confidence(
        0.95, direction="long", alignment="confirms", rsi=55
    )
    assert adjusted == 0.95


def test_adjust_floors_at_0() -> None:
    adjusted, _ = adjust_confidence(
        0.10, direction="short", alignment="contradicts", rsi=25
    )
    # 0.10 - 0.15 - 0.10 = -0.15 -> clipped to 0.0
    assert adjusted == 0.0


def test_adjust_long_overbought_penalty() -> None:
    adjusted, reasons = adjust_confidence(
        0.70, direction="long", alignment="neutral", rsi=72
    )
    assert adjusted == pytest.approx(0.70 - PENALTY_ALIGNMENT_NEUTRAL - PENALTY_RSI_CONFLICT)
    assert any("rsi_overbought_for_long" in r for r in reasons)


def test_adjust_contradicts_alignment() -> None:
    adjusted, reasons = adjust_confidence(
        0.80, direction="long", alignment="contradicts", rsi=55
    )
    assert adjusted == pytest.approx(0.80 - PENALTY_ALIGNMENT_CONTRADICTS)
    assert any("alignment_contradicts" in r for r in reasons)


def test_pre_filter_admits_borderline_with_max_bonus(settings: Settings) -> None:
    # base 0.56, MIN_CONFIDENCE=0.6: with +0.05 bonus could pass, so admit.
    a = _analysis(confidence=0.56)
    assert passes_pre_filter(a, settings) is True


def test_pre_filter_rejects_below_max_bonus_threshold(settings: Settings) -> None:
    # base 0.50, MIN_CONFIDENCE=0.6: even +0.05 max bonus = 0.55 < 0.6 -> drop.
    a = _analysis(confidence=0.50)
    assert passes_pre_filter(a, settings) is False
