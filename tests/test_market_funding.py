"""Smoke tests for funding-rate alignment logic."""

import httpx
import pytest
import respx

from skeptiq.market.funding import (
    BINANCE_PREMIUM_URL,
    FundingContext,
    FundingProvider,
    alignment_for_direction,
)


def _ctx(rate: float | None) -> FundingContext:
    return FundingContext(
        ticker="BTC",
        funding_rate_8h=rate,
        next_funding_time_ms=None,
        available=rate is not None,
    )


def test_neutral_when_funding_inside_threshold() -> None:
    # 0.0003 = 0.03% per 8h, well under the 0.0005 trigger.
    ctx = _ctx(0.0003)
    assert alignment_for_direction(ctx, "long") == "neutral"
    assert alignment_for_direction(ctx, "short") == "neutral"


def test_long_into_crowded_long_is_conflict() -> None:
    # 0.001 = 0.1% per 8h, clearly crowded long.
    ctx = _ctx(0.001)
    assert alignment_for_direction(ctx, "long") == "conflict"


def test_short_against_crowded_long_is_support() -> None:
    ctx = _ctx(0.001)
    assert alignment_for_direction(ctx, "short") == "support"


def test_short_into_crowded_short_is_conflict() -> None:
    # Negative funding = shorts paying longs = market crowded short
    ctx = _ctx(-0.001)
    assert alignment_for_direction(ctx, "short") == "conflict"


def test_long_against_crowded_short_is_support() -> None:
    ctx = _ctx(-0.001)
    assert alignment_for_direction(ctx, "long") == "support"


def test_unavailable_returns_unavailable() -> None:
    ctx = _ctx(None)
    assert alignment_for_direction(ctx, "long") == "unavailable"
    assert alignment_for_direction(ctx, "short") == "unavailable"


@pytest.mark.asyncio
async def test_provider_fetches_and_caches() -> None:
    payload = {
        "symbol": "BTCUSDT",
        "lastFundingRate": "0.0008",
        "nextFundingTime": 1700000000000,
    }
    async with httpx.AsyncClient() as client, respx.mock(
        assert_all_called=False
    ) as router:
        route = router.get(BINANCE_PREMIUM_URL).mock(
            return_value=httpx.Response(200, json=payload)
        )
        provider = FundingProvider(http_client=client, cache_ttl_sec=300.0)

        ctx1 = await provider.get_context("BTC")
        ctx2 = await provider.get_context("BTC")  # cached, no second HTTP

        assert ctx1.available is True
        assert ctx1.funding_rate_8h == 0.0008
        assert ctx2.funding_rate_8h == 0.0008
        assert route.call_count == 1


@pytest.mark.asyncio
async def test_provider_handles_unlisted_symbol() -> None:
    async with httpx.AsyncClient() as client, respx.mock(
        assert_all_called=False
    ) as router:
        router.get(BINANCE_PREMIUM_URL).mock(
            return_value=httpx.Response(400, json={"code": -1121})
        )
        provider = FundingProvider(http_client=client)
        ctx = await provider.get_context("UNLISTED")
        assert ctx.available is False
        assert ctx.funding_rate_8h is None
