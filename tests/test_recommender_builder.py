from datetime import UTC, datetime
from typing import Any

import pytest

from skeptiq.core.config import Settings
from skeptiq.core.models import IngestedItem
from skeptiq.recommender.builder import (
    RecommendationBuilder,
    direction_from_sentiment,
    passes_filter,
    technical_alignment_for_long,
    technical_alignment_for_short,
)
from skeptiq.schemas import NewsAnalysis, TechnicalContext


def _analysis(**overrides: Any) -> NewsAnalysis:
    base: dict[str, Any] = {
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


def _tc(rsi: float, *, above_ema: bool, volume_spike: bool) -> TechnicalContext:
    return TechnicalContext(
        ticker="BTC",
        price=70_000.0,
        rsi_14=rsi,
        rsi_state=("oversold" if rsi < 30 else "overbought" if rsi > 70 else "neutral"),
        volume_spike=volume_spike,
        above_ema20=above_ema,
        change_24h_pct=1.0,
        volume_ratio=2.5 if volume_spike else 0.8,
    )


def test_filter_pass(settings: Settings) -> None:
    assert passes_filter(_analysis(), settings) is True


def test_filter_rejects_neutral_sentiment(settings: Settings) -> None:
    assert passes_filter(_analysis(sentiment="neutral"), settings) is False


def test_filter_rejects_low_confidence(settings: Settings) -> None:
    assert passes_filter(_analysis(confidence=0.4), settings) is False


def test_filter_rejects_off_watchlist(settings: Settings) -> None:
    assert passes_filter(_analysis(affected_tickers=["DOGE"]), settings) is False


def test_filter_rejects_low_impact(settings: Settings) -> None:
    assert passes_filter(_analysis(impact_magnitude="low"), settings) is False


def test_direction_from_sentiment() -> None:
    assert direction_from_sentiment("very_bullish") == "long"
    assert direction_from_sentiment("bullish") == "long"
    assert direction_from_sentiment("bearish") == "short"
    assert direction_from_sentiment("very_bearish") == "short"


def test_alignment_long_overbought_contradicts() -> None:
    assert technical_alignment_for_long(
        _tc(80, above_ema=True, volume_spike=False)
    ) == "contradicts"


def test_alignment_long_room_to_run_confirms() -> None:
    assert technical_alignment_for_long(
        _tc(40, above_ema=False, volume_spike=False)
    ) == "confirms"


def test_alignment_long_uptrend_with_spike_confirms() -> None:
    assert technical_alignment_for_long(
        _tc(60, above_ema=True, volume_spike=True)
    ) == "confirms"


def test_alignment_short_oversold_contradicts() -> None:
    assert technical_alignment_for_short(
        _tc(25, above_ema=False, volume_spike=False)
    ) == "contradicts"


class _FakeBinance:
    def __init__(self, ctx_by_ticker: dict[str, TechnicalContext]) -> None:
        self._ctx = ctx_by_ticker

    async def fetch_klines(self, ticker: str, **_kw: Any) -> list[Any]:
        # The builder doesn't call this directly; it goes through
        # compute_technical_context. We patch builder.compute_technical_context
        # in the test instead.
        raise NotImplementedError


@pytest.mark.asyncio
async def test_build_emits_one_rec_per_watchlist_ticker(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    contexts = {
        "BTC": _tc(60, above_ema=True, volume_spike=True),
        "ETH": _tc(45, above_ema=False, volume_spike=False),
    }
    invalidations = {
        "BTC": (68_500.0, "swing_low"),
        "ETH": (3_100.0, "atr_2_5x"),
    }

    async def _fake_fetch(self: Any, ticker: str, **_kw: Any) -> list[Any]:
        return [object()]  # placeholder; compute_* are patched

    def _fake_compute_tech(ticker: str, _klines: list[Any]) -> TechnicalContext:
        return contexts[ticker]

    def _fake_compute_invalidation(
        direction: str, _klines: list[Any]
    ) -> tuple[float, str]:
        # The harness only runs one direction per build call, so we look up by
        # whichever ticker is in flight via the patched tech-context call order.
        # Simpler: pick BTC then ETH as they're called in sorted order.
        # We track via a side effect.
        ticker = next(iter(_fake_compute_invalidation._queue))
        _fake_compute_invalidation._queue.popleft()
        return invalidations[ticker]

    from collections import deque

    _fake_compute_invalidation._queue = deque(["BTC", "ETH"])  # type: ignore[attr-defined]

    monkeypatch.setattr(
        "skeptiq.market.binance.BinanceClient.fetch_klines", _fake_fetch
    )
    monkeypatch.setattr(
        "skeptiq.recommender.builder.compute_technical_context", _fake_compute_tech
    )
    monkeypatch.setattr(
        "skeptiq.recommender.builder.compute_invalidation_level",
        _fake_compute_invalidation,
    )

    from skeptiq.market.binance import BinanceClient

    binance = BinanceClient()
    builder = RecommendationBuilder(settings=settings, binance=binance)

    item = IngestedItem(
        id=1,
        source="coindesk",
        external_id="x",
        url="https://example.com/x",
        title="t",
        content="c",
        published_at=datetime.now(UTC),
    )
    analysis = _analysis(affected_tickers=["BTC", "ETH", "DOGE"])
    recs = await builder.build(analysis=analysis, item=item)

    assert {r.ticker for r in recs} == {"BTC", "ETH"}
    btc = next(r for r in recs if r.ticker == "BTC")
    eth = next(r for r in recs if r.ticker == "ETH")
    assert btc.direction == "long"
    assert btc.technical_alignment == "confirms"
    assert eth.technical_alignment == "confirms"
    assert btc.directional_arguments == ["a", "b"]
    assert btc.counter_signals == ["c"]
    assert btc.invalidation_level == 68_500.0
    assert btc.invalidation_kind == "swing_low"
    assert eth.invalidation_kind == "atr_2_5x"
    # confirms alignment -> +0.05 bonus (but cap at 0.95). base 0.7 -> 0.75.
    assert btc.confidence == pytest.approx(0.75)
    assert btc.base_confidence == pytest.approx(0.7)
    assert any("alignment_confirms" in adj for adj in btc.confidence_adjustments)

    await binance.aclose()
