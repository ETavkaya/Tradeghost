from types import SimpleNamespace

from tradeghost.services.knowledge_graph.outbox import KnowledgeGraphOutboxEvent, KnowledgeGraphOutboxStore
from tradeghost.services.knowledge_graph.projection import (
    build_market_regime_projection,
    build_outcome_projection,
    build_prediction_projection,
    build_report_projection,
)
from tradeghost.services.knowledge_graph.service import KnowledgeGraphIngestionService


def test_build_report_projection_preserves_only_deterministic_report_facts() -> None:
    projection = build_report_projection(
        {
            "id": "11111111-1111-4111-8111-111111111111",
            "cohort_id": "22222222-2222-4222-8222-222222222222",
            "cohort_name": "Momentum cohort",
            "market": "us",
            "report_date": "2026-08-15",
            "report_mode": "followup",
            "created_at": "2026-08-15T12:00:00+00:00",
            "report_markdown": "Deterministic report body",
            "candidate_followup_json": [
                {
                    "symbol": "TSLA",
                    "company_name": "Tesla, Inc.",
                    "selected_categories": ["trend_mode", "momentum_mode"],
                    "selected_setup_type": "pullback",
                    "validity_state": "valid",
                }
            ],
        }
    )

    assert projection.report["report_id"] == "11111111-1111-4111-8111-111111111111"
    assert projection.report["market"] == "us"
    assert projection.segment["text"] == "Deterministic report body"
    assert projection.assets == [
        {
            "asset_key": "us:TSLA",
            "symbol": "TSLA",
            "market": "us",
            "asset_type": "equity",
            "company_name": "Tesla, Inc.",
        }
    ]
    assert {(row["signal_type"], row["state"]) for row in projection.signals} == {
        ("selection_category", "trend_mode"),
        ("selection_category", "momentum_mode"),
        ("setup_type", "pullback"),
        ("candidate_validity", "valid"),
    }
    assert all("target_price" not in row for row in projection.signals)


def test_build_research_projections_preserves_deterministic_lineage() -> None:
    regime = build_market_regime_projection(
        {
            "id": "33333333-3333-4333-8333-333333333333",
            "idempotency_key": "us:2026-08-15:market_regime_v1:data-v1",
            "payload_hash": "regime-hash",
            "market": "us",
            "as_of_date": "2026-08-15",
            "primary_benchmark_symbol": "SPY",
            "benchmark_returns_json": {"SPY": {"28d": 4.2}},
            "volatility_20d_pct": 17.5,
            "regime_label": "risk_on",
            "classifier_version": "market_regime_v1",
            "raw_inputs_json": {"source": "canonical"},
            "data_quality_flags": [],
            "rule_version": "scanner_rules_v1",
            "feature_version": "scanner_features_v1",
            "data_version": "market_data_daily_v1",
            "created_at": "2026-08-15T12:00:00+00:00",
        }
    )
    prediction = build_prediction_projection(
        {
            "id": "44444444-4444-4444-8444-444444444444",
            "idempotency_key": "prediction-key",
            "payload_hash": "prediction-hash",
            "cohort_id": "55555555-5555-4555-8555-555555555555",
            "symbol": "TSLA",
            "market": "us",
            "selected_at": "2026-08-15T12:00:00+00:00",
            "selected_date": "2026-08-15",
            "selected_price": 300.0,
            "categories": ["trend_mode"],
            "setup_type": "pullback",
            "trend_state": "bullish_trend",
            "expected_horizon_days": 28,
            "expected_direction": "up",
            "prediction_type": "follow_through_watch",
            "invalidation_conditions": {
                "confirmation": "Close above the trigger level.",
                "invalidation": "Trend structure fails.",
            },
            "selection_market_regime_id": regime["regime_id"],
            "rule_version": "scanner_rules_v1",
            "feature_version": "scanner_features_v1",
            "data_version": "market_data_daily_v1",
            "created_at": "2026-08-15T12:00:00+00:00",
        }
    )
    outcome = build_outcome_projection(
        {
            "id": "66666666-6666-4666-8666-666666666666",
            "idempotency_key": "outcome-key",
            "payload_hash": "outcome-hash",
            "prediction_id": prediction.prediction["prediction_id"],
            "cohort_id": "55555555-5555-4555-8555-555555555555",
            "symbol": "TSLA",
            "market": "us",
            "horizon_days": 28,
            "selection_date": "2026-08-15",
            "outcome_date": "2026-09-23",
            "evaluated_at": "2026-09-23T12:00:00+00:00",
            "outcome_status": "available",
            "outcome_label": "success",
            "return_pct": 8.5,
            "directional_return_pct": 8.5,
            "selection_market_regime_id": regime["regime_id"],
            "outcome_market_regime_id": regime["regime_id"],
            "market_regime_label": "risk_on",
            "relative_to_spy": 4.3,
            "attribution_label": "stock_specific_move",
            "attribution_json": {"primary_benchmark_symbol": "SPY"},
            "evaluator_version": "outcome_evaluator_v2",
            "rule_version": "scanner_rules_v1",
            "feature_version": "scanner_features_v1",
            "data_version": "market_data_daily_v1",
            "created_at": "2026-09-23T12:00:00+00:00",
        }
    )

    assert regime["regime_id"] == "33333333-3333-4333-8333-333333333333"
    assert regime["benchmark_returns_json"] == '{"SPY":{"28d":4.2}}'
    assert prediction.asset == {"asset_key": "us:TSLA", "symbol": "TSLA", "market": "us", "asset_type": "equity"}
    assert prediction.prediction["selection_market_regime_id"] == regime["regime_id"]
    assert prediction.confirmation_conditions[0]["condition_type"] == "confirmation"
    assert prediction.invalidation_conditions[0]["condition_type"] == "invalidation"
    assert outcome.outcome["prediction_id"] == prediction.prediction["prediction_id"]
    assert outcome.outcome["outcome_market_regime_id"] == regime["regime_id"]
    assert outcome.outcome["attribution_json"] == '{"primary_benchmark_symbol":"SPY"}'


def test_graph_worker_dispatches_typed_research_events() -> None:
    event = KnowledgeGraphOutboxEvent(
        id="77777777-7777-4777-8777-777777777777",
        event_type=KnowledgeGraphOutboxStore.prediction_event_type,
        event_version=1,
        aggregate_id="44444444-4444-4444-8444-444444444444",
        payload={"id": "44444444-4444-4444-8444-444444444444"},
        attempt_count=1,
    )

    class FakeOutbox:
        configured = True

        def __init__(self) -> None:
            self.processed = []

        def claim_events(self, limit: int):
            return [event]

        def mark_processed(self, processed_event):
            self.processed.append(processed_event)
            return True

    class FakeProjector:
        configured = True

        def __init__(self) -> None:
            self.calls = []

        def project(self, payload, *, event_type: str):
            self.calls.append((event_type, payload))

    service = KnowledgeGraphIngestionService(
        SimpleNamespace(
            database_url="",
            neo4j_uri="",
            neo4j_username="",
            neo4j_password="",
            knowledge_graph_enabled=True,
            knowledge_graph_batch_size=25,
            knowledge_graph_retry_seconds=30,
        )
    )
    service.outbox = FakeOutbox()
    service.projector = FakeProjector()

    result = service.process_pending_events()

    assert result["claimed"] == 1
    assert result["projected"] == 1
    assert service.projector.calls == [(KnowledgeGraphOutboxStore.prediction_event_type, event.payload)]
    assert service.outbox.processed == [event]
