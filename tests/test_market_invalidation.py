import math

from skeptiq.market.binance import Kline
from skeptiq.market.indicators import compute_invalidation_level


def _wavy_klines(
    n: int = 100,
    *,
    base: float = 70_000.0,
    amp: float = 200.0,
    drift: float = 0.5,
    period: int = 10,
) -> list[Kline]:
    klines: list[Kline] = []
    for i in range(n):
        c = base + amp * math.sin(2 * math.pi * i / period) + i * drift
        o = c - 1.0
        klines.append(
            Kline(
                open_time_ms=i * 3_600_000,
                open=o,
                high=c + 5.0,
                low=o - 5.0,
                close=c,
                volume=1_000.0,
                close_time_ms=(i + 1) * 3_600_000 - 1,
            )
        )
    return klines


def test_long_invalidation_below_last_close() -> None:
    klines = _wavy_klines(100)
    last_close = klines[-1].close
    level, kind = compute_invalidation_level("long", klines)
    assert level < last_close
    assert kind in {"swing_low", "atr_2_5x"}


def test_short_invalidation_above_last_close() -> None:
    klines = _wavy_klines(100)
    last_close = klines[-1].close
    level, kind = compute_invalidation_level("short", klines)
    assert level > last_close
    assert kind in {"swing_high", "atr_2_5x"}


def test_kind_is_one_of_three_values_for_normal_data() -> None:
    klines = _wavy_klines(100, amp=200.0)
    _, kind_long = compute_invalidation_level("long", klines)
    _, kind_short = compute_invalidation_level("short", klines)
    assert kind_long in {"swing_low", "atr_2_5x"}
    assert kind_short in {"swing_high", "atr_2_5x"}


def test_invalidation_distance_grows_with_volatility() -> None:
    """Higher amplitude -> larger absolute distance between entry and stop."""
    quiet = _wavy_klines(100, amp=50.0)
    loud = _wavy_klines(100, amp=2_000.0)
    quiet_level, _ = compute_invalidation_level("long", quiet)
    loud_level, _ = compute_invalidation_level("long", loud)
    quiet_dist = quiet[-1].close - quiet_level
    loud_dist = loud[-1].close - loud_level
    assert loud_dist > quiet_dist
