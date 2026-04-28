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
    # Periods in numbers must be escaped
    assert r"71,240\.55" in msg


def test_format_message_short_uses_bearish_label() -> None:
    rec = _sample_rec().model_copy(update={"direction": "short"})
    msg = format_message(rec, tz=ZoneInfo("UTC"))
    assert "*SHORT signal" in msg
    assert "*Why bearish:*" in msg
