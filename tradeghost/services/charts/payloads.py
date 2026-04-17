from __future__ import annotations

from typing import Any

import pandas as pd

from tradeghost.services.indicators.calculations import ema
from tradeghost.shared.models.schemas import AnalysisChart, ChartCandle, ChartLinePoint

WINDOW_TO_PERIOD = {
    "5d": "6mo",
    "1m": "1y",
    "3m": "2y",
    "6m": "2y",
    "1y": "2y",
    "2y": "3y",
    "3y": "5y",
    "4y": "5y",
    "5y": "5y",
    "10y": "10y",
}

WINDOW_TO_BARS = {
    "5d": 5,
    "1m": 22,
    "3m": 66,
    "6m": 132,
    "1y": 252,
    "2y": 504,
    "3y": 756,
    "4y": 1008,
    "5y": 1260,
    "10y": 2520,
}


def normalize_window(window: str | None) -> str:
    raw = (window or "6m").strip().lower()
    return raw if raw in WINDOW_TO_PERIOD else "6m"


def visible_window_slice(daily: pd.DataFrame, window: str) -> pd.DataFrame:
    bars = WINDOW_TO_BARS[window]
    return daily.tail(bars).copy()


def _ema_points(full_daily: pd.DataFrame, display: pd.DataFrame, period: int) -> list[ChartLinePoint]:
    series = ema(full_daily["close"], period).tail(len(display))
    return [ChartLinePoint(date=idx.date(), value=float(value)) for idx, value in series.items()]


def build_analysis_chart(
    daily: pd.DataFrame,
    snapshot: dict[str, Any],
    trade_plan,
    window: str,
) -> AnalysisChart:
    display = visible_window_slice(daily, window)
    candles = [
        ChartCandle(
            date=idx.date(),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
        )
        for idx, row in display.iterrows()
    ]

    sr = snapshot.get("support_resistance", {})
    fib = snapshot.get("fibonacci", {})
    support = float(sr.get("support", 0.0)) if sr.get("support") is not None else 0.0
    resistance = float(sr.get("resistance", 0.0)) if sr.get("resistance") is not None else 0.0

    return AnalysisChart(
        candles=candles,
        ema_20=_ema_points(daily, display, 20),
        ema_50=_ema_points(daily, display, 50),
        ema_100=_ema_points(daily, display, 100),
        ema_200=_ema_points(daily, display, 200),
        current_price=float(snapshot.get("close", daily.iloc[-1]["close"])),
        support_levels=[support],
        resistance_levels=[resistance],
        fibonacci_levels={str(k): float(v) for k, v in fib.items()},
        trade_plan_overlay=trade_plan,
    )
