from __future__ import annotations

from typing import Any

from tradeghost.shared.models.schemas import LocationDiagnostics, RegimeDiagnostics, SetupInterpretation, TriggerDiagnostics


def _safe_pct(value: float) -> float:
    return round(float(value), 2)


def classify_setup(
    *,
    snapshot: dict[str, Any],
    regime: RegimeDiagnostics,
    location: LocationDiagnostics,
    trigger: TriggerDiagnostics,
    threshold_passed: bool,
    final_entry_decision: bool,
) -> SetupInterpretation:
    close = float(snapshot["close"])
    ema20 = float(snapshot["ema_20"])
    ema50 = float(snapshot["ema_50"])
    ema100 = float(snapshot["ema_100"])
    ema200 = float(snapshot["ema_200"])

    transition_codes = {"ema200_reclaim_transition", "early_trend_rebuild", "post_regime_reclaim_watchlist"}
    prior_breakout_failed = bool(snapshot.get("prior_breakout_failed", False))
    reclaim_attempt_count = int(snapshot.get("reclaim_attempt_count", 0))
    second_attempt_breakout = bool(snapshot.get("second_attempt_breakout_candidate", False))

    if regime.regime_reason_code == "ema200_reclaim_transition":
        trend_state = "early_trend_transition"
    elif regime.regime_reason_code in {"early_trend_rebuild", "post_regime_reclaim_watchlist"}:
        trend_state = "early_trend_rebuild"
    elif close > ema200 and ema50 > ema100 > ema200:
        trend_state = "bullish_trend"
    elif close > ema200 and ema100 > ema200:
        trend_state = "weakening_trend"
    elif close > ema100:
        trend_state = "sideways"
    else:
        trend_state = "damaged_trend"

    abs20 = abs(location.distance_to_ema20_pct)
    abs50 = abs(location.distance_to_ema50_pct)
    abs100 = abs(location.distance_to_ema100_pct)
    if abs20 <= 1.5:
        pullback_state = "at_ema20"
    elif abs50 <= 1.5:
        pullback_state = "at_ema50"
    elif abs100 <= 1.5:
        pullback_state = "at_ema100"
    elif close > ema20:
        pullback_state = "shallow_pullback"
    elif close > ema100:
        pullback_state = "deep_pullback"
    else:
        pullback_state = "no_pullback"

    room = location.resistance_room_pct
    if room >= 4.0:
        resistance_test_state = "clear_room"
    elif room >= 2.0:
        resistance_test_state = "approaching_resistance"
    else:
        resistance_test_state = "at_resistance"

    if final_entry_decision and regime.regime_reason_code in transition_codes:
        setup_status = "early_trend_transition"
    elif final_entry_decision:
        setup_status = "actionable"
    elif regime.regime_reason_code in transition_codes and threshold_passed and not location.overextended_flag:
        setup_status = "watchlist"
    elif threshold_passed and regime.regime_valid and location.location_valid:
        setup_status = "watchlist"
    elif regime.regime_valid and not location.overextended_flag and resistance_test_state != "at_resistance":
        setup_status = "watchlist"
    else:
        setup_status = "avoid"

    tags: list[str] = []
    if close > ema20:
        tags.append("above_ema20")
    if close > ema50:
        tags.append("above_ema50")
    if pullback_state in {"at_ema20", "at_ema50", "at_ema100"}:
        tags.append(f"{pullback_state}_pullback")
    if location.support_proximity_ok:
        tags.append("near_support")
    if not location.resistance_room_ok:
        tags.append("limited_resistance_room")
    if location.extension_state in {"stretched", "overextended", "controlled_extension", "blowoff_extension"}:
        tags.append(f"{location.extension_state}_state")
    if trigger.trigger_type != "none":
        tags.append(trigger.trigger_type)
    if trigger.trigger_state != "confirmed":
        tags.append("breakout_not_confirmed")
    if regime.regime_reason_code in transition_codes:
        tags.append("ema200_reclaim_transition")
    if second_attempt_breakout:
        tags.append("second_attempt_breakout")
    if prior_breakout_failed:
        tags.append("prior_breakout_failed")

    setup_type = "pullback"
    if second_attempt_breakout:
        setup_type = "second_attempt_breakout"
    elif trend_state in {"bullish_trend", "weakening_trend"} and location.extension_state in {"controlled_extension", "normal"} and trigger.trigger_state in {"pending", "confirmed"}:
        setup_type = "momentum_continuation"
    elif trend_state in {"early_trend_rebuild", "early_trend_transition"} and pullback_state in {"at_ema100", "at_ema50"}:
        setup_type = "value_rebuild"
    elif setup_status in {"watchlist", "early_trend_transition"}:
        setup_type = "build_up"

    return SetupInterpretation(
        trend_state=trend_state,
        pullback_state=pullback_state,
        extension_state=location.extension_state,
        resistance_test_state=resistance_test_state,
        trigger_state=trigger.trigger_state,
        trigger_type=trigger.trigger_type,
        setup_type=setup_type,
        prior_breakout_failed=prior_breakout_failed,
        reclaim_attempt_count=reclaim_attempt_count,
        second_attempt_breakout_candidate=second_attempt_breakout,
        setup_status=setup_status,
        reasoning_tags=tags,
    )
