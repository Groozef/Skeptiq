import re
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import LinkPreviewOptions

from skeptiq.core.logging import get_logger
from skeptiq.schemas import Recommendation

log = get_logger(__name__)

_MD_V2_SPECIALS = re.compile(r"([_*\[\]()~`>#+\-=|{}.!\\])")
_ALIGNMENT_GLYPH: dict[str, str] = {
    "confirms": "✅",      # ✅
    "neutral": "➖",       # ➖
    "contradicts": "⚠️",  # ⚠️
}


def _md(text: str) -> str:
    """Escape every MarkdownV2 special char in plain text."""
    return _MD_V2_SPECIALS.sub(r"\\\1", text)


def _md_url(url: str) -> str:
    """Escape only what MarkdownV2 requires inside a link's (url)."""
    return url.replace("\\", "\\\\").replace(")", "\\)")


def format_message(rec: Recommendation, *, tz: ZoneInfo) -> str:
    direction_emoji = "\U0001f7e2" if rec.direction == "long" else "\U0001f534"  # 🟢 / 🔴
    direction_word = "LONG" if rec.direction == "long" else "SHORT"
    why_label = "Why bullish" if rec.direction == "long" else "Why bearish"

    confidence_pct = round(rec.confidence * 100)
    base_pct = round(rec.base_confidence * 100)
    delta_pp = confidence_pct - base_pct
    if delta_pp == 0:
        confidence_str = f"{confidence_pct}%"
    elif delta_pp > 0:
        confidence_str = f"{confidence_pct}% \\(\\+{delta_pp} from base\\)"
    else:
        confidence_str = f"{confidence_pct}% \\({delta_pp} from base\\)"

    tc = rec.technical_context
    symbol = f"{tc.ticker.upper()}USDT"

    invalidation_pct = (
        (rec.invalidation_level - tc.price) / tc.price * 100.0 if tc.price else 0.0
    )
    invalidation_label = "Invalid below" if rec.direction == "long" else "Invalid above"
    invalidation_kind_label = {
        "swing_low": "swing low",
        "swing_high": "swing high",
        "atr_2_5x": "ATR×2\\.5",
    }.get(rec.invalidation_kind, rec.invalidation_kind)
    invalidation_sign = "+" if invalidation_pct >= 0 else ""

    sign_24h = "+" if tc.change_24h_pct >= 0 else ""
    spike_glyph = "✅" if tc.volume_spike else "❌"  # ✅ / ❌
    above_glyph = "✅" if tc.above_ema20 else "❌"
    align_glyph = _ALIGNMENT_GLYPH[rec.technical_alignment]

    detected_local = rec.detected_at.astimezone(tz)
    detected_str = detected_local.strftime("%d %b %Y, %H:%M")
    tz_label = tz.key

    why_bullets = "\n".join(f"• {_md(p)}" for p in rec.directional_arguments)
    counter_bullets = "\n".join(f"• {_md(p)}" for p in rec.counter_signals)

    price_str = f"{tc.price:,.2f}"
    rsi_str = f"{tc.rsi_14:.1f}"
    chg_str = f"{sign_24h}{tc.change_24h_pct:.2f}%"
    vol_str = f"{tc.volume_ratio:.1f}×"  # ×

    invalidation_price_str = f"{rec.invalidation_level:,.2f}"
    invalidation_pct_str = f"{invalidation_sign}{invalidation_pct:.2f}%"

    lines = [
        f"{direction_emoji} *{direction_word} signal — {_md(rec.ticker)}*",
        (
            f"Confidence: {confidence_str} · "
            f"Impact: {_md(rec.impact.upper())} · "
            f"Horizon: {_md(rec.horizon)}"
        ),
        "",
        "*Situation:*",
        _md(rec.summary),
        "",
        f"*{why_label}:*",
        why_bullets,
        "",
        "*Counter\\-signals:*",
        counter_bullets,
        "",
        f"*Technical context \\({_md(symbol)}\\):*",
        (
            f"Price: ${_md(price_str)} · "
            f"RSI\\(14\\): {_md(rsi_str)} · "
            f"24h: {_md(chg_str)}"
        ),
        (
            f"Volume spike: {spike_glyph} \\({_md(vol_str)} avg\\) · "
            f"Above EMA20: {above_glyph}"
        ),
        f"Alignment: {align_glyph} {_md(rec.technical_alignment)}",
        (
            f"{invalidation_label}: ${_md(invalidation_price_str)} "
            f"\\({_md(invalidation_pct_str)}, {invalidation_kind_label}\\)"
        ),
        "",
        f"\U0001f4f0 [{_md(rec.source_name)}]({_md_url(rec.source_url)})",
        f"\U0001f550 Detected: {_md(detected_str)} \\({_md(tz_label)}\\)",
    ]
    return "\n".join(lines)


class TelegramSender:
    def __init__(self, *, bot_token: str, chat_id: int, tz: ZoneInfo) -> None:
        self._bot = Bot(
            token=bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN_V2),
        )
        self._chat_id = chat_id
        self._tz = tz

    async def send(self, recommendation: Recommendation) -> int:
        text = format_message(recommendation, tz=self._tz)
        msg = await self._bot.send_message(
            chat_id=self._chat_id,
            text=text,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        log.info(
            "telegram_sent",
            chat_id=self._chat_id,
            message_id=msg.message_id,
            ticker=recommendation.ticker,
            direction=recommendation.direction,
        )
        return msg.message_id

    async def aclose(self) -> None:
        await self._bot.session.close()
