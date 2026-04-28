from datetime import UTC, datetime

from skeptiq.core.config import Settings
from skeptiq.core.db import session_scope
from skeptiq.core.logging import get_logger
from skeptiq.core.models import IngestedItem
from skeptiq.core.models import Recommendation as RecommendationORM
from skeptiq.market.binance import BinanceClient
from skeptiq.market.indicators import compute_technical_context
from skeptiq.schemas import (
    IMPACT_ORDER,
    Direction,
    NewsAnalysis,
    Recommendation,
    TechnicalAlignment,
    TechnicalContext,
)

log = get_logger(__name__)


def passes_filter(analysis: NewsAnalysis, settings: Settings) -> bool:
    if not analysis.is_relevant:
        return False
    if analysis.sentiment == "neutral":
        return False
    if not (set(analysis.affected_tickers) & settings.watchlist_set):
        return False
    if analysis.confidence < settings.min_confidence:
        return False
    if IMPACT_ORDER[analysis.impact_magnitude] < IMPACT_ORDER[settings.min_impact]:
        return False
    return True


def direction_from_sentiment(sentiment: str) -> Direction:
    return "long" if sentiment in ("very_bullish", "bullish") else "short"


def technical_alignment_for_long(tc: TechnicalContext) -> TechnicalAlignment:
    if tc.rsi_14 > 70:
        return "contradicts"
    if tc.rsi_14 < 50 and not tc.above_ema20:
        return "confirms"
    if tc.volume_spike and tc.above_ema20 and tc.rsi_14 <= 65:
        return "confirms"
    return "neutral"


def technical_alignment_for_short(tc: TechnicalContext) -> TechnicalAlignment:
    if tc.rsi_14 < 30:
        return "contradicts"
    if tc.rsi_14 > 50 and tc.above_ema20:
        return "confirms"
    if tc.volume_spike and not tc.above_ema20 and tc.rsi_14 >= 35:
        return "confirms"
    return "neutral"


def technical_alignment(direction: Direction, tc: TechnicalContext) -> TechnicalAlignment:
    if direction == "long":
        return technical_alignment_for_long(tc)
    return technical_alignment_for_short(tc)


class RecommendationBuilder:
    def __init__(self, *, settings: Settings, binance: BinanceClient) -> None:
        self._settings = settings
        self._binance = binance

    async def build(
        self,
        *,
        analysis: NewsAnalysis,
        item: IngestedItem,
    ) -> list[Recommendation]:
        if not passes_filter(analysis, self._settings):
            log.debug(
                "recommendation_filtered_out",
                item_id=item.id,
                relevant=analysis.is_relevant,
                sentiment=analysis.sentiment,
                impact=analysis.impact_magnitude,
                confidence=round(analysis.confidence, 2),
                tickers=analysis.affected_tickers,
            )
            return []

        tickers = sorted(set(analysis.affected_tickers) & self._settings.watchlist_set)
        direction = direction_from_sentiment(analysis.sentiment)
        detected_at = datetime.now(UTC)

        recs: list[Recommendation] = []
        for ticker in tickers:
            try:
                klines = await self._binance.fetch_klines(ticker)
                tc = compute_technical_context(ticker, klines)
            except Exception as exc:
                log.warning(
                    "tech_context_failed",
                    ticker=ticker,
                    error=str(exc),
                )
                continue

            recs.append(
                Recommendation(
                    ticker=ticker,
                    direction=direction,
                    confidence=analysis.confidence,
                    impact=analysis.impact_magnitude,
                    horizon=analysis.time_horizon,
                    summary=analysis.summary,
                    directional_arguments=list(analysis.key_points),
                    counter_signals=list(analysis.counter_signals),
                    technical_context=tc,
                    technical_alignment=technical_alignment(direction, tc),
                    source_url=item.url,
                    source_name=item.source,
                    detected_at=detected_at,
                )
            )

        return recs

    async def persist(
        self,
        *,
        recommendation: Recommendation,
        analysis_id: int,
        telegram_message_id: int | None = None,
    ) -> int:
        orm = RecommendationORM(
            analysis_id=analysis_id,
            ticker=recommendation.ticker,
            direction=recommendation.direction,
            technical_context_json=recommendation.technical_context.model_dump_json(),
            technical_alignment=recommendation.technical_alignment,
            telegram_message_id=telegram_message_id,
            price_at_send=recommendation.technical_context.price,
        )
        async with session_scope() as session:
            session.add(orm)
            await session.flush()
            rec_id = orm.id
        return rec_id
