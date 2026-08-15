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
