from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, Field


class CategoryScores(BaseModel):
    momentum_score: float
    trend_score: float
    volatility_score: float
    structure_score: float
    context_score: float


class TradePlan(BaseModel):
    bias: str
    entry_zone: tuple[float, float]
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    risk_reward: float
    invalidation_note: str


class AnalysisResponse(BaseModel):
    ticker: str
    as_of: date
    final_score: float
    category_scores: CategoryScores
    indicator_summary: dict[str, Any]
    interpreted_signals: dict[str, str]
    swing_candidate: bool
    trade_plan: TradePlan


class ScoreResponse(BaseModel):
    ticker: str
    as_of: date
    final_score: float
    category_scores: CategoryScores
    interpreted_signals: dict[str, str]


class TradePlanResponse(BaseModel):
    ticker: str
    as_of: date
    final_score: float
    swing_candidate: bool
    trade_plan: TradePlan


class BacktestTrade(BaseModel):
    entry_date: date
    exit_date: date
    entry_price: float
    exit_price: float
    return_pct: float
    hold_days: int
    result: str


class BacktestSummary(BaseModel):
    ticker: str
    period_start: date
    period_end: date
    trades: int
    win_rate: float
    average_return: float
    max_drawdown: float
    average_hold_days: float
    expectancy: float
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sample_trades: list[BacktestTrade]
