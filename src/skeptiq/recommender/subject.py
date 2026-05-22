"""Subject detection: is the watchlist ticker the *main* subject of the news?

The first AAVE long signal in the v0.2.0 prod run came from an article whose
main subject was Kelp DAO (the protocol that got exploited) — Aave was named
once as the coordinator of the DeFi United relief effort. Going long AAVE on
that news was a category mistake driven by "ticker appeared in headline ->
fire signal" pipeline logic. notatki-4 calls this out.

This module decides per (ticker, news item) whether the ticker is a primary
subject or a secondary mention. Secondary-mention signals get a confidence
penalty (notatki: -0.10) which usually drops them below MIN_CONFIDENCE.
"""

import re
from typing import Literal

from skeptiq.core.models import IngestedItem

# Common case-insensitive aliases for the v0.2 watchlist. Adding here is cheap
# and helps when articles use the protocol name instead of the ticker.
_TICKER_ALIASES: dict[str, tuple[str, ...]] = {
    "BTC": ("btc", "bitcoin"),
    "ETH": ("eth", "ethereum", "ether"),
    "SOL": ("sol", "solana"),
    "LINK": ("link", "chainlink"),
    "AVAX": ("avax", "avalanche"),
    "DOGE": ("doge", "dogecoin"),
    "XRP": ("xrp", "ripple"),
    "ADA": ("ada", "cardano"),
    "DOT": ("dot", "polkadot"),
    "MATIC": ("matic", "polygon"),
    "AAVE": ("aave",),
    "UNI": ("uni", "uniswap"),
}

SubjectKind = Literal["primary", "secondary"]


def _count_word(needle: str, haystack: str) -> int:
    """Case-insensitive word-boundary count, with regex special chars escaped."""
    if not needle or not haystack:
        return 0
    pattern = rf"\b{re.escape(needle.lower())}\b"
    return len(re.findall(pattern, haystack.lower()))


def _count_ticker_mentions(ticker: str, text: str) -> int:
    aliases = _TICKER_ALIASES.get(ticker.upper(), (ticker.lower(),))
    return sum(_count_word(alias, text) for alias in aliases)


def _count_project_mentions(project_name: str, text: str) -> int:
    """Project names from event_related_projects can be multi-word (e.g.
    'DeFi United', 'Kelp DAO'). News articles often use the short form
    ('Kelp') after the first reference, so we count both the full string
    and a word-boundary count of the first token, taking the max."""
    if not project_name or not text:
        return 0
    haystack = text.lower()
    full_count = haystack.count(project_name.lower())
    parts = project_name.lower().split()
    if not parts:
        return full_count
    first = parts[0]
    if len(first) <= 2 or first == project_name.lower():
        return full_count
    short_count = len(re.findall(rf"\b{re.escape(first)}\b", haystack))
    return max(full_count, short_count)


def detect_subject(
    *,
    ticker: str,
    item: IngestedItem,
    related_projects: list[str],
) -> tuple[SubjectKind, dict[str, int]]:
    """Classify the ticker as primary or secondary subject of the article.

    Rules (any of these makes it 'secondary'):
      a) ticker is mentioned <= 1 time across title+body
      b) ticker appears only in title with no body coverage
      c) some entity in related_projects is mentioned strictly more times
         than the ticker

    Returns (kind, debug_counts) where debug_counts holds the integer
    mention counts for caller-side logging.
    """
    title = item.title or ""
    body = item.content or ""
    full = f"{title}\n{body}"

    title_count = _count_ticker_mentions(ticker, title)
    body_count = _count_ticker_mentions(ticker, body)
    total_count = title_count + body_count

    counts: dict[str, int] = {
        f"ticker_{ticker}": total_count,
        f"ticker_{ticker}_title": title_count,
        f"ticker_{ticker}_body": body_count,
    }

    # Rule b: only in headline, never expanded in body.
    if title_count > 0 and body_count == 0:
        return "secondary", counts

    # Rule a: only one mention overall.
    if total_count <= 1:
        return "secondary", counts

    # Rule c: another related project dominates.
    for project in related_projects:
        proj_count = _count_project_mentions(project, full)
        counts[f"project_{project}"] = proj_count
        if proj_count > total_count:
            return "secondary", counts

    return "primary", counts
