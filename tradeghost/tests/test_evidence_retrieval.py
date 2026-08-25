from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from tradeghost.services.intelligence.retrieval import SimilarSetupEvidenceService
from tradeghost.shared.models.schemas import (
    OutcomeRecord,
    PredictionRecord,
    SimilarSetupRequest,
    SimilarSetupSimilarityMode,
)


class FakeResearchRecordStore:
    def __init__(self, cases):
        self.cases = cases
        self.calls = []

    def list_historical_evidence_cases(self, **kwargs):
        self.calls.append(kwargs)
        return self.cases


def _prediction(case_number: int, *, matching: bool = True) -> PredictionRecord:
    token = f"{case_number:012d}"
    return PredictionRecord(
        id=f"11111111-1111-4111-8111-{token}",
        idempotency_key=f"prediction-{case_number}",
        payload_hash=f"prediction-hash-{case_number}",
        cohort_id=f"22222222-2222-4222-8222-{token}",
        symbol="AAA" if matching else "BBB",
        market="us",
        selected_at=datetime(2026, 1, 2, tzinfo=UTC),
        selected_date=date(2026, 1, 2),
        selected_price=100.0,
        categories=["trend_mode"] if matching else ["build_up"],
        setup_type="pullback" if matching else "breakout",
        trend_state="bullish_trend" if matching else "neutral",
        extension_state="normal",
        trigger_state="confirmed",
        blocked_by="none",
        risk_flags=["none"],
        prediction_type="follow_through_watch",
        invalidation_conditions={"confirmation": "close above trigger", "invalidation": "trend fails"},
        selection_snapshot_json={
            "selected_structure_snapshot": {
                "price_vs_ema200": 6.0,
                "support_distance": 3.0,
                "resistance_room": 12.0,
            }
        },
        rule_version="scanner_rules_v1",
        feature_version="scanner_features_v1",
        data_version="market_data_daily_v1",
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
    )


def _outcome(
    case_number: int,
    prediction_id: str,
    *,
    outcome_status: str = "available",
    outcome_label: str = "success",
    return_pct: float | None = 10.0,
    relative_to_spy: float | None = 5.0,
    daily_snapshot_path_complete: bool = True,
) -> OutcomeRecord:
    token = f"{case_number:012d}"
    return OutcomeRecord(
        id=f"33333333-3333-4333-8333-{token}",
        idempotency_key=f"outcome-{case_number}",
        payload_hash=f"outcome-hash-{case_number}",
        prediction_id=prediction_id,
        cohort_id=f"22222222-2222-4222-8222-{token}",
        symbol="AAA",
        market="us",
        horizon_days=28,
        selection_date=date(2026, 1, 2),
        outcome_date=date(2026, 2, 10),
        evaluated_at=datetime(2026, 2, 11, tzinfo=UTC),
        outcome_status=outcome_status,
        outcome_label=outcome_label,
        return_pct=return_pct,
        directional_return_pct=return_pct,
        daily_snapshot_path_complete=daily_snapshot_path_complete,
        daily_snapshot_coverage_pct=100.0 if daily_snapshot_path_complete else 50.0,
        categories=["trend_mode"],
        setup_type="pullback",
        blocked_by="none",
        attribution_label="stock_specific_move",
        relative_to_spy=relative_to_spy,
        evaluator_version="outcome_evaluator_v2",
        rule_version="scanner_rules_v1",
        feature_version="scanner_features_v1",
        data_version="market_data_daily_v1",
        created_at=datetime(2026, 2, 11, tzinfo=UTC),
    )


def _request() -> SimilarSetupRequest:
    return SimilarSetupRequest(
        symbol="AAA",
        category="trend_mode",
        setup_type="pullback",
        trend_state="bullish_trend",
        extension_state="normal",
        trigger_state="confirmed",
        blocked_by="none",
        market_regime="risk_on",
        price_vs_ema200_pct=5.0,
        support_distance_pct=3.0,
        resistance_room_pct=12.0,
        as_of_date=date(2026, 12, 31),
        lookback_limit=10,
        similarity_mode=SimilarSetupSimilarityMode.EXACT,
    )


def test_similar_setup_retrieval_uses_deterministic_evidence_and_sample_safeguards() -> None:
    prediction_one = _prediction(1)
    prediction_two = _prediction(2)
    prediction_three = _prediction(3)
    prediction_four = _prediction(4)
    nonmatching_prediction = _prediction(5, matching=False)
    store = FakeResearchRecordStore(
        [
            (prediction_one, _outcome(1, prediction_one.id, return_pct=10.0, relative_to_spy=5.0), "risk_on"),
            (prediction_two, _outcome(2, prediction_two.id, outcome_label="failure", return_pct=-2.0, relative_to_spy=-4.0), "risk_on"),
            (prediction_three, _outcome(3, prediction_three.id, return_pct=7.0, relative_to_spy=3.0, daily_snapshot_path_complete=False), "risk_on"),
            (
                prediction_four,
                _outcome(4, prediction_four.id, outcome_status="data_quality_excluded", outcome_label="data_quality_excluded", return_pct=None, relative_to_spy=None),
                "risk_on",
            ),
            (nonmatching_prediction, _outcome(5, nonmatching_prediction.id), "risk_on"),
        ]
    )
    service = SimilarSetupEvidenceService(record_store=store, min_sample_size=3, source_limit=2000)

    response = service.retrieve(_request())

    assert response.similar_case_count == 4
    assert response.evaluable_case_count == 3
    assert response.data_quality_excluded_count == 1
    assert response.sample_size_sufficient is True
    assert response.success_rate_28d == 66.67
    assert response.failure_rate_28d == 33.33
    assert response.average_28d_return == 5.0
    assert response.average_relative_return == 1.3333
    assert len(response.top_similar_predictions) == 4
    assert all(case.similarity_score == 1.0 for case in response.top_similar_predictions)
    assert any("data-quality-excluded" in caveat for caveat in response.caveats)
    assert any("incomplete daily snapshot paths" in caveat for caveat in response.caveats)
    assert store.calls == [
        {
            "market": "us",
            "as_of_date": date(2026, 12, 31),
            "horizon_days": 28,
            "limit": 2000,
        }
    ]


def test_similar_setup_retrieval_withholds_statistics_below_minimum_sample() -> None:
    prediction = _prediction(1)
    service = SimilarSetupEvidenceService(
        record_store=FakeResearchRecordStore([(prediction, _outcome(1, prediction.id), "risk_on")]),
        min_sample_size=2,
        source_limit=2000,
    )

    response = service.retrieve(_request())

    assert response.sample_size_sufficient is False
    assert response.success_rate_28d is None
    assert response.average_28d_return is None
    assert response.common_failure_modes == []
    assert any("Performance aggregates are withheld" in caveat for caveat in response.caveats)


def test_similar_setup_retrieval_requires_a_similarity_criterion() -> None:
    service = SimilarSetupEvidenceService(
        record_store=FakeResearchRecordStore([]),
        min_sample_size=2,
        source_limit=2000,
    )

    with pytest.raises(ValueError, match="At least one similarity criterion"):
        service.retrieve(SimilarSetupRequest())
