from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from tradeghost.services.indicators.calculations import compute_indicator_snapshot
from tradeghost.services.interpretation.rules import interpret_snapshot
from tradeghost.services.scoring.engine import score_analysis
from tradeghost.services.strategy.config import ANALYSIS_PIPELINE_ORDER
from tradeghost.services.strategy.filters import evaluate_entry_gate, evaluate_location, evaluate_regime, evaluate_trigger
from tradeghost.shared.models.schemas import AnalysisConfig, AnalysisPipelineResult, EntryGateDiagnostics, LocationDiagnostics, RegimeDiagnostics, TriggerDiagnostics


@dataclass
class StrategyPipelineState:
    snapshot: dict[str, Any]
    interpreted: dict[str, Any]
    final_score: float
    category_scores: Any
    threshold_passed: bool
    regime: RegimeDiagnostics
    location: LocationDiagnostics
    trigger: TriggerDiagnostics
    entry_gate: EntryGateDiagnostics
    pipeline_result: AnalysisPipelineResult


def run_analysis_pipeline(
    *,
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    market_cap: float | None,
    config: AnalysisConfig,
) -> StrategyPipelineState:
    # Step 1-2: indicators
    snapshot = compute_indicator_snapshot(daily=daily, weekly=weekly, market_cap=market_cap)

    # Step 3: category scores
    interpreted = interpret_snapshot(snapshot)
    category_scores, final_score = score_analysis(interpreted)

    # Step 4: threshold gate
    threshold_passed = bool(final_score >= config.score_threshold)

    # Step 5-7: gate diagnostics
    regime = evaluate_regime(snapshot, config)
    location = evaluate_location(snapshot, config)
    trigger = evaluate_trigger(snapshot, config, location)

    # Step 8: final decision
    entry_gate = evaluate_entry_gate(
        final_score=final_score,
        config=config,
        regime=regime,
        location=location,
        trigger=trigger,
    )

    pipeline_result = AnalysisPipelineResult(
        pipeline_order=list(ANALYSIS_PIPELINE_ORDER),
        final_score=round(final_score, 2),
        threshold_passed=threshold_passed,
        regime_valid=regime.regime_valid,
        location_valid=location.location_valid,
        trigger_valid=trigger.trigger_valid,
        final_entry_decision=entry_gate.final_entry_decision,
        diagnostics={
            "skip_reason": entry_gate.skip_reason,
            "regime_reason": regime.regime_reason,
            "location_reason": location.location_reason,
            "trigger_reason": trigger.trigger_reason,
        },
    )

    return StrategyPipelineState(
        snapshot=snapshot,
        interpreted=interpreted,
        final_score=final_score,
        category_scores=category_scores,
        threshold_passed=threshold_passed,
        regime=regime,
        location=location,
        trigger=trigger,
        entry_gate=entry_gate,
        pipeline_result=pipeline_result,
    )

