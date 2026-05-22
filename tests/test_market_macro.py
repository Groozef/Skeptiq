"""Smoke tests for macro alignment logic. The actual yfinance fetch is
network-dependent so we test the pure logic here, not the live provider."""

from skeptiq.market.macro import (
    MacroContext,
    _macro_score,
    alignment_for_direction,
)


def test_score_extreme_risk_on() -> None:
    # SPX +1.5%, DXY -0.7%, VIX 18 -> all three vote risk-on
    score = _macro_score(spx_pct=1.5, dxy_pct=-0.7, vix=18.0)
    assert score == 3


def test_score_extreme_risk_off() -> None:
    # SPX -1.5%, DXY +0.7%, VIX 30 -> all three vote risk-off
    score = _macro_score(spx_pct=-1.5, dxy_pct=0.7, vix=30.0)
    assert score == -3


def test_score_neutral_inside_thresholds() -> None:
    score = _macro_score(spx_pct=0.3, dxy_pct=-0.2, vix=22.0)
    assert score == 0


def test_alignment_long_with_strong_risk_on_is_support() -> None:
    macro = MacroContext(
        spx_change_24h_pct=1.5,
        dxy_change_24h_pct=-0.7,
        vix_level=18.0,
        score=3,
        available=True,
    )
    assert alignment_for_direction(macro, "long") == "support"


def test_alignment_long_with_strong_risk_off_is_conflict() -> None:
    macro = MacroContext(
        spx_change_24h_pct=-1.5,
        dxy_change_24h_pct=0.7,
        vix_level=30.0,
        score=-3,
        available=True,
    )
    assert alignment_for_direction(macro, "long") == "conflict"


def test_alignment_short_mirrors_long() -> None:
    risk_on = MacroContext(
        spx_change_24h_pct=1.5, dxy_change_24h_pct=-0.7, vix_level=18.0,
        score=3, available=True,
    )
    risk_off = MacroContext(
        spx_change_24h_pct=-1.5, dxy_change_24h_pct=0.7, vix_level=30.0,
        score=-3, available=True,
    )
    assert alignment_for_direction(risk_on, "short") == "conflict"
    assert alignment_for_direction(risk_off, "short") == "support"


def test_alignment_neutral_score_is_neutral() -> None:
    macro = MacroContext(
        spx_change_24h_pct=0.3, dxy_change_24h_pct=-0.2, vix_level=22.0,
        score=0, available=True,
    )
    assert alignment_for_direction(macro, "long") == "neutral"
    assert alignment_for_direction(macro, "short") == "neutral"


def test_alignment_unavailable_returns_unavailable() -> None:
    macro = MacroContext(
        spx_change_24h_pct=0.0, dxy_change_24h_pct=0.0, vix_level=0.0,
        score=0, available=False,
    )
    assert alignment_for_direction(macro, "long") == "unavailable"
