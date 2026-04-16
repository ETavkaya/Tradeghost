from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tradeghost.shared.models.schemas import EntryGateDiagnostics, LocationDiagnostics, RegimeDiagnostics, StrategyMode, TriggerDiagnostics


@dataclass(frozen=True)
class StrategyModeConfig:
    score_threshold: float
    regime_mode: str
    max_support_distance_pct: float
    min_resistance_room_pct: float
    max_overextension_ema20_pct: float
    max_overextension_ema50_pct: float
    max_overextension_ema100_pct: float
    min_trigger_score: float


_MODE_CONFIGS: dict[StrategyMode, StrategyModeConfig] = {
    StrategyMode.AGGRESSIVE: StrategyModeConfig(
        score_threshold=50.0,
        regime_mode="relaxed",
        max_support_distance_pct=7.5,
        min_resistance_room_pct=1.5,
        max_overextension_ema20_pct=7.0,
        max_overextension_ema50_pct=10.0,
        max_overextension_ema100_pct=14.0,
        min_trigger_score=55.0,
    ),
    StrategyMode.BALANCED: StrategyModeConfig(
        score_threshold=60.0,
        regime_mode="medium",
        max_support_distance_pct=5.0,
        min_resistance_room_pct=2.5,
        max_overextension_ema20_pct=5.0,
        max_overextension_ema50_pct=8.0,
        max_overextension_ema100_pct=11.0,
        min_trigger_score=65.0,
    ),
    StrategyMode.CONSERVATIVE: StrategyModeConfig(
        score_threshold=72.0,
        regime_mode="strict",
        max_support_distance_pct=3.5,
        min_resistance_room_pct=3.5,
        max_overextension_ema20_pct=3.0,
        max_overextension_ema50_pct=5.0,
        max_overextension_ema100_pct=8.0,
        min_trigger_score=75.0,
    ),
}


def normalize_strategy_mode(mode: StrategyMode | str | None) -> StrategyMode:
    if isinstance(mode, StrategyMode):
        return mode
    if not mode:
        return StrategyMode.BALANCED
    raw = str(mode).strip().lower()
    if raw == StrategyMode.AGGRESSIVE.value:
        return StrategyMode.AGGRESSIVE
    if raw == StrategyMode.CONSERVATIVE.value:
        return StrategyMode.CONSERVATIVE
    return StrategyMode.BALANCED


def get_strategy_mode_config(mode: StrategyMode | str | None) -> StrategyModeConfig:
    normalized = normalize_strategy_mode(mode)
    return _MODE_CONFIGS[normalized]


def evaluate_regime(snapshot: dict[str, Any], mode: StrategyMode | str | None) -> RegimeDiagnostics:
    config = get_strategy_mode_config(mode)
    close = float(snapshot["close"])
    ema50 = float(snapshot["ema_50"])
    ema100 = float(snapshot["ema_100"])
    ema200 = float(snapshot["ema_200"])

    price_above_ema200 = close > ema200
    ema100_above_ema200 = ema100 > ema200
    full_stack = ema50 > ema100 > ema200
    if full_stack and close > ema200:
        stack_quality = "strong"
    elif ema100_above_ema200:
        stack_quality = "moderate"
    else:
        stack_quality = "weak"

    if config.regime_mode == "strict":
        regime_valid = price_above_ema200 and ema100_above_ema200 and full_stack
        reason = "Strict regime requires price > EMA200 and EMA50 > EMA100 > EMA200."
    elif config.regime_mode == "medium":
        regime_valid = price_above_ema200 and ema100_above_ema200
        reason = "Medium regime requires price > EMA200 and EMA100 > EMA200."
    else:
        regime_valid = price_above_ema200 or ema100_above_ema200
        reason = "Relaxed regime accepts either price > EMA200 or EMA100 > EMA200."

    return RegimeDiagnostics(
        regime_valid=bool(regime_valid),
        regime_mode_used=config.regime_mode,
        price_above_ema200=price_above_ema200,
        ema100_above_ema200=ema100_above_ema200,
        ema_stack_quality=stack_quality,
        regime_reason=reason if regime_valid else f"{reason} Condition not met.",
    )


def evaluate_location(snapshot: dict[str, Any], mode: StrategyMode | str | None) -> LocationDiagnostics:
    config = get_strategy_mode_config(mode)
    close = max(float(snapshot["close"]), 0.01)
    support = float(snapshot["support_resistance"]["support"])
    resistance = float(snapshot["support_resistance"]["resistance"])
    ema20 = float(snapshot["ema_20"])
    ema50 = float(snapshot["ema_50"])
    ema100 = float(snapshot["ema_100"])

    support_distance_pct = max((close - support) / close * 100, 0.0)
    resistance_distance_pct = max((resistance - close) / close * 100, 0.0)
    ext20 = ((close - ema20) / max(ema20, 0.01)) * 100
    ext50 = ((close - ema50) / max(ema50, 0.01)) * 100
    ext100 = ((close - ema100) / max(ema100, 0.01)) * 100

    support_ok = support_distance_pct <= config.max_support_distance_pct
    resistance_ok = resistance_distance_pct >= config.min_resistance_room_pct
    overextended = (
        ext20 > config.max_overextension_ema20_pct
        or ext50 > config.max_overextension_ema50_pct
        or ext100 > config.max_overextension_ema100_pct
    )
    location_valid = support_ok and resistance_ok and not overextended

    score = 100.0
    score -= max(0.0, support_distance_pct - config.max_support_distance_pct) * 8.0
    score -= max(0.0, config.min_resistance_room_pct - resistance_distance_pct) * 12.0
    score -= 20.0 if overextended else 0.0
    score = max(0.0, min(100.0, score))

    reasons: list[str] = []
    reasons.append("Support proximity ok" if support_ok else "Too far from support")
    reasons.append("Resistance room ok" if resistance_ok else "Upside room too small")
    reasons.append("Not overextended" if not overextended else "Price overextended above key EMAs")

    return LocationDiagnostics(
        location_valid=location_valid,
        location_score=round(score, 2),
        support_proximity_ok=support_ok,
        resistance_room_ok=resistance_ok,
        overextended_flag=overextended,
        support_distance_pct=round(support_distance_pct, 2),
        resistance_distance_pct=round(resistance_distance_pct, 2),
        overextension_ema20_pct=round(ext20, 2),
        overextension_ema50_pct=round(ext50, 2),
        overextension_ema100_pct=round(ext100, 2),
        location_reason="; ".join(reasons),
    )


def evaluate_trigger(snapshot: dict[str, Any], mode: StrategyMode | str | None, location: LocationDiagnostics) -> TriggerDiagnostics:
    config = get_strategy_mode_config(mode)
    close = float(snapshot["close"])
    ema20 = float(snapshot["ema_20"])
    ema50 = float(snapshot["ema_50"])
    pattern = str(snapshot.get("candlestick_pattern", "none"))
    breakout_candidate = bool(snapshot.get("breakout_candidate", False))
    volume_ratio = float(snapshot.get("volume", {}).get("volume_ratio", 0.0))

    trigger_type = "none"
    trigger_score = 35.0
    reason = "No high-quality trigger confirmation."

    if pattern == "bullish_engulfing":
        trigger_type = "bullish_rejection"
        trigger_score = 84.0
        reason = "Bullish engulfing confirms rejection and demand response."
    elif breakout_candidate and volume_ratio >= 1.2:
        trigger_type = "breakout_continuation"
        trigger_score = 76.0
        reason = "Breakout candidate with supportive volume ratio."
    elif close > ema20 and close > ema50 and location.support_proximity_ok:
        trigger_type = "pullback_continuation"
        trigger_score = 67.0
        reason = "Continuation trigger after pullback while trend MAs hold."
    elif pattern == "doji" and location.support_proximity_ok and close > ema20:
        trigger_type = "support_reaction"
        trigger_score = 62.0
        reason = "Doji near support with short-term trend support."

    trigger_valid = trigger_score >= config.min_trigger_score
    if not trigger_valid:
        reason = f"{reason} Trigger score {trigger_score:.1f} below {config.min_trigger_score:.1f}."

    return TriggerDiagnostics(
        trigger_valid=trigger_valid,
        trigger_type=trigger_type,
        trigger_score=round(trigger_score, 2),
        trigger_reason=reason,
    )


def evaluate_entry_gate(
    *,
    final_score: float,
    score_threshold_used: float,
    regime: RegimeDiagnostics,
    location: LocationDiagnostics,
    trigger: TriggerDiagnostics,
) -> EntryGateDiagnostics:
    score_passed = final_score >= score_threshold_used
    entry_quality_score = (
        (0.35 * final_score)
        + (0.2 * (100.0 if regime.regime_valid else 0.0))
        + (0.25 * location.location_score)
        + (0.2 * trigger.trigger_score)
    ) / 1.0
    final_decision = bool(score_passed and regime.regime_valid and location.location_valid and trigger.trigger_valid)

    skip_reason = None
    if not final_decision:
        if not score_passed:
            skip_reason = "score_threshold"
        elif not regime.regime_valid:
            skip_reason = "regime_filter"
        elif not location.location_valid:
            if location.overextended_flag:
                skip_reason = "overextended_filter"
            elif not location.resistance_room_ok:
                skip_reason = "resistance_room_filter"
            else:
                skip_reason = "location_filter"
        elif not trigger.trigger_valid:
            skip_reason = "trigger_filter"
        else:
            skip_reason = "setup_filter"

    return EntryGateDiagnostics(
        final_score=round(final_score, 2),
        score_threshold_used=round(score_threshold_used, 2),
        score_threshold_passed=score_passed,
        regime_valid=regime.regime_valid,
        location_valid=location.location_valid,
        trigger_valid=trigger.trigger_valid,
        entry_quality_score=round(entry_quality_score, 2),
        final_entry_decision=final_decision,
        skip_reason=skip_reason,
    )

