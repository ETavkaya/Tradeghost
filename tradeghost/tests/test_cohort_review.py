from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pandas as pd

from tradeghost.services.intelligence.service import IntelligenceService
from tradeghost.shared.models.schemas import (
    CandidateCohort,
    CohortCandidate,
    CohortDailySnapshot,
    CohortReviewRequest,
    MarketCode,
    ScannerCategory,
    ScannerDuration,
)


class FakeDailyReportStore:
    configured = True

    def list_reports(self, cohort_id: str):
        return []


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
        for snapshot_date in [date(2026, 7, 17), latest_followup_date]
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
