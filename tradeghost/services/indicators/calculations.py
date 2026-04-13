from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)
    avg_gain = gains.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return pd.DataFrame(
        {
            "macd_line": macd_line,
            "signal_line": signal_line,
            "histogram": hist,
        }
    )


def stochastic(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.DataFrame:
    lowest_low = low.rolling(period).min()
    highest_high = high.rolling(period).max()
    denominator = (highest_high - lowest_low).replace(0, np.nan)
    k = 100 * ((close - lowest_low) / denominator)
    d = k.rolling(3).mean()
    return pd.DataFrame({"k": k, "d": d})


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff().fillna(0))
    return (direction * volume).fillna(0).cumsum()


def ad_line(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    denominator = (high - low).replace(0, np.nan)
    money_flow_multiplier = ((close - low) - (high - close)) / denominator
    money_flow_volume = money_flow_multiplier.fillna(0) * volume
    return money_flow_volume.cumsum()


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False).mean()


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    tr = atr(high, low, close, period=1)
    plus_di = 100 * pd.Series(plus_dm, index=high.index).ewm(alpha=1 / period, adjust=False).mean() / tr
    minus_di = 100 * pd.Series(minus_dm, index=high.index).ewm(alpha=1 / period, adjust=False).mean() / tr
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)) * 100
    return dx.ewm(alpha=1 / period, adjust=False).mean()


def bollinger_bands(close: pd.Series, period: int = 20, std_mult: float = 2.0) -> pd.DataFrame:
    mid = sma(close, period)
    std = close.rolling(period).std()
    upper = mid + std_mult * std
    lower = mid - std_mult * std
    bandwidth = (upper - lower) / mid.replace(0, np.nan)
    return pd.DataFrame({"mid": mid, "upper": upper, "lower": lower, "bandwidth": bandwidth})


def fibonacci_levels(high: pd.Series, low: pd.Series, lookback: int = 90) -> dict[str, float]:
    recent_high = float(high.tail(lookback).max())
    recent_low = float(low.tail(lookback).min())
    diff = recent_high - recent_low
    return {
        "0.0": recent_high,
        "0.236": recent_high - diff * 0.236,
        "0.382": recent_high - diff * 0.382,
        "0.5": recent_high - diff * 0.5,
        "0.618": recent_high - diff * 0.618,
        "0.786": recent_high - diff * 0.786,
        "1.0": recent_low,
    }


def range_position_52w(close: pd.Series, lookback: int = 252) -> float:
    high_52w = close.tail(lookback).max()
    low_52w = close.tail(lookback).min()
    denominator = high_52w - low_52w
    if denominator == 0:
        return 0.5
    return float((close.iloc[-1] - low_52w) / denominator)


def volume_stats(volume: pd.Series, period: int = 20) -> dict[str, float]:
    rolling_avg = volume.rolling(period).mean().iloc[-1]
    current = volume.iloc[-1]
    ratio = current / rolling_avg if rolling_avg and not np.isnan(rolling_avg) else np.nan
    trend = volume.tail(period).pct_change().mean()
    return {
        "volume_current": float(current),
        "volume_avg": float(rolling_avg) if not np.isnan(rolling_avg) else 0.0,
        "volume_ratio": float(ratio) if not np.isnan(ratio) else 0.0,
        "volume_trend": float(trend) if not np.isnan(trend) else 0.0,
    }


def support_resistance(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    lookback: int = 30,
) -> dict[str, float]:
    recent_high = float(high.tail(lookback).max())
    recent_low = float(low.tail(lookback).min())
    current = float(close.iloc[-1])
    return {"support": recent_low, "resistance": recent_high, "distance_to_resistance": recent_high - current}


def candlestick_pattern(df: pd.DataFrame) -> str:
    if len(df) < 2:
        return "none"
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    prev_body = prev["close"] - prev["open"]
    curr_body = curr["close"] - curr["open"]
    if prev_body < 0 < curr_body and curr["close"] > prev["open"] and curr["open"] < prev["close"]:
        return "bullish_engulfing"
    if prev_body > 0 > curr_body and curr["open"] > prev["close"] and curr["close"] < prev["open"]:
        return "bearish_engulfing"
    body_size = abs(curr_body)
    candle_range = curr["high"] - curr["low"]
    if candle_range > 0 and (body_size / candle_range) < 0.15:
        return "doji"
    return "none"


def breakout_candidate(close: pd.Series, high: pd.Series, volume_ratio: float, lookback: int = 20) -> bool:
    if len(close) <= lookback:
        return False
    prior_high = high.shift(1).tail(lookback).max()
    return bool(close.iloc[-1] > prior_high and volume_ratio >= 1.2)


def compute_indicator_snapshot(
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    market_cap: float | None = None,
) -> dict[str, Any]:
    close = daily["close"]
    high = daily["high"]
    low = daily["low"]
    volume = daily["volume"]

    macd_df = macd(close)
    stoch_df = stochastic(high, low, close)
    bb = bollinger_bands(close)
    adx_series = adx(high, low, close)
    atr_series = atr(high, low, close)
    obv_series = obv(close, volume)
    adl_series = ad_line(high, low, close, volume)
    ema_20 = ema(close, 20)
    ema_50 = ema(close, 50)
    sma_20 = sma(close, 20)
    sma_50 = sma(close, 50)
    fib = fibonacci_levels(high, low)
    vol = volume_stats(volume)
    sr = support_resistance(high, low, close)
    pattern = candlestick_pattern(daily)
    weekly_ema_20 = ema(weekly["close"], 20)
    weekly_ema_50 = ema(weekly["close"], 50)

    snapshot = {
        "close": float(close.iloc[-1]),
        "rsi": float(rsi(close).iloc[-1]),
        "macd_line": float(macd_df["macd_line"].iloc[-1]),
        "macd_signal": float(macd_df["signal_line"].iloc[-1]),
        "macd_hist": float(macd_df["histogram"].iloc[-1]),
        "stoch_k": float(stoch_df["k"].iloc[-1]),
        "stoch_d": float(stoch_df["d"].iloc[-1]),
        "obv_slope": float(obv_series.tail(20).diff().mean()),
        "ad_line_slope": float(adl_series.tail(20).diff().mean()),
        "ema_20": float(ema_20.iloc[-1]),
        "ema_50": float(ema_50.iloc[-1]),
        "sma_20": float(sma_20.iloc[-1]),
        "sma_50": float(sma_50.iloc[-1]),
        "adx": float(adx_series.iloc[-1]),
        "atr": float(atr_series.iloc[-1]),
        "bb_upper": float(bb["upper"].iloc[-1]),
        "bb_mid": float(bb["mid"].iloc[-1]),
        "bb_lower": float(bb["lower"].iloc[-1]),
        "bb_bandwidth": float(bb["bandwidth"].iloc[-1]),
        "fibonacci": fib,
        "range_pos_52w": range_position_52w(close),
        "volume": vol,
        "support_resistance": sr,
        "candlestick_pattern": pattern,
        "breakout_candidate": breakout_candidate(close, high, vol["volume_ratio"]),
        "market_cap": float(market_cap) if market_cap else None,
        "weekly_trend_aligned": bool(weekly_ema_20.iloc[-1] > weekly_ema_50.iloc[-1]),
    }
    return snapshot

