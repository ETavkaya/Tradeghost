from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pandas as pd

from tradeghost.services.intelligence.service import IntelligenceService
from tradeghost.shared.models.schemas import (
    CandidateCohort,
    CohortCandidate,
    CohortDailyReportDetail,
    CohortDailySnapshot,
    CohortReviewRequest,
    MarketCode,
    ScannerCategory,
    ScannerDuration,
)


class FakeDailyReportStore:
    configured = True

    def __init__(self, reports=None, details=None) -> None:
        self.reports = reports or []
        self.details = details or {}

    def list_reports(self, cohort_id: str):
        return self.reports

    def get_report(self, cohort_id: str, report_date: date, report_mode: str = "followup"):
        return self.details.get(report_date)


class FakeResearchRecordStore:
    configured = True

    def __init__(self) -> None:
        self.predictions = {}
        self.outcomes = {}
        self.market_regimes = {}
        self.canonical_bars = {}
        self.summaries = []
        self.data_quality_events = []

    def create_predictions(self, records):
        created_count = 0
        persisted = []
        for record in records:
            existing = self.predictions.get(record.idempotency_key)
            if existing is None:
                self.predictions[record.idempotency_key] = record
                existing = record
                created_count += 1
            persisted.append(existing)
        return persisted, created_count

    def list_predictions(self, cohort_id: str):
        return [record for record in self.predictions.values() if record.cohort_id == cohort_id]

    def create_market_regime_snapshot(self, record):
        existing = self.market_regimes.get(record.idempotency_key)
        if existing is not None:
            return existing, False
        self.market_regimes[record.idempotency_key] = record
        return record, True

    def get_market_regime_snapshot(self, snapshot_id: str):
        return next((record for record in self.market_regimes.values() if record.id == snapshot_id), None)

    def upsert_canonical_bars(self, bars):
        for bar in bars:
            key = (bar["market"], bar["symbol"], bar["data_version"])
            self.canonical_bars.setdefault(key, {})[bar["bar_date"]] = bar

    def list_canonical_bars(self, *, market: str, symbol: str, data_version: str, through_date=None):
        rows = self.canonical_bars.get((market, symbol, data_version), {}).values()
        return sorted(
            [row for row in rows if through_date is None or row["bar_date"] <= through_date],
            key=lambda row: row["bar_date"],
        )

    def latest_outcome_id(self, prediction_id: str, *, horizon_days: int, evaluator_version: str):
        matches = [
            record
            for record in self.outcomes.values()
            if record.prediction_id == prediction_id
            and record.horizon_days == horizon_days
            and record.evaluator_version == evaluator_version
        ]
        return max(matches, key=lambda record: (record.evaluated_at, record.created_at)).id if matches else None

    def create_outcome(self, record):
        existing = self.outcomes.get(record.idempotency_key)
        if existing is not None:
            return existing, False
        self.outcomes[record.idempotency_key] = record
        return record, True

    def list_outcomes(self, cohort_id: str, horizon_days: int | None = None):
        return [
            record
            for record in self.outcomes.values()
            if record.cohort_id == cohort_id and (horizon_days is None or record.horizon_days == horizon_days)
        ]

    def upsert_outcome_summaries(self, records):
        self.summaries = records
        return records

    def list_outcome_summaries(self, cohort_id: str):
        return [record for record in self.summaries if record.cohort_id == cohort_id]

    def record_data_quality_event(self, **event):
        self.data_quality_events.append(event)


class FakeDataService:
    def __init__(self, frames: dict[str, pd.DataFrame]) -> None:
        self.frames = frames

    def get_market_data(self, symbol: str, market: str | None = None, period: str | None = None, use_cache: bool = True):
        frame = self.frames[symbol].copy()
        return SimpleNamespace(normalized_ticker=symbol, daily=frame)


class FakeAnalysisEngine:
    def __init__(self, frames: dict[str, pd.DataFrame]) -> None:
        self.data_service = FakeDataService(frames)


def _wire_temp_storage(service: IntelligenceService, tmp_path) -> None:
    service.base_dir = tmp_path
    service.runs_path = tmp_path / "daily_runs.json"
    service.results_path = tmp_path / "symbol_results.json"
    service.contexts_path = tmp_path / "symbol_contexts.json"
    service.briefings_path = tmp_path / "daily_briefings.json"
    service.reviews_path = tmp_path / "system_reviews.json"
    service.approvals_path = tmp_path / "review_approvals.json"
    service.cohorts_path = tmp_path / "candidate_cohorts.json"
    service.cohort_candidates_path = tmp_path / "cohort_candidates.json"
    service.cohort_snapshots_path = tmp_path / "cohort_daily_snapshots.json"
    service.llm_logs_path = tmp_path / "llm_calls.json"
    service.pipeline_logs_path = tmp_path / "pipeline_events.json"
    service.scheduler_logs_dir = tmp_path / "scheduler"
    service.scheduler_logs_path = service.scheduler_logs_dir / "daily_followup.log"
    service.daily_report_store = FakeDailyReportStore()


def _phase2b_cohort_and_candidate(cohort_id: str, symbol: str = "AAA") -> tuple[CandidateCohort, CohortCandidate]:
    cohort = CandidateCohort(
        id=cohort_id,
        name="Phase 2B deterministic cohort",
        start_date=date(2026, 5, 13),
        market=MarketCode.US,
        analysis_window=ScannerDuration.ONE_YEAR,
        selected_categories=[ScannerCategory.TREND_MODE],
        followup_enabled=True,
        followup_start_date=date(2026, 5, 13),
        followup_target_days=28,
    )
    candidate = CohortCandidate(
        cohort_id=cohort_id,
        symbol=symbol,
        market=MarketCode.US,
        selected_at=datetime(2026, 5, 13, tzinfo=UTC),
        selected_price=100.0,
        selected_rank=1,
        selected_score=82.0,
        selected_categories=[ScannerCategory.TREND_MODE],
        selected_setup_type="momentum_continuation",
        selected_candidate_type="watch_candidate",
        selected_entry_readiness="watch",
        selected_blocked_by="none",
        selected_trend_state="bullish_trend",
        selected_score_dynamics="improving",
        selected_reason="Deterministic trend-mode selection.",
        selected_sector="Technology",
        selected_invalidation_condition="Invalidate if trend structure fails.",
        selected_structure_snapshot={
            "extension_state": "normal",
            "trigger_state": "confirmed",
            "trigger_score": 76.0,
            "trigger_threshold": 55.0,
        },
    )
    return cohort, candidate


def test_phase2b_outcomes_are_deterministic_and_independent_of_snapshot_coverage(tmp_path) -> None:
    cohort_id = "26262626-2626-4262-8262-262626262626"
    cohort, candidate = _phase2b_cohort_and_candidate(cohort_id)
    service = IntelligenceService(
        analysis_engine=FakeAnalysisEngine({}),
        scanner_engine=object(),
        backtest_engine=object(),
    )
    _wire_temp_storage(service, tmp_path)
    trading_dates = service._trading_days_between(cohort.start_date, date(2026, 7, 1))
    prices = [100.0 + index for index in range(len(trading_dates))]
    frame = pd.DataFrame(
        {
            "open": prices,
            "high": [price + 1.0 for price in prices],
            "low": [price - 1.0 for price in prices],
            "close": prices,
            "volume": [1_000_000] * len(prices),
        },
        index=pd.to_datetime(trading_dates),
    )
    service.analysis_engine = FakeAnalysisEngine({"AAA": frame})
    service.research_record_store = FakeResearchRecordStore()
    service._save_cohorts([cohort])
    service._save_cohort_candidates([candidate])
    prediction_one = service._prediction_record_from_candidate(cohort, candidate)
    prediction_two = service._prediction_record_from_candidate(cohort, candidate)
    assert prediction_one.idempotency_key == prediction_two.idempotency_key
    assert prediction_one.id == prediction_two.id
    assert prediction_one.payload_hash == prediction_two.payload_hash
    prediction_backfill = service.backfill_cohort_prediction_records(cohort_id)
    assert prediction_backfill.created_prediction_count == 1
    assert prediction_backfill.existing_prediction_count == 0

    first_evaluation = service.evaluate_cohort_outcomes(cohort_id, as_of_date=trading_dates[29])

    assert first_evaluation.created_outcome_count == 3
    assert first_evaluation.pending_horizon_count == 0
    outcomes_by_horizon = {outcome.horizon_days: outcome for outcome in first_evaluation.outcomes}
    assert sorted(outcomes_by_horizon) == [7, 14, 28]
    assert outcomes_by_horizon[7].return_pct == 6.0
    assert outcomes_by_horizon[14].return_pct == 13.0
    assert outcomes_by_horizon[28].return_pct == 27.0
    assert all(outcome.outcome_status == "available" for outcome in outcomes_by_horizon.values())
    assert all(outcome.daily_snapshot_path_complete is False for outcome in outcomes_by_horizon.values())
    assert all(outcome.price_path_complete is True for outcome in outcomes_by_horizon.values())
    assert {summary.grouping for summary in first_evaluation.summaries} == {
        "category",
        "setup_type",
        "blocked_by",
        "market_regime",
    }

    second_evaluation = service.evaluate_cohort_outcomes(cohort_id, as_of_date=trading_dates[29])

    assert second_evaluation.created_outcome_count == 0
    assert second_evaluation.existing_outcome_count == 3


def test_outcome_validity_reads_prediction_selected_date(tmp_path) -> None:
    cohort_id = "27272727-2727-4272-8272-272727272727"
    cohort, candidate = _phase2b_cohort_and_candidate(cohort_id)
    service = IntelligenceService(
        analysis_engine=FakeAnalysisEngine({}),
        scanner_engine=object(),
        backtest_engine=object(),
    )
    _wire_temp_storage(service, tmp_path)
    service._save_cohorts([cohort])
    service._save_cohort_candidates([candidate])
    service._save_cohort_snapshots(
        [
            CohortDailySnapshot(
                cohort_id=cohort_id,
                symbol=candidate.symbol,
                snapshot_date=date(2026, 5, 14),
                still_valid_candidate=True,
            )
        ]
    )

    invalidated_quickly, stayed_valid = service._outcome_validity_flags(
        service.get_cohort_detail(cohort_id),
        service._prediction_record_from_candidate(cohort, candidate),
        outcome_date=date(2026, 5, 20),
    )

    assert invalidated_quickly is False
    assert stayed_valid is True


def test_phase2c_outcomes_include_deterministic_regime_and_benchmark_attribution(tmp_path) -> None:
    cohort_id = "28282828-2828-4282-8282-282828282828"
    cohort, candidate = _phase2b_cohort_and_candidate(cohort_id)
    service = IntelligenceService(
        analysis_engine=FakeAnalysisEngine({}),
        scanner_engine=object(),
        backtest_engine=object(),
    )
    _wire_temp_storage(service, tmp_path)
    selection_dates = service._trading_days_between(cohort.start_date, date(2026, 7, 1))
    prior_dates = list(pd.bdate_range(end=pd.Timestamp(cohort.start_date) - pd.Timedelta(days=1), periods=30).date)
    all_dates = prior_dates + selection_dates
    selection_index = len(prior_dates)

    def frame_for(step: float) -> pd.DataFrame:
        prices = [100.0 + (index - selection_index) * step for index in range(len(all_dates))]
        return pd.DataFrame(
            {
                "open": prices,
                "high": [price + 1.0 for price in prices],
                "low": [price - 1.0 for price in prices],
                "close": prices,
                "volume": [1_000_000] * len(prices),
            },
            index=pd.to_datetime(all_dates),
        )

    service.analysis_engine = FakeAnalysisEngine(
        {
            "AAA": frame_for(1.0),
            "SPY": frame_for(0.5),
            "QQQ": frame_for(0.25),
            "IWM": frame_for(0.1),
            "XLK": frame_for(0.75),
        }
    )
    service.research_record_store = FakeResearchRecordStore()
    service._save_cohorts([cohort])
    service._save_cohort_candidates([candidate])

    prediction = service.backfill_cohort_prediction_records(cohort_id).predictions[0]
    evaluation = service.evaluate_cohort_outcomes(cohort_id, as_of_date=selection_dates[29])
    outcome = next(record for record in evaluation.outcomes if record.horizon_days == 28)

    assert prediction.selection_market_regime_id is not None
    assert outcome.outcome_market_regime_id is not None
    assert outcome.market_regime_label == "risk_on"
    assert outcome.market_return_pct == 13.5
    assert outcome.sector_proxy_symbol == "XLK"
    assert outcome.sector_return_pct == 20.25
    assert outcome.relative_to_spy == 13.5
    assert outcome.relative_to_qqq == 20.25
    assert outcome.relative_to_sector_proxy == 6.75
    assert outcome.attribution_label == "stock_specific_move"
    assert outcome.attribution_json["primary_benchmark_symbol"] == "SPY"
    assert "market_regime" in {summary.grouping for summary in evaluation.summaries}


def test_phase2b_symbol_mismatch_creates_data_quality_excluded_outcomes(tmp_path) -> None:
    cohort_id = "27272727-2727-4272-8272-272727272727"
    cohort, candidate = _phase2b_cohort_and_candidate(cohort_id)
    service = IntelligenceService(
        analysis_engine=FakeAnalysisEngine({}),
        scanner_engine=object(),
        backtest_engine=object(),
    )
    _wire_temp_storage(service, tmp_path)

    class MismatchedDataService:
        def get_market_data(self, symbol: str, market: str | None = None, period: str | None = None, use_cache: bool = True):
            return SimpleNamespace(normalized_ticker="BBB", daily=pd.DataFrame())

    service.analysis_engine = SimpleNamespace(data_service=MismatchedDataService())
    service.research_record_store = FakeResearchRecordStore()
    service._save_cohorts([cohort])
    service._save_cohort_candidates([candidate])
    prediction_backfill = service.backfill_cohort_prediction_records(cohort_id)
    assert prediction_backfill.created_prediction_count == 1

    evaluation = service.evaluate_cohort_outcomes(cohort_id, as_of_date=date(2026, 7, 1))

    assert evaluation.created_outcome_count == 3
    assert evaluation.pending_horizon_count == 0
    assert evaluation.data_quality_excluded_count == 3
    assert {outcome.horizon_days for outcome in evaluation.outcomes} == {7, 14, 28}
    assert all(outcome.outcome_status == "data_quality_excluded" for outcome in evaluation.outcomes)
    assert all("possible_symbol_price_mismatch" in outcome.data_quality_flags for outcome in evaluation.outcomes)


def test_cohort_review_separates_elapsed_coverage_and_28d_horizon(tmp_path) -> None:
    start_date = date(2026, 5, 13)
    latest_followup_date = date(2026, 7, 20)
    cohort_id = "11111111-1111-4111-8111-111111111111"
    symbols = [f"TST{index:02d}" for index in range(19)]

    service = IntelligenceService(
        analysis_engine=FakeAnalysisEngine({}),
        scanner_engine=object(),
        backtest_engine=object(),
    )
    _wire_temp_storage(service, tmp_path)
    trading_days = service._trading_days_between(start_date, latest_followup_date)
    frames: dict[str, pd.DataFrame] = {}
    for index, symbol in enumerate(symbols):
        days = trading_days[:10] if index == 18 else trading_days
        step = 0.4 if index % 2 == 0 else -0.2
        prices = [100.0 + (day_index * step) for day_index in range(len(days))]
        frames[symbol] = pd.DataFrame({"close": prices}, index=pd.to_datetime(days))
    service.analysis_engine = FakeAnalysisEngine(frames)

    cohort = CandidateCohort(
        id=cohort_id,
        name="Milestone#1",
        start_date=start_date,
        market=MarketCode.US,
        analysis_window=ScannerDuration.ONE_YEAR,
        selected_categories=[ScannerCategory.TREND_MODE],
        followup_enabled=True,
        followup_start_date=start_date,
        followup_target_days=28,
    )
    candidates = [
        CohortCandidate(
            cohort_id=cohort_id,
            symbol=symbol,
            market=MarketCode.US,
            selected_at=datetime(2026, 5, 13, tzinfo=UTC),
            selected_price=100.0,
            selected_rank=index + 1,
            selected_score=80.0 - index,
            selected_categories=[ScannerCategory.TREND_MODE if index < 10 else ScannerCategory.BUILD_UP],
        )
        for index, symbol in enumerate(symbols)
    ]
    snapshots = [
        CohortDailySnapshot(cohort_id=cohort_id, symbol=symbol, snapshot_date=snapshot_date)
        for snapshot_date in [trading_days[0], trading_days[1], latest_followup_date]
        for symbol in symbols
    ]
    service._save_cohorts([cohort])
    service._save_cohort_candidates(candidates)
    service._save_cohort_snapshots(snapshots)

    review = service.run_cohort_review(CohortReviewRequest(cohort_id=cohort_id, days_required=28))

    assert review.start_date == start_date
    assert review.latest_followup_date == latest_followup_date
    assert review.trading_days_elapsed > 28
    assert review.valid_followup_snapshot_days == 2
    assert review.expected_followup_days == 28
    assert review.snapshot_coverage_pct == 7.1
    assert review.missing_followup_days_count == 26
    assert len(review.missing_followup_dates) == 26
    assert review.horizon_28d_available is True
    assert review.horizon_outcome_review_available is True
    assert review.daily_path_review_complete is False
    assert review.snapshot_coverage_warning == "Historical price horizon is available, but daily follow-up snapshots are incomplete. Run backfill."
    assert "Daily snapshot coverage: 2/28 days" in review.readiness_message
    assert "Review needs more history" not in review.readiness_message
    assert review.deterministic_stats.horizon_28d_candidate_count == 18
    assert review.deterministic_stats.horizon_28d_missing_count == 1
    assert review.deterministic_stats.horizon_28d_positive_count > 0
    assert review.deterministic_stats.horizon_28d_negative_count > 0
    assert review.deterministic_stats.return_28d_by_category


def test_cohort_coverage_requires_every_candidate_state(tmp_path) -> None:
    cohort_id = "22222222-2222-4222-8222-222222222222"
    start_date = date(2026, 5, 13)
    symbols = ["AAA", "BBB", "CCC"]
    service = IntelligenceService(
        analysis_engine=FakeAnalysisEngine({}),
        scanner_engine=object(),
        backtest_engine=object(),
    )
    _wire_temp_storage(service, tmp_path)
    followup_dates = service._trading_days_between(start_date, date(2026, 5, 15))
    cohort = CandidateCohort(
        id=cohort_id,
        name="Partial coverage",
        start_date=start_date,
        market=MarketCode.US,
        analysis_window=ScannerDuration.ONE_YEAR,
        followup_enabled=True,
        followup_start_date=start_date,
        followup_target_days=28,
    )
    candidates = [
        CohortCandidate(
            cohort_id=cohort_id,
            symbol=symbol,
            market=MarketCode.US,
            selected_at=datetime(2026, 5, 13, tzinfo=UTC),
            selected_price=100.0,
            selected_rank=index + 1,
            selected_score=80.0,
        )
        for index, symbol in enumerate(symbols)
    ]
    snapshots = [
        CohortDailySnapshot(cohort_id=cohort_id, symbol=symbol, snapshot_date=followup_dates[0])
        for symbol in symbols
    ]
    snapshots.extend(
        CohortDailySnapshot(cohort_id=cohort_id, symbol=symbol, snapshot_date=followup_dates[1])
        for symbol in symbols[:2]
    )
    service.daily_report_store = FakeDailyReportStore(
        [SimpleNamespace(report_date=followup_dates[2], followup_snapshot_count=len(symbols))]
    )
    service._save_cohorts([cohort])
    service._save_cohort_candidates(candidates)
    service._save_cohort_snapshots(snapshots)

    review = service.run_cohort_review(CohortReviewRequest(cohort_id=cohort_id, days_required=28))

    assert review.latest_followup_date == followup_dates[1]
    assert review.trading_days_elapsed == 2
    assert review.valid_followup_snapshot_days == 1
    assert review.expected_followup_days == 2
    assert review.missing_followup_dates == [followup_dates[1]]
    assert review.actual_followup_snapshot_count == 5
    assert review.complete_followup_snapshot_count == 3
    assert review.partial_followup_snapshot_count == 2
    assert review.expected_followup_snapshot_count == 6
    assert review.partial_followup_dates == [followup_dates[1]]
    assert review.daily_path_review_complete is False
    assert "Backfill required: 1 missing trading day" in review.readiness_message


def test_coverage_monitor_reports_partial_missing_and_duplicate_snapshot_states(tmp_path) -> None:
    cohort_id = "25252525-2525-4252-8252-252525252525"
    start_date = date(2026, 5, 13)
    symbols = ["AAA", "BBB", "CCC"]
    service = IntelligenceService(
        analysis_engine=FakeAnalysisEngine({}),
        scanner_engine=object(),
        backtest_engine=object(),
    )
    _wire_temp_storage(service, tmp_path)
    followup_dates = service._trading_days_between(start_date, date(2026, 5, 15))
    cohort = CandidateCohort(
        id=cohort_id,
        name="Coverage monitor",
        start_date=start_date,
        market=MarketCode.US,
        analysis_window=ScannerDuration.ONE_YEAR,
        followup_enabled=True,
        followup_start_date=start_date,
        followup_target_days=28,
    )
    candidates = [
        CohortCandidate(
            cohort_id=cohort_id,
            symbol=symbol,
            market=MarketCode.US,
            selected_at=datetime(2026, 5, 13, tzinfo=UTC),
            selected_price=100.0,
            selected_rank=index + 1,
            selected_score=80.0,
        )
        for index, symbol in enumerate(symbols)
    ]
    snapshots = [
        CohortDailySnapshot(cohort_id=cohort_id, symbol=symbol, snapshot_date=followup_dates[0])
        for symbol in symbols
    ]
    snapshots.append(CohortDailySnapshot(cohort_id=cohort_id, symbol="AAA", snapshot_date=followup_dates[0]))
    snapshots.extend(
        CohortDailySnapshot(cohort_id=cohort_id, symbol=symbol, snapshot_date=followup_dates[1])
        for symbol in symbols[:2]
    )
    service._save_cohorts([cohort])
    service._save_cohort_candidates(candidates)
    service._save_cohort_snapshots(snapshots)

    monitor = service.get_cohort_coverage(
        cohort_id,
        days_required=3,
        as_of_date=followup_dates[2],
    )

    assert monitor.status == "anomalies_detected"
    assert monitor.expected_followup_days == 3
    assert monitor.complete_followup_days == 1
    assert monitor.partial_followup_days == 1
    assert monitor.missing_followup_days == 1
    assert monitor.snapshot_coverage_pct == 33.3
    assert monitor.partial_followup_dates == [followup_dates[1]]
    assert monitor.missing_followup_dates == [followup_dates[2]]
    assert monitor.backfill_required is True
    assert monitor.backfill_dates == [followup_dates[1], followup_dates[2]]
    assert monitor.duplicate_snapshot_state_count == 1
    assert monitor.duplicate_snapshot_dates == [followup_dates[0]]
    assert monitor.duplicate_repair_required is True
    assert monitor.duplicate_repair_dates == [followup_dates[0]]
    assert {anomaly.code for anomaly in monitor.anomalies} == {
        "duplicate_followup_snapshot_state",
        "partial_followup_snapshot_day",
        "missing_followup_snapshot_day",
    }
    assert len(service._read_cohort_snapshots()) == 6
    pipeline_event = service._read_pipeline_events()[-1]
    assert pipeline_event.step_name == "cohort_followup_coverage_monitor"
    assert pipeline_event.status == "warning"
    assert "anomalies=3" in (pipeline_event.message or "")


def test_backfill_repairs_partial_days_without_duplicate_states(tmp_path) -> None:
    cohort_id = "33333333-3333-4333-8333-333333333333"
    start_date = date(2026, 5, 13)
    symbols = ["AAA", "BBB", "CCC"]
    service = IntelligenceService(
        analysis_engine=FakeAnalysisEngine({}),
        scanner_engine=object(),
        backtest_engine=object(),
    )
    _wire_temp_storage(service, tmp_path)
    followup_dates = service._trading_days_between(start_date, date(2026, 5, 14))
    cohort = CandidateCohort(
        id=cohort_id,
        name="Repair partial coverage",
        start_date=start_date,
        market=MarketCode.US,
        analysis_window=ScannerDuration.ONE_YEAR,
        followup_enabled=True,
        followup_start_date=start_date,
        followup_target_days=28,
    )
    candidates = [
        CohortCandidate(
            cohort_id=cohort_id,
            symbol=symbol,
            market=MarketCode.US,
            selected_at=datetime(2026, 5, 13, tzinfo=UTC),
            selected_price=100.0,
            selected_rank=index + 1,
            selected_score=80.0,
        )
        for index, symbol in enumerate(symbols)
    ]
    snapshots = [
        CohortDailySnapshot(cohort_id=cohort_id, symbol=symbol, snapshot_date=followup_dates[0])
        for symbol in symbols
    ]
    snapshots.extend(
        CohortDailySnapshot(cohort_id=cohort_id, symbol=symbol, snapshot_date=followup_dates[1])
        for symbol in symbols[:2]
    )
    service._save_cohorts([cohort])
    service._save_cohort_candidates(candidates)
    service._save_cohort_snapshots(snapshots)
    generated_dates = []

    def generate_report(*, cohort_id: str, report_date: date, include_llm: bool):
        generated_dates.append(report_date)
        existing_snapshots = [
            snapshot
            for snapshot in service._read_cohort_snapshots()
            if not (snapshot.cohort_id == cohort_id and snapshot.snapshot_date == report_date)
        ]
        existing_snapshots.extend(
            CohortDailySnapshot(cohort_id=cohort_id, symbol=symbol, snapshot_date=report_date)
            for symbol in symbols
        )
        service._save_cohort_snapshots(existing_snapshots)
        return CohortDailyReportDetail(
            cohort_id=cohort_id,
            report_date=report_date,
            report_mode="followup",
            candidate_count=len(symbols),
            followup_snapshot_count=len(symbols),
        )

    service._generate_and_store_daily_report = generate_report

    first_backfill = service.backfill_cohort_followup(
        cohort_id,
        to_date=followup_dates[1],
        include_llm=False,
    )
    second_backfill = service.backfill_cohort_followup(
        cohort_id,
        to_date=followup_dates[1],
        include_llm=False,
    )

    assert generated_dates == [followup_dates[1]]
    assert first_backfill.generated == 1
    assert second_backfill.generated == 0
    assert second_backfill.skipped == 1
    repaired_states = [
        snapshot
        for snapshot in service._read_cohort_snapshots()
        if snapshot.cohort_id == cohort_id and snapshot.snapshot_date == followup_dates[1]
    ]
    assert sorted(snapshot.symbol for snapshot in repaired_states) == symbols


def test_selection_horizons_rejects_mismatched_source_symbol(tmp_path) -> None:
    requested_symbol = "AAA"
    dates = pd.date_range("2026-05-13", periods=30, freq="B")
    frame = pd.DataFrame({"close": [100.0 + index for index in range(len(dates))]}, index=dates)

    class MismatchedDataService:
        def get_market_data(self, symbol: str, market: str | None = None, period: str | None = None, use_cache: bool = True):
            return SimpleNamespace(normalized_ticker="WRONG", daily=frame.copy())

    service = IntelligenceService(
        analysis_engine=SimpleNamespace(data_service=MismatchedDataService()),
        scanner_engine=object(),
        backtest_engine=object(),
    )
    _wire_temp_storage(service, tmp_path)
    candidate = CohortCandidate(
        cohort_id="44444444-4444-4444-8444-444444444444",
        symbol=requested_symbol,
        market=MarketCode.US,
        selected_at=datetime(2026, 5, 13, tzinfo=UTC),
        selected_price=100.0,
        selected_rank=1,
        selected_score=80.0,
    )

    horizons = service._selection_price_horizons(
        candidate,
        selection_date=candidate.selected_at.date(),
        as_of_date=dates[-1].date(),
    )

    assert horizons["return_28d"] is None
    assert horizons["data_quality_flags"] == ["possible_symbol_price_mismatch"]


def test_selection_horizons_uses_the_28th_cohort_trading_day(tmp_path) -> None:
    symbol = "AAA"
    dates = pd.date_range("2026-05-13", periods=28, freq="B")
    frame = pd.DataFrame({"close": [100.0 + index for index in range(len(dates))]}, index=dates)
    service = IntelligenceService(
        analysis_engine=FakeAnalysisEngine({symbol: frame}),
        scanner_engine=object(),
        backtest_engine=object(),
    )
    _wire_temp_storage(service, tmp_path)
    candidate = CohortCandidate(
        cohort_id="66666666-6666-4666-8666-666666666666",
        symbol=symbol,
        market=MarketCode.US,
        selected_at=datetime(2026, 5, 13, tzinfo=UTC),
        selected_price=100.0,
        selected_rank=1,
        selected_score=80.0,
    )

    horizons = service._selection_price_horizons(
        candidate,
        selection_date=candidate.selected_at.date(),
        as_of_date=dates[-1].date(),
    )

    assert horizons["price_28d"] == 127.0
    assert horizons["return_28d"] == 27.0


def test_backfill_rehydrates_complete_daily_report_states_idempotently(tmp_path) -> None:
    cohort_id = "55555555-5555-4555-8555-555555555555"
    start_date = date(2026, 5, 13)
    symbols = ["AAA", "BBB", "CCC"]
    service = IntelligenceService(
        analysis_engine=FakeAnalysisEngine({}),
        scanner_engine=object(),
        backtest_engine=object(),
    )
    _wire_temp_storage(service, tmp_path)
    followup_dates = service._trading_days_between(start_date, date(2026, 5, 14))
    cohort = CandidateCohort(
        id=cohort_id,
        name="Rehydrated report states",
        start_date=start_date,
        market=MarketCode.US,
        analysis_window=ScannerDuration.ONE_YEAR,
        followup_enabled=True,
        followup_start_date=start_date,
        followup_target_days=2,
    )
    candidates = [
        CohortCandidate(
            cohort_id=cohort_id,
            symbol=symbol,
            market=MarketCode.US,
            selected_at=datetime(2026, 5, 13, tzinfo=UTC),
            selected_price=100.0,
            selected_rank=index + 1,
            selected_score=80.0,
        )
        for index, symbol in enumerate(symbols)
    ]
    service._save_cohorts([cohort])
    service._save_cohort_candidates(candidates)
    service._save_cohort_snapshots(
        [
            CohortDailySnapshot(cohort_id=cohort_id, symbol=symbol, snapshot_date=followup_dates[0])
            for symbol in symbols
        ]
    )
    report = CohortDailyReportDetail(
        id="report-5555",
        cohort_id=cohort_id,
        report_date=followup_dates[1],
        report_mode="followup",
        candidate_count=len(symbols),
        followup_snapshot_count=len(symbols),
        candidate_followup_json=[
            {
                "symbol": symbol,
                "latest_price": 101.0 + index,
                "return_since_selection": 1.0 + index,
                "return_1d": 0.5,
                "return_3d": 0.75,
                "return_7d": None,
                "return_14d": None,
                "return_28d": None,
                "validity_state": "pending_validation",
                "readiness": "pending_validation",
                "blocked_by": "none",
                "readiness_explanation": "Recovered from report.",
                "data_quality_flags": [],
            }
            for index, symbol in enumerate(symbols)
        ],
    )
    service.daily_report_store = FakeDailyReportStore(
        reports=[report],
        details={followup_dates[1]: report},
    )

    first_recovery = service._rehydrate_followup_snapshots_from_daily_reports(
        cohort,
        target_dates=followup_dates,
    )
    second_recovery = service._rehydrate_followup_snapshots_from_daily_reports(
        cohort,
        target_dates=followup_dates,
    )
    completed_backfill = service.backfill_cohort_followup(
        cohort_id,
        to_date=followup_dates[1],
        include_llm=False,
    )

    assert first_recovery == {"days": 1, "states": len(symbols)}
    assert second_recovery == {"days": 0, "states": 0}
    recovered_states = [
        snapshot
        for snapshot in service._read_cohort_snapshots()
        if snapshot.cohort_id == cohort_id and snapshot.snapshot_date == followup_dates[1]
    ]
    assert len(recovered_states) == len(symbols)
    assert {snapshot.symbol for snapshot in recovered_states} == set(symbols)
    assert {snapshot.state_source for snapshot in recovered_states} == {"rehydrated_daily_report"}
    assert {snapshot.source_report_id for snapshot in recovered_states} == {"report-5555"}
    assert completed_backfill.skipped == 1
    assert service.get_cohort_detail(cohort_id).cohort.followup_completed is True
