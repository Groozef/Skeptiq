import json
from datetime import UTC, datetime, timedelta

from skeptiq.core.config import Settings
from skeptiq.core.db import session_scope
from skeptiq.core.logging import get_logger
from skeptiq.core.models import IngestedItem
from skeptiq.core.models import Recommendation as RecommendationORM
from skeptiq.market.binance import BinanceClient
from skeptiq.market.funding import FundingProvider
from skeptiq.market.funding import alignment_for_direction as funding_alignment
from skeptiq.market.indicators import (
    ATR_MULTIPLE,
    HORIZON_TO_INVALIDATION_INTERVAL,
    compute_invalidation_level,
    compute_technical_context,
)
from skeptiq.market.macro import MacroProvider
from skeptiq.market.macro import alignment_for_direction as macro_alignment
from skeptiq.recommender.dedup import find_recent_duplicate
from skeptiq.recommender.subject import detect_subject
from skeptiq.schemas import (
    IMPACT_ORDER,
    CounterSignal,
    Direction,
    NewsAnalysis,
    NewsClass,
    Recommendation,
    TechnicalAlignment,
    TechnicalContext,
)

log = get_logger(__name__)

# Penalty/bonus weights for confidence calibration. See adjust_confidence
# for the reasoning behind each.
# Notatki-5 changed the middle and contradicts magnitudes; the old single-
# rule alignment logic flagged things confirms based on one factor, so
# notatki suggested softer penalties to match the multi-factor read.
PENALTY_ALIGNMENT_MIXED = 0.0
PENALTY_ALIGNMENT_CONTRADICTS = 0.08  # was 0.15 in v0.2.0
BONUS_ALIGNMENT_CONFIRMS = 0.05
# Backwards-compat alias for any caller still passing "neutral".
PENALTY_ALIGNMENT_NEUTRAL = PENALTY_ALIGNMENT_MIXED
PENALTY_RSI_CONFLICT = 0.10
RSI_CONFLICT_LONG_THRESHOLD = 65.0     # buying when RSI already > 65
RSI_CONFLICT_SHORT_THRESHOLD = 35.0    # shorting when RSI already < 35
CONFIDENCE_CAP = 0.95
# Pre-fetch guard: if the LLM's raw confidence is so low that even with the
# maximum possible bonus we'd still be below MIN_CONFIDENCE, skip Binance.
# v0.4 widened to include impulsive news bonus (+0.05) on top of
# alignment_confirms (+0.05) and critical-impact (+0.10). Hardcoded as
# 0.20 to avoid forward references; matches BONUS_ALIGNMENT_CONFIRMS +
# IMPACT_BONUS["critical"] + BONUS_IMPULSIVE_NEWS below.
MAX_POSSIBLE_BONUS = 0.20

# Take-profit distance is a fixed multiple of the stop-loss distance.
# 2.0 = 1:2 risk-reward (lose 1 unit on SL, win 2 units on TP).
TAKE_PROFIT_RR_MULTIPLE = 2.0

# Counter-signal severity → confidence penalty (in confidence-point units).
# v0.2.1 values were too harsh: 16/16 watchlist candidates over a 39-min run
# got dropped by counter-overload while LLM honestly tagged 3-4 caveats per
# news. v0.3 softens by ~30% across the board.
COUNTER_PENALTY: dict[str, float] = {
    "minor": 0.01,      # was 0.02
    "moderate": 0.03,   # was 0.04
    "strong": 0.05,     # was 0.07
    "critical": 0.10,   # was 0.12
}
# Drop threshold also raised — three "strong" (=15pp) is no longer auto-drop
# unless combined with secondary mention.
COUNTER_TOTAL_DROP_THRESHOLD = 0.20  # was 0.15

# Notatki-3: if the SL distance from entry exceeds this fraction, flag the
# signal as high-risk and apply a -0.05 confidence penalty. Wide SL means
# either tech context is very volatile or the structure level is far —
# either way the trade is more risky than typical.
HIGH_RISK_SL_DISTANCE = 0.05
PENALTY_HIGH_RISK_SL = 0.05

# Secondary-mention penalty (notatki-4). v0.3 lowered from 0.10 → 0.05 — the
# previous magnitude was sole-killer of any borderline signal where the
# watchlist ticker was even slightly secondary to a related project.
PENALTY_SECONDARY_MENTION = 0.05  # was 0.10

# v0.3: macro context — risk-on/risk-off regime from SPX, DXY, VIX. When the
# broader market direction directly contradicts the news-driven signal,
# discount confidence; when it supports, small bonus.
PENALTY_MACRO_CONFLICT = 0.10
BONUS_MACRO_SUPPORT = 0.05

# v0.3: per-ticker funding context. Joining a crowded one-sided trade is late
# entry / squeeze risk; taking the other side of crowded positioning is the
# structural contrarian play.
PENALTY_FUNDING_CONFLICT = 0.05
BONUS_FUNDING_SUPPORT = 0.05

# v0.3: bonus for high-impact news. The intuition is that high-impact events
# (ETF approval, FOMC, hack of top-20 venue) deserve a confidence push because
# the LLM's `impact_magnitude` rubric is conservative — when it labels
# critical/high, the news is genuinely in that tier.
IMPACT_BONUS: dict[str, float] = {
    "low": 0.0,
    "medium": 0.0,
    "high": 0.05,
    "critical": 0.10,
}

# v0.4: news_class — orthogonal magnitude class set by the LLM.
# - impulsive (FOMC surprise, hack, ETF approval): wider stops + small
#   confidence bonus, since the news mechanism produces 3-10% moves and
#   tight ATR x1.5 stops would get noise-stopped before the move plays out.
# - trend (large inflows, treasury moves): current default, ATR x1.5 unchanged.
# - baseline (minor partnerships, opinion, rehashes): expected <1% moves,
#   not actionable with our stop sizing — dropped before sending.
NEWS_CLASS_ATR_MULTIPLIER: dict[str, float] = {
    "impulsive": 1.5,  # widens ATR component of SL by 50% (1.5*1.5 = 2.25 base ATR)
    "trend": 1.0,      # current behavior preserved
    # baseline: dropped in passes_pre_filter, never reaches invalidation calc.
}
BONUS_IMPULSIVE_NEWS = 0.05

# v0.3: per-impact MIN_CONFIDENCE offset. Idea: a high/critical event with
# raw 0.55 confidence is worth a Telegram alert; a low-impact 0.55 is noise.
# Applied as `effective_min = settings.min_confidence + offset`.
#   low:    +0.05 (need 0.65 if base is 0.60)
#   medium:  0.00 (use settings as-is)
#   high:   -0.05 (allow 0.55 to fire if MIN=0.60)
#   critical: -0.10
IMPACT_CONFIDENCE_OFFSET: dict[str, float] = {
    "low": 0.05,
    "medium": 0.0,
    "high": -0.05,
    "critical": -0.10,
}

# Notatki — auto-expire window per horizon. Beyond expires_at, the hit-rate
# tracker writes a final outcome (tp_hit / sl_hit / expired) so signals don't
# stay "open" indefinitely.
HORIZON_EXPIRE_HOURS: dict[str, int] = {
    "immediate": 6,
    "hours": 12,
    "days": 72,
    "weeks": 168,
}


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
    impact: str | None = None,
    news_class: NewsClass | None = None,
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

    if alignment in ("mixed", "neutral"):
        # PENALTY_ALIGNMENT_MIXED is 0 in v0.2.1 — surface the audit entry
        # only if the legacy "neutral" path is hit so old rows are still
        # interpretable.
        if alignment == "neutral":
            adjusted -= PENALTY_ALIGNMENT_NEUTRAL
            reasons.append(f"alignment_neutral_-{PENALTY_ALIGNMENT_NEUTRAL:.2f}")
        else:
            reasons.append("alignment_mixed_+0.00")
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

    if impact is not None:
        bonus = IMPACT_BONUS.get(impact, 0.0)
        if bonus > 0:
            adjusted += bonus
            reasons.append(f"impact_{impact}_+{bonus:.2f}")

    if news_class == "impulsive":
        adjusted += BONUS_IMPULSIVE_NEWS
        reasons.append(f"news_impulsive_+{BONUS_IMPULSIVE_NEWS:.2f}")

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
    # v0.4: baseline-class news doesn't move price enough for ATR-based
    # entries to make sense. Drop before fetching tech context.
    if analysis.news_class == "baseline":
        return False
    # v0.3: per-impact effective min, accounting for max possible bonus.
    effective_min = settings.min_confidence + IMPACT_CONFIDENCE_OFFSET.get(
        analysis.impact_magnitude, 0.0
    )
    return analysis.confidence + MAX_POSSIBLE_BONUS >= effective_min


def direction_from_sentiment(sentiment: str) -> Direction:
    return "long" if sentiment in ("very_bullish", "bullish") else "short"


RSI_NEUTRAL_BAND_LO = 45.0
RSI_NEUTRAL_BAND_HI = 55.0
H24_NEUTRAL_BAND = 0.5  # %


def alignment_score(direction: Direction, tc: TechnicalContext) -> int:
    """Sum of {-1, 0, +1} contributions across 4 factors (notatki-5):

      - RSI direction relative to 50.
      - Price vs EMA20.
      - 24h percent change.
      - Volume spike, with direction inferred from 24h%.

    For a LONG signal, "confirms" means: momentum up (RSI>55), price above
    EMA20, recently rising (24h>+0.5%), and volume spiking on a green day.

    For a SHORT signal, mirrored.

    Score collapses to alignment label:
      score >= +2  -> confirms
      |score| <= 1 -> mixed
      score <= -2  -> contradicts
    """
    score = 0
    rsi = tc.rsi_14
    chg = tc.change_24h_pct

    # Helpers depending on direction.
    sign = 1 if direction == "long" else -1

    # 1. RSI vs 50.
    if rsi > RSI_NEUTRAL_BAND_HI:
        score += sign  # momentum-up: +1 for long, -1 for short
    elif rsi < RSI_NEUTRAL_BAND_LO:
        score -= sign

    # 2. Price vs EMA20.
    if tc.above_ema20:
        score += sign
    else:
        score -= sign

    # 3. 24h change.
    if chg > H24_NEUTRAL_BAND:
        score += sign
    elif chg < -H24_NEUTRAL_BAND:
        score -= sign

    # 4. Volume spike, only meaningful with directional 24h candle.
    if tc.volume_spike:
        if chg > 0:
            score += sign
        elif chg < 0:
            score -= sign

    return score


def technical_alignment(direction: Direction, tc: TechnicalContext) -> TechnicalAlignment:
    score = alignment_score(direction, tc)
    if score >= 2:
        return "confirms"
    if score <= -2:
        return "contradicts"
    return "mixed"


# Backwards-compat shims for tests that still call the per-direction helpers.
def technical_alignment_for_long(tc: TechnicalContext) -> TechnicalAlignment:
    return technical_alignment("long", tc)


def technical_alignment_for_short(tc: TechnicalContext) -> TechnicalAlignment:
    return technical_alignment("short", tc)


# Backwards-compat for tests that still import passes_filter.
passes_filter = passes_pre_filter


class RecommendationBuilder:
    def __init__(
        self,
        *,
        settings: Settings,
        binance: BinanceClient,
        macro: MacroProvider | None = None,
        funding: FundingProvider | None = None,
    ) -> None:
        self._settings = settings
        self._binance = binance
        # macro is optional — when None, the macro adjustment is skipped
        # entirely (useful in tests). Production main.py wires a real
        # MacroProvider so signals see SPX/DXY/VIX context.
        self._macro = macro
        # funding is optional — when None, the funding adjustment is
        # skipped. Production main.py wires a real FundingProvider so
        # signals see Binance perp funding rates.
        self._funding = funding

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

            # Subject detection: is this ticker the main subject of the news,
            # or just a passing mention?
            subject_kind, subject_counts = detect_subject(
                ticker=ticker,
                item=item,
                related_projects=list(analysis.event_related_projects),
            )
            if subject_kind == "secondary":
                log.info(
                    "secondary_mention_detected",
                    ticker=ticker,
                    item_id=item.id,
                    counts=subject_counts,
                )

            try:
                # Tech context always on 1h regardless of horizon.
                tech_klines = await self._binance.fetch_klines(ticker, interval="1h")
                tc = compute_technical_context(ticker, tech_klines)

                # Invalidation/SL on the timeframe matching the horizon, so
                # an "hours" signal isn't measured against weekly volatility
                # and a "days" signal isn't trapped inside hourly noise.
                inv_interval = HORIZON_TO_INVALIDATION_INTERVAL.get(
                    analysis.time_horizon, "1h"
                )
                if inv_interval == "1h":
                    inv_klines = tech_klines
                else:
                    inv_klines = await self._binance.fetch_klines(
                        ticker, interval=inv_interval
                    )
                # v0.4: news_class scales the ATR component of the stop.
                # impulsive (x1.5 -> 2.25 base ATR) gives the move room to
                # play out without getting noise-stopped; trend keeps
                # current ATR x1.5 sizing. Swing-low/high paths are
                # untouched — structure stays structure.
                atr_mult = ATR_MULTIPLE * NEWS_CLASS_ATR_MULTIPLIER[
                    analysis.news_class
                ]
                invalidation_level, invalidation_kind = compute_invalidation_level(
                    direction, inv_klines, atr_multiple=atr_mult
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
                impact=analysis.impact_magnitude,
                news_class=analysis.news_class,
            )

            # Notatki-3: wide SL flag.
            sl_distance_pct = abs(invalidation_level - tc.price) / tc.price
            if sl_distance_pct > HIGH_RISK_SL_DISTANCE:
                adjusted = max(0.0, adjusted - PENALTY_HIGH_RISK_SL)
                adjustments.append(
                    f"high_risk_sl_{sl_distance_pct:.1%}_-{PENALTY_HIGH_RISK_SL:.2f}"
                )

            # Notatki-4: secondary-mention penalty applied here so it shows in
            # the same audit trail as alignment / counter-signal adjustments.
            if subject_kind == "secondary":
                adjusted = max(0.0, adjusted - PENALTY_SECONDARY_MENTION)
                adjustments.append(
                    f"secondary_mention_-{PENALTY_SECONDARY_MENTION:.2f}"
                )

            # v0.3: macro regime adjustment.
            if self._macro is not None:
                try:
                    macro_ctx = await self._macro.get_context()
                    m_align = macro_alignment(macro_ctx, direction)
                    if m_align == "conflict":
                        adjusted = max(0.0, adjusted - PENALTY_MACRO_CONFLICT)
                        adjustments.append(
                            f"macro_conflict_score{macro_ctx.score:+d}"
                            f"_-{PENALTY_MACRO_CONFLICT:.2f}"
                        )
                    elif m_align == "support":
                        adjusted = min(CONFIDENCE_CAP, adjusted + BONUS_MACRO_SUPPORT)
                        adjustments.append(
                            f"macro_support_score{macro_ctx.score:+d}"
                            f"_+{BONUS_MACRO_SUPPORT:.2f}"
                        )
                    # neutral / unavailable -> no adjustment
                except Exception as exc:
                    log.warning("macro_adjustment_skipped", error=str(exc))

            # v0.3: funding-rate adjustment per ticker.
            if self._funding is not None:
                try:
                    f_ctx = await self._funding.get_context(ticker)
                    f_align = funding_alignment(f_ctx, direction)
                    if f_align == "conflict":
                        adjusted = max(0.0, adjusted - PENALTY_FUNDING_CONFLICT)
                        rate_pct = (
                            (f_ctx.funding_rate_8h or 0.0) * 100
                        )
                        adjustments.append(
                            f"funding_crowded_{rate_pct:+.3f}%"
                            f"_-{PENALTY_FUNDING_CONFLICT:.2f}"
                        )
                    elif f_align == "support":
                        adjusted = min(CONFIDENCE_CAP, adjusted + BONUS_FUNDING_SUPPORT)
                        rate_pct = (
                            (f_ctx.funding_rate_8h or 0.0) * 100
                        )
                        adjustments.append(
                            f"funding_contrarian_{rate_pct:+.3f}%"
                            f"_+{BONUS_FUNDING_SUPPORT:.2f}"
                        )
                except Exception as exc:
                    log.warning(
                        "funding_adjustment_skipped",
                        ticker=ticker,
                        error=str(exc),
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

            effective_min = self._settings.min_confidence + IMPACT_CONFIDENCE_OFFSET.get(
                analysis.impact_magnitude, 0.0
            )
            if adjusted < effective_min:
                log.info(
                    "recommendation_post_adjust_dropped",
                    item_id=item.id,
                    ticker=ticker,
                    base=round(analysis.confidence, 2),
                    adjusted=round(adjusted, 2),
                    min_required=round(effective_min, 2),
                    impact=analysis.impact_magnitude,
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
        expire_h = HORIZON_EXPIRE_HOURS.get(recommendation.horizon, 24)
        sent_at = recommendation.detected_at or datetime.now(UTC)
        expires_at = sent_at + timedelta(hours=expire_h)
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
            sent_at=sent_at,
            expires_at=expires_at,
        )
        async with session_scope() as session:
            session.add(orm)
            await session.flush()
            rec_id = orm.id
        return rec_id
