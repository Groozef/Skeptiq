"""Lightweight per-key translations for the Telegram message shell.

Static labels (section headers, alignment names, disclaimer) are translated.
LLM-generated prose (summary, key_points, counter_signals, reasoning) is
left in its source language — Claude reasons in English over English news.
A future v0.3 may add a per-user translation layer if multi-user requires it.
"""

from typing import Literal

Language = Literal["en", "ru"]

_LABELS: dict[Language, dict[str, str]] = {
    "en": {
        "long_signal": "LONG signal",
        "short_signal": "SHORT signal",
        "confidence": "Confidence",
        "impact": "Impact",
        "horizon": "Horizon",
        "from_base": "from base",
        "situation": "Situation",
        "why_bullish": "Why bullish",
        "why_bearish": "Why bearish",
        "counter_signals": "Counter-signals",
        "technical_context": "Technical context",
        "price": "Price",
        "volume_spike": "Volume spike",
        "above_ema20": "Above EMA20",
        "alignment": "Alignment",
        "invalid_below": "Invalid below",
        "invalid_above": "Invalid above",
        "stop_loss": "Stop loss",
        "take_profit": "Take profit",
        "rr": "R:R 1:2",
        "detected": "Detected",
        # alignment values
        "align_confirms": "confirms",
        "align_neutral": "neutral",
        "align_contradicts": "contradicts",
        # invalidation kinds
        "kind_swing_low": "swing low",
        "kind_swing_high": "swing high",
        "kind_atr": "ATR×1.5",
        # impact values
        "imp_low": "LOW",
        "imp_medium": "MEDIUM",
        "imp_high": "HIGH",
        "imp_critical": "CRITICAL",
        # horizon values
        "hor_immediate": "immediate",
        "hor_hours": "hours",
        "hor_days": "days",
        "hor_weeks": "weeks",
        # 24h change phrasing
        "h24": "24h",
        "avg_suffix": "avg",
        # disclaimer
        "disclaimer": (
            "Educational/informational only — not investment advice. "
            "Historical patterns don't guarantee future outcomes. "
            "Trade at your own risk."
        ),
    },
    "ru": {
        "long_signal": "LONG сигнал",
        "short_signal": "SHORT сигнал",
        "confidence": "Уверенность",
        "impact": "Сила",
        "horizon": "Горизонт",
        "from_base": "от базы",
        "situation": "Что произошло",
        "why_bullish": "Почему вверх",
        "why_bearish": "Почему вниз",
        "counter_signals": "Контр-аргументы",
        "technical_context": "Тех. контекст",
        "price": "Цена",
        "volume_spike": "Объёмный спайк",
        "above_ema20": "Выше EMA20",
        "alignment": "Согласование",
        "invalid_below": "Тезис мёртв ниже",
        "invalid_above": "Тезис мёртв выше",
        "stop_loss": "Стоп-лосс",
        "take_profit": "Тейк-профит",
        "rr": "R:R 1:2",
        "detected": "Получено",
        "align_confirms": "подтверждает",
        "align_neutral": "нейтрально",
        "align_contradicts": "противоречит",
        "kind_swing_low": "swing low",
        "kind_swing_high": "swing high",
        "kind_atr": "ATR×1.5",
        "imp_low": "НИЗКАЯ",
        "imp_medium": "СРЕДНЯЯ",
        "imp_high": "ВЫСОКАЯ",
        "imp_critical": "КРИТИЧЕСКАЯ",
        "hor_immediate": "немедленно",
        "hor_hours": "часы",
        "hor_days": "дни",
        "hor_weeks": "недели",
        "h24": "24ч",
        "avg_suffix": "ср.",
        "disclaimer": (
            "Образовательная информация, не инвестиционная рекомендация. "
            "Исторические закономерности не гарантируют будущих результатов. "
            "Решение о сделке — за вами."
        ),
    },
}


def t(language: Language, key: str) -> str:
    """Translate a key. Falls back to English if missing."""
    return _LABELS[language].get(key) or _LABELS["en"].get(key, key)
