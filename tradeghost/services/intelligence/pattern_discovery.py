from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from tradeghost.services.intelligence.research_record_store import ResearchRecordStore
from tradeghost.shared.models.schemas import (
    OutcomeRecord,
    PatternCandidate,
    PatternCandidateStatus,
    PatternDiscoveryRequest,
    PatternDiscoveryResponse,
    PredictionRecord,
)


PATTERN_STATISTICS_VERSION = "pattern_discovery_v1"
MIN_TRAIN_CASES = 20
MIN_VALIDATION_CASES = 10
PATTERN_FACET_SETS = (
    ("category", "setup_type"),
    ("category", "setup_type", "selection_market_regime"),
    ("setup_type", "trend_state", "trigger_state"),
    ("blocked_by", "selection_market_regime"),
)


@dataclass(frozen=True)
class _EvidenceCase:
    prediction: PredictionRecord
    outcome: OutcomeRecord
    selection_market_regime: str | None
    observed_date: date

    @property
    def evaluable(self) -> bool:
        return self.outcome.outcome_status == "available" and self.outcome.return_pct is not None


class PatternDiscoveryService:
    def __init__(
        self,
        *,
        record_store: ResearchRecordStore,
        min_sample_size: int,
        min_evaluable_ratio: float,
        min_distinct_cohorts: int,
        max_symbol_concentration: float,
        min_effect_size_pct_points: float,
        max_p_value: float,
        source_limit: int,
    ) -> None:
        self.record_store = record_store
        self.min_sample_size = max(30, int(min_sample_size))
        self.min_evaluable_ratio = min(1.0, max(0.8, float(min_evaluable_ratio)))
        self.min_distinct_cohorts = max(3, int(min_distinct_cohorts))
        self.max_symbol_concentration = min(0.5, max(0.01, float(max_symbol_concentration)))
        self.min_effect_size_pct_points = max(0.0, float(min_effect_size_pct_points))
        self.max_p_value = min(0.05, max(0.0001, float(max_p_value)))
        self.source_limit = max(1, min(int(source_limit), 5000))

    def discover(self, request: PatternDiscoveryRequest) -> PatternDiscoveryResponse:
        as_of_date = request.as_of_date or date.today()
        source_rows = self.record_store.list_historical_evidence_cases(
            market=request.market.value,
            as_of_date=as_of_date,
            horizon_days=request.horizon_days,
            limit=self.source_limit,
        )
        source_cases = [self._to_evidence_case(row) for row in source_rows]
        version_groups: dict[tuple[str, str, str], list[_EvidenceCase]] = defaultdict(list)
        for case in source_cases:
            version_groups[
                (
                    case.outcome.rule_version,
                    case.outcome.feature_version,
                    case.outcome.data_version,
                )
            ].append(case)

        candidates: list[PatternCandidate] = []
        for versions, version_cases in sorted(version_groups.items()):
            candidates.extend(
                self._discover_version_group(
                    cases=version_cases,
                    market=request.market.value,
                    horizon_days=request.horizon_days,
                    as_of_date=as_of_date,
                    rule_version=versions[0],
                    feature_version=versions[1],
                    data_version=versions[2],
                )
            )
        candidates.sort(key=lambda item: (-item.sample_size, item.pattern_key, item.id))
        persisted, created_count = self.record_store.create_pattern_candidates(candidates)
        caveats = [
            "Pattern candidates are descriptive statistical records, not trade instructions or scanner-rule changes.",
            "Only observed Outcomes before the as-of date are used; data-quality-excluded and unavailable outcomes are excluded from performance metrics.",
            "Candidate discovery does not create Neo4j Pattern nodes or alter production configuration. Human approval only permits read-only retrieval use.",
        ]
        if len(source_rows) >= self.source_limit:
            caveats.append(
                f"The source retrieval reached its {self.source_limit}-record cap; older eligible outcomes may be omitted."
            )
        if not candidates:
            caveats.append("No condition grouping met the fixed sample, coverage, concentration, and holdout requirements.")
        return PatternDiscoveryResponse(
            market=request.market.value,
            horizon_days=request.horizon_days,
            as_of_date=as_of_date,
            source_case_count=len(source_cases),
            evaluable_case_count=sum(1 for case in source_cases if case.evaluable),
            candidate_count=len(persisted),
            created_candidate_count=created_count,
            thresholds=self.thresholds,
            caveats=caveats,
            patterns=persisted,
        )

    @property
    def thresholds(self) -> dict[str, Any]:
        return {
            "min_sample_size": self.min_sample_size,
            "min_evaluable_ratio": self.min_evaluable_ratio,
            "min_distinct_cohorts": self.min_distinct_cohorts,
            "max_symbol_concentration": self.max_symbol_concentration,
            "min_train_cases": MIN_TRAIN_CASES,
            "min_validation_cases": MIN_VALIDATION_CASES,
            "min_effect_size_pct_points": self.min_effect_size_pct_points,
            "max_two_proportion_p_value": self.max_p_value,
            "statistics_version": PATTERN_STATISTICS_VERSION,
        }

    @staticmethod
    def _to_evidence_case(row: tuple[PredictionRecord, OutcomeRecord, str | None]) -> _EvidenceCase:
        prediction, outcome, selection_regime = row
        return _EvidenceCase(
            prediction=prediction,
            outcome=outcome,
            selection_market_regime=selection_regime,
            observed_date=outcome.outcome_date or outcome.evaluated_at.date(),
        )

    def _discover_version_group(
        self,
        *,
        cases: list[_EvidenceCase],
        market: str,
        horizon_days: int,
        as_of_date: date,
        rule_version: str,
        feature_version: str,
        data_version: str,
    ) -> list[PatternCandidate]:
        groups: dict[tuple[tuple[str, str], ...], list[_EvidenceCase]] = defaultdict(list)
        for case in cases:
            for condition_set in self._condition_sets(case):
                groups[tuple(sorted(condition_set.items()))].append(case)

        records: list[PatternCandidate] = []
        for signature, grouped_cases in sorted(groups.items()):
            record = self._build_candidate(
                cases=cases,
                grouped_cases=grouped_cases,
                condition_set=dict(signature),
                market=market,
                horizon_days=horizon_days,
                as_of_date=as_of_date,
                rule_version=rule_version,
                feature_version=feature_version,
                data_version=data_version,
            )
            if record is not None:
                records.append(record)
        return records

    @staticmethod
    def _condition_sets(case: _EvidenceCase) -> list[dict[str, str]]:
        prediction = case.prediction
        common = {
            "setup_type": _normalized(prediction.setup_type),
            "trend_state": _normalized(prediction.trend_state),
            "trigger_state": _normalized(prediction.trigger_state),
            "blocked_by": _normalized(prediction.blocked_by or "none"),
            "selection_market_regime": _normalized(case.selection_market_regime or "unavailable"),
        }
        categories = sorted({_normalized(category) for category in prediction.categories if _normalized(category)})
        condition_sets: list[dict[str, str]] = []
        for category in categories:
            values = {**common, "category": category}
            for facets in PATTERN_FACET_SETS:
                selected = {facet: values[facet] for facet in facets if values.get(facet)}
                if len(selected) == len(facets):
                    condition_sets.append(selected)
        return condition_sets

    def _build_candidate(
        self,
        *,
        cases: list[_EvidenceCase],
        grouped_cases: list[_EvidenceCase],
        condition_set: dict[str, str],
        market: str,
        horizon_days: int,
        as_of_date: date,
        rule_version: str,
        feature_version: str,
        data_version: str,
    ) -> PatternCandidate | None:
        sample_size = len(grouped_cases)
        evaluable_cases = [case for case in grouped_cases if case.evaluable]
        evaluable_ratio = len(evaluable_cases) / sample_size if sample_size else 0.0
        if sample_size < self.min_sample_size or evaluable_ratio < self.min_evaluable_ratio:
            return None
        cohort_count = len({case.prediction.cohort_id for case in evaluable_cases})
        symbol_concentration = self._symbol_concentration(evaluable_cases)
        if cohort_count < self.min_distinct_cohorts or symbol_concentration > self.max_symbol_concentration:
            return None

        candidate_train, candidate_validation, cutoff_date = self._chronological_split(evaluable_cases)
        if len(candidate_train) < MIN_TRAIN_CASES or len(candidate_validation) < MIN_VALIDATION_CASES:
            return None
        candidate_ids = {case.outcome.id for case in evaluable_cases}
        comparator_cases = [
            case for case in cases if case.evaluable and case.outcome.id not in candidate_ids
        ]
        comparator_train = [case for case in comparator_cases if case.observed_date <= cutoff_date]
        comparator_validation = [case for case in comparator_cases if case.observed_date > cutoff_date]
        if len(comparator_train) < MIN_TRAIN_CASES or len(comparator_validation) < MIN_VALIDATION_CASES:
            return None

        overall_metrics = self._metrics(evaluable_cases)
        train_candidate_metrics = self._metrics(candidate_train)
        validation_candidate_metrics = self._metrics(candidate_validation)
        train_baseline_metrics = self._metrics(comparator_train)
        validation_baseline_metrics = self._metrics(comparator_validation)
        validation_effect = round(
            validation_candidate_metrics["success_rate_pct"] - validation_baseline_metrics["success_rate_pct"],
            4,
        )
        validation_return_effect = round(
            validation_candidate_metrics["average_return_pct"] - validation_baseline_metrics["average_return_pct"],
            4,
        )
        train_effect = round(
            train_candidate_metrics["success_rate_pct"] - train_baseline_metrics["success_rate_pct"],
            4,
        )
        p_value = _two_proportion_p_value(
            successes_a=validation_candidate_metrics["success_count"],
            total_a=validation_candidate_metrics["sample_size"],
            successes_b=validation_baseline_metrics["success_count"],
            total_b=validation_baseline_metrics["sample_size"],
        )
        approval_eligible = (
            train_effect >= self.min_effect_size_pct_points
            and validation_effect >= self.min_effect_size_pct_points
            and validation_return_effect >= 0.0
            and p_value is not None
            and p_value <= self.max_p_value
            and validation_candidate_metrics["confidence_interval_low_pct"]
            > validation_baseline_metrics["success_rate_pct"]
        )
        pattern_key = "|".join(f"{key}={value}" for key, value in sorted(condition_set.items()))
        population_definition = {
            "market": market,
            "horizon_days": horizon_days,
            "condition_set": condition_set,
            "comparator": "evaluable cases with matching market, horizon, and versions that do not match the condition set",
            "outcome_inclusion": "outcome_status=available and return_pct is not null",
            "as_of_date": as_of_date,
        }
        metrics_json = {
            "overall": overall_metrics,
            "train": {"candidate": train_candidate_metrics, "baseline": train_baseline_metrics, "effect_size_pct_points": train_effect},
            "validation": {
                "candidate": validation_candidate_metrics,
                "baseline": validation_baseline_metrics,
                "effect_size_pct_points": validation_effect,
                "average_return_effect_pct": validation_return_effect,
                "two_proportion_p_value": p_value,
            },
            "evaluable_ratio": round(evaluable_ratio, 4),
            "distinct_cohort_count": cohort_count,
            "max_symbol_concentration": round(symbol_concentration, 4),
            "split_cutoff_date": cutoff_date,
            "thresholds": self.thresholds,
        }
        payload_body = {
            "pattern_key": pattern_key,
            "market": market,
            "horizon_days": horizon_days,
            "condition_set": condition_set,
            "population_definition": population_definition,
            "metrics": metrics_json,
            "source_prediction_ids": sorted(case.prediction.id for case in grouped_cases),
            "source_outcome_ids": sorted(case.outcome.id for case in grouped_cases),
            "rule_version": rule_version,
            "feature_version": feature_version,
            "data_version": data_version,
            "statistics_version": PATTERN_STATISTICS_VERSION,
            "as_of_date": as_of_date,
        }
        payload_hash = _stable_hash(payload_body)
        idempotency_key = (
            f"pattern-candidate:{market}:{horizon_days}:{rule_version}:{feature_version}:{data_version}:"
            f"{as_of_date.isoformat()}:{_stable_hash(condition_set)}:{PATTERN_STATISTICS_VERSION}"
        )
        now = datetime.now(UTC)
        return PatternCandidate(
            id=str(uuid5(NAMESPACE_URL, f"tradeghost:{idempotency_key}")),
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            pattern_key=pattern_key,
            market=market,
            horizon_days=horizon_days,
            condition_set=condition_set,
            population_definition=population_definition,
            metrics_json=metrics_json,
            source_prediction_ids=payload_body["source_prediction_ids"],
            source_outcome_ids=payload_body["source_outcome_ids"],
            sample_size=sample_size,
            evaluable_case_count=len(evaluable_cases),
            success_count=overall_metrics["success_count"],
            success_rate_pct=overall_metrics["success_rate_pct"],
            average_return_pct=overall_metrics["average_return_pct"],
            effect_size_pct_points=validation_effect,
            p_value=p_value,
            confidence_interval_low_pct=overall_metrics["confidence_interval_low_pct"],
            confidence_interval_high_pct=overall_metrics["confidence_interval_high_pct"],
            approval_eligible=approval_eligible,
            status=PatternCandidateStatus.CANDIDATE,
            rule_version=rule_version,
            feature_version=feature_version,
            data_version=data_version,
            statistics_version=PATTERN_STATISTICS_VERSION,
            as_of_date=as_of_date,
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def _chronological_split(cases: list[_EvidenceCase]) -> tuple[list[_EvidenceCase], list[_EvidenceCase], date]:
        ordered = sorted(cases, key=lambda case: (case.observed_date, case.outcome.id))
        target_train = max(MIN_TRAIN_CASES, len(ordered) - MIN_VALIDATION_CASES)
        target_train = min(target_train, len(ordered) - MIN_VALIDATION_CASES)
        cutoff_date = ordered[target_train - 1].observed_date
        train = [case for case in ordered if case.observed_date <= cutoff_date]
        validation = [case for case in ordered if case.observed_date > cutoff_date]
        return train, validation, cutoff_date

    @staticmethod
    def _metrics(cases: list[_EvidenceCase]) -> dict[str, float | int]:
        success_count = sum(1 for case in cases if case.outcome.outcome_label == "success")
        sample_size = len(cases)
        success_rate = (success_count / sample_size * 100.0) if sample_size else 0.0
        returns = [float(case.outcome.return_pct) for case in cases if case.outcome.return_pct is not None]
        ci_low, ci_high = _wilson_interval(success_count, sample_size)
        return {
            "sample_size": sample_size,
            "success_count": success_count,
            "success_rate_pct": round(success_rate, 4),
            "average_return_pct": round(sum(returns) / len(returns), 4) if returns else 0.0,
            "confidence_interval_low_pct": round(ci_low * 100.0, 4),
            "confidence_interval_high_pct": round(ci_high * 100.0, 4),
        }

    @staticmethod
    def _symbol_concentration(cases: list[_EvidenceCase]) -> float:
        if not cases:
            return 1.0
        counts = Counter(case.prediction.symbol for case in cases)
        return max(counts.values()) / len(cases)


def _stable_hash(payload: Any) -> str:
    import hashlib

    return hashlib.sha256(
        json.dumps(payload, default=str, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def _wilson_interval(successes: int, total: int, z_score: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 0.0
    proportion = successes / total
    z_squared = z_score**2
    denominator = 1.0 + z_squared / total
    center = (proportion + z_squared / (2.0 * total)) / denominator
    margin = z_score * math.sqrt(
        (proportion * (1.0 - proportion) / total) + (z_squared / (4.0 * total**2))
    ) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def _two_proportion_p_value(*, successes_a: int, total_a: int, successes_b: int, total_b: int) -> float | None:
    if total_a <= 0 or total_b <= 0:
        return None
    pooled = (successes_a + successes_b) / (total_a + total_b)
    standard_error = math.sqrt(pooled * (1.0 - pooled) * ((1.0 / total_a) + (1.0 / total_b)))
    if standard_error == 0.0:
        return 0.0 if successes_a != successes_b else 1.0
    z_score = ((successes_a / total_a) - (successes_b / total_b)) / standard_error
    return round(math.erfc(abs(z_score) / math.sqrt(2.0)), 8)
