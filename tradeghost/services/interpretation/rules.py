from __future__ import annotations

from typing import Any


def _score_from_state(state: str) -> float:
    mapping = {
        "bullish": 0.8,
        "moderate_bullish": 0.4,
        "neutral": 0.0,
        "moderate_bearish": -0.4,
        "bearish": -0.8,
        "strong": 0.8,
        "weak": -0.3,
        "overbought": -0.3,
        "oversold": 0.3,
        "accumulation": 0.5,
        "distribution": -0.5,
        "yes": 0.6,
        "no": -0.1,
        "aligned": 0.6,
        "not_aligned": -0.4,
    }
    return mapping.get(state, 0.0)


def interpret_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    close = snapshot["close"]
    ema_20 = snapshot["ema_20"]
    ema_50 = snapshot["ema_50"]
    sma_20 = snapshot["sma_20"]
    sma_50 = snapshot["sma_50"]

    rsi_state = "neutral"
    if snapshot["rsi"] >= 70:
        rsi_state = "overbought"
    elif snapshot["rsi"] <= 30:
        rsi_state = "oversold"
    elif snapshot["rsi"] > 55:
        rsi_state = "moderate_bullish"
    elif snapshot["rsi"] < 45:
        rsi_state = "moderate_bearish"

    macd_state = "bullish" if snapshot["macd_line"] > snapshot["macd_signal"] else "bearish"
    stoch_state = "bullish" if snapshot["stoch_k"] > snapshot["stoch_d"] else "bearish"
    obv_state = "accumulation" if snapshot["obv_slope"] > 0 else "distribution"
    ad_state = "accumulation" if snapshot["ad_line_slope"] > 0 else "distribution"
    volume_state = "strong" if snapshot["volume"]["volume_ratio"] >= 1.2 else "weak"

    ma_alignment = "bullish" if (ema_20 > ema_50 and sma_20 > sma_50 and close > ema_20) else "bearish"
    adx_state = "strong" if snapshot["adx"] >= 25 else "weak"
    weekly_alignment = "aligned" if snapshot["weekly_trend_aligned"] else "not_aligned"

    if close >= snapshot["bb_upper"]:
        bb_state = "overbought"
    elif close <= snapshot["bb_lower"]:
        bb_state = "oversold"
    else:
        bb_state = "neutral"

    atr_state = "moderate_bullish" if snapshot["atr"] / close < 0.04 else "moderate_bearish"
    fib_618 = snapshot["fibonacci"]["0.618"]
    fib_state = "bullish" if close > fib_618 else "bearish"

    sr = snapshot["support_resistance"]
    structure_state = "bullish" if (close > sr["support"] and close < sr["resistance"]) else "bearish"
    candle = snapshot["candlestick_pattern"]
    if candle == "bullish_engulfing":
        candle_state = "bullish"
    elif candle == "bearish_engulfing":
        candle_state = "bearish"
    else:
        candle_state = "neutral"
    breakout_state = "yes" if snapshot["breakout_candidate"] else "no"

    range_state = "moderate_bullish" if 0.35 <= snapshot["range_pos_52w"] <= 0.8 else "moderate_bearish"
    market_cap = snapshot.get("market_cap")
    market_cap_state = "neutral"
    if market_cap:
        market_cap_state = "moderate_bullish" if market_cap >= 2_000_000_000 else "moderate_bearish"

    signals = {
        "rsi_state": rsi_state,
        "macd_state": macd_state,
        "stoch_state": stoch_state,
        "obv_state": obv_state,
        "ad_state": ad_state,
        "volume_state": volume_state,
        "ma_alignment_state": ma_alignment,
        "adx_state": adx_state,
        "weekly_alignment_state": weekly_alignment,
        "bollinger_state": bb_state,
        "atr_state": atr_state,
        "fibonacci_state": fib_state,
        "structure_state": structure_state,
        "candle_state": candle_state,
        "breakout_state": breakout_state,
        "range_state": range_state,
        "market_cap_state": market_cap_state,
        "divergence_state": "neutral",  # Placeholder for future divergence logic.
    }

    momentum_inputs = [
        signals["rsi_state"],
        signals["macd_state"],
        signals["stoch_state"],
        signals["obv_state"],
        signals["ad_state"],
        signals["volume_state"],
        signals["divergence_state"],
    ]
    trend_inputs = [signals["ma_alignment_state"], signals["adx_state"], signals["weekly_alignment_state"]]
    volatility_inputs = [signals["bollinger_state"], signals["atr_state"], signals["fibonacci_state"]]
    structure_inputs = [signals["structure_state"], signals["candle_state"], signals["breakout_state"]]
    context_inputs = [signals["range_state"], signals["market_cap_state"]]

    category_raw = {
        "momentum_raw": sum(_score_from_state(s) for s in momentum_inputs) / len(momentum_inputs),
        "trend_raw": sum(_score_from_state(s) for s in trend_inputs) / len(trend_inputs),
        "volatility_raw": sum(_score_from_state(s) for s in volatility_inputs) / len(volatility_inputs),
        "structure_raw": sum(_score_from_state(s) for s in structure_inputs) / len(structure_inputs),
        "context_raw": sum(_score_from_state(s) for s in context_inputs) / len(context_inputs),
    }
    return {"signals": signals, "category_raw": category_raw}

