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
SWING_LOOKBACK = 24  # hourly candles -> last 24h
ATR_MULTIPLE = 2.5

InvalidationKind = Literal["swing_low", "swing_high", "atr_2_5x"]


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
) -> tuple[float, InvalidationKind]:
    """Compute the price level that would invalidate the directional thesis.

    For longs: the higher of (recent swing low) and (entry - 2.5×ATR).
              "Higher" = tighter stop, so we don't sit through random noise.
    For shorts: the lower of (recent swing high) and (entry + 2.5×ATR).

    Returns (level, kind) where kind names which constraint actually bound.
    Caller is responsible for showing this as a *thesis-invalidation* level,
    not a recommended trading stop-loss.
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
        atr_stop = last_close - ATR_MULTIPLE * atr
        if swing_low >= atr_stop:
            return swing_low, "swing_low"
        return atr_stop, "atr_2_5x"

    swing_high = float(highs.iloc[-lookback:].max())
    atr_stop = last_close + ATR_MULTIPLE * atr
    if swing_high <= atr_stop:
        return swing_high, "swing_high"
    return atr_stop, "atr_2_5x"
