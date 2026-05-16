from __future__ import annotations

import logging
import threading
from fastapi import FastAPI, HTTPException, Query

from tradeghost.services.analysis_engine import AnalysisEngine
from tradeghost.services.backtest.engine import BacktestEngine
from tradeghost.services.backtest.review_log import BacktestReviewLogService
from tradeghost.services.intelligence.service import IntelligenceService
from tradeghost.services.monitoring.service import MonitoringService
from tradeghost.services.scanner.engine import ScannerEngine
from tradeghost.shared.config.settings import get_settings
from tradeghost.shared.models.schemas import (
    AlertEvent,
    AlertEventStatus,
    AlertEventStatusUpdateRequest,
    AlertRule,
    AlertRuleCreateRequest,
    AlertRuleUpdateRequest,
    AlertProfileApplyRequest,
    AlertProfileSuggestRequest,
    AlertProfileSuggestionResponse,
    AnalysisResponse,
    BacktestFromAnalysisRequest,
    BacktestFromAnalysisResponse,
    BacktestSummary,
    BacktestSnapshot,
    BacktestSnapshotCommentCreateRequest,
    BacktestSnapshotCreateRequest,
    CombinedAnalysisResponse,
    DailyBriefing,
    CandidateCohort,
    CohortDetail,
    CohortReportMode,
    CohortFollowupRequest,
    CohortFollowupResponse,
    CohortSymbolContextRequest,
    CohortBriefingRequest,
    CohortCleanupDuplicateRequest,
    CohortCleanupDuplicateResponse,
    CohortDeleteResponse,
    CohortStatusUpdateResponse,
    CohortReviewRequest,
    CohortReviewResponse,
    DiscoveryCreateCohortRequest,
    DailyBriefingRequest,
    DailyPipelineRequest,
    IntelligenceReviewApproval,
    IntelligenceReviewApprovalRequest,
    IntelligenceRunReport,
    IntelligenceRunReportExport,
    IntelligenceDashboardResponse,
    IntelligenceRunResponse,
    LLMConnectionStatus,
    LLMDebugLog,
    LLMResponseTestRequest,
    LLMResponseTestResult,
    PipelineDebugEvent,
    MonitoringRunRequest,
    MonitoringRunDueRequest,
    MonitoringRunSummary,
    MonitoringSchedule,
    MonitoringScheduleCreateRequest,
    MonitoringScheduleUpdateRequest,
    ScannerRequest,
    ScannerResponse,
    ScannerLLMQRequest,
    ScannerLLMQResponse,
    ScannerLLMQChatRequest,
    ScannerLLMQChatResponse,
    ScoreResponse,
    SymbolContextBatchRequest,
    SymbolContextBatchResponse,
    StrategyMode,
    SystemReview,
    SystemReviewRequest,
    TradePlanResponse,
    Watchlist,
    WatchlistCreateRequest,
    WatchlistItemCreateRequest,
    WatchlistRenameRequest,
)

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
logger = logging.getLogger(__name__)

analysis_engine = AnalysisEngine()
backtest_engine = BacktestEngine(analysis_engine=analysis_engine)
review_log_service = BacktestReviewLogService()
scanner_engine = ScannerEngine(analysis_engine=analysis_engine)
monitoring_service = MonitoringService(analysis_engine=analysis_engine, scanner_engine=scanner_engine)
intelligence_service = IntelligenceService(
    analysis_engine=analysis_engine,
    scanner_engine=scanner_engine,
    backtest_engine=backtest_engine,
)
_monitor_stop_event = threading.Event()
_monitor_thread: threading.Thread | None = None


def _background_monitor_loop() -> None:
    logger.info("background monitor loop started")
    while not _monitor_stop_event.is_set():
        try:
            monitoring_service.run_due_schedules(max_runtime_seconds=30.0)
        except Exception as exc:  # pragma: no cover
            logger.warning("background monitor loop error: %s", exc)
        _monitor_stop_event.wait(30.0)
    logger.info("background monitor loop stopped")


@app.on_event("startup")
def startup_background_monitor() -> None:
    global _monitor_thread
    if _monitor_thread is not None and _monitor_thread.is_alive():
        return
    _monitor_stop_event.clear()
    _monitor_thread = threading.Thread(target=_background_monitor_loop, name="tradeghost-monitor-loop", daemon=True)
    _monitor_thread.start()


@app.on_event("shutdown")
def shutdown_background_monitor() -> None:
    _monitor_stop_event.set()
    global _monitor_thread
    if _monitor_thread is not None and _monitor_thread.is_alive():
        _monitor_thread.join(timeout=2.0)
    _monitor_thread = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


@app.get("/analyze", response_model=AnalysisResponse)
def analyze(
    ticker: str = Query(..., min_length=1, max_length=12),
    market: str = Query(default="us"),
) -> AnalysisResponse:
    try:
        return analysis_engine.analyze(ticker, market=market)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/analyze-combined", response_model=CombinedAnalysisResponse)
def analyze_combined(
    ticker: str = Query(..., min_length=1, max_length=12),
    market: str = Query(default="us"),
    window: str = Query(default="6m"),
    strategy_mode: StrategyMode = Query(default=StrategyMode.BALANCED),
    score_threshold: float | None = Query(default=None, ge=0, le=100),
    warmup_bars: int | None = Query(default=None, ge=20, le=400),
    regime_mode: str | None = Query(default=None),
    max_support_distance_pct: float | None = Query(default=None, ge=0, le=30),
    min_resistance_room_pct: float | None = Query(default=None, ge=0, le=30),
    min_trigger_score: float | None = Query(default=None, ge=0, le=100),
    max_overextension_ema20_pct: float | None = Query(default=None, ge=0, le=40),
    max_overextension_ema50_pct: float | None = Query(default=None, ge=0, le=40),
    max_overextension_ema100_pct: float | None = Query(default=None, ge=0, le=40),
    max_overextension_ema200_pct: float | None = Query(default=None, ge=0, le=40),
) -> CombinedAnalysisResponse:
    try:
        return analysis_engine.analyze_combined(
            ticker=ticker,
            window=window,
            market=market,
            strategy_mode=strategy_mode,
            score_threshold=score_threshold,
            warmup_bars=warmup_bars,
            regime_mode=regime_mode,
            max_support_distance_pct=max_support_distance_pct,
            min_resistance_room_pct=min_resistance_room_pct,
            min_trigger_score=min_trigger_score,
            max_overextension_ema20_pct=max_overextension_ema20_pct,
            max_overextension_ema50_pct=max_overextension_ema50_pct,
            max_overextension_ema100_pct=max_overextension_ema100_pct,
            max_overextension_ema200_pct=max_overextension_ema200_pct,
        )
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/score", response_model=ScoreResponse)
def score(
    ticker: str = Query(..., min_length=1, max_length=12),
    market: str = Query(default="us"),
) -> ScoreResponse:
    try:
        return analysis_engine.score_only(ticker, market=market)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/trade-plan", response_model=TradePlanResponse)
def trade_plan(
    ticker: str = Query(..., min_length=1, max_length=12),
    market: str = Query(default="us"),
) -> TradePlanResponse:
    try:
        return analysis_engine.trade_plan_only(ticker, market=market)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/backtest", response_model=BacktestSummary)
def backtest(
    ticker: str = Query(..., min_length=1, max_length=12),
    market: str = Query(default="us"),
    window: str = Query(default="6m"),
    score_threshold: float | None = Query(default=None, ge=0, le=100),
    strategy_mode: StrategyMode = Query(default=StrategyMode.BALANCED),
    warmup_bars: int | None = Query(default=None, ge=20, le=400),
) -> BacktestSummary:
    try:
        return backtest_engine.run(
            ticker=ticker,
            window=window,
            market=market,
            score_threshold=score_threshold,
            strategy_mode=strategy_mode,
            warmup_bars=warmup_bars,
        )
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/backtest-from-analysis", response_model=BacktestFromAnalysisResponse)
def backtest_from_analysis(payload: BacktestFromAnalysisRequest) -> BacktestFromAnalysisResponse:
    try:
        return backtest_engine.run_from_analysis(payload)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/backtest-snapshots", response_model=BacktestSnapshot)
def create_backtest_snapshot(payload: BacktestSnapshotCreateRequest) -> BacktestSnapshot:
    try:
        return review_log_service.create_snapshot(payload)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/backtest-snapshots", response_model=list[BacktestSnapshot])
def list_backtest_snapshots() -> list[BacktestSnapshot]:
    try:
        return review_log_service.list_snapshots()
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/backtest-snapshots/{snapshot_id}", response_model=BacktestSnapshot)
def get_backtest_snapshot(snapshot_id: str) -> BacktestSnapshot:
    try:
        return review_log_service.get_snapshot(snapshot_id)
    except FileNotFoundError as exc:  # pragma: no cover
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/backtest-snapshots/{snapshot_id}/comments", response_model=BacktestSnapshot)
def add_backtest_snapshot_comment(snapshot_id: str, payload: BacktestSnapshotCommentCreateRequest) -> BacktestSnapshot:
    try:
        return review_log_service.add_comment(snapshot_id, payload)
    except FileNotFoundError as exc:  # pragma: no cover
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/scanner", response_model=ScannerResponse)
def scanner_legacy(
    market: str = Query(default="us"),
    duration: str = Query(default="2y"),
    category: str = Query(default="trend_mode"),
    max_results: int = Query(default=20, ge=1, le=100),
    universe_scope: str = Query(default="capped_universe"),
    max_runtime_seconds: float = Query(default=18.0, ge=3.0, le=45.0),
) -> ScannerResponse:
    try:
        payload = ScannerRequest(
            market=market,
            duration=duration,
            category=category,
            max_results=max_results,
            universe_scope=universe_scope,
            max_runtime_seconds=max_runtime_seconds,
        )
        return scanner_engine.scan(payload)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/scanner", response_model=ScannerResponse)
def scanner(payload: ScannerRequest) -> ScannerResponse:
    try:
        return scanner_engine.scan(payload)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/scanner/llmq", response_model=ScannerLLMQResponse)
def scanner_llmq(payload: ScannerLLMQRequest) -> ScannerLLMQResponse:
    try:
        return scanner_engine.generate_llmq(payload)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/intelligence/llmq/chat", response_model=ScannerLLMQChatResponse)
def intelligence_llmq_chat(payload: ScannerLLMQChatRequest) -> ScannerLLMQChatResponse:
    try:
        logger.info("[LLMQ] chat endpoint called")
        logger.info("[LLMQ] /chat called symbol=%s messages=%s", payload.symbol, len(payload.messages))
        return scanner_engine.chat_llmq(payload)
    except Exception as exc:  # pragma: no cover
        logger.exception("[LLMQ] /chat failed symbol=%s error=%s", payload.symbol, str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/watchlists", response_model=list[Watchlist])
def list_watchlists() -> list[Watchlist]:
    try:
        return monitoring_service.list_watchlists()
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/watchlists", response_model=Watchlist)
def create_watchlist(payload: WatchlistCreateRequest) -> Watchlist:
    try:
        return monitoring_service.create_watchlist(payload)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/watchlists/{watchlist_id}", response_model=Watchlist)
def rename_watchlist(watchlist_id: str, payload: WatchlistRenameRequest) -> Watchlist:
    try:
        return monitoring_service.rename_watchlist(watchlist_id, payload)
    except FileNotFoundError as exc:  # pragma: no cover
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/watchlists/{watchlist_id}")
def delete_watchlist(watchlist_id: str) -> dict[str, str]:
    try:
        monitoring_service.delete_watchlist(watchlist_id)
        return {"status": "ok"}
    except FileNotFoundError as exc:  # pragma: no cover
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/watchlists/{watchlist_id}/items", response_model=Watchlist)
def add_watchlist_item(watchlist_id: str, payload: WatchlistItemCreateRequest) -> Watchlist:
    try:
        return monitoring_service.add_watchlist_item(watchlist_id, payload)
    except FileNotFoundError as exc:  # pragma: no cover
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/watchlists/{watchlist_id}/refresh-metrics", response_model=Watchlist)
def refresh_watchlist_metrics(watchlist_id: str) -> Watchlist:
    try:
        monitoring_service.run_monitoring(
            MonitoringRunRequest(
                watchlist_id=watchlist_id,
                max_runtime_seconds=30.0,
                max_symbols_per_batch=200,
            )
        )
        return monitoring_service.refresh_watchlist_metrics(watchlist_id)
    except FileNotFoundError as exc:  # pragma: no cover
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/watchlists/{watchlist_id}/items")
def remove_watchlist_item(
    watchlist_id: str,
    symbol: str = Query(...),
    market: str = Query(...),
) -> Watchlist:
    try:
        return monitoring_service.remove_watchlist_item(watchlist_id, symbol=symbol, market=market)
    except FileNotFoundError as exc:  # pragma: no cover
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/alert-rules", response_model=list[AlertRule])
def list_alert_rules(
    symbol: str | None = Query(default=None),
    watchlist_id: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
) -> list[AlertRule]:
    try:
        return monitoring_service.list_alert_rules(
            symbol=symbol,
            watchlist_id=watchlist_id,
            severity=severity,
            enabled=enabled,
        )
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/alert-rules", response_model=AlertRule)
def create_alert_rule(payload: AlertRuleCreateRequest) -> AlertRule:
    try:
        return monitoring_service.create_alert_rule(payload)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/alert-profiles/suggest", response_model=AlertProfileSuggestionResponse)
def suggest_alert_profile(payload: AlertProfileSuggestRequest) -> AlertProfileSuggestionResponse:
    try:
        return monitoring_service.suggest_alert_profile(payload)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/alert-profiles/apply", response_model=list[AlertRule])
def apply_alert_profile(payload: AlertProfileApplyRequest) -> list[AlertRule]:
    try:
        return monitoring_service.apply_alert_profile(payload)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/alert-rules/{rule_id}", response_model=AlertRule)
def update_alert_rule(rule_id: str, payload: AlertRuleUpdateRequest) -> AlertRule:
    try:
        return monitoring_service.update_alert_rule(rule_id, payload)
    except FileNotFoundError as exc:  # pragma: no cover
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/alert-rules/{rule_id}")
def delete_alert_rule(rule_id: str) -> dict[str, str]:
    try:
        monitoring_service.delete_alert_rule(rule_id)
        return {"status": "ok"}
    except FileNotFoundError as exc:  # pragma: no cover
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/alert-events", response_model=list[AlertEvent])
def list_alert_events(
    status: AlertEventStatus | None = Query(default=None),
    severity: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
) -> list[AlertEvent]:
    try:
        return monitoring_service.list_alert_events(status=status, severity=severity, symbol=symbol)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/alert-events/{event_id}/status", response_model=AlertEvent)
def update_alert_event_status(event_id: str, payload: AlertEventStatusUpdateRequest) -> AlertEvent:
    try:
        return monitoring_service.update_event_status(event_id, payload)
    except FileNotFoundError as exc:  # pragma: no cover
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/monitoring/schedules", response_model=list[MonitoringSchedule])
def list_monitoring_schedules() -> list[MonitoringSchedule]:
    try:
        return monitoring_service.list_schedules()
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/monitoring/schedules", response_model=MonitoringSchedule)
def create_monitoring_schedule(payload: MonitoringScheduleCreateRequest) -> MonitoringSchedule:
    try:
        return monitoring_service.create_schedule(payload)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/monitoring/schedules/{schedule_id}", response_model=MonitoringSchedule)
def update_monitoring_schedule(schedule_id: str, payload: MonitoringScheduleUpdateRequest) -> MonitoringSchedule:
    try:
        return monitoring_service.update_schedule(schedule_id, payload)
    except FileNotFoundError as exc:  # pragma: no cover
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/monitoring/schedules/{schedule_id}")
def delete_monitoring_schedule(schedule_id: str) -> dict[str, str]:
    try:
        monitoring_service.delete_schedule(schedule_id)
        return {"status": "ok"}
    except FileNotFoundError as exc:  # pragma: no cover
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/monitoring/run", response_model=MonitoringRunSummary)
def run_monitoring(payload: MonitoringRunRequest) -> MonitoringRunSummary:
    try:
        return monitoring_service.run_monitoring(payload)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/monitoring/run-due", response_model=MonitoringRunSummary)
def run_due_monitoring(payload: MonitoringRunDueRequest) -> MonitoringRunSummary:
    try:
        return monitoring_service.run_due_schedules(max_runtime_seconds=payload.max_runtime_seconds)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/intelligence/daily-pipeline", response_model=IntelligenceRunResponse)
def run_daily_pipeline(payload: DailyPipelineRequest) -> IntelligenceRunResponse:
    try:
        return intelligence_service.run_daily_pipeline(payload)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/intelligence/discovery/create-cohort", response_model=CohortDetail)
def run_discovery_create_cohort(payload: DiscoveryCreateCohortRequest) -> CohortDetail:
    try:
        return intelligence_service.run_discovery_create_cohort(payload)
    except ValueError as exc:  # pragma: no cover
        raise HTTPException(
            status_code=422,
            detail={
                "detail": "Cohort creation validation failed.",
                "failed_stage": "create_cohort_validation",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "suggested_action": "Check cohort name, categories, market/window, and duplicate strategy.",
            },
        ) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/intelligence/cohorts", response_model=list[CandidateCohort])
def list_intelligence_cohorts() -> list[CandidateCohort]:
    try:
        return intelligence_service.list_cohorts()
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/intelligence/cohorts/{cohort_id}", response_model=CohortDetail)
def get_intelligence_cohort_detail(cohort_id: str) -> CohortDetail:
    try:
        return intelligence_service.get_cohort_detail(cohort_id)
    except FileNotFoundError as exc:  # pragma: no cover
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/intelligence/cohorts/{cohort_id}/archive", response_model=CohortStatusUpdateResponse)
def archive_intelligence_cohort(cohort_id: str) -> CohortStatusUpdateResponse:
    try:
        return intelligence_service.archive_cohort(cohort_id)
    except FileNotFoundError as exc:  # pragma: no cover
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/intelligence/cohorts/{cohort_id}/activate", response_model=CohortStatusUpdateResponse)
def activate_intelligence_cohort(cohort_id: str) -> CohortStatusUpdateResponse:
    try:
        return intelligence_service.activate_cohort(cohort_id)
    except FileNotFoundError as exc:  # pragma: no cover
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/intelligence/cohorts/{cohort_id}", response_model=CohortDeleteResponse)
def delete_intelligence_cohort(cohort_id: str) -> CohortDeleteResponse:
    try:
        return intelligence_service.delete_cohort(cohort_id)
    except FileNotFoundError as exc:  # pragma: no cover
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/intelligence/cohorts/cleanup-duplicates", response_model=CohortCleanupDuplicateResponse)
def cleanup_intelligence_duplicate_cohorts(payload: CohortCleanupDuplicateRequest) -> CohortCleanupDuplicateResponse:
    try:
        return intelligence_service.cleanup_duplicate_cohorts(payload)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/intelligence/cohorts/follow-up", response_model=CohortFollowupResponse)
def run_intelligence_cohort_followup(payload: CohortFollowupRequest) -> CohortFollowupResponse:
    try:
        return intelligence_service.run_cohort_followup(payload)
    except FileNotFoundError as exc:  # pragma: no cover
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/intelligence/cohorts/symbol-contexts", response_model=SymbolContextBatchResponse)
def generate_cohort_symbol_contexts(payload: CohortSymbolContextRequest) -> SymbolContextBatchResponse:
    try:
        return intelligence_service.generate_cohort_symbol_contexts(payload)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=400,
            detail={
                "detail": "Cohort symbol context generation completed with failures." if "failed" in str(exc).lower() else "Cohort symbol context generation failed",
                "failed_stage": "cohort_symbol_context_batch",
                "failed_symbol": None,
                "llm_provider": settings.llm_provider,
                "llm_fallback_provider": settings.llm_fallback_provider,
                "primary_endpoint": settings.openai_base_url if settings.llm_provider.lower() == "openai" else settings.ollama_base_url,
                "model": payload.model,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
        ) from exc


@app.post("/intelligence/cohorts/briefing", response_model=DailyBriefing)
def generate_cohort_briefing(payload: CohortBriefingRequest) -> DailyBriefing:
    try:
        return intelligence_service.generate_cohort_briefing(payload)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/intelligence/cohorts/review", response_model=CohortReviewResponse)
def run_intelligence_cohort_review(payload: CohortReviewRequest) -> CohortReviewResponse:
    try:
        return intelligence_service.run_cohort_review(payload)
    except FileNotFoundError as exc:  # pragma: no cover
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/intelligence/cohorts/{cohort_id}/export", response_model=IntelligenceRunReportExport)
def export_intelligence_cohort_report(
    cohort_id: str,
    mode: CohortReportMode = Query(default=CohortReportMode.FOLLOWUP),
) -> IntelligenceRunReportExport:
    try:
        return intelligence_service.export_cohort_report_markdown(cohort_id, report_mode=mode)
    except FileNotFoundError as exc:  # pragma: no cover
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/intelligence/symbol-contexts", response_model=SymbolContextBatchResponse)
def generate_symbol_contexts(payload: SymbolContextBatchRequest) -> SymbolContextBatchResponse:
    try:
        return intelligence_service.generate_symbol_contexts(payload)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=400,
            detail={
                "detail": "Symbol context generation failed",
                "failed_stage": "symbol_context_batch",
                "failed_symbol": None,
                "llm_provider": settings.llm_provider,
                "llm_fallback_provider": settings.llm_fallback_provider,
                "ollama_endpoint": settings.ollama_base_url,
                "model": payload.model,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
        ) from exc


@app.post("/intelligence/daily-briefing", response_model=DailyBriefing)
def generate_daily_briefing(payload: DailyBriefingRequest) -> DailyBriefing:
    try:
        return intelligence_service.generate_daily_briefing(payload)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/intelligence/review", response_model=SystemReview)
def run_system_review(payload: SystemReviewRequest) -> SystemReview:
    try:
        return intelligence_service.run_system_review(payload)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/intelligence/report/{run_id}", response_model=IntelligenceRunReport)
def get_intelligence_run_report(run_id: str) -> IntelligenceRunReport:
    try:
        return intelligence_service.get_run_report(run_id)
    except FileNotFoundError as exc:  # pragma: no cover
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/intelligence/report/{run_id}/export", response_model=IntelligenceRunReportExport)
def export_intelligence_run_report(run_id: str) -> IntelligenceRunReportExport:
    try:
        return intelligence_service.export_run_report_markdown(run_id)
    except FileNotFoundError as exc:  # pragma: no cover
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/intelligence/report/approve", response_model=IntelligenceReviewApproval)
def approve_intelligence_run_report(payload: IntelligenceReviewApprovalRequest) -> IntelligenceReviewApproval:
    try:
        return intelligence_service.approve_run_report(payload)
    except FileNotFoundError as exc:  # pragma: no cover
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/intelligence/dashboard", response_model=IntelligenceDashboardResponse)
def get_intelligence_dashboard() -> IntelligenceDashboardResponse:
    try:
        return intelligence_service.get_dashboard()
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/intelligence/llm/status", response_model=LLMConnectionStatus)
def get_intelligence_llm_status() -> LLMConnectionStatus:
    try:
        return intelligence_service.get_llm_status()
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/intelligence/llm/logs", response_model=list[LLMDebugLog])
def get_intelligence_llm_logs(limit: int = Query(default=200, ge=1, le=500)) -> list[LLMDebugLog]:
    try:
        return intelligence_service.get_llm_logs(limit=limit)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/intelligence/pipeline-events", response_model=list[PipelineDebugEvent])
def get_intelligence_pipeline_events(limit: int = Query(default=250, ge=1, le=1500)) -> list[PipelineDebugEvent]:
    try:
        dashboard = intelligence_service.get_dashboard()
        return dashboard.pipeline_events[:limit]
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/intelligence/llm/test", response_model=LLMResponseTestResult)
def test_intelligence_llm_response(payload: LLMResponseTestRequest) -> LLMResponseTestResult:
    try:
        return intelligence_service.test_llm_response(payload)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc
