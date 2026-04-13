from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query

from tradeghost.services.analysis_engine import AnalysisEngine
from tradeghost.services.backtest.engine import BacktestEngine
from tradeghost.shared.config.settings import get_settings
from tradeghost.shared.models.schemas import AnalysisResponse, BacktestSummary, ScoreResponse, TradePlanResponse

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")

analysis_engine = AnalysisEngine()
backtest_engine = BacktestEngine(analysis_engine=analysis_engine)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


@app.get("/analyze", response_model=AnalysisResponse)
def analyze(ticker: str = Query(..., min_length=1, max_length=10)) -> AnalysisResponse:
    try:
        return analysis_engine.analyze(ticker)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/score", response_model=ScoreResponse)
def score(ticker: str = Query(..., min_length=1, max_length=10)) -> ScoreResponse:
    try:
        return analysis_engine.score_only(ticker)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/trade-plan", response_model=TradePlanResponse)
def trade_plan(ticker: str = Query(..., min_length=1, max_length=10)) -> TradePlanResponse:
    try:
        return analysis_engine.trade_plan_only(ticker)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/backtest", response_model=BacktestSummary)
def backtest(ticker: str = Query(..., min_length=1, max_length=10)) -> BacktestSummary:
    try:
        return backtest_engine.run(ticker)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=str(exc)) from exc

