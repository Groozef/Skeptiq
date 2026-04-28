import json
from datetime import UTC, datetime

from skeptiq.core.config import Settings
from skeptiq.core.db import session_scope
from skeptiq.core.logging import get_logger
from skeptiq.core.models import IngestedItem
from skeptiq.core.models import Recommendation as RecommendationORM
from skeptiq.market.binance import BinanceClient
from skeptiq.market.indicators import (
    compute_invalidation_level,
    compute_technical_context,
)
from skeptiq.recommender.dedup import find_recent_duplicate
from skeptiq.schemas import (
    IMPACT_ORDER,
    CounterSignal,
    Direction,
    NewsAnalysis,
    Recommendation,
    TechnicalAlignment,
    TechnicalContext,
)

log = get_logger(__name__)

# Penalty/bonus weights for confidence calibration. See adjust_confidence
# for the reasoning behind each.
PENALTY_ALIGNMENT_NEUTRAL = 0.08
PENALTY_ALIGNMENT_CONTRADICTS = 0.15
BONUS_ALIGNMENT_CONFIRMS = 0.05
PENALTY_RSI_CONFLICT = 0.10
RSI_CONFLICT_LONG_THRESHOLD = 65.0     # buying when RSI already > 65
RSI_CONFLICT_SHORT_THRESHOLD = 35.0    # shorting when RSI already < 35
CONFIDENCE_CAP = 0.95
# Pre-fetch guard: if the LLM's raw confidence is so low that even with the
# maximum possible bonus we'd still be below MIN_CONFIDENCE, skip Binance.
MAX_POSSIBLE_BONUS = BONUS_ALIGNMENT_CONFIRMS

# Take-profit distance is a fixed multiple of the stop-loss distance.
# 2.0 = 1:2 risk-reward (lose 1 unit on SL, win 2 units on TP).
TAKE_PROFIT_RR_MULTIPLE = 2.0

# Counter-signal severity → confidence penalty (in confidence-point units, i.e.
# 0.07 = 7pp). Notatki #2 calibration: minor/-2, moderate/-4, strong/-7, critical/-12.
COUNTER_PENALTY: dict[str, float] = {
    "minor": 0.02,
    "moderate": 0.04,
    "strong": 0.07,
    "critical": 0.12,
}
# If the SUM of counter-signal penalties exceeds this threshold, drop the
# recommendation entirely — the LLM is signalling that its own counter-args
# overwhelm its directional thesis.
COUNTER_TOTAL_DROP_THRESHOLD = 0.15


def compute_stop_loss_take_profit(
    *,
    direction: Direction,
    entry: float,
    invalidation_level: float,
) -> tuple[float, float]:
    """SL = invalidation level (the thesis is mechanically dead beyond it).
    TP = entry +/- 2 × |entry - SL| (fixed 1:2 R:R)."""
    risk = abs(entry - invalidation_level)
    if direction == "long":
        return invalidation_level, entry + TAKE_PROFIT_RR_MULTIPLE * risk
    return invalidation_level, entry - TAKE_PROFIT_RR_MULTIPLE * risk


def adjust_confidence(
    base: float,
    *,
    direction: Direction,
    alignment: TechnicalAlignment,
    rsi: float,
    counter_signals: list[CounterSignal] | None = None,
) -> tuple[float, list[str], bool]:
    """Apply technical-conflict penalties / agreement bonuses / counter-signal
    severity penalties to the LLM's raw confidence.

    Returns (adjusted_confidence, audit_trail, drop_flag).

    drop_flag is True when the sum of counter-signal penalties alone exceeds
    COUNTER_TOTAL_DROP_THRESHOLD (default 0.15) — the LLM is essentially
    saying its own caveats outweigh its directional thesis.

    Reasoning behind each component:
    - alignment=neutral: tech context didn't confirm the directional thesis,
      so we have one fewer corroborating signal than if it had.
    - alignment=contradicts: tech context actively argues against the thesis;
      the LLM didn't have access to it, so we discount harder.
    - alignment=confirms: small bonus, capped at 0.95 to avoid false certainty.
    - RSI conflict: shorting at RSI<35 (near-oversold) or longing at RSI>65
      (near-overbought) means we're entering against the local technical
      reflex, which historically takes a few bars to play out.
    - counter-signal severities: minor/moderate/strong/critical map to
      0.02/0.04/0.07/0.12 penalty each; sum aggregates.
    """
    adjusted = base
    reasons: list[str] = []

    if alignment == "neutral":
        adjusted -= PENALTY_ALIGNMENT_NEUTRAL
        reasons.append(f"alignment_neutral_-{PENALTY_ALIGNMENT_NEUTRAL:.2f}")
    elif alignment == "contradicts":
        adjusted -= PENALTY_ALIGNMENT_CONTRADICTS
        reasons.append(f"alignment_contradicts_-{PENALTY_ALIGNMENT_CONTRADICTS:.2f}")
    elif alignment == "confirms":
        adjusted += BONUS_ALIGNMENT_CONFIRMS
        reasons.append(f"alignment_confirms_+{BONUS_ALIGNMENT_CONFIRMS:.2f}")

    if direction == "short" and rsi < RSI_CONFLICT_SHORT_THRESHOLD:
        adjusted -= PENALTY_RSI_CONFLICT
        reasons.append(f"rsi_oversold_for_short_-{PENALTY_RSI_CONFLICT:.2f}")
    elif direction == "long" and rsi > RSI_CONFLICT_LONG_THRESHOLD:
        adjusted -= PENALTY_RSI_CONFLICT
        reasons.append(f"rsi_overbought_for_long_-{PENALTY_RSI_CONFLICT:.2f}")

    counter_total = 0.0
    for cs in counter_signals or []:
        penalty = COUNTER_PENALTY.get(cs.severity, 0.0)
        if penalty > 0:
            adjusted -= penalty
            reasons.append(f"counter_{cs.severity}_-{penalty:.2f}")
            counter_total += penalty

    drop = counter_total >= COUNTER_TOTAL_DROP_THRESHOLD
    if drop:
        reasons.append(f"counter_total_drop_-{counter_total:.2f}")

    return max(0.0, min(CONFIDENCE_CAP, adjusted)), reasons, drop


def adjust_confidence_legacy_unchecked(
    base: float,
    *,
    direction: Direction,
    alignment: TechnicalAlignment,
    rsi: float,
) -> tuple[float, list[str]]:
    """Two-tuple wrapper for older callers that haven't migrated to the
    drop-flag form. Counter-signal penalties are NOT applied here; new code
    should use adjust_confidence() with counter_signals=."""
    adjusted, reasons, _drop = adjust_confidence(
        base, direction=direction, alignment=alignment, rsi=rsi,
    )
    return adjusted, reasons


def passes_pre_filter(analysis: NewsAnalysis, settings: Settings) -> bool:
    """Cheap checks that don't need market data — run BEFORE Binance fetch."""
    if not analysis.is_relevant:
        return False
    if analysis.sentiment == "neutral":
        return False
    if not (set(analysis.affected_tickers) & settings.watchlist_set):
        return False
    if IMPACT_ORDER[analysis.impact_magnitude] < IMPACT_ORDER[settings.min_impact]:
        return False
    # If even the best-case bonus can't bring this above the threshold, bail.
    return analysis.confidence + MAX_POSSIBLE_BONUS >= settings.min_confidence


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


# Backwards-compat for tests that still import passes_filter.
passes_filter = passes_pre_filter


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
        if not passes_pre_filter(analysis, self._settings):
            log.debug(
                "recommendation_pre_filter_dropped",
                item_id=item.id,
                relevant=analysis.is_relevant,
                sentiment=analysis.sentiment,
                impact=analysis.impact_magnitude,
                base_confidence=round(analysis.confidence, 2),
                tickers=analysis.affected_tickers,
            )
            return []

        tickers = sorted(set(analysis.affected_tickers) & self._settings.watchlist_set)
        direction = direction_from_sentiment(analysis.sentiment)
        detected_at = datetime.now(UTC)

        recs: list[Recommendation] = []
        for ticker in tickers:
            # Event-level dedup: another article about the same event already
            # produced a Recommendation for this ticker in the last 24h.
            dedup = await find_recent_duplicate(
                ticker=ticker,
                direction=direction,
                event_subject=analysis.event_subject,
                event_key_numbers=list(analysis.event_key_numbers),
                event_related_projects=list(analysis.event_related_projects),
            )
            if dedup is not None:
                kind, prev_id = dedup
                log.info(
                    "recommendation_deduplicated",
                    ticker=ticker,
                    direction=direction,
                    kind=kind,
                    prev_recommendation_id=prev_id,
                    item_id=item.id,
                )
                continue

            try:
                klines = await self._binance.fetch_klines(ticker)
                tc = compute_technical_context(ticker, klines)
                invalidation_level, invalidation_kind = compute_invalidation_level(
                    direction, klines
                )
            except Exception as exc:
                log.warning(
                    "tech_context_failed",
                    ticker=ticker,
                    error=str(exc),
                )
                continue

            alignment = technical_alignment(direction, tc)
            adjusted, adjustments, drop = adjust_confidence(
                analysis.confidence,
                direction=direction,
                alignment=alignment,
                rsi=tc.rsi_14,
                counter_signals=list(analysis.counter_signals),
            )

            if drop:
                log.info(
                    "recommendation_counter_overload_dropped",
                    item_id=item.id,
                    ticker=ticker,
                    base=round(analysis.confidence, 2),
                    adjustments=adjustments,
                )
                continue

            if adjusted < self._settings.min_confidence:
                log.info(
                    "recommendation_post_adjust_dropped",
                    item_id=item.id,
                    ticker=ticker,
                    base=round(analysis.confidence, 2),
                    adjusted=round(adjusted, 2),
                    min_required=self._settings.min_confidence,
                    alignment=alignment,
                    rsi=round(tc.rsi_14, 1),
                    adjustments=adjustments,
                )
                continue

            stop_loss, take_profit = compute_stop_loss_take_profit(
                direction=direction,
                entry=tc.price,
                invalidation_level=invalidation_level,
            )

            recs.append(
                Recommendation(
                    ticker=ticker,
                    direction=direction,
                    confidence=adjusted,
                    base_confidence=analysis.confidence,
                    confidence_adjustments=adjustments,
                    impact=analysis.impact_magnitude,
                    horizon=analysis.time_horizon,
                    summary=analysis.summary,
                    directional_arguments=list(analysis.key_points),
                    counter_signals=[cs.text for cs in analysis.counter_signals],
                    technical_context=tc,
                    technical_alignment=alignment,
                    invalidation_level=invalidation_level,
                    invalidation_kind=invalidation_kind,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
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
            base_confidence=recommendation.base_confidence,
            confidence_adjusted=recommendation.confidence,
            confidence_adjustments_json=json.dumps(recommendation.confidence_adjustments),
            invalidation_level=recommendation.invalidation_level,
            invalidation_kind=recommendation.invalidation_kind,
            stop_loss=recommendation.stop_loss,
            take_profit=recommendation.take_profit,
            telegram_message_id=telegram_message_id,
            price_at_send=recommendation.technical_context.price,
        )
        async with session_scope() as session:
            session.add(orm)
            await session.flush()
            rec_id = orm.id
        return rec_id
