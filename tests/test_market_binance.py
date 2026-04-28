import json

import httpx
import pytest
import respx

from skeptiq.market.binance import BINANCE_KLINES_URL, BinanceClient


def _kline_row(ts: int, close: float, volume: float = 1.0) -> list[float | int]:
    return [
        ts,
        close - 1.0,
        close + 1.0,
        close - 2.0,
        close,
        volume,
        ts + 3_600_000 - 1,
        0.0,
        0,
        0.0,
        0.0,
        0.0,
    ]


@pytest.mark.asyncio
async def test_fetch_klines_parses_response_and_caches() -> None:
    raw = [_kline_row(i * 3_600_000, 70_000 + i * 10, 1000.0) for i in range(100)]

    async with httpx.AsyncClient() as client, respx.mock(
        assert_all_called=False
    ) as router:
        route = router.get(BINANCE_KLINES_URL).mock(
            return_value=httpx.Response(200, json=raw)
        )
        binance = BinanceClient(http_client=client, cache_ttl_sec=300.0)

        first = await binance.fetch_klines("BTC")
        assert len(first) == 100
        assert first[-1].close == pytest.approx(70_990.0)
        assert first[0].volume == 1000.0

        # Within TTL → cached, no second HTTP call.
        second = await binance.fetch_klines("BTC")
        assert second is first or second == first
        assert route.call_count == 1


@pytest.mark.asyncio
async def test_fetch_klines_propagates_http_errors() -> None:
    async with httpx.AsyncClient() as client, respx.mock(
        assert_all_called=False
    ) as router:
        router.get(BINANCE_KLINES_URL).mock(
            return_value=httpx.Response(429, json={"code": -1003})
        )
        binance = BinanceClient(http_client=client)
        with pytest.raises(httpx.HTTPError):
            await binance.fetch_klines("BTC")
