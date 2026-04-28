import dataclasses
import math

from skeptiq.market.binance import Kline
from skeptiq.market.indicators import compute_technical_context


def _wavy_klines(
    n: int = 100,
    *,
    base: float = 70_000.0,
    amp: float = 200.0,
    drift: float = 0.5,
    period: int = 10,
) -> list[Kline]:
    """Wavy upward-drifting closes so RSI / EMA are well-defined."""
    klines: list[Kline] = []
    for i in range(n):
        c = base + amp * math.sin(2 * math.pi * i / period) + i * drift
        o = c - 1.0
        klines.append(
            Kline(
                open_time_ms=i * 3_600_000,
                open=o,
                high=c + 2.0,
                low=o - 2.0,
                close=c,
                volume=1_000.0,
                close_time_ms=(i + 1) * 3_600_000 - 1,
            )
        )
    return klines


def test_indicators_smoke_returns_well_defined_values() -> None:
    klines = _wavy_klines(100)
    ctx = compute_technical_context("BTC", klines)
    assert ctx.ticker == "BTC"
    assert 0.0 < ctx.rsi_14 < 100.0
    assert ctx.rsi_state in {"oversold", "neutral", "overbought"}
    assert ctx.price > 0
    assert ctx.volume_ratio > 0


def test_indicators_volume_spike_detected() -> None:
    klines = _wavy_klines(100)
    klines[-1] = dataclasses.replace(klines[-1], volume=3_000.0)
    ctx = compute_technical_context("BTC", klines)
    assert ctx.volume_spike is True
    assert ctx.volume_ratio > 2.0


def test_indicators_flat_volume_no_spike() -> None:
    klines = _wavy_klines(100)
    ctx = compute_technical_context("BTC", klines)
    assert ctx.volume_spike is False


def test_indicators_rejects_too_few_klines() -> None:
    klines = _wavy_klines(10)
    try:
        compute_technical_context("BTC", klines)
    except ValueError as exc:
        assert "Need at least" in str(exc)
    else:
        raise AssertionError("expected ValueError")
