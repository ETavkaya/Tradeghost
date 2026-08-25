from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from tradeghost.services.intelligence.service import IntelligenceService
from tradeghost.shared.models.schemas import (
    HypothesisBacktestRequest,
    HypothesisGeneratedBy,
    HypothesisReviewRequest,
    HypothesisTemporalSplit,
    OutcomeRecord,
    PredictionRecord,
    RuleHypothesisCreateRequest,
    RuleHypothesisStatus,
    StrategyMode,
)


class FakeResearchRecordStore:
    configured = True

    def __init__(self, prediction: PredictionRecord, outcome: OutcomeRecord) -> None:
        self.predictions = {prediction.id: prediction}
        self.outcomes = {outcome.id: outcome}
        self.hypotheses = {}
        self.validations = {}

    def get_predictions_by_ids(self, prediction_ids):
        return [self.predictions[record_id] for record_id in prediction_ids if record_id in self.predictions]

    def get_outcomes_by_ids(self, outcome_ids):
        return [self.outcomes[record_id] for record_id in outcome_ids if record_id in self.outcomes]

    def create_rule_hypothesis(self, record):
        existing = next(
            (value for value in self.hypotheses.values() if value.idempotency_key == record.idempotency_key),
            None,
        )
        if existing is not None:
            return existing, False
        self.hypotheses[record.id] = record
        return record, True

    def get_rule_hypothesis(self, hypothesis_id):
        return self.hypotheses.get(hypothesis_id)

    def list_rule_hypotheses(self, status=None):
        return [record for record in self.hypotheses.values() if status is None or record.status == status]

    def get_hypothesis_validation_by_input_hash(self, hypothesis_id, input_hash):
        return next(
            (
                value
                for value in self.validations.values()
                if value.hypothesis_id == hypothesis_id and value.input_hash == input_hash
            ),
            None,
        )

    def get_hypothesis_validation_run(self, validation_id):
        return self.validations.get(validation_id)

    def create_hypothesis_validation_run(self, record):
        existing = self.get_hypothesis_validation_by_input_hash(record.hypothesis_id, record.input_hash)
        if existing is not None:
            return existing, False
        self.validations[record.id] = record
        return record, True

    def complete_hypothesis_validation_run(self, record):
        self.validations[record.id] = record
        return record

    def transition_rule_hypothesis(
        self,
        hypothesis_id,
        *,
        allowed_current_statuses,
        new_status,
        reviewer_id,
        reviewer_notes="",
        latest_validation_id=None,
        action,
        details=None,
    ):
        current = self.hypotheses[hypothesis_id]
        if current.status not in allowed_current_statuses:
            raise ValueError("invalid fake lifecycle transition")
        updated = current.model_copy(
            update={
                "status": new_status,
                "reviewed_by": reviewer_id,
                "review_notes": reviewer_notes,
                "reviewed_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "latest_validation_id": latest_validation_id or current.latest_validation_id,
            }
        )
        self.hypotheses[hypothesis_id] = updated
        return updated


class FakeBacktestEngine:
    def __init__(self) -> None:
        self.calls = []

    def run(self, ticker, **kwargs):
        self.calls.append((ticker, kwargs))
        candidate = kwargs.get("score_threshold") is not None
        return SimpleNamespace(
            ticker=ticker,
            period_start=kwargs["evaluation_start"],
            period_end=kwargs["evaluation_end"],
            trades=40,
            win_rate=60.0 if candidate else 55.0,
            average_return=4.0 if candidate else 3.0,
            max_drawdown=8.0 if candidate else 10.0,
            average_hold_days=7.0,
            expectancy=2.0 if candidate else 1.0,
            score_threshold_used=70.0 if candidate else 60.0,
            strategy_mode_used=StrategyMode.BALANCED,
            analysis_config=SimpleNamespace(model_dump=lambda mode: {"score_threshold": 70.0 if candidate else 60.0}),
            generated_at=datetime(2026, 8, 20, tzinfo=UTC),
        )


def _prediction() -> PredictionRecord:
    return PredictionRecord(
        id="11111111-1111-4111-8111-000000000001",
        idempotency_key="prediction-1",
        payload_hash="prediction-hash",
        cohort_id="22222222-2222-4222-8222-000000000001",
        symbol="AAA",
        market="us",
        selected_at=datetime(2025, 1, 2, tzinfo=UTC),
        selected_date=date(2025, 1, 2),
        selected_price=100.0,
        categories=["trend_mode"],
        setup_type="pullback",
        blocked_by="none",
        prediction_type="follow_through_watch",
        rule_version="scanner_rules_v1",
        feature_version="scanner_features_v1",
        data_version="market_data_daily_v1",
        created_at=datetime(2025, 1, 2, tzinfo=UTC),
    )


def _outcome(prediction: PredictionRecord) -> OutcomeRecord:
    return OutcomeRecord(
        id="33333333-3333-4333-8333-000000000001",
        idempotency_key="outcome-1",
        payload_hash="outcome-hash",
        prediction_id=prediction.id,
        cohort_id=prediction.cohort_id,
        symbol=prediction.symbol,
        market="us",
        horizon_days=28,
        selection_date=prediction.selected_date,
        outcome_date=date(2025, 2, 10),
        evaluated_at=datetime(2025, 2, 11, tzinfo=UTC),
        outcome_status="available",
        outcome_label="failure",
        return_pct=-3.0,
        false_positive=True,
        categories=prediction.categories,
        setup_type=prediction.setup_type,
        blocked_by=prediction.blocked_by,
        evaluator_version="outcome_evaluator_v2",
        rule_version=prediction.rule_version,
        feature_version=prediction.feature_version,
        data_version=prediction.data_version,
        created_at=datetime(2025, 2, 11, tzinfo=UTC),
    )


def _request(prediction: PredictionRecord, outcome: OutcomeRecord) -> RuleHypothesisCreateRequest:
    return RuleHypothesisCreateRequest(
        title="Raise threshold for repeated false positives",
        hypothesis_text="A higher sandbox threshold may reduce repeated false-positive pullback selections.",
        expected_metric="Improve expectancy without increasing maximum drawdown.",
        evidence_prediction_ids=[prediction.id],
        evidence_outcome_ids=[outcome.id],
        affected_conditions={"category": "trend_mode", "setup_type": "pullback"},
        suggested_rule_change="Test a 70-point score threshold in the isolated backtest sandbox.",
        proposed_config_patch={"score_threshold": 70.0},
        affected_universe={"market": "us", "symbols": ["AAA"]},
        temporal_split=HypothesisTemporalSplit(
            train_start=date(2021, 1, 4),
            train_end=date(2022, 12, 30),
            validation_start=date(2023, 1, 3),
            validation_end=date(2023, 12, 29),
            out_of_sample_start=date(2024, 1, 2),
            out_of_sample_end=date(2024, 12, 31),
        ),
        submitted_by="researcher@example.com",
    )


def test_hypothesis_validation_is_frozen_human_gated_and_never_mutates_scanner() -> None:
    prediction = _prediction()
    outcome = _outcome(prediction)
    service = IntelligenceService()
    store = FakeResearchRecordStore(prediction, outcome)
    engine = FakeBacktestEngine()
    service.research_record_store = store
    service.backtest_engine = engine

    hypothesis = service.create_rule_hypothesis(_request(prediction, outcome))

    assert hypothesis.status == RuleHypothesisStatus.EVIDENCE_READY
    assert hypothesis.evidence_json["prediction_ids"] == [prediction.id]
    assert hypothesis.evidence_json["outcomes"][0]["false_positive"] is True
    assert hypothesis.candidate_rule_version.startswith("scanner_rules_v1:candidate:")

    validation = service.run_rule_hypothesis_backtest(
        hypothesis.id,
        HypothesisBacktestRequest(symbols=["AAA"], minimum_total_trades=30),
    )

    assert validation.validation_status == "completed"
    assert validation.qualified_for_review is True
    assert len(engine.calls) == 6
    assert all("evaluation_start" in kwargs and "evaluation_end" in kwargs for _, kwargs in engine.calls)
    assert all(call[1]["score_threshold"] == 70.0 for call in engine.calls[1::2])

    approved = service.approve_rule_hypothesis(
        hypothesis.id,
        HypothesisReviewRequest(reviewer_id="reviewer@example.com", reviewer_notes="Reviewed frozen comparison."),
    )

    assert approved.status == RuleHypothesisStatus.APPROVED_FOR_RELEASE
    assert approved.reviewed_by == "reviewer@example.com"
    assert approved.rule_version == "scanner_rules_v1"
    assert all("production_config_mutated" not in kwargs for _, kwargs in engine.calls)


def test_llm_cannot_persist_rule_hypothesis() -> None:
    prediction = _prediction()
    outcome = _outcome(prediction)
    service = IntelligenceService()
    service.research_record_store = FakeResearchRecordStore(prediction, outcome)
    request = _request(prediction, outcome).model_copy(update={"generated_by": HypothesisGeneratedBy.LLM_SUMMARY})

    with pytest.raises(ValueError, match="LLM summaries are advisory only"):
        service.create_rule_hypothesis(request)
