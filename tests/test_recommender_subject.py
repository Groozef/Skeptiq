"""Subject detection: ticker primary vs secondary mention in news article."""

from datetime import UTC, datetime

import pytest

from skeptiq.core.models import IngestedItem
from skeptiq.recommender.subject import detect_subject


def _item(*, title: str, content: str) -> IngestedItem:
    return IngestedItem(
        id=1,
        source="test",
        external_id="x",
        url="http://x",
        title=title,
        content=content,
        published_at=datetime.now(UTC),
    )


def test_primary_when_ticker_is_main_subject() -> None:
    item = _item(
        title="Bitcoin ETF inflows hit $1.2B amid Fed pivot",
        content=(
            "Bitcoin spot ETFs recorded a record $1.2B in inflows on Tuesday. "
            "BTC traded above $76,000 as investors rotated into Bitcoin ahead of "
            "the FOMC. Analysts say Bitcoin's institutional adoption is accelerating."
        ),
    )
    kind, counts = detect_subject(ticker="BTC", item=item, related_projects=[])
    assert kind == "primary"
    assert counts["ticker_BTC"] >= 4  # Bitcoin ×3 + BTC ×1


def test_secondary_when_only_in_title() -> None:
    item = _item(
        title="Aave coordinates DeFi recovery effort",
        content=(
            "The recovery initiative was launched after a $293M exploit at Kelp "
            "DAO. DeFi United is leading the response while affected users wait "
            "for resolution. Industry leaders pledged hundreds of millions."
        ),
    )
    kind, counts = detect_subject(
        ticker="AAVE", item=item, related_projects=["Kelp DAO", "DeFi United"]
    )
    # Title-only mention -> secondary by rule (b).
    assert kind == "secondary"
    assert counts["ticker_AAVE_title"] == 1
    assert counts["ticker_AAVE_body"] == 0


def test_secondary_when_related_project_dominates() -> None:
    """Reproduction of the AAVE long bug: article is really about Kelp DAO,
    Aave is mentioned twice as the coordinator."""
    item = _item(
        title="Aave-Led DeFi United Relief Effort Raises $300M to Cover Kelp Loss",
        content=(
            "Following the Kelp DAO exploit that drained $293M from rsETH "
            "depositors, an industry-wide effort dubbed DeFi United, with Aave "
            "as a coordinating partner, has raised $300M to cover Kelp losses. "
            "Kelp users will be made whole. Kelp's rsETH token had become a key "
            "collateral asset across DeFi. The Kelp DAO team is investigating "
            "the root cause of the exploit."
        ),
    )
    kind, _counts = detect_subject(
        ticker="AAVE",
        item=item,
        related_projects=["Kelp DAO", "DeFi United", "rsETH"],
    )
    # Aave mentioned 2 times; Kelp/Kelp DAO mentioned much more.
    assert kind == "secondary"


def test_primary_when_ticker_dominates_over_related_projects() -> None:
    item = _item(
        title="Ethereum upgrade Pectra activates, raising blob throughput",
        content=(
            "Ethereum's Pectra hard fork went live this morning. Ethereum's "
            "block builders confirmed adoption. The upgrade affects layer-2 "
            "rollups built on Ethereum, including Arbitrum and Optimism. "
            "Ethereum supply remains stable post-merge as ETH burn continues."
        ),
    )
    kind, _ = detect_subject(
        ticker="ETH",
        item=item,
        related_projects=["Arbitrum", "Optimism"],
    )
    assert kind == "primary"


def test_secondary_when_ticker_appears_once_in_body() -> None:
    item = _item(
        title="Solana DeFi protocol launches new product",
        content=(
            "The new yield aggregator promises higher returns. Some users have "
            "compared it to similar offerings on AAVE."
        ),
    )
    kind, counts = detect_subject(ticker="AAVE", item=item, related_projects=[])
    assert kind == "secondary"
    assert counts["ticker_AAVE"] == 1


def test_aliases_count_for_btc() -> None:
    """'Bitcoin' should count as a BTC mention."""
    item = _item(
        title="Bitcoin treasury crosses 9000 BTC at Block",
        content=(
            "Block, Inc. announced that its Bitcoin holdings reached 9,000 BTC "
            "after another quarterly purchase. Block's CEO noted Bitcoin remains "
            "a strategic reserve asset, even as Bitcoin's price has been volatile."
        ),
    )
    kind, _ = detect_subject(ticker="BTC", item=item, related_projects=["Block"])
    # Bitcoin appears 4 times, BTC once = 5 ticker mentions; Block appears 3.
    # Per rule (c) Block is NOT > BTC, so BTC stays primary.
    assert kind == "primary"


@pytest.mark.parametrize(
    "ticker",
    ["BTC", "ETH", "SOL", "AAVE", "LINK", "AVAX", "DOGE", "XRP", "ADA", "MATIC", "UNI"],
)
def test_known_tickers_have_aliases_registered(ticker: str) -> None:
    """Smoke check that the watchlist tickers are all in the alias map."""
    from skeptiq.recommender.subject import _TICKER_ALIASES

    assert ticker in _TICKER_ALIASES
