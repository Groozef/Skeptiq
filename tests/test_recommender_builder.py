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
        "counter_signals": [{"text": "c", "severity": "minor"}],
        "event_subject": "test event placeholder",
        "event_key_numbers": [],
        "event_related_projects": [],
        "news_class": "trend",
    }
    base.update(overrides)
    return NewsAnalysis.model_validate(base)


def _tc(
    rsi: float,
    *,
    above_ema: bool,
    volume_spike: bool,
    ticker: str = "BTC",
    price: float = 70_000.0,
) -> TechnicalContext:
    return TechnicalContext(
        ticker=ticker,
        price=price,
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
    # v0.3: high impact gives -0.05 offset (eff_min=0.55) and max bonus 0.15.
    # base 0.30 + 0.15 = 0.45 < 0.55 -> drop.
    assert passes_filter(_analysis(confidence=0.3), settings) is False


def test_filter_rejects_off_watchlist(settings: Settings) -> None:
    assert passes_filter(_analysis(affected_tickers=["DOGE"]), settings) is False


def test_filter_rejects_low_impact(settings: Settings) -> None:
    assert passes_filter(_analysis(impact_magnitude="low"), settings) is False


def test_direction_from_sentiment() -> None:
    assert direction_from_sentiment("very_bullish") == "long"
    assert direction_from_sentiment("bullish") == "long"
    assert direction_from_sentiment("bearish") == "short"
    assert direction_from_sentiment("very_bearish") == "short"


def test_alignment_long_all_factors_positive_is_confirms() -> None:
    """RSI > 55 + above EMA + 24h up + green-day vol spike: 4 votes for long."""
    tc = _tc(60, above_ema=True, volume_spike=True)
    # default change_24h_pct=1.0 in _tc — positive
    assert technical_alignment_for_long(tc) == "confirms"


def test_alignment_long_all_factors_negative_is_contradicts() -> None:
    """RSI 29, below EMA, 24h −2.4%, red-day spike — the notatki bug repro."""
    from skeptiq.recommender.builder import alignment_score

    tc = TechnicalContext(
        ticker="BTC",
        price=70_000.0,
        rsi_14=29.0,
        rsi_state="oversold",
        volume_spike=True,
        above_ema20=False,
        change_24h_pct=-2.4,
        volume_ratio=2.5,
    )
    assert alignment_score("long", tc) <= -2
    assert technical_alignment_for_long(tc) == "contradicts"


def test_alignment_long_mixed_factors_is_mixed() -> None:
    """RSI 40 below 45, above EMA, +1% (default), no spike: ±1 net = mixed."""
    tc = _tc(40, above_ema=True, volume_spike=False)
    assert technical_alignment_for_long(tc) == "mixed"


def test_alignment_short_mirrors_long_for_oversold_overbought() -> None:
    """RSI 25 + below EMA + 24h −2% + red-day spike — for SHORT this is mostly
    aligned (RSI is the only conflict; the rest agree). v0.2.1 multi-factor
    score: rsi 25 < 45 (+1), below EMA (+1), chg<-0.5 (+1), red spike (+1)
    -> +4 score -> confirms. The "shorting an oversold market" caveat is
    handled separately by PENALTY_RSI_CONFLICT in adjust_confidence."""
    tc = TechnicalContext(
        ticker="BTC",
        price=70_000.0,
        rsi_14=25.0,
        rsi_state="oversold",
        volume_spike=True,
        above_ema20=False,
        change_24h_pct=-2.0,
        volume_ratio=2.5,
    )
    assert technical_alignment_for_short(tc) == "confirms"


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
        "BTC": _tc(60, above_ema=True, volume_spike=True, ticker="BTC", price=70_000.0),
        # ETH context tuned to score `confirms` under multi-factor alignment:
        # rsi 60 (+1), above EMA (+1), 24h +1% (+1), green-day spike (+1) = +4.
        "ETH": _tc(60, above_ema=True, volume_spike=True, ticker="ETH", price=3_500.0),
    }
    invalidations: dict[str, tuple[float, str]] = {
        # 2.1% below for BTC (under 5% high-risk threshold).
        "BTC": (68_500.0, "swing_low"),
        # 4.3% below for ETH.
        "ETH": (3_350.0, "atr"),
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

    # Dedup needs DB; this unit test isolates builder logic, so stub it out.
    async def _no_dedup(**_kw: Any) -> None:
        return None

    monkeypatch.setattr(
        "skeptiq.recommender.builder.find_recent_duplicate", _no_dedup
    )

    from skeptiq.market.binance import BinanceClient

    binance = BinanceClient()
    builder = RecommendationBuilder(settings=settings, binance=binance)

    # Title + body must mention BTC and ETH enough times that subject detection
    # classifies both as primary.
    item = IngestedItem(
        id=1,
        source="coindesk",
        external_id="x",
        url="https://example.com/x",
        title="Bitcoin and Ethereum rally on macro tailwinds",
        content=(
            "Bitcoin and Ethereum both posted strong gains. "
            "BTC traded above $70k while Ethereum cleared $3500. "
            "Analysts expect Bitcoin and ETH to lead the next leg up. "
            "Bitcoin's institutional flows continue to dominate, with Ethereum "
            "tracking closely. BTC dominance held while ETH funding stayed flat."
        ),
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
    assert eth.invalidation_kind == "atr"
    # v0.3: base 0.7 + alignment_confirms +0.05 - counter_minor -0.01
    # + impact_high +0.05 = 0.79.
    # SL distance 2.1% (under 5%), subject = primary -> no further penalty.
    assert btc.confidence == pytest.approx(0.79)
    assert btc.base_confidence == pytest.approx(0.7)
    assert any("alignment_confirms" in adj for adj in btc.confidence_adjustments)

    # SL = invalidation level; TP at 1:2 R:R from entry (70_000)
    btc_entry = btc.technical_context.price
    btc_risk = btc_entry - btc.stop_loss
    btc_reward = btc.take_profit - btc_entry
    assert btc.stop_loss == pytest.approx(68_500.0)
    assert btc_reward == pytest.approx(2 * btc_risk)

    await binance.aclose()
