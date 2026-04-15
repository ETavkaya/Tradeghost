from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, Field
from tradeghost.shared.market import MarketCode


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


class QuantEdgeSection(BaseModel):
    final_score: float
    category_scores: CategoryScores
    summary_interpretation: str
    structured_score_breakdown: dict[str, float]


class SwingPulseSection(BaseModel):
    swing_candidate: bool
    setup_quality: float
    entry_zone: tuple[float, float]
    stop_loss: float
    take_profit_levels: list[float]
    risk_reward: float
    invalidation_note: str


class DetectedLevel(BaseModel):
    level_name: str
    value: float
    level_type: str


class ChartMapSection(BaseModel):
    ema_proximity_summary: str
    nearest_support: float | None
    nearest_resistance: float | None
    nearest_fib_zone: str | None
    market_state: str
    candle_confirmation_summary: str
    detected_levels: list[DetectedLevel]


class ChartCandle(BaseModel):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


class ChartLinePoint(BaseModel):
    date: date
    value: float


class BacktestMarker(BaseModel):
    date: date
    price: float
    marker_type: str
    label: str


class AnalysisChart(BaseModel):
    candles: list[ChartCandle]
    ema_20: list[ChartLinePoint]
    ema_50: list[ChartLinePoint]
    current_price: float
    support_levels: list[float]
    resistance_levels: list[float]
    fibonacci_levels: dict[str, float]
    trade_plan_overlay: TradePlan | None


class CombinedAnalysisResponse(BaseModel):
    ticker: str
    normalized_ticker: str
    market: MarketCode
    window: str
    as_of: date
    chart: AnalysisChart
    quantedge: QuantEdgeSection
    swingpulse: SwingPulseSection
    chartmap: ChartMapSection
    interpreted_signals: dict[str, str]
    indicator_summary: dict[str, Any]
    trade_plan_summary: str


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
    stop_loss: float | None = None
    take_profit: float | None = None
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


class BacktestFromAnalysisRequest(BaseModel):
    ticker: str
    market: MarketCode = MarketCode.US
    window: str
    analysis_as_of: date | None = None
    quantedge_final_score: float
    category_scores: CategoryScores
    swing_candidate: bool
    trade_plan: TradePlan


class BacktestFromAnalysisResponse(BaseModel):
    ticker: str
    normalized_ticker: str
    market: MarketCode
    window: str
    generated_from_analysis: bool
    analysis_as_of: date
    period_start: date
    period_end: date
    trades: int
    win_rate: float
    average_return: float
    max_drawdown: float
    average_hold_days: float
    expectancy: float
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    trades_table: list[BacktestTrade]
    chart: AnalysisChart
    markers: list[BacktestMarker]
