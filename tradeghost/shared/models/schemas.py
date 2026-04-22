from __future__ import annotations

from datetime import UTC, date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field
from tradeghost.shared.market import MarketCode


class StrategyMode(str, Enum):
    AGGRESSIVE = "aggressive"
    BALANCED = "balanced"
    CONSERVATIVE = "conservative"
    CUSTOM = "custom"


class RegimeFilterSettings(BaseModel):
    regime_mode: str


class LocationFilterSettings(BaseModel):
    max_support_distance_pct: float
    min_resistance_room_pct: float
    max_overextension_ema20_pct: float
    max_overextension_ema50_pct: float
    max_overextension_ema100_pct: float
    max_overextension_ema200_pct: float


class TriggerFilterSettings(BaseModel):
    min_trigger_score: float


class AnalysisConfig(BaseModel):
    ticker: str
    market: MarketCode
    lookback_window: str
    strategy_mode: StrategyMode
    score_threshold: float
    warmup_bars: int
    regime_filter: RegimeFilterSettings
    location_filter: LocationFilterSettings
    trigger_filter: TriggerFilterSettings


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
    strategy_mode_used: StrategyMode
    score_threshold_used: float


class RegimeDiagnostics(BaseModel):
    regime_valid: bool
    regime_mode_used: str
    price_above_ema200: bool
    ema100_above_ema200: bool
    ema_stack_quality: str
    price_vs_ema200_pct: float
    ema200_slope_state: str
    ema_stack_alignment: str
    bars_since_reclaim: int | None = None
    regime_reason_code: str
    regime_reason: str


class LocationDiagnostics(BaseModel):
    location_valid: bool
    location_score: float
    support_proximity_ok: bool
    resistance_room_ok: bool
    overextended_flag: bool
    support_distance_pct: float
    resistance_distance_pct: float
    overextension_ema20_pct: float
    overextension_ema50_pct: float
    overextension_ema100_pct: float
    overextension_ema200_pct: float
    distance_to_ema20_pct: float
    distance_to_ema50_pct: float
    distance_to_ema100_pct: float
    distance_to_ema200_pct: float
    distance_to_support_pct: float
    resistance_room_pct: float
    support_quality_score: float
    pullback_depth: str
    extension_state: str
    location_reason: str


class TriggerDiagnostics(BaseModel):
    trigger_valid: bool
    trigger_state: str
    trigger_type: str
    trigger_score: float
    trigger_reason: str


class SetupInterpretation(BaseModel):
    trend_state: str
    pullback_state: str
    extension_state: str
    resistance_test_state: str
    trigger_state: str
    trigger_type: str
    setup_status: str
    reasoning_tags: list[str] = Field(default_factory=list)


class EntryGateDiagnostics(BaseModel):
    final_score: float
    score_threshold_used: float
    score_threshold_passed: bool
    regime_valid: bool
    location_valid: bool
    trigger_valid: bool
    entry_quality_score: float
    transition_entry_allowed: bool = False
    final_entry_decision: bool
    skip_reason: str | None = None


class AnalysisPipelineResult(BaseModel):
    pipeline_order: list[str]
    final_score: float
    threshold_passed: bool
    regime_valid: bool
    location_valid: bool
    trigger_valid: bool
    final_entry_decision: bool
    setup_status: str
    diagnostics: dict[str, Any]


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
    hover_text: str | None = None
    trade_id: int | None = None


class AnalysisChart(BaseModel):
    candles: list[ChartCandle]
    ema_20: list[ChartLinePoint]
    ema_50: list[ChartLinePoint]
    ema_100: list[ChartLinePoint]
    ema_200: list[ChartLinePoint]
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
    analysis_config: AnalysisConfig
    chart: AnalysisChart
    quantedge: QuantEdgeSection
    swingpulse: SwingPulseSection
    chartmap: ChartMapSection
    regime: RegimeDiagnostics
    location: LocationDiagnostics
    trigger: TriggerDiagnostics
    setup_interpretation: SetupInterpretation
    entry_gate: EntryGateDiagnostics
    analysis_pipeline: AnalysisPipelineResult
    strategy_mode_used: StrategyMode
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
    trade_id: int
    entry_date: date
    exit_date: date
    entry_price: float
    exit_price: float
    stop_loss: float | None = None
    take_profit: float | None = None
    return_pct: float
    hold_days: int
    result: str
    entry_reason: str | None = None
    exit_reason: str | None = None
    threshold_used: float | None = None
    score_at_entry: float | None = None
    score_at_exit: float | None = None
    major_conditions_met: list[str] = Field(default_factory=list)
    score_exit_threshold: float | None = None
    strategy_mode_used: StrategyMode = StrategyMode.BALANCED
    regime_valid: bool = False
    location_valid: bool = False
    trigger_valid: bool = False
    trigger_type: str | None = None
    regime_reason: str | None = None
    location_reason: str | None = None
    trigger_reason: str | None = None
    support_distance_pct: float | None = None
    resistance_distance_pct: float | None = None
    overextended_flag: bool = False
    entry_quality_score: float | None = None
    trend_state: str | None = None
    setup_status: str | None = None
    trigger_state: str | None = None
    is_early_trend_transition: bool = False
    reasoning_tags: list[str] = Field(default_factory=list)


class SkippedEntrySignal(BaseModel):
    date: date
    final_score: float
    threshold_used: float
    setup_status: str = "watchlist"
    first_failed_gate: str | None = None
    reason: str
    reason_detail: str | None = None
    swing_candidate: bool
    strategy_mode_used: StrategyMode = StrategyMode.BALANCED
    regime_valid: bool | None = None
    location_valid: bool | None = None
    trigger_valid: bool | None = None
    trigger_state: str | None = None
    trigger_score: float | None = None
    trend_state: str | None = None
    support_distance_pct: float | None = None
    resistance_room_pct: float | None = None
    price_vs_ema200_pct: float | None = None
    ema200_slope_state: str | None = None
    ema_stack_alignment: str | None = None
    regime_reason_code: str | None = None


class BacktestSummary(BaseModel):
    ticker: str
    period_start: date
    period_end: date
    analysis_config: AnalysisConfig
    trades: int
    win_rate: float
    average_return: float
    max_drawdown: float
    average_hold_days: float
    expectancy: float
    score_threshold_used: float
    strategy_mode_used: StrategyMode
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sample_trades: list[BacktestTrade]


class BacktestFromAnalysisRequest(BaseModel):
    ticker: str
    market: MarketCode = MarketCode.US
    window: str
    analysis_as_of: date | None = None
    analysis_config: AnalysisConfig | None = None
    quantedge_final_score: float
    category_scores: CategoryScores
    swing_candidate: bool
    trade_plan: TradePlan
    backtest_score_threshold: float | None = None
    strategy_mode: StrategyMode | None = None
    backtest_history_window: str | None = None
    visible_chart_window: str | None = None


class BacktestFromAnalysisResponse(BaseModel):
    ticker: str
    normalized_ticker: str
    market: MarketCode
    window: str
    generated_from_analysis: bool
    analysis_as_of: date
    analysis_config: AnalysisConfig
    period_start: date
    period_end: date
    trades: int
    win_rate: float
    average_return: float
    max_drawdown: float
    average_hold_days: float
    expectancy: float
    score_threshold_used: float
    strategy_mode_used: StrategyMode
    evaluation_history_window: str
    visible_chart_window: str
    fetched_data_range_start: date
    fetched_data_range_end: date
    evaluation_start: date
    evaluation_end: date
    warmup_bars_used: int
    evaluated_bars: int
    visible_start: date
    visible_end: date
    entries_considered: int
    entries_triggered: int
    skipped_due_to_threshold: int
    skipped_due_to_setup: int
    skipped_regime: int
    skipped_location: int
    skipped_trigger: int
    skipped_overextended: int
    skipped_resistance_room: int
    skipped_ema200_transition: int
    actionable_setups: int
    watchlist_setups: int
    avoid_setups: int
    early_trend_transition_entries: int
    early_trend_transition_wins: int
    early_transition_skip_share_pct: float
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    trades_table: list[BacktestTrade]
    skipped_signals_sample: list[SkippedEntrySignal]
    decision_log_sample: list[SkippedEntrySignal]
    chart: AnalysisChart
    markers: list[BacktestMarker]


class ScannerCategory(str, Enum):
    TREND_MODE = "trend_mode"
    BUILD_UP = "build_up"
    MOMENTUM_MODE = "momentum_mode"
    OVEREXTENDED = "overextended"


class ScannerUniverseScope(str, Enum):
    FULL = "full_universe"
    WATCHLIST = "watchlist"
    CAPPED = "capped_universe"


class ScannerDuration(str, Enum):
    ONE_YEAR = "1y"
    TWO_YEAR = "2y"
    THREE_YEAR = "3y"
    FIVE_YEAR = "5y"


class ScannerPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ScannerRuleField(str, Enum):
    PRICE_VS_EMA200_PCT = "price_vs_ema200_pct"
    DISTANCE_TO_EMA20_PCT = "distance_to_ema20_pct"
    DISTANCE_TO_EMA50_PCT = "distance_to_ema50_pct"
    RSI_14 = "rsi_14"
    VOLUME_RATIO_20 = "volume_ratio_20"
    SUPPORT_DISTANCE_PCT = "support_distance_pct"
    RESISTANCE_ROOM_PCT = "resistance_room_pct"
    EMA200_SLOPE_STATE = "ema200_slope_state"
    TREND_STATE = "trend_state"


class ScannerRuleOperator(str, Enum):
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    EQ = "eq"
    IN = "in"


class ScannerCustomRule(BaseModel):
    field: ScannerRuleField
    operator: ScannerRuleOperator
    value_number: float | None = None
    value_text: str | None = None
    value_list: list[str] = Field(default_factory=list)


class ScannerRequest(BaseModel):
    market: MarketCode
    duration: ScannerDuration
    category: ScannerCategory
    max_results: int = Field(default=20, ge=1, le=100)
    universe_scope: ScannerUniverseScope = ScannerUniverseScope.CAPPED
    max_runtime_seconds: float = Field(default=18.0, ge=3.0, le=45.0)
    use_custom_rules: bool = False
    custom_rules: list[ScannerCustomRule] = Field(default_factory=list)
    range_start: date | None = None
    range_end: date | None = None
    symbol_overrides: list[str] = Field(default_factory=list)


class ScannerResult(BaseModel):
    symbol: str
    normalized_symbol: str
    scanner_score: float
    category_tag: str
    priority: ScannerPriority
    short_reason: str
    current_score: float
    score_delta_short: float
    score_delta_medium: float
    score_dynamics_state: str
    trend_state: str
    setup_status: str
    price_vs_ema200_pct: float
    ema200_slope_state: str
    ema_stack_alignment: str
    support_distance_pct: float
    resistance_room_pct: float
    volume_ratio_20: float
    resistance_test_count: int
    ema200_test_count: int
    repeated_test_count: int
    distance_from_range_low_pct: float | None = None
    distance_to_range_high_pct: float | None = None
    range_low: float | None = None
    range_high: float | None = None
    tradingview_url: str
    bars_since_reclaim: int | None = None
    compression_state: str


class ScannerScopeSummary(BaseModel):
    market: MarketCode
    category: ScannerCategory
    duration: ScannerDuration
    recommended_duration: ScannerDuration
    universe_scope: ScannerUniverseScope
    symbol_count: int
    processed_count: int
    max_results: int
    runtime_seconds: float
    partial_scan: bool
    partial_scan_note: str | None = None
    category_eligible_count: int = 0
    relaxed_eligible_count: int = 0
    custom_filtered_count: int = 0
    ranked_count: int = 0
    final_returned_count: int = 0
    used_relaxed_fallback: bool = False


class ScannerResponse(BaseModel):
    scope: ScannerScopeSummary
    results: list[ScannerResult]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WatchlistItem(BaseModel):
    watchlist_id: str
    symbol: str
    market: MarketCode
    added_at: datetime
    notes: str | None = None


class Watchlist(BaseModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    items: list[WatchlistItem] = Field(default_factory=list)


class WatchlistCreateRequest(BaseModel):
    name: str


class WatchlistRenameRequest(BaseModel):
    name: str


class WatchlistItemCreateRequest(BaseModel):
    symbol: str
    market: MarketCode
    notes: str | None = None


class AlertSeverity(str, Enum):
    INFO = "info"
    WATCH = "watch"
    IMPORTANT = "important"
    CRITICAL = "critical"


class AlertScopeType(str, Enum):
    SYMBOL = "symbol"
    WATCHLIST = "watchlist"


class AlertRuleType(str, Enum):
    NEAR_EMA20 = "near_ema20"
    NEAR_EMA50 = "near_ema50"
    NEAR_EMA200 = "near_ema200"
    PRICE_GTE = "price_gte"
    PRICE_LTE = "price_lte"
    TREND_STATE_IS = "trend_state_is"
    DYNAMICS_STATE_IS = "dynamics_state_is"
    SCANNER_TOP_N = "scanner_top_n"
    RECLAIM_EMA200 = "reclaim_ema200"
    RESISTANCE_TEST_COUNT_GTE = "resistance_test_count_gte"
    VOLUME_RATIO_20_GTE = "volume_ratio_20_gte"
    RSI14_LTE = "rsi14_lte"
    RSI14_GTE = "rsi14_gte"


class AlertRule(BaseModel):
    id: str
    scope_type: AlertScopeType
    scope_ref: str
    market: MarketCode
    symbol: str | None = None
    name: str
    rule_type: AlertRuleType
    parameters: dict[str, Any] = Field(default_factory=dict)
    timeframe: str = "daily"
    severity: AlertSeverity = AlertSeverity.WATCH
    color: str = "yellow"
    is_enabled: bool = True
    created_at: datetime
    updated_at: datetime
    preferred_regime_mode: str | None = None
    notification_email_enabled: bool = False
    notification_webhook_enabled: bool = False


class AlertRuleCreateRequest(BaseModel):
    scope_type: AlertScopeType
    scope_ref: str
    market: MarketCode
    symbol: str | None = None
    name: str
    rule_type: AlertRuleType
    parameters: dict[str, Any] = Field(default_factory=dict)
    timeframe: str = "daily"
    severity: AlertSeverity = AlertSeverity.WATCH
    color: str = "yellow"
    is_enabled: bool = True


class AlertRuleUpdateRequest(BaseModel):
    name: str | None = None
    parameters: dict[str, Any] | None = None
    severity: AlertSeverity | None = None
    color: str | None = None
    is_enabled: bool | None = None
    timeframe: str | None = None


class MonitoringSchedule(BaseModel):
    id: str
    name: str
    market: MarketCode
    frequency: str
    watchlist_id: str | None = None
    symbols: list[str] = Field(default_factory=list)
    category: ScannerCategory = ScannerCategory.TREND_MODE
    duration: ScannerDuration = ScannerDuration.TWO_YEAR
    max_results: int = 20
    is_enabled: bool = True
    created_at: datetime
    updated_at: datetime
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None


class MonitoringScheduleCreateRequest(BaseModel):
    name: str
    market: MarketCode
    frequency: str = "daily"
    watchlist_id: str | None = None
    symbols: list[str] = Field(default_factory=list)
    category: ScannerCategory = ScannerCategory.TREND_MODE
    duration: ScannerDuration = ScannerDuration.TWO_YEAR
    max_results: int = Field(default=20, ge=1, le=100)
    is_enabled: bool = True


class MonitoringScheduleUpdateRequest(BaseModel):
    name: str | None = None
    frequency: str | None = None
    watchlist_id: str | None = None
    symbols: list[str] | None = None
    category: ScannerCategory | None = None
    duration: ScannerDuration | None = None
    max_results: int | None = Field(default=None, ge=1, le=100)
    is_enabled: bool | None = None


class AlertEventStatus(str, Enum):
    NEW = "new"
    SEEN = "seen"
    ARCHIVED = "archived"


class AlertEvent(BaseModel):
    id: str
    alert_rule_id: str
    timestamp: datetime
    symbol: str
    market: MarketCode
    triggered_value: float | str | None = None
    trigger_context: dict[str, Any] = Field(default_factory=dict)
    severity: AlertSeverity
    status: AlertEventStatus = AlertEventStatus.NEW
    message: str
    scanner_context: dict[str, Any] = Field(default_factory=dict)
    analysis_context: dict[str, Any] = Field(default_factory=dict)


class AlertEventStatusUpdateRequest(BaseModel):
    status: AlertEventStatus


class MonitoringRunRequest(BaseModel):
    market: MarketCode | None = None
    watchlist_id: str | None = None
    symbols: list[str] = Field(default_factory=list)
    max_runtime_seconds: float = Field(default=20.0, ge=3.0, le=90.0)


class MonitoringRunSummary(BaseModel):
    started_at: datetime
    finished_at: datetime
    processed_rules: int
    evaluated_symbols: int
    events_created: int
    partial_run: bool
    note: str | None = None


class MonitoringRunDueRequest(BaseModel):
    max_runtime_seconds: float = Field(default=30.0, ge=5.0, le=120.0)


class BacktestSnapshotMetrics(BaseModel):
    total_trades: int
    win_rate: float
    expectancy: float
    max_drawdown: float


class BacktestSnapshotSkipSummary(BaseModel):
    threshold_fail: int
    regime_fail: int
    location_fail: int
    trigger_fail: int
    overextended_fail: int
    resistance_room_fail: int
    ema200_transition_fail: int = 0


class BacktestSnapshotComment(BaseModel):
    id: str
    snapshot_id: str
    commentator: str
    timestamp: datetime
    content: str
    tags: list[str] = Field(default_factory=list)


class BacktestSnapshot(BaseModel):
    id: str
    timestamp: datetime
    symbol: str
    market: MarketCode
    mode: StrategyMode
    review_status: str = "exploratory"
    experiment_group: str | None = None
    evaluation_history: str
    visible_window: str
    config: AnalysisConfig
    metrics: BacktestSnapshotMetrics
    trades_summary: dict[str, Any]
    skip_summary: BacktestSnapshotSkipSummary
    artifacts: dict[str, str] = Field(default_factory=dict)
    comments: list[BacktestSnapshotComment] = Field(default_factory=list)
    github_mapping_hint: dict[str, str | None] = Field(default_factory=dict)


class BacktestSnapshotCreateRequest(BaseModel):
    result: BacktestFromAnalysisResponse
    review_status: str = "exploratory"
    experiment_group: str | None = None


class BacktestSnapshotCommentCreateRequest(BaseModel):
    commentator: str
    content: str
    tags: list[str] = Field(default_factory=list)
