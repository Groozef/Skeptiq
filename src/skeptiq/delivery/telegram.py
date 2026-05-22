import re
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import LinkPreviewOptions

from skeptiq.core.logging import get_logger
from skeptiq.delivery.i18n import Language, t
from skeptiq.schemas import Recommendation

log = get_logger(__name__)

_MD_V2_SPECIALS = re.compile(r"([_*\[\]()~`>#+\-=|{}.!\\])")
_ALIGNMENT_GLYPH: dict[str, str] = {
    "confirms": "✅",
    "mixed": "➖",
    # legacy v0.2.0 stored "neutral"; keep mapping for historical journal renders.
    "neutral": "➖",
    "contradicts": "⚠️",
}


def _md(text: str) -> str:
    """Escape every MarkdownV2 special char in plain text."""
    return _MD_V2_SPECIALS.sub(r"\\\1", text)


def _md_url(url: str) -> str:
    """Escape only what MarkdownV2 requires inside a link's (url)."""
    return url.replace("\\", "\\\\").replace(")", "\\)")


def _signed_pct(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.2f}%"


def format_grouped_message(
    recs: list[Recommendation], *, tz: ZoneInfo, language: Language = "en"
) -> str:
    """One message for >=1 Recommendations that share an analysis_id.

    For len==1 -> identical to format_message (single-ticker path).
    For len>1  -> shared narrative (situation/why/counter-signals) followed
                  by a separate technical-context block per ticker, ending
                  with one shared source link / timestamp / disclaimer.
    """
    if not recs:
        raise ValueError("format_grouped_message requires at least one rec")
    if len(recs) == 1:
        return format_message(recs[0], tz=tz, language=language)
    return _format_multi(recs, tz=tz, language=language)


def format_message(rec: Recommendation, *, tz: ZoneInfo, language: Language = "en") -> str:
    direction_emoji = "\U0001f7e2" if rec.direction == "long" else "\U0001f534"
    signal_label = t(language, "long_signal" if rec.direction == "long" else "short_signal")
    why_label = t(language, "why_bullish" if rec.direction == "long" else "why_bearish")

    confidence_pct = round(rec.confidence * 100)
    base_pct = round(rec.base_confidence * 100)
    delta_pp = confidence_pct - base_pct
    if delta_pp == 0:
        confidence_str = f"{confidence_pct}%"
    elif delta_pp > 0:
        confidence_str = f"{confidence_pct}% \\(\\+{delta_pp} {_md(t(language, 'from_base'))}\\)"
    else:
        confidence_str = f"{confidence_pct}% \\(\\{delta_pp} {_md(t(language, 'from_base'))}\\)"

    tc = rec.technical_context
    symbol = f"{tc.ticker.upper()}USDT"

    invalidation_pct = (
        (rec.invalidation_level - tc.price) / tc.price * 100.0 if tc.price else 0.0
    )
    invalidation_label_key = "invalid_below" if rec.direction == "long" else "invalid_above"
    invalidation_kind_key = {
        "swing_low": "kind_swing_low",
        "swing_high": "kind_swing_high",
        "atr": "kind_atr",
        # legacy v0.2.0 rows used "atr_2_5x"; map to the same label so
        # historical journal/Telegram reprints don't crash.
        "atr_2_5x": "kind_atr",
    }.get(rec.invalidation_kind, "kind_atr")

    sl_pct = (rec.stop_loss - tc.price) / tc.price * 100.0
    tp_pct = (rec.take_profit - tc.price) / tc.price * 100.0

    align_glyph = _ALIGNMENT_GLYPH[rec.technical_alignment]
    spike_glyph = "✅" if tc.volume_spike else "❌"
    above_glyph = "✅" if tc.above_ema20 else "❌"

    detected_local = rec.detected_at.astimezone(tz)
    detected_str = detected_local.strftime("%d %b %Y, %H:%M")
    tz_label = tz.key

    why_bullets = "\n".join(f"• {_md(p)}" for p in rec.directional_arguments)
    counter_bullets = "\n".join(f"• {_md(p)}" for p in rec.counter_signals)

    price_str = f"{tc.price:,.2f}"
    rsi_str = f"{tc.rsi_14:.1f}"
    chg_str = _signed_pct(tc.change_24h_pct)
    vol_str = f"{tc.volume_ratio:.1f}×"

    impact_label = t(language, f"imp_{rec.impact}")
    horizon_label = t(language, f"hor_{rec.horizon}")
    align_label = t(language, f"align_{rec.technical_alignment}")
    inv_kind_label = t(language, invalidation_kind_key)
    inv_label = t(language, invalidation_label_key)

    lines = [
        f"{direction_emoji} *{_md(signal_label)} — {_md(rec.ticker)}*",
        (
            f"{_md(t(language, 'confidence'))}: {confidence_str} · "
            f"{_md(t(language, 'impact'))}: {_md(impact_label)} · "
            f"{_md(t(language, 'horizon'))}: {_md(horizon_label)}"
        ),
        "",
        f"*{_md(t(language, 'situation'))}:*",
        _md(rec.summary),
        "",
        f"*{_md(why_label)}:*",
        why_bullets,
        "",
        f"*{_md(t(language, 'counter_signals'))}:*",
        counter_bullets,
        "",
        f"*{_md(t(language, 'technical_context'))} \\({_md(symbol)}\\):*",
        (
            f"{_md(t(language, 'price'))}: ${_md(price_str)} · "
            f"RSI\\(14\\): {_md(rsi_str)} · "
            f"{_md(t(language, 'h24'))}: {_md(chg_str)}"
        ),
        (
            f"{_md(t(language, 'volume_spike'))}: {spike_glyph} "
            f"\\({_md(vol_str)} {_md(t(language, 'avg_suffix'))}\\) · "
            f"{_md(t(language, 'above_ema20'))}: {above_glyph}"
        ),
        f"{_md(t(language, 'alignment'))}: {align_glyph} {_md(align_label)}",
        (
            f"{_md(inv_label)}: ${_md(f'{rec.invalidation_level:,.2f}')} "
            f"\\({_md(_signed_pct(invalidation_pct))}, {_md(inv_kind_label)}\\)"
        ),
        (
            f"{_md(t(language, 'stop_loss'))}: ${_md(f'{rec.stop_loss:,.2f}')} "
            f"\\({_md(_signed_pct(sl_pct))}\\) · "
            f"{_md(t(language, 'take_profit'))}: ${_md(f'{rec.take_profit:,.2f}')} "
            f"\\({_md(_signed_pct(tp_pct))}, {_md(t(language, 'rr'))}\\)"
        ),
        "",
        f"\U0001f4f0 [{_md(rec.source_name)}]({_md_url(rec.source_url)})",
        f"\U0001f550 {_md(t(language, 'detected'))}: {_md(detected_str)} \\({_md(tz_label)}\\)",
        "",
        f"_⚠️ {_md(t(language, 'disclaimer'))}_",
    ]
    return "\n".join(lines)


def _format_multi(
    recs: list[Recommendation], *, tz: ZoneInfo, language: Language = "en"
) -> str:
    """Render a multi-ticker grouped signal — shared narrative, per-ticker
    technical context blocks. Used when the same analysis covers multiple
    watchlist tickers (e.g. CoinShares inflow report relevant to BTC + ETH)."""
    primary = recs[0]
    direction_emoji = "\U0001f7e2" if primary.direction == "long" else "\U0001f534"
    signal_label = t(
        language, "long_signal" if primary.direction == "long" else "short_signal"
    )
    why_label = t(
        language, "why_bullish" if primary.direction == "long" else "why_bearish"
    )

    tickers_header = ", ".join(_md(r.ticker) for r in recs)
    impact_label = t(language, f"imp_{primary.impact}")
    horizon_label = t(language, f"hor_{primary.horizon}")

    detected_local = primary.detected_at.astimezone(tz)
    detected_str = detected_local.strftime("%d %b %Y, %H:%M")
    tz_label = tz.key

    why_bullets = "\n".join(f"• {_md(p)}" for p in primary.directional_arguments)
    counter_bullets = "\n".join(f"• {_md(p)}" for p in primary.counter_signals)

    lines = [
        f"{direction_emoji} *{_md(signal_label)} — {tickers_header}*",
        (
            f"{_md(t(language, 'impact'))}: {_md(impact_label)} · "
            f"{_md(t(language, 'horizon'))}: {_md(horizon_label)}"
        ),
        "",
        f"*{_md(t(language, 'situation'))}:*",
        _md(primary.summary),
        "",
        f"*{_md(why_label)}:*",
        why_bullets,
        "",
        f"*{_md(t(language, 'counter_signals'))}:*",
        counter_bullets,
        "",
    ]

    for rec in recs:
        tc = rec.technical_context
        symbol = f"{tc.ticker.upper()}USDT"
        align_glyph = _ALIGNMENT_GLYPH.get(rec.technical_alignment, "➖")
        spike_glyph = "✅" if tc.volume_spike else "❌"
        above_glyph = "✅" if tc.above_ema20 else "❌"
        align_label = t(language, f"align_{rec.technical_alignment}")
        invalidation_kind_key = {
            "swing_low": "kind_swing_low",
            "swing_high": "kind_swing_high",
            "atr": "kind_atr",
            "atr_2_5x": "kind_atr",
        }.get(rec.invalidation_kind, "kind_atr")
        inv_kind_label = t(language, invalidation_kind_key)
        inv_label = t(
            language,
            "invalid_below" if rec.direction == "long" else "invalid_above",
        )

        confidence_pct = round(rec.confidence * 100)
        base_pct = round(rec.base_confidence * 100)
        delta_pp = confidence_pct - base_pct
        if delta_pp == 0:
            confidence_str = f"{confidence_pct}%"
        elif delta_pp > 0:
            confidence_str = (
                f"{confidence_pct}% \\(\\+{delta_pp} {_md(t(language, 'from_base'))}\\)"
            )
        else:
            confidence_str = (
                f"{confidence_pct}% \\(\\{delta_pp} {_md(t(language, 'from_base'))}\\)"
            )

        sign_24h = "+" if tc.change_24h_pct >= 0 else ""
        chg_str = f"{sign_24h}{tc.change_24h_pct:.2f}%"
        invalidation_pct = (
            (rec.invalidation_level - tc.price) / tc.price * 100.0 if tc.price else 0.0
        )
        invalidation_sign = "+" if invalidation_pct >= 0 else ""
        sl_pct = (rec.stop_loss - tc.price) / tc.price * 100.0
        tp_pct = (rec.take_profit - tc.price) / tc.price * 100.0
        sl_sign = "+" if sl_pct >= 0 else ""
        tp_sign = "+" if tp_pct >= 0 else ""

        lines.extend(
            [
                f"*{_md(t(language, 'technical_context'))} \\({_md(symbol)}\\):*",
                f"{_md(t(language, 'confidence'))}: {confidence_str}",
                (
                    f"{_md(t(language, 'price'))}: ${_md(f'{tc.price:,.2f}')} · "
                    f"RSI\\(14\\): {_md(f'{tc.rsi_14:.1f}')} · "
                    f"{_md(t(language, 'h24'))}: {_md(chg_str)}"
                ),
                (
                    f"{_md(t(language, 'volume_spike'))}: {spike_glyph} \\("
                    f"{_md(f'{tc.volume_ratio:.1f}×')} {_md(t(language, 'avg_suffix'))}"
                    f"\\) · {_md(t(language, 'above_ema20'))}: {above_glyph}"
                ),
                f"{_md(t(language, 'alignment'))}: {align_glyph} {_md(align_label)}",
                (
                    f"{_md(inv_label)}: ${_md(f'{rec.invalidation_level:,.2f}')} "
                    f"\\({_md(f'{invalidation_sign}{invalidation_pct:.2f}%')}, "
                    f"{_md(inv_kind_label)}\\)"
                ),
                (
                    f"{_md(t(language, 'stop_loss'))}: ${_md(f'{rec.stop_loss:,.2f}')} "
                    f"\\({_md(f'{sl_sign}{sl_pct:.2f}%')}\\) · "
                    f"{_md(t(language, 'take_profit'))}: "
                    f"${_md(f'{rec.take_profit:,.2f}')} "
                    f"\\({_md(f'{tp_sign}{tp_pct:.2f}%')}, {_md(t(language, 'rr'))}\\)"
                ),
                "",
            ]
        )

    lines.extend(
        [
            f"\U0001f4f0 [{_md(primary.source_name)}]({_md_url(primary.source_url)})",
            (
                f"\U0001f550 {_md(t(language, 'detected'))}: "
                f"{_md(detected_str)} \\({_md(tz_label)}\\)"
            ),
            "",
            f"_⚠️ {_md(t(language, 'disclaimer'))}_",
        ]
    )
    return "\n".join(lines)


class TelegramSender:
    def __init__(
        self,
        *,
        bot_token: str,
        chat_id: int,
        tz: ZoneInfo,
        language: Language = "en",
    ) -> None:
        self._bot = Bot(
            token=bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN_V2),
        )
        self._chat_id = chat_id
        self._tz = tz
        self._language = language

    async def send(self, recommendation: Recommendation) -> int:
        """Send a single-ticker signal — kept for callers that haven't
        migrated to the grouped form."""
        return await self.send_grouped([recommendation])

    async def send_grouped(self, recs: list[Recommendation]) -> int:
        """Send one Telegram message that covers >=1 Recommendations
        sharing a single underlying analysis. For multi-asset news
        (e.g. CoinShares inflow report relevant to BTC + ETH) this
        replaces N separate identical-narrative messages with one
        message that has per-ticker technical context blocks."""
        if not recs:
            raise ValueError("send_grouped requires at least one rec")
        text = format_grouped_message(recs, tz=self._tz, language=self._language)
        msg = await self._bot.send_message(
            chat_id=self._chat_id,
            text=text,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        primary = recs[0]
        log.info(
            "telegram_sent",
            chat_id=self._chat_id,
            message_id=msg.message_id,
            tickers=[r.ticker for r in recs],
            direction=primary.direction,
            language=self._language,
            n_tickers=len(recs),
        )
        return msg.message_id

    async def aclose(self) -> None:
        await self._bot.session.close()
