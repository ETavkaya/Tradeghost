from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from tradeghost.services.intelligence.service import IntelligenceService
from tradeghost.shared.models.schemas import (
    OutcomeRecord,
    PatternCandidateStatus,
    PatternDiscoveryRequest,
    PatternReviewRequest,
    PredictionRecord,
)


class FakeResearchRecordStore:
    configured = True

    def __init__(self, cases) -> None:
        self.cases = cases
        self.patterns = {}

    def list_historical_evidence_cases(self, **kwargs):
        return self.cases

    def create_pattern_candidates(self, records):
        created = 0
        persisted = []
        for record in records:
            existing = next(
                (value for value in self.patterns.values() if value.idempotency_key == record.idempotency_key),
                None,
            )
            if existing is None:
                self.patterns[record.id] = record
                existing = record
                created += 1
            persisted.append(existing)
        return persisted, created

    def get_pattern_candidate(self, pattern_candidate_id):
        return self.patterns.get(pattern_candidate_id)

    def transition_pattern_candidate(
        self,
        pattern_candidate_id,
        *,
        allowed_current_statuses,
        new_status,
        reviewer_id,
        reviewer_notes,
        action,
        details=None,
    ):
        record = self.patterns[pattern_candidate_id]
        assert record.status in allowed_current_statuses
        updated = record.model_copy(
            update={
                "status": new_status,
                "reviewed_by": reviewer_id,
                "review_notes": reviewer_notes,
                "reviewed_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        )
        self.patterns[pattern_candidate_id] = updated
        return updated


def _case(
    case_number: int,
    *,
    category: str,
    successful: bool,
    observed_date: date,
    evaluable: bool = True,
):
    token = f"{case_number:012d}"
    prediction = PredictionRecord(
        id=f"11111111-1111-4111-8111-{token}",
        idempotency_key=f"prediction-{case_number}",
        payload_hash=f"prediction-hash-{case_number}",
        cohort_id=f"22222222-2222-4222-8222-{case_number % 4:012d}",
        symbol=f"SYM{case_number % 4}",
        market="us",
        selected_at=datetime(2022, 12, 1, tzinfo=UTC),
        selected_date=date(2022, 12, 1),
        selected_price=100.0,
        categories=[category],
        setup_type="pullback",
        trend_state="bullish_trend",
        trigger_state="confirmed",
        blocked_by="none",
        prediction_type="follow_through_watch",
        rule_version="scanner_rules_v1",
        feature_version="scanner_features_v1",
        data_version="market_data_daily_v1",
        created_at=datetime(2022, 12, 1, tzinfo=UTC),
    )
    outcome = OutcomeRecord(
        id=f"33333333-3333-4333-8333-{token}",
        idempotency_key=f"outcome-{case_number}",
        payload_hash=f"outcome-hash-{case_number}",
        prediction_id=prediction.id,
        cohort_id=prediction.cohort_id,
        symbol=prediction.symbol,
        market="us",
        horizon_days=28,
        selection_date=prediction.selected_date,
        outcome_date=observed_date if evaluable else None,
        evaluated_at=datetime.combine(observed_date, datetime.min.time(), tzinfo=UTC),
        outcome_status="available" if evaluable else "pending",
        outcome_label="success" if successful and evaluable else "failure",
        return_pct=8.0 if successful and evaluable else (-3.0 if evaluable else None),
        categories=[category],
        setup_type="pullback",
        blocked_by="none",
        evaluator_version="outcome_evaluator_v2",
        rule_version="scanner_rules_v1",
        feature_version="scanner_features_v1",
        data_version="market_data_daily_v1",
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
    )
    return prediction, outcome, "risk_on"


def _qualified_cases():
    cases = []
    start = date(2023, 1, 3)
    for index in range(40):
        cases.append(
            _case(
                index + 1,
                category="trend_mode",
                successful=True,
                observed_date=start + timedelta(days=index),
            )
        )
        cases.append(
            _case(
                100 + index,
                category="build_up",
                successful=index < 15 or index >= 30 and index < 33,
                observed_date=start + timedelta(days=index),
            )
        )
    return cases


def test_pattern_discovery_requires_statistics_then_human_retrieval_approval() -> None:
    service = IntelligenceService()
    store = FakeResearchRecordStore(_qualified_cases())
    service.research_record_store = store

    response = service.discover_pattern_candidates(
        PatternDiscoveryRequest(as_of_date=date(2025, 1, 1))
    )

    pattern = next(
        record
        for record in response.patterns
        if record.condition_set == {"category": "trend_mode", "setup_type": "pullback"}
    )
    assert pattern.sample_size == 40
    assert pattern.evaluable_case_count == 40
    assert pattern.approval_eligible is True
    assert pattern.status == PatternCandidateStatus.CANDIDATE
    assert pattern.metrics_json["validation"]["effect_size_pct_points"] >= 10.0
    assert pattern.metrics_json["validation"]["two_proportion_p_value"] <= 0.05

    approved = service.approve_pattern_candidate(
        pattern.id,
        PatternReviewRequest(reviewer_id="reviewer@example.com", reviewer_notes="Statistical checks reviewed."),
    )

    assert approved.status == PatternCandidateStatus.APPROVED_FOR_RETRIEVAL
    assert approved.rule_version == "scanner_rules_v1"
    assert approved.reviewed_by == "reviewer@example.com"


def test_pattern_discovery_rejects_incomplete_evaluable_coverage() -> None:
    start = date(2023, 1, 3)
    cases = [
        _case(
            index + 1,
            category="trend_mode",
            successful=True,
            observed_date=start + timedelta(days=index),
            evaluable=index < 23,
        )
        for index in range(30)
    ]
    service = IntelligenceService()
    service.research_record_store = FakeResearchRecordStore(cases)

    response = service.discover_pattern_candidates(PatternDiscoveryRequest(as_of_date=date(2025, 1, 1)))

    assert response.candidate_count == 0
    assert any("No condition grouping met" in caveat for caveat in response.caveats)
