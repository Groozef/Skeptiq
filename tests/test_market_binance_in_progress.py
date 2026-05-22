"""Verify BinanceClient drops the in-progress kline (close_time > now)."""

import time

import httpx
import pytest
import respx

from skeptiq.market.binance import BINANCE_KLINES_URL, BinanceClient


def _row(open_time_ms: int, close_time_ms: int, close: float = 70_000.0) -> list:
    return [
        open_time_ms,
        close - 1.0,
        close + 1.0,
        close - 2.0,
        close,
        1_000.0,
        close_time_ms,
        0.0,
        0,
        0.0,
        0.0,
        0.0,
    ]


@pytest.mark.asyncio
async def test_fetch_klines_drops_in_progress_last_bar() -> None:
    now_ms = int(time.time() * 1000)
    closed_close = now_ms - 10  # already closed
    in_progress_close = now_ms + 1_000_000  # 16+ minutes in the future

    raw = [
        _row(now_ms - 7_200_000, now_ms - 3_600_001),  # closed
        _row(now_ms - 3_600_000, closed_close),         # just-closed
        _row(now_ms - 1_000, in_progress_close),        # in-progress
    ]

    async with httpx.AsyncClient() as client, respx.mock(
        assert_all_called=False
    ) as router:
        router.get(BINANCE_KLINES_URL).mock(
            return_value=httpx.Response(200, json=raw)
        )
        binance = BinanceClient(http_client=client)
        klines = await binance.fetch_klines("BTC")

    assert len(klines) == 2  # in-progress dropped
    assert all(k.close_time_ms <= now_ms for k in klines)


@pytest.mark.asyncio
async def test_fetch_kline_at_returns_none_for_in_progress() -> None:
    now_ms = int(time.time() * 1000)
    raw = [_row(now_ms - 1_000, now_ms + 1_000_000)]  # in-progress

    async with httpx.AsyncClient() as client, respx.mock(
        assert_all_called=False
    ) as router:
        router.get(BINANCE_KLINES_URL).mock(
            return_value=httpx.Response(200, json=raw)
        )
        binance = BinanceClient(http_client=client)
        from datetime import UTC, datetime

        result = await binance.fetch_kline_at("BTC", datetime.now(UTC))

    assert result is None


@pytest.mark.asyncio
async def test_fetch_klines_keeps_all_when_all_closed() -> None:
    now_ms = int(time.time() * 1000)
    raw = [
        _row(now_ms - 7_200_000, now_ms - 3_600_001),
        _row(now_ms - 3_600_000, now_ms - 1),
    ]

    async with httpx.AsyncClient() as client, respx.mock(
        assert_all_called=False
    ) as router:
        router.get(BINANCE_KLINES_URL).mock(
            return_value=httpx.Response(200, json=raw)
        )
        binance = BinanceClient(http_client=client)
        klines = await binance.fetch_klines("BTC")

    assert len(klines) == 2  # nothing dropped
