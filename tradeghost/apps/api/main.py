from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query

from tradeghost.services.analysis_engine import AnalysisEngine
from tradeghost.services.backtest.engine import BacktestEngine
from tradeghost.services.backtest.review_log import BacktestReviewLogService
from tradeghost.services.scanner.engine import ScannerEngine
from tradeghost.shared.config.settings import get_settings
from tradeghost.shared.models.schemas import (
    AnalysisResponse,
    BacktestFromAnalysisRequest,
    BacktestFromAnalysisResponse,
    BacktestSummary,
    BacktestSnapshot,
    BacktestSnapshotCommentCreateRequest,
    BacktestSnapshotCreateRequest,
    CombinedAnalysisResponse,
    ScannerRequest,
    ScannerResponse,
    ScoreResponse,
    StrategyMode,
    TradePlanResponse,
)

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")

analysis_engine = AnalysisEngine()
backtest_engine = BacktestEngine(analysis_engine=analysis_engine)
review_log_service = BacktestReviewLogService()
scanner_engine = ScannerEngine(analysis_engine=analysis_engine)


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
