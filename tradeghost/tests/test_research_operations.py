from __future__ import annotations

from datetime import UTC, date, datetime

from tradeghost.services.intelligence.service import IntelligenceService
from tradeghost.shared.models.schemas import (
    CandidateCohort,
    CohortCoverageMonitorResponse,
    MarketCode,
    OutcomeRecord,
    OutcomeSummaryRecord,
    PredictionRecord,
    ScannerCategory,
    ScannerDuration,
)


class FakeResearchRecordStore:
    configured = True

    def __init__(self, prediction: PredictionRecord, outcome: OutcomeRecord, summary: OutcomeSummaryRecord) -> None:
        self.prediction = prediction
        self.outcome = outcome
        self.summary = summary

    def list_predictions(self, cohort_id: str):
        return [self.prediction] if cohort_id == self.prediction.cohort_id else []

    def list_outcomes(self, cohort_id: str, horizon_days: int | None = None):
        if cohort_id != self.outcome.cohort_id or horizon_days not in {None, 28}:
            return []
        return [self.outcome]

    def list_outcome_summaries(self, cohort_id: str):
        return [self.summary] if cohort_id == self.summary.cohort_id else []

    def list_rule_hypotheses(self):
        return []

    def list_pattern_candidates(self):
        return []


def test_research_dashboard_keeps_28d_outcome_separate_from_daily_path_and_exports_audit() -> None:
    cohort_id = "22222222-2222-4222-8222-000000000001"
    cohort = CandidateCohort(
        id=cohort_id,
        name="Research operations cohort",
        start_date=date(2026, 5, 13),
        market=MarketCode.US,
        analysis_window=ScannerDuration.ONE_YEAR,
        selected_categories=[ScannerCategory.TREND_MODE],
        followup_enabled=True,
        followup_start_date=date(2026, 5, 13),
        followup_target_days=28,
    )
    prediction = PredictionRecord(
        id="11111111-1111-4111-8111-000000000001",
        idempotency_key="prediction-1",
        payload_hash="prediction-hash",
        cohort_id=cohort_id,
        symbol="AAA",
        market="us",
        selected_at=datetime(2026, 5, 13, tzinfo=UTC),
        selected_date=date(2026, 5, 13),
        selected_price=100.0,
        categories=["trend_mode"],
        setup_type="momentum_continuation",
        blocked_by="none",
        prediction_type="follow_through_watch",
        source_report_id="report-1",
        rule_version="scanner_rules_v1",
        feature_version="scanner_features_v1",
        data_version="market_data_daily_v1",
        created_at=datetime(2026, 5, 13, tzinfo=UTC),
    )
    outcome = OutcomeRecord(
        id="33333333-3333-4333-8333-000000000001",
        idempotency_key="outcome-1",
        payload_hash="outcome-hash",
        prediction_id=prediction.id,
        cohort_id=cohort_id,
        symbol="AAA",
        market="us",
        horizon_days=28,
        selection_date=prediction.selected_date,
        outcome_date=date(2026, 6, 20),
        evaluated_at=datetime(2026, 6, 20, tzinfo=UTC),
        outcome_status="available",
        outcome_label="success",
        return_pct=4.0,
        daily_snapshot_path_complete=False,
        daily_snapshot_coverage_pct=50.0,
        categories=prediction.categories,
        setup_type=prediction.setup_type,
        blocked_by=prediction.blocked_by,
        evaluator_version="outcome_evaluator_v2",
        rule_version=prediction.rule_version,
        feature_version=prediction.feature_version,
        data_version=prediction.data_version,
        created_at=datetime(2026, 6, 20, tzinfo=UTC),
    )
    summary = OutcomeSummaryRecord(
        cohort_id=cohort_id,
        grouping="category",
        group_value="trend_mode",
        horizon_days=28,
        prediction_count=1,
        available_outcome_count=1,
        average_return_pct=4.0,
        rule_version=prediction.rule_version,
        feature_version=prediction.feature_version,
        data_version=prediction.data_version,
        evaluator_version="outcome_evaluator_v2",
        calculated_at=datetime(2026, 6, 20, tzinfo=UTC),
    )
    coverage = CohortCoverageMonitorResponse(
        cohort_id=cohort_id,
        start_date=date(2026, 5, 13),
        evaluated_through=date(2026, 6, 20),
        expected_candidate_count=1,
        expected_followup_days=28,
        complete_followup_days=14,
        partial_followup_days=0,
        missing_followup_days=14,
        snapshot_coverage_pct=50.0,
        missing_followup_dates=[date(2026, 6, 2)],
        backfill_required=True,
        backfill_dates=[date(2026, 6, 2)],
        status="backfill_required",
        readiness_message="Backfill required for 14 trading day(s).",
    )

    service = IntelligenceService()
    service.research_record_store = FakeResearchRecordStore(prediction, outcome, summary)
    service.list_cohorts = lambda: [cohort]  # type: ignore[method-assign]
    coverage_calls = []

    def get_coverage(cohort_id_arg: str, **kwargs):
        coverage_calls.append((cohort_id_arg, kwargs))
        return coverage

    service.get_cohort_coverage = get_coverage  # type: ignore[method-assign]
    service.get_knowledge_graph_status = lambda: {"enabled": True, "neo4j_connected": True}  # type: ignore[method-assign]
    service._read_pipeline_events = lambda: []  # type: ignore[method-assign]
    service.list_cohort_daily_reports = lambda cohort_id_arg: []  # type: ignore[method-assign]

    dashboard = service.get_research_dashboard()

    readiness = dashboard.cohorts[0]
    assert readiness.horizon_28d_available_count == 1
    assert readiness.horizon_28d_complete is True
    assert readiness.daily_path_review_complete is False
    assert readiness.coverage.backfill_dates == [date(2026, 6, 2)]
    assert any(message.code == "daily_path_incomplete" for message in dashboard.operational_messages)
    assert coverage_calls == [(cohort_id, {"days_required": 28, "emit_event": False})]

    exported = service.export_research_audit(cohort_id)
    assert exported.cohort_id == cohort_id
    assert exported.payload["authority"]["llm"].startswith("advisory only")
    assert exported.payload["selected_cohort"]["horizon_28d_available_count"] == 1
