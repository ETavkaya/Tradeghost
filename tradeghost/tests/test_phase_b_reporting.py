from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from tradeghost.services.intelligence.service import IntelligenceService
from tradeghost.shared.models.schemas import MarketRegimeSnapshot, OperationalReportType


class FakePhaseBResearchStore:
    configured = True

    def __init__(self) -> None:
        self.market_states = {}
        self.reports = {}
        self.metrics = {
            "predictions": {"count": 3, "cohort_count": 2, "ready_count": 1, "blocked_count": 2},
            "outcomes": {
                "count": 4,
                "available_count": 3,
                "data_quality_excluded_count": 1,
                "positive_count": 2,
                "negative_count": 1,
                "average_directional_return_pct": 1.25,
            },
            "outcome_version_groups": [
                {
                    "rule_version": "scanner_rules_v1",
                    "feature_version": "scanner_features_v1",
                    "data_version": "market_data_daily_v1",
                    "evaluator_version": "outcome_evaluator_v2",
                    "outcome_count": 3,
                }
            ],
            "point_in_time_filter": {
                "as_of_date": "2026-09-13",
                "source_created_before_next_day": True,
                "outcomes_evaluated_before_next_day": True,
            },
        }

    def create_market_state_snapshot(self, record):
        existing = self.market_states.get(record.idempotency_key)
        if existing is not None:
            return existing, False
        self.market_states[record.idempotency_key] = record
        return record, True

    def list_market_state_snapshots(self, *, market, as_of_date=None, limit=30):
        rows = [
            record
            for record in self.market_states.values()
            if record.market == market and (as_of_date is None or record.as_of_date == as_of_date)
        ]
        return sorted(rows, key=lambda record: (record.as_of_date, record.created_at), reverse=True)[:limit]

    def operational_report_metrics(self, **_kwargs):
        return self.metrics

    def get_operational_report_by_idempotency_key(self, idempotency_key):
        return self.reports.get(idempotency_key)

    def latest_operational_report(self, *, report_type, market, period_start, period_end):
        rows = [
            record
            for record in self.reports.values()
            if record.report_type == report_type
            and record.market == market
            and record.period_start == period_start
            and record.period_end == period_end
        ]
        return max(rows, key=lambda record: (record.generated_at, record.created_at)) if rows else None

    def create_operational_report(self, record):
        existing = self.reports.get(record.idempotency_key)
        if existing is not None:
            return existing, False
        self.reports[record.idempotency_key] = record
        return record, True

    def list_operational_reports(self, *, market=None, report_type=None, limit=20):
        rows = [
            record
            for record in self.reports.values()
            if (market is None or record.market == market)
            and (report_type is None or record.report_type == report_type)
        ]
        return sorted(rows, key=lambda record: (record.period_end, record.generated_at), reverse=True)[:limit]


def _service(monkeypatch) -> tuple[IntelligenceService, FakePhaseBResearchStore, list[tuple[str, date]]]:
    service = IntelligenceService(analysis_engine=object(), scanner_engine=object(), backtest_engine=object())
    store = FakePhaseBResearchStore()
    service.research_record_store = store
    monkeypatch.setattr(service.settings, "product_v2_enabled", True)
    monkeypatch.setattr(service.settings, "market_state_enabled", True)
    monkeypatch.setattr(service.settings, "operational_reporting_enabled", True)
    monkeypatch.setattr(service.settings, "market_state_sector_proxy_limit", 2)
    regime = MarketRegimeSnapshot(
        id="11111111-1111-4111-8111-111111111111",
        idempotency_key="us:2026-09-13:market-regime-v1:data-v1",
        payload_hash="regime-payload-hash",
        market="us",
        as_of_date=date(2026, 9, 13),
        primary_benchmark_symbol="SPY",
        benchmark_returns_json={"SPY": {"28d": 3.0}, "QQQ": {"28d": 4.0}},
        volatility_20d_pct=17.0,
        regime_label="risk_on",
        classifier_version="market_regime_v1",
        raw_inputs_json={},
        data_quality_flags=[],
        rule_version="scanner_rules_v1",
        feature_version="scanner_features_v1",
        data_version="market_data_daily_v1:regime:abc",
        created_at=datetime(2026, 9, 13, tzinfo=UTC),
    )
    monkeypatch.setattr(service, "_get_or_create_market_regime_snapshot", lambda **_kwargs: regime)
    calls: list[tuple[str, date]] = []

    def instrument(*, symbol, market, as_of_date):
        calls.append((symbol, as_of_date))
        return (
            {
                "symbol": symbol,
                "source_data_version": f"market-data:{symbol}",
                "latest_bar_date": as_of_date.isoformat(),
                "latest_close": 18.0 if symbol == "^VIX" else 100.0,
                "returns_pct": {"1d": 0.1, "5d": 0.5, "20d": 2.0 if symbol == "XLK" else -1.0},
            },
            [],
        )

    monkeypatch.setattr(service, "_market_state_instrument", instrument)
    return service, store, calls


def test_market_state_reuses_regime_and_persists_bounded_provenance(monkeypatch) -> None:
    service, store, calls = _service(monkeypatch)

    captured = service.capture_market_state(market="US", as_of_date=date(2026, 9, 13))
    replay = service.capture_market_state(market="us", as_of_date=date(2026, 9, 13))

    assert captured.id == replay.id
    assert len(store.market_states) == 1
    assert captured.source_market_regime_id == "11111111-1111-4111-8111-111111111111"
    assert captured.source_market_regime_payload_hash == "regime-payload-hash"
    assert captured.inputs_json["market_regime"]["label"] == "risk_on"
    assert captured.state_json["market_regime"] == "risk_on"
    assert captured.state_json["risk_posture"] == "constructive"
    assert captured.unavailable_inputs == ["us_2y_yield"]
    assert captured.availability_status == "partial"
    assert all(as_of_date == date(2026, 9, 13) for _, as_of_date in calls)
    assert {symbol for symbol, _ in calls} == {"^VIX", "DX-Y.NYB", "^TNX", "XLK", "XLF"}


def test_manual_weekly_report_is_compact_point_in_time_and_supersedes(monkeypatch) -> None:
    service, store, _ = _service(monkeypatch)

    first = service.generate_operational_report(
        report_type=OperationalReportType.WEEKLY,
        market="us",
        period_end=date(2026, 9, 13),
    )
    replay = service.generate_operational_report(
        report_type=OperationalReportType.WEEKLY,
        market="us",
        period_end=date(2026, 9, 13),
    )

    assert first.id == replay.id
    assert first.period_start == date(2026, 9, 7)
    assert first.period_end == date(2026, 9, 13)
    assert first.as_of_date == date(2026, 9, 13)
    assert first.summary_json["predictions"]["count"] == 3
    assert first.summary_json["outcomes"]["available_count"] == 3
    assert first.source_versions_json["point_in_time_filter"]["outcomes_evaluated_before_next_day"] is True
    assert "selection_snapshot_json" not in first.summary_json
    assert len(store.reports) == 1

    store.metrics["outcomes"]["available_count"] = 4
    corrected = service.generate_operational_report(
        report_type=OperationalReportType.WEEKLY,
        market="us",
        period_end=date(2026, 9, 13),
    )

    assert corrected.id != first.id
    assert corrected.supersedes_report_id == first.id
    assert len(store.reports) == 2


def test_phase_b_writers_remain_feature_gated(monkeypatch) -> None:
    service, _, _ = _service(monkeypatch)
    monkeypatch.setattr(service.settings, "market_state_enabled", False)

    with pytest.raises(RuntimeError, match="Market State is disabled"):
        service.capture_market_state(market="us", as_of_date=date(2026, 9, 13))


def test_phase_b_migration_is_additive_and_compact() -> None:
    migration = Path("tradeghost/services/intelligence/migrations/006_phase2b_market_state_reporting.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE TABLE IF NOT EXISTS market_state_snapshots" in migration
    assert "CREATE TABLE IF NOT EXISTS operational_reports" in migration
    assert "ALTER TABLE prediction_records" not in migration
    assert "ALTER TABLE outcome_records" not in migration
    assert "CREATE INDEX IF NOT EXISTS operational_reports_lookup_idx" in migration
