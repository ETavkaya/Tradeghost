from __future__ import annotations

from typing import Any

from tradeghost.services.charts.payloads import normalize_window
from tradeghost.shared.config.settings import get_settings
from tradeghost.shared.market import normalize_market
from tradeghost.shared.models.schemas import (
    AnalysisConfig,
    LocationFilterSettings,
    RegimeFilterSettings,
    StrategyMode,
    TriggerFilterSettings,
)

ANALYSIS_PIPELINE_ORDER = [
    "fetch_data",
    "calculate_indicators",
    "calculate_category_scores",
    "evaluate_threshold_gate",
    "evaluate_regime_gate",
    "evaluate_location_gate",
    "evaluate_trigger_gate",
    "compute_final_entry_decision",
]

MODE_PRESETS: dict[StrategyMode, dict[str, Any]] = {
    StrategyMode.AGGRESSIVE: {
        "score_threshold": 50.0,
        "regime_mode": "relaxed",
        "max_support_distance_pct": 7.5,
        "min_resistance_room_pct": 1.5,
        "max_overextension_ema20_pct": 7.0,
        "max_overextension_ema50_pct": 10.0,
        "max_overextension_ema100_pct": 14.0,
        "max_overextension_ema200_pct": 18.0,
        "min_trigger_score": 55.0,
    },
    StrategyMode.BALANCED: {
        "score_threshold": 60.0,
        "regime_mode": "medium",
        "max_support_distance_pct": 5.0,
        "min_resistance_room_pct": 2.5,
        "max_overextension_ema20_pct": 5.0,
        "max_overextension_ema50_pct": 8.0,
        "max_overextension_ema100_pct": 11.0,
        "max_overextension_ema200_pct": 15.0,
        "min_trigger_score": 65.0,
    },
    StrategyMode.CONSERVATIVE: {
        "score_threshold": 72.0,
        "regime_mode": "strict",
        "max_support_distance_pct": 3.5,
        "min_resistance_room_pct": 3.5,
        "max_overextension_ema20_pct": 3.0,
        "max_overextension_ema50_pct": 5.0,
        "max_overextension_ema100_pct": 8.0,
        "max_overextension_ema200_pct": 12.0,
        "min_trigger_score": 75.0,
    },
    StrategyMode.CUSTOM: {
        # Custom inherits balanced defaults unless user overrides threshold/warmup.
        "score_threshold": 60.0,
        "regime_mode": "medium",
        "max_support_distance_pct": 5.0,
        "min_resistance_room_pct": 2.5,
        "max_overextension_ema20_pct": 5.0,
        "max_overextension_ema50_pct": 8.0,
        "max_overextension_ema100_pct": 11.0,
        "max_overextension_ema200_pct": 15.0,
        "min_trigger_score": 65.0,
    },
}


def normalize_strategy_mode(mode: StrategyMode | str | None) -> StrategyMode:
    if isinstance(mode, StrategyMode):
        return mode
    raw = str(mode or StrategyMode.BALANCED).strip().lower()
    if raw == StrategyMode.AGGRESSIVE.value:
        return StrategyMode.AGGRESSIVE
    if raw == StrategyMode.CONSERVATIVE.value:
        return StrategyMode.CONSERVATIVE
    if raw == StrategyMode.CUSTOM.value:
        return StrategyMode.CUSTOM
    return StrategyMode.BALANCED


def build_analysis_config(
    *,
    ticker: str,
    market: str | None,
    lookback_window: str | None,
    strategy_mode: StrategyMode | str | None,
    score_threshold: float | None = None,
    warmup_bars: int | None = None,
    regime_mode: str | None = None,
    max_support_distance_pct: float | None = None,
    min_resistance_room_pct: float | None = None,
    min_trigger_score: float | None = None,
    max_overextension_ema20_pct: float | None = None,
    max_overextension_ema50_pct: float | None = None,
    max_overextension_ema100_pct: float | None = None,
    max_overextension_ema200_pct: float | None = None,
) -> AnalysisConfig:
    settings = get_settings()
    mode = normalize_strategy_mode(strategy_mode)
    preset = MODE_PRESETS[mode]
    normalized_window = normalize_window(lookback_window)
    normalized_market = normalize_market(market)

    threshold = float(score_threshold) if score_threshold is not None else float(preset["score_threshold"])
    warmup = int(warmup_bars) if warmup_bars is not None else int(settings.backtest_warmup_bars)

    return AnalysisConfig(
        ticker=ticker.strip().upper(),
        market=normalized_market,
        lookback_window=normalized_window,
        strategy_mode=mode,
        score_threshold=threshold,
        warmup_bars=warmup,
        location_filter=LocationFilterSettings(
            max_support_distance_pct=float(
                max_support_distance_pct if max_support_distance_pct is not None else preset["max_support_distance_pct"]
            ),
            min_resistance_room_pct=float(
                min_resistance_room_pct if min_resistance_room_pct is not None else preset["min_resistance_room_pct"]
            ),
            max_overextension_ema20_pct=float(
                max_overextension_ema20_pct if max_overextension_ema20_pct is not None else preset["max_overextension_ema20_pct"]
            ),
            max_overextension_ema50_pct=float(
                max_overextension_ema50_pct if max_overextension_ema50_pct is not None else preset["max_overextension_ema50_pct"]
            ),
            max_overextension_ema100_pct=float(
                max_overextension_ema100_pct if max_overextension_ema100_pct is not None else preset["max_overextension_ema100_pct"]
            ),
            max_overextension_ema200_pct=float(
                max_overextension_ema200_pct if max_overextension_ema200_pct is not None else preset["max_overextension_ema200_pct"]
            ),
        ),
        regime_filter=RegimeFilterSettings(regime_mode=str(regime_mode if regime_mode is not None else preset["regime_mode"])),
        trigger_filter=TriggerFilterSettings(
            min_trigger_score=float(min_trigger_score if min_trigger_score is not None else preset["min_trigger_score"])
        ),
    )
