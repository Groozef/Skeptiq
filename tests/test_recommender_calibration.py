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
        "counter_signals": [{"text": "c", "severity": "minor"}],
        "event_subject": "test event placeholder",
        "event_key_numbers": [],
        "event_related_projects": [],
    }
    base.update(overrides)
    return NewsAnalysis.model_validate(base)


def test_adjust_short_against_oversold_rsi() -> None:
    """Live BTC short reproduction (raw 0.62, alignment=neutral, RSI 32.3)."""
    adjusted, reasons, drop = adjust_confidence(
        0.62, direction="short", alignment="neutral", rsi=32.3
    )
    assert adjusted == pytest.approx(0.62 - PENALTY_ALIGNMENT_NEUTRAL - PENALTY_RSI_CONFLICT)
    assert drop is False
    assert any("alignment_neutral" in r for r in reasons)
    assert any("rsi_oversold_for_short" in r for r in reasons)


def test_adjust_long_with_confirms_and_healthy_rsi() -> None:
    adjusted, reasons, drop = adjust_confidence(
        0.65, direction="long", alignment="confirms", rsi=55
    )
    assert adjusted == pytest.approx(0.65 + BONUS_ALIGNMENT_CONFIRMS)
    assert drop is False
    assert reasons == ["alignment_confirms_+0.05"]


def test_adjust_caps_at_0_95() -> None:
    adjusted, _, _ = adjust_confidence(
        0.95, direction="long", alignment="confirms", rsi=55
    )
    assert adjusted == 0.95


def test_adjust_floors_at_0() -> None:
    adjusted, _, _ = adjust_confidence(
        0.10, direction="short", alignment="contradicts", rsi=25
    )
    # 0.10 - 0.15 - 0.10 = -0.15 -> clipped to 0.0
    assert adjusted == 0.0


def test_adjust_long_overbought_penalty() -> None:
    adjusted, reasons, _ = adjust_confidence(
        0.70, direction="long", alignment="neutral", rsi=72
    )
    assert adjusted == pytest.approx(0.70 - PENALTY_ALIGNMENT_NEUTRAL - PENALTY_RSI_CONFLICT)
    assert any("rsi_overbought_for_long" in r for r in reasons)


def test_adjust_contradicts_alignment() -> None:
    adjusted, reasons, _ = adjust_confidence(
        0.80, direction="long", alignment="contradicts", rsi=55
    )
    assert adjusted == pytest.approx(0.80 - PENALTY_ALIGNMENT_CONTRADICTS)
    assert any("alignment_contradicts" in r for r in reasons)


def test_adjust_with_strong_counter_signal_subtracts_penalty() -> None:
    from skeptiq.schemas import CounterSignal

    cs = [CounterSignal(text="article body is sparse", severity="strong")]
    adjusted, reasons, drop = adjust_confidence(
        0.70,
        direction="long",
        alignment="confirms",
        rsi=55,
        counter_signals=cs,
    )
    # v0.3: 0.70 + 0.05 (confirms) - 0.05 (strong) = 0.70
    assert adjusted == pytest.approx(0.70)
    assert drop is False
    assert any(r == "counter_strong_-0.05" for r in reasons)


def test_adjust_four_strong_counters_triggers_drop() -> None:
    from skeptiq.schemas import CounterSignal

    cs = [
        CounterSignal(text=f"caveat #{i}", severity="strong") for i in range(4)
    ]
    _adjusted, reasons, drop = adjust_confidence(
        0.80,
        direction="long",
        alignment="confirms",
        rsi=55,
        counter_signals=cs,
    )
    # v0.3: four strong = 0.20 = drop threshold (>=).
    assert drop is True
    assert any("counter_total_drop" in r for r in reasons)


def test_adjust_three_strong_just_below_drop_threshold() -> None:
    from skeptiq.schemas import CounterSignal

    cs = [CounterSignal(text=f"c#{i}", severity="strong") for i in range(3)]
    _adjusted, _, drop = adjust_confidence(
        0.70,
        direction="long",
        alignment="confirms",
        rsi=55,
        counter_signals=cs,
    )
    # v0.3: three strong = 0.15 < 0.20 threshold; no drop.
    assert drop is False


def test_pre_filter_admits_borderline_with_max_bonus(settings: Settings) -> None:
    # v0.3: high impact gives -0.05 offset, max bonus 0.15.
    # base 0.40 high: 0.40 + 0.15 = 0.55 >= 0.55 (eff_min for high) -> admit.
    a = _analysis(confidence=0.40, impact_magnitude="high")
    assert passes_pre_filter(a, settings) is True


def test_pre_filter_rejects_below_max_bonus_threshold(settings: Settings) -> None:
    # v0.3: base 0.30 high: 0.30 + 0.15 = 0.45 < 0.55 (eff_min) -> drop.
    a = _analysis(confidence=0.30, impact_magnitude="high")
    assert passes_pre_filter(a, settings) is False
