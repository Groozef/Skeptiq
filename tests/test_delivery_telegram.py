from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from skeptiq.delivery.telegram import _md, _md_url, format_message
from skeptiq.schemas import Recommendation, TechnicalContext


def test_md_escapes_specials() -> None:
    assert _md("Hello.") == r"Hello\."
    assert _md("a+b-c=d") == r"a\+b\-c\=d"
    assert _md("(x)") == r"\(x\)"


def test_md_url_escapes_only_close_paren_and_backslash() -> None:
    # MarkdownV2: inside (url), only ) and \ are special.
    assert _md_url("https://x?a=1&b=2") == "https://x?a=1&b=2"
    assert _md_url("https://x/(y)") == r"https://x/(y\)"
    assert _md_url(r"https://x\y") == r"https://x\\y"


def _sample_rec() -> Recommendation:
    return Recommendation(
        ticker="BTC",
        direction="long",
        confidence=0.78,
        base_confidence=0.78,
        confidence_adjustments=[],
        impact="high",
        horizon="hours",
        summary="Spot ETF inflow $1.2B.",
        directional_arguments=[
            "Institutional demand confirmed at scale",
            "Coincides with FOMC dovish stance",
        ],
        counter_signals=[
            "Resistance at $73,400 historically rejected",
        ],
        technical_context=TechnicalContext(
            ticker="BTC",
            price=71_240.55,
            rsi_14=58.3,
            rsi_state="neutral",
            volume_spike=True,
            above_ema20=True,
            change_24h_pct=2.4,
            volume_ratio=2.3,
        ),
        technical_alignment="confirms",
        invalidation_level=68_500.00,
        invalidation_kind="swing_low",
        stop_loss=68_500.00,
        take_profit=76_721.65,  # entry + 2 × (entry - SL)
        source_url="https://example.com/x?a=1&b=2",
        source_name="CoinDesk",
        detected_at=datetime(2026, 4, 28, 14, 32, tzinfo=UTC),
    )


def test_format_message_long_renders_expected_sections() -> None:
    msg = format_message(_sample_rec(), tz=ZoneInfo("Asia/Almaty"))
    assert "*LONG signal — BTC*" in msg
    assert "Confidence: 78%" in msg
    assert "Impact: HIGH" in msg
    assert "*Why bullish:*" in msg
    assert "*Counter\\-signals:*" in msg
    assert "BTCUSDT" in msg
    assert "Asia/Almaty" in msg
    # 14:32 UTC -> 19:32 in Asia/Almaty (UTC+5)
    assert "19:32" in msg
    assert r"71,240\.55" in msg
    # invalidation + SL/TP + disclaimer
    assert "Invalid below" in msg
    assert "swing low" in msg
    assert "Stop loss" in msg
    assert "Take profit" in msg
    assert "R:R 1:2" in msg
    assert "Educational/informational" in msg


def test_format_message_short_uses_bearish_label_and_invalid_above() -> None:
    rec = _sample_rec().model_copy(
        update={
            "direction": "short",
            "invalidation_level": 73_500.00,
            "invalidation_kind": "atr_2_5x",
            "stop_loss": 73_500.00,
            "take_profit": 66_721.65,  # 71,240 - 2*(73,500-71,240)
        }
    )
    msg = format_message(rec, tz=ZoneInfo("UTC"))
    assert "*SHORT signal" in msg
    assert "*Why bearish:*" in msg
    assert "Invalid above" in msg
    assert "ATR×2\\.5" in msg


def test_format_message_shows_calibration_delta_when_applied() -> None:
    rec = _sample_rec().model_copy(
        update={
            "confidence": 0.62,
            "base_confidence": 0.70,
            "confidence_adjustments": ["alignment_neutral_-0.08"],
        }
    )
    msg = format_message(rec, tz=ZoneInfo("UTC"))
    assert "Confidence: 62%" in msg
    assert "from base" in msg
    assert "\\-8" in msg


def test_format_message_no_calibration_note_when_no_delta() -> None:
    rec = _sample_rec()  # base==confidence
    msg = format_message(rec, tz=ZoneInfo("UTC"))
    assert "Confidence: 78%" in msg
    assert "from base" not in msg


def test_format_message_russian_translates_static_labels() -> None:
    msg = format_message(_sample_rec(), tz=ZoneInfo("UTC"), language="ru")
    # signal header / sections / fields
    assert "LONG сигнал" in msg
    assert "Уверенность:" in msg
    assert "Сила:" in msg
    assert "Горизонт:" in msg
    assert "Что произошло:" in msg
    assert "Почему вверх:" in msg
    assert "Контр\\-аргументы:" in msg
    assert "Тех\\. контекст" in msg
    assert "Тезис мёртв ниже" in msg
    assert "Стоп\\-лосс" in msg
    assert "Тейк\\-профит" in msg
    assert "Получено:" in msg
    assert "Образовательная информация" in msg
    # English labels should be gone
    assert "LONG signal" not in msg
    assert "Confidence:" not in msg
    assert "Stop loss:" not in msg


def test_format_message_short_russian_says_pochemu_vniz() -> None:
    rec = _sample_rec().model_copy(
        update={
            "direction": "short",
            "invalidation_level": 73_500.00,
            "invalidation_kind": "atr_2_5x",
            "stop_loss": 73_500.00,
            "take_profit": 66_721.65,
        }
    )
    msg = format_message(rec, tz=ZoneInfo("UTC"), language="ru")
    assert "SHORT сигнал" in msg
    assert "Почему вниз:" in msg
    assert "Тезис мёртв выше" in msg
