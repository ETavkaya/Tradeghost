from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from tradeghost.services.strategy_lab.service import StrategyLabService
from tradeghost.shared.models.schemas import (
    DailyRun,
    DailyRunDetail,
    MarketCode,
    ScannerCategory,
    StrategyLabDecisionCreateRequest,
    StrategyLabExperimentCreateRequest,
    StrategyLabPositionStatus,
    SymbolResult,
)


class FakeStrategyLabStore:
    configured = True

    def __init__(self) -> None:
        self.experiments = {}
        self.sleeves = {}
        self.decisions = {}
        self.positions = {}
        self.events = {}
        self.avoided = {}

    def create_strategy_lab_experiment(self, experiment, sleeves, initial_events):
        existing = self.experiments.get(experiment.idempotency_key)
        if existing is not None:
            return existing, self.list_strategy_lab_sleeves(existing.id), False
        self.experiments[experiment.idempotency_key] = experiment
        self.sleeves.update({sleeve.id: sleeve for sleeve in sleeves})
        for event in initial_events:
            self.events.setdefault(event.idempotency_key, event)
        return experiment, sleeves, True

    def get_strategy_lab_experiment(self, experiment_id):
        return next((row for row in self.experiments.values() if row.id == experiment_id), None)

    def activate_strategy_lab_experiment(self, experiment_id):
        record = self.get_strategy_lab_experiment(experiment_id)
        if record is None:
            raise FileNotFoundError(experiment_id)
        return record

    def list_strategy_lab_experiments(self, limit=30):
        return list(self.experiments.values())[:limit]

    def list_strategy_lab_sleeves(self, experiment_id):
        return [row for row in self.sleeves.values() if row.experiment_id == experiment_id]

    def create_strategy_lab_decision(self, decision, *, position=None, ledger_events=None, avoided_observation=None):
        existing = self.decisions.get(decision.idempotency_key)
        if existing is not None:
            return existing, False
        self.decisions[decision.idempotency_key] = decision
        if position is not None:
            self.positions[position.id] = position
        for event in ledger_events or []:
            self.events.setdefault(event.idempotency_key, event)
        if avoided_observation is not None:
            self.avoided[avoided_observation.id] = avoided_observation
        return decision, True

    def list_strategy_lab_decisions(self, experiment_id):
        return [row for row in self.decisions.values() if row.experiment_id == experiment_id]

    def list_strategy_lab_positions(self, experiment_id):
        return [row for row in self.positions.values() if row.experiment_id == experiment_id]

    def update_strategy_lab_position(self, record):
        self.positions[record.id] = record
        return record

    def create_strategy_lab_ledger_event(self, event):
        existing = self.events.get(event.idempotency_key)
        if existing is not None:
            return existing, False
        self.events[event.idempotency_key] = event
        return event, True

    def list_strategy_lab_ledger_events(self, experiment_id):
        return [row for row in self.events.values() if row.experiment_id == experiment_id]

    def list_strategy_lab_avoided_observations(self, experiment_id):
        return [row for row in self.avoided.values() if row.experiment_id == experiment_id]

    def update_strategy_lab_avoided_observation(self, record):
        self.avoided[record.id] = record
        return record


def _run(run_id: str, run_date: date, *, symbol: str, category: ScannerCategory, final_entry: bool = True) -> DailyRunDetail:
    return DailyRunDetail(
        run=DailyRun(
            id=run_id,
            date=run_date,
            timestamp=datetime.combine(run_date, datetime.min.time(), tzinfo=UTC),
            symbols_count=1,
            scanner_categories=[category],
        ),
        symbol_results=[
            SymbolResult(
                symbol=symbol,
                market=MarketCode.US,
                category_tags=[category],
                score=80.0,
                trend="bullish_trend",
                setup_type="momentum_continuation",
                structure_snapshot={"final_entry_decision": final_entry},
            )
        ],
    )


def _service(monkeypatch):
    store = FakeStrategyLabStore()
    runs = {
        "run-eligible": _run("run-eligible", date(2026, 8, 20), symbol="AAA", category=ScannerCategory.TREND_MODE),
        "run-overextended": _run("run-overextended", date(2026, 8, 20), symbol="BBB", category=ScannerCategory.OVEREXTENDED, final_entry=False),
        "run-blocked": _run("run-blocked", date(2026, 8, 20), symbol="CCC", category=ScannerCategory.MOMENTUM_MODE, final_entry=False),
    }
    intelligence = SimpleNamespace(
        settings=SimpleNamespace(product_v2_enabled=True, strategy_lab_enabled=True),
        research_record_store=store,
        _research_versions=lambda: {
            "rule_version": "scanner_rules_v1",
            "feature_version": "scanner_features_v1",
            "data_version": "market_data_daily_v1",
            "evaluator_version": "outcome_evaluator_v2",
        },
        _get_run_detail=lambda run_id: runs[run_id],
    )
    service = StrategyLabService(intelligence)
    clock = {"now": datetime(2026, 8, 19, 12, tzinfo=UTC)}
    monkeypatch.setattr(service, "_now", lambda: clock["now"])
    dates = []
    cursor = date(2026, 8, 20)
    while len(dates) < 70:
        if cursor.weekday() < 5:
            dates.append(cursor)
        cursor += timedelta(days=1)
    bars = [
        {"bar_date": bar_date, "open": 100.0 + index, "close": 100.5 + index}
        for index, bar_date in enumerate(dates)
    ]
    intelligence._load_canonical_bars_for_symbol = lambda _symbol, **_kwargs: (bars, "market-data-v1", [])
    return service, store, clock


def test_strategy_lab_is_future_only_and_uses_append_only_lifecycle(monkeypatch) -> None:
    service, store, clock = _service(monkeypatch)
    experiment = service.create_experiment(
        StrategyLabExperimentCreateRequest(
            name="August Forward Test",
            market=MarketCode.US,
            activation_at=clock["now"],
        )
    )

    assert len(experiment.sleeves) == 5
    assert len(store.events) == 5

    decision = service.record_decision(
        experiment.experiment.id,
        StrategyLabDecisionCreateRequest(
            source_run_id="run-eligible",
            symbol="AAA",
            category=ScannerCategory.TREND_MODE,
        ),
    )
    assert decision.decision_status.value == "reserved"
    assert len(store.positions) == 1

    clock["now"] = datetime(2026, 11, 17, 12, tzinfo=UTC)
    processed = service.process_experiment(experiment.experiment.id, as_of_date=date(2026, 11, 17))
    position = next(iter(store.positions.values()))

    assert processed.entry_fills_created == 1
    assert processed.exits_created == 1
    assert position.status == StrategyLabPositionStatus.CLOSED
    assert position.entry_date and position.exit_date
    assert len(store.events) == 8

    replay = service.process_experiment(experiment.experiment.id, as_of_date=date(2026, 11, 17))
    assert replay.entry_fills_created == 0
    assert replay.exits_created == 0
    assert len(store.events) == 8


def test_overextended_is_separate_avoided_basket_and_gate_failures_do_not_open_positions(monkeypatch) -> None:
    service, store, clock = _service(monkeypatch)
    experiment = service.create_experiment(
        StrategyLabExperimentCreateRequest(name="Avoided Test", activation_at=clock["now"])
    )

    avoided = service.record_decision(
        experiment.experiment.id,
        StrategyLabDecisionCreateRequest(
            source_run_id="run-overextended",
            symbol="BBB",
            category=ScannerCategory.OVEREXTENDED,
        ),
    )
    rejected = service.record_decision(
        experiment.experiment.id,
        StrategyLabDecisionCreateRequest(
            source_run_id="run-blocked",
            symbol="CCC",
            category=ScannerCategory.MOMENTUM_MODE,
        ),
    )

    assert avoided.decision_status.value == "avoided"
    assert rejected.decision_status.value == "rejected"
    assert len(store.positions) == 0
    assert len(store.avoided) == 1
    detail = service.get_experiment_detail(experiment.experiment.id)
    assert detail.metrics["avoided_basket"]["excluded_from_realised_pnl"] is True
    assert detail.metrics["realised_pnl"] == "0"


def test_long_sleeve_enforces_five_slots_at_twenty_dollars_each(monkeypatch) -> None:
    service, store, clock = _service(monkeypatch)
    experiment = service.create_experiment(
        StrategyLabExperimentCreateRequest(name="Capacity Test", activation_at=clock["now"])
    )
    generated_runs = {
        f"run-{index}": _run(
            f"run-{index}",
            date(2026, 8, 20),
            symbol=f"T{index}",
            category=ScannerCategory.TREND_MODE,
        )
        for index in range(6)
    }
    service.intelligence_service._get_run_detail = lambda run_id: generated_runs[run_id]

    decisions = [
        service.record_decision(
            experiment.experiment.id,
            StrategyLabDecisionCreateRequest(
                source_run_id=f"run-{index}",
                symbol=f"T{index}",
                category=ScannerCategory.TREND_MODE,
            ),
        )
        for index in range(6)
    ]

    assert [decision.decision_status.value for decision in decisions].count("reserved") == 5
    assert decisions[-1].decision_status.value == "rejected"
    assert decisions[-1].reason_codes == ["sleeve_capacity_reached"]
    assert {position.allocated_cash for position in store.positions.values()} == {20}


def test_strategy_lab_rejects_historical_source_run_and_disabled_writes(monkeypatch) -> None:
    service, _, clock = _service(monkeypatch)
    clock["now"] = datetime(2026, 8, 21, 12, tzinfo=UTC)
    experiment = service.create_experiment(
        StrategyLabExperimentCreateRequest(name="Forward Only", activation_at=clock["now"])
    )
    with pytest.raises(ValueError, match="predates"):
        service.record_decision(
            experiment.experiment.id,
            StrategyLabDecisionCreateRequest(
                source_run_id="run-eligible",
                symbol="AAA",
                category=ScannerCategory.TREND_MODE,
            ),
        )

    service.settings.strategy_lab_enabled = False
    with pytest.raises(RuntimeError, match="Strategy Lab is disabled"):
        service.list_experiments()


def test_strategy_lab_migration_is_additive() -> None:
    migration = open(
        "tradeghost/services/intelligence/migrations/007_phase2c_strategy_lab.sql",
        encoding="utf-8",
    ).read()

    for table in (
        "strategy_lab_experiments",
        "strategy_lab_sleeves",
        "strategy_lab_decisions",
        "strategy_lab_positions",
        "strategy_lab_ledger_events",
        "strategy_lab_avoided_observations",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in migration
    assert "ALTER TABLE prediction_records" not in migration
    assert "ALTER TABLE outcome_records" not in migration
