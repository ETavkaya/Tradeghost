from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

from tradeghost.services.intelligence.research_record_store import ResearchRecordStore
from tradeghost.shared.models.schemas import (
    HistoricalEvidenceFrequency,
    OutcomeRecord,
    PredictionRecord,
    SimilarSetupEvidenceCase,
    SimilarSetupRequest,
    SimilarSetupRetrievalResponse,
    SimilarSetupSimilarityMode,
)


MIN_WEIGHTED_SIMILARITY = 0.5


class SimilarSetupEvidenceService:
    def __init__(
        self,
        *,
        record_store: ResearchRecordStore,
        min_sample_size: int,
        source_limit: int,
    ) -> None:
        self.record_store = record_store
        self.min_sample_size = max(1, int(min_sample_size))
        self.source_limit = max(1, min(int(source_limit), 5000))

    def retrieve(self, request: SimilarSetupRequest) -> SimilarSetupRetrievalResponse:
        criteria_count = self._criteria_count(request)
        if criteria_count == 0:
            raise ValueError("At least one similarity criterion is required for historical evidence retrieval.")
        as_of_date = request.as_of_date or date.today()
        source_cases = self.record_store.list_historical_evidence_cases(
            market=request.market.value,
            as_of_date=as_of_date,
            horizon_days=request.horizon_days,
            limit=self.source_limit,
        )
        scored_cases = [
            scored_case
            for prediction, outcome, selection_regime in source_cases
            if (scored_case := self._score_case(request, prediction, outcome, selection_regime)) is not None
        ]
        scored_cases.sort(
            key=lambda case: (
                -case.similarity_score,
                -(case.outcome_date.toordinal() if case.outcome_date else date.min.toordinal()),
                case.prediction_id,
            )
        )
        evaluable_cases = [
            case
            for case in scored_cases
            if case.outcome_status == "available" and case.return_pct is not None
        ]
        data_quality_excluded_count = sum(
            1 for case in scored_cases if case.outcome_status == "data_quality_excluded"
        )
        sample_size_sufficient = len(evaluable_cases) >= self.min_sample_size
        performance = self._performance_metrics(evaluable_cases) if sample_size_sufficient else {}
        caveats = self._build_caveats(
            source_cases_count=len(source_cases),
            similar_cases=scored_cases,
            evaluable_cases=evaluable_cases,
            data_quality_excluded_count=data_quality_excluded_count,
            as_of_date=as_of_date,
            horizon_days=request.horizon_days,
        )
        evidence_summary = self._build_evidence_summary(
            evaluable_cases=evaluable_cases,
            sample_size_sufficient=sample_size_sufficient,
            performance=performance,
            horizon_days=request.horizon_days,
        )
        return SimilarSetupRetrievalResponse(
            market=request.market.value,
            as_of_date=as_of_date,
            horizon_days=request.horizon_days,
            similarity_mode=request.similarity_mode,
            similar_case_count=len(scored_cases),
            evaluable_case_count=len(evaluable_cases),
            data_quality_excluded_count=data_quality_excluded_count,
            min_sample_size=self.min_sample_size,
            sample_size_sufficient=sample_size_sufficient,
            success_rate=performance.get("success_rate"),
            failure_rate=performance.get("failure_rate"),
            average_return=performance.get("average_return"),
            success_rate_28d=performance.get("success_rate") if request.horizon_days == 28 else None,
            failure_rate_28d=performance.get("failure_rate") if request.horizon_days == 28 else None,
            average_28d_return=performance.get("average_return") if request.horizon_days == 28 else None,
            average_relative_return=performance.get("average_relative_return"),
            common_failure_modes=(
                self._common_failure_modes(evaluable_cases) if sample_size_sufficient else []
            ),
            common_success_conditions=(
                self._common_success_conditions(evaluable_cases) if sample_size_sufficient else []
            ),
            top_similar_predictions=scored_cases[: request.lookback_limit],
            evidence_summary=evidence_summary,
            caveats=caveats,
        )

    def _score_case(
        self,
        request: SimilarSetupRequest,
        prediction: PredictionRecord,
        outcome: OutcomeRecord,
        selection_regime: str | None,
    ) -> SimilarSetupEvidenceCase | None:
        checks = self._matching_checks(request, prediction, selection_regime)
        matched_features = [name for name, matched in checks if matched]
        similarity_score = round(len(matched_features) / len(checks), 4)
        if request.similarity_mode == SimilarSetupSimilarityMode.EXACT and len(matched_features) != len(checks):
            return None
        if request.similarity_mode == SimilarSetupSimilarityMode.WEIGHTED and similarity_score < MIN_WEIGHTED_SIMILARITY:
            return None
        return SimilarSetupEvidenceCase(
            prediction_id=prediction.id,
            outcome_id=outcome.id,
            cohort_id=prediction.cohort_id,
            symbol=prediction.symbol,
            market=prediction.market,
            selected_date=prediction.selected_date,
            outcome_date=outcome.outcome_date,
            categories=prediction.categories,
            setup_type=prediction.setup_type,
            trend_state=prediction.trend_state,
            extension_state=prediction.extension_state,
            trigger_state=prediction.trigger_state,
            blocked_by=prediction.blocked_by,
            risk_flags=prediction.risk_flags,
            selection_market_regime=selection_regime,
            outcome_market_regime=outcome.market_regime_label,
            outcome_status=outcome.outcome_status,
            outcome_label=outcome.outcome_label,
            return_pct=outcome.return_pct,
            relative_to_spy=outcome.relative_to_spy,
            attribution_label=outcome.attribution_label,
            data_quality_flags=outcome.data_quality_flags,
            daily_snapshot_path_complete=outcome.daily_snapshot_path_complete,
            daily_snapshot_coverage_pct=outcome.daily_snapshot_coverage_pct,
            similarity_score=similarity_score,
            matched_features=matched_features,
        )

    def _matching_checks(
        self,
        request: SimilarSetupRequest,
        prediction: PredictionRecord,
        selection_regime: str | None,
    ) -> list[tuple[str, bool]]:
        checks: list[tuple[str, bool]] = []
        if request.symbol:
            checks.append(("symbol", prediction.symbol.upper() == request.symbol.strip().upper()))
        if request.category:
            category = _normalized(request.category)
            checks.append((f"category={category}", category in {_normalized(value) for value in prediction.categories}))
        if request.setup_type:
            checks.append(("setup_type", _normalized(prediction.setup_type) == _normalized(request.setup_type)))
        if request.trend_state:
            checks.append(("trend_state", _normalized(prediction.trend_state) == _normalized(request.trend_state)))
        if request.extension_state:
            checks.append(("extension_state", _normalized(prediction.extension_state) == _normalized(request.extension_state)))
        if request.trigger_state:
            checks.append(("trigger_state", _normalized(prediction.trigger_state) == _normalized(request.trigger_state)))
        if request.blocked_by:
            checks.append(("blocked_by", _normalized(prediction.blocked_by or "none") == _normalized(request.blocked_by)))
        for risk_flag in sorted({_normalized(flag) for flag in request.risk_flags if _normalized(flag)}):
            checks.append((f"risk_flag={risk_flag}", risk_flag in {_normalized(flag) for flag in prediction.risk_flags}))
        if request.market_regime:
            checks.append(("market_regime", _normalized(selection_regime) == _normalized(request.market_regime)))
        numeric_requests = (
            ("price_vs_ema200", request.price_vs_ema200_pct),
            ("support_distance", request.support_distance_pct),
            ("resistance_room", request.resistance_room_pct),
        )
        for field_name, requested_value in numeric_requests:
            if requested_value is None:
                continue
            requested_bucket = _numeric_bucket(field_name, requested_value)
            case_value = _selection_snapshot_value(prediction.selection_snapshot_json, field_name)
            checks.append((f"{field_name}_bucket={requested_bucket}", _numeric_bucket(field_name, case_value) == requested_bucket))
        return checks

    @staticmethod
    def _criteria_count(request: SimilarSetupRequest) -> int:
        return sum(
            (
                bool(request.symbol and request.symbol.strip()),
                bool(request.category and request.category.strip()),
                bool(request.setup_type and request.setup_type.strip()),
                bool(request.trend_state and request.trend_state.strip()),
                bool(request.extension_state and request.extension_state.strip()),
                bool(request.trigger_state and request.trigger_state.strip()),
                bool(request.blocked_by and request.blocked_by.strip()),
                len([flag for flag in request.risk_flags if str(flag).strip()]),
                bool(request.market_regime and request.market_regime.strip()),
                request.price_vs_ema200_pct is not None,
                request.support_distance_pct is not None,
                request.resistance_room_pct is not None,
            )
        )

    @staticmethod
    def _performance_metrics(evaluable_cases: list[SimilarSetupEvidenceCase]) -> dict[str, float | None]:
        success_count = sum(1 for case in evaluable_cases if case.outcome_label == "success")
        failure_count = sum(1 for case in evaluable_cases if case.outcome_label == "failure")
        returns = [case.return_pct for case in evaluable_cases if case.return_pct is not None]
        relative_returns = [case.relative_to_spy for case in evaluable_cases if case.relative_to_spy is not None]
        return {
            "success_rate": round(success_count / len(evaluable_cases) * 100.0, 2),
            "failure_rate": round(failure_count / len(evaluable_cases) * 100.0, 2),
            "average_return": round(sum(returns) / len(returns), 4) if returns else None,
            "average_relative_return": round(sum(relative_returns) / len(relative_returns), 4) if relative_returns else None,
        }

    @staticmethod
    def _common_failure_modes(evaluable_cases: list[SimilarSetupEvidenceCase]) -> list[HistoricalEvidenceFrequency]:
        failed_cases = [case for case in evaluable_cases if case.outcome_label == "failure"]
        values: list[tuple[str, str]] = []
        for case in failed_cases:
            values.append(("outcome_label", case.outcome_label))
            values.append(("blocked_by", case.blocked_by or "none"))
            values.append(("attribution_label", case.attribution_label or "unattributed"))
            values.append(("selection_market_regime", case.selection_market_regime or "unavailable"))
        return _frequency_rows(values, denominator=len(failed_cases))

    @staticmethod
    def _common_success_conditions(evaluable_cases: list[SimilarSetupEvidenceCase]) -> list[HistoricalEvidenceFrequency]:
        successful_cases = [case for case in evaluable_cases if case.outcome_label == "success"]
        values: list[tuple[str, str]] = []
        for case in successful_cases:
            values.extend(("category", category) for category in case.categories)
            values.extend(
                (
                    ("setup_type", case.setup_type or "unknown"),
                    ("trend_state", case.trend_state or "unknown"),
                    ("extension_state", case.extension_state or "unknown"),
                    ("trigger_state", case.trigger_state or "unknown"),
                    ("selection_market_regime", case.selection_market_regime or "unavailable"),
                )
            )
        return _frequency_rows(values, denominator=len(successful_cases))

    def _build_caveats(
        self,
        *,
        source_cases_count: int,
        similar_cases: list[SimilarSetupEvidenceCase],
        evaluable_cases: list[SimilarSetupEvidenceCase],
        data_quality_excluded_count: int,
        as_of_date: date,
        horizon_days: int,
    ) -> list[str]:
        caveats = [
            "Historical evidence is descriptive and is not a buy, sell, hold, or rule-change recommendation.",
            f"Only selections and observed outcome dates before {as_of_date.isoformat()} are eligible, preventing future-outcome leakage.",
        ]
        if len(evaluable_cases) < self.min_sample_size:
            caveats.append(
                f"Performance aggregates are withheld: {len(evaluable_cases)} evaluable {horizon_days}D cases are below the minimum sample size of {self.min_sample_size}."
            )
        if data_quality_excluded_count:
            caveats.append(
                f"{data_quality_excluded_count} similar cases are excluded from performance metrics because their outcomes are data-quality-excluded."
            )
        incomplete_paths = sum(1 for case in evaluable_cases if not case.daily_snapshot_path_complete)
        if incomplete_paths:
            caveats.append(
                f"{incomplete_paths} evaluable cases have incomplete daily snapshot paths; horizon outcomes remain independently measured."
            )
        if source_cases_count >= self.source_limit:
            caveats.append(
                f"The source retrieval window reached its {self.source_limit}-record cap; older matching records may be omitted."
            )
        symbol_counts = Counter(case.symbol for case in evaluable_cases)
        if symbol_counts and max(symbol_counts.values()) / len(evaluable_cases) >= 0.5:
            dominant_symbol, dominant_count = symbol_counts.most_common(1)[0]
            caveats.append(
                f"Evidence is concentrated in {dominant_symbol}: {dominant_count}/{len(evaluable_cases)} evaluable cases."
            )
        if not similar_cases:
            caveats.append("No historical cases met the requested deterministic similarity criteria.")
        return caveats

    @staticmethod
    def _build_evidence_summary(
        *,
        evaluable_cases: list[SimilarSetupEvidenceCase],
        sample_size_sufficient: bool,
        performance: dict[str, float | None],
        horizon_days: int,
    ) -> list[str]:
        if not evaluable_cases:
            return [f"No evaluable {horizon_days}D outcomes were retrieved for the requested similarity criteria."]
        if not sample_size_sufficient:
            return [
                f"Retrieved {len(evaluable_cases)} evaluable {horizon_days}D outcomes; the configured minimum sample size has not been reached."
            ]
        return [
            "Retrieved "
            f"{len(evaluable_cases)} evaluable {horizon_days}D outcomes: "
            f"success_rate={performance['success_rate']}%, "
            f"failure_rate={performance['failure_rate']}%, "
            f"average_return={performance['average_return']}%."
        ]


def _frequency_rows(values: list[tuple[str, str]], *, denominator: int) -> list[HistoricalEvidenceFrequency]:
    if denominator <= 0:
        return []
    counts = Counter(values)
    return [
        HistoricalEvidenceFrequency(
            kind=kind,
            value=value,
            count=count,
            share_pct=round(count / denominator * 100.0, 2),
        )
        for (kind, value), count in sorted(counts.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))[:5]
    ]


def _selection_snapshot_value(snapshot: dict[str, Any], field_name: str) -> float | None:
    structure = snapshot.get("selected_structure_snapshot") if isinstance(snapshot, dict) else None
    values = [
        structure.get(field_name) if isinstance(structure, dict) else None,
        snapshot.get(field_name) if isinstance(snapshot, dict) else None,
    ]
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _numeric_bucket(field_name: str, value: float | None) -> str | None:
    if value is None:
        return None
    numeric_value = float(value)
    if field_name == "price_vs_ema200":
        if numeric_value <= -20:
            return "<=-20"
        if numeric_value <= -10:
            return "-20_to_-10"
        if numeric_value <= 0:
            return "-10_to_0"
        if numeric_value <= 10:
            return "0_to_10"
        if numeric_value <= 25:
            return "10_to_25"
        return ">25"
    if field_name == "support_distance":
        if numeric_value <= 2:
            return "<=2"
        if numeric_value <= 5:
            return "2_to_5"
        if numeric_value <= 10:
            return "5_to_10"
        return ">10"
    if field_name == "resistance_room":
        if numeric_value <= 5:
            return "<=5"
        if numeric_value <= 10:
            return "5_to_10"
        if numeric_value <= 20:
            return "10_to_20"
        return ">20"
    return None


def _normalized(value: Any) -> str:
    return str(value or "").strip().lower()
