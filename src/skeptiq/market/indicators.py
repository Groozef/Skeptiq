from typing import Literal

import pandas as pd
import pandas_ta as ta

from skeptiq.market.binance import Kline
from skeptiq.schemas.technical import TechnicalContext, classify_rsi

VOLUME_SPIKE_THRESHOLD = 2.0
VOLUME_AVG_WINDOW = 20
EMA_WINDOW = 20
RSI_LENGTH = 14
ATR_LENGTH = 14
SWING_LOOKBACK = 24  # candles back over which we look for swing high/low
ATR_MULTIPLE = 1.5  # was 2.5; tightened per notatki-3 with the comparison fix

# Map horizon -> kline interval used for invalidation/SL computation.
# A "days" signal needs structure and volatility on a 4H frame; a "weeks"
# signal needs them on a 1D frame. tech_context still uses 1H regardless.
HORIZON_TO_INVALIDATION_INTERVAL: dict[str, str] = {
    "immediate": "1h",
    "hours": "1h",
    "days": "4h",
    "weeks": "1d",
}

InvalidationKind = Literal["swing_low", "swing_high", "atr"]


def klines_to_df(klines: list[Kline]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open_time_ms": [k.open_time_ms for k in klines],
            "open": [k.open for k in klines],
            "high": [k.high for k in klines],
            "low": [k.low for k in klines],
            "close": [k.close for k in klines],
            "volume": [k.volume for k in klines],
        }
    )


def compute_technical_context(ticker: str, klines: list[Kline]) -> TechnicalContext:
    min_required = max(RSI_LENGTH + 1, EMA_WINDOW + 1, VOLUME_AVG_WINDOW + 1, 25)
    if len(klines) < min_required:
        raise ValueError(
            f"Need at least {min_required} klines for {ticker}, got {len(klines)}"
        )

    df = klines_to_df(klines)
    closes = df["close"]
    volumes = df["volume"]

    rsi = float(ta.rsi(closes, length=RSI_LENGTH).iloc[-1])
    ema = float(ta.ema(closes, length=EMA_WINDOW).iloc[-1])
    last_close = float(closes.iloc[-1])
    last_volume = float(volumes.iloc[-1])

    avg_vol = float(volumes.iloc[-(VOLUME_AVG_WINDOW + 1) : -1].mean())
    volume_ratio = last_volume / avg_vol if avg_vol > 0 else 0.0

    # 1h interval -> close 24 candles back is the price ~24h ago.
    close_24h_ago = float(closes.iloc[-25])
    change_24h_pct = (
        (last_close - close_24h_ago) / close_24h_ago * 100.0
        if close_24h_ago > 0
        else 0.0
    )

    return TechnicalContext(
        ticker=ticker.upper(),
        price=last_close,
        rsi_14=rsi,
        rsi_state=classify_rsi(rsi),
        volume_spike=volume_ratio > VOLUME_SPIKE_THRESHOLD,
        above_ema20=last_close > ema,
        change_24h_pct=change_24h_pct,
        volume_ratio=volume_ratio,
    )


def compute_invalidation_level(
    direction: Literal["long", "short"],
    klines: list[Kline],
    *,
    atr_multiple: float = ATR_MULTIPLE,
) -> tuple[float, InvalidationKind]:
    """Price level beyond which the directional thesis is invalidated.

    Picks the FARTHER of two candidates from entry, so the trade has room
    to breathe through normal volatility. Notatki-3 revealed that the
    previous tighter-of-two heuristic produced 0.37% SL on BTC longs —
    inside one bar's worth of noise — because BTC's swing_low over the
    last 24 1h candles was very close to entry.

    For long:  SL = min(swing_low_lookback, entry - 1.5*ATR)   (lower = farther)
    For short: SL = max(swing_high_lookback, entry + 1.5*ATR)  (higher = farther)

    `klines` should be on the timeframe matching the signal's horizon
    (1h / 4h / 1d) — see HORIZON_TO_INVALIDATION_INTERVAL.
    """
    df = klines_to_df(klines)
    closes = df["close"]
    highs = df["high"]
    lows = df["low"]

    atr_series = ta.atr(highs, lows, closes, length=ATR_LENGTH)
    atr = float(atr_series.iloc[-1])
    last_close = float(closes.iloc[-1])

    lookback = min(SWING_LOOKBACK, len(klines))

    if direction == "long":
        swing_low = float(lows.iloc[-lookback:].min())
        atr_stop = last_close - atr_multiple * atr
        # Pick whichever sits FARTHER below entry (lower price).
        if swing_low <= atr_stop:
            return swing_low, "swing_low"
        return atr_stop, "atr"

    swing_high = float(highs.iloc[-lookback:].max())
    atr_stop = last_close + atr_multiple * atr
    if swing_high >= atr_stop:
        return swing_high, "swing_high"
    return atr_stop, "atr"
