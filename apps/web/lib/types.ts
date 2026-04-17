export type AnalysisWindow = "5d" | "1m" | "3m" | "6m" | "1y" | "2y" | "3y" | "4y" | "5y" | "10y";
export type BacktestHistoryWindow = "1y" | "2y" | "3y" | "4y" | "5y";
export type MarketCode = "us" | "bist";
export type StrategyMode = "aggressive" | "balanced" | "conservative" | "custom";

export type RegimeFilterSettings = {
  regime_mode: string;
};

export type LocationFilterSettings = {
  max_support_distance_pct: number;
  min_resistance_room_pct: number;
  max_overextension_ema20_pct: number;
  max_overextension_ema50_pct: number;
  max_overextension_ema100_pct: number;
  max_overextension_ema200_pct: number;
};

export type TriggerFilterSettings = {
  min_trigger_score: number;
};

export type AnalysisConfig = {
  ticker: string;
  market: MarketCode;
  lookback_window: AnalysisWindow;
  strategy_mode: StrategyMode;
  score_threshold: number;
  warmup_bars: number;
  regime_filter: RegimeFilterSettings;
  location_filter: LocationFilterSettings;
  trigger_filter: TriggerFilterSettings;
};

export type CategoryScores = {
  momentum_score: number;
  trend_score: number;
  volatility_score: number;
  structure_score: number;
  context_score: number;
};

export type TradePlan = {
  bias: string;
  entry_zone: [number, number];
  stop_loss: number;
  take_profit_1: number;
  take_profit_2: number;
  risk_reward: number;
  invalidation_note: string;
};

export type ChartCandle = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type ChartLinePoint = {
  date: string;
  value: number;
};

export type AnalysisChart = {
  candles: ChartCandle[];
  ema_20: ChartLinePoint[];
  ema_50: ChartLinePoint[];
  ema_100: ChartLinePoint[];
  ema_200: ChartLinePoint[];
  current_price: number;
  support_levels: number[];
  resistance_levels: number[];
  fibonacci_levels: Record<string, number>;
  trade_plan_overlay: TradePlan | null;
};

export type QuantEdgeSection = {
  final_score: number;
  category_scores: CategoryScores;
  summary_interpretation: string;
  structured_score_breakdown: Record<string, number>;
};

export type SwingPulseSection = {
  swing_candidate: boolean;
  setup_quality: number;
  entry_zone: [number, number];
  stop_loss: number;
  take_profit_levels: number[];
  risk_reward: number;
  invalidation_note: string;
  strategy_mode_used: StrategyMode;
  score_threshold_used: number;
};

export type RegimeDiagnostics = {
  regime_valid: boolean;
  regime_mode_used: string;
  price_above_ema200: boolean;
  ema100_above_ema200: boolean;
  ema_stack_quality: string;
  price_vs_ema200_pct: number;
  ema200_slope_state: string;
  ema_stack_alignment: string;
  bars_since_reclaim: number | null;
  regime_reason_code: string;
  regime_reason: string;
};

export type LocationDiagnostics = {
  location_valid: boolean;
  location_score: number;
  support_proximity_ok: boolean;
  resistance_room_ok: boolean;
  overextended_flag: boolean;
  support_distance_pct: number;
  resistance_distance_pct: number;
  overextension_ema20_pct: number;
  overextension_ema50_pct: number;
  overextension_ema100_pct: number;
  overextension_ema200_pct: number;
  distance_to_ema20_pct: number;
  distance_to_ema50_pct: number;
  distance_to_ema100_pct: number;
  distance_to_ema200_pct: number;
  distance_to_support_pct: number;
  resistance_room_pct: number;
  support_quality_score: number;
  pullback_depth: string;
  extension_state: string;
  location_reason: string;
};

export type TriggerDiagnostics = {
  trigger_valid: boolean;
  trigger_state: string;
  trigger_type: string;
  trigger_score: number;
  trigger_reason: string;
};

export type SetupInterpretation = {
  trend_state: string;
  pullback_state: string;
  extension_state: string;
  resistance_test_state: string;
  trigger_state: string;
  trigger_type: string;
  setup_status: string;
  reasoning_tags: string[];
};

export type EntryGateDiagnostics = {
  final_score: number;
  score_threshold_used: number;
  score_threshold_passed: boolean;
  regime_valid: boolean;
  location_valid: boolean;
  trigger_valid: boolean;
  entry_quality_score: number;
  final_entry_decision: boolean;
  skip_reason: string | null;
};

export type AnalysisPipelineResult = {
  pipeline_order: string[];
  final_score: number;
  threshold_passed: boolean;
  regime_valid: boolean;
  location_valid: boolean;
  trigger_valid: boolean;
  final_entry_decision: boolean;
  setup_status: string;
  diagnostics: Record<string, unknown>;
};

export type DetectedLevel = {
  level_name: string;
  value: number;
  level_type: string;
};

export type ChartMapSection = {
  ema_proximity_summary: string;
  nearest_support: number | null;
  nearest_resistance: number | null;
  nearest_fib_zone: string | null;
  market_state: string;
  candle_confirmation_summary: string;
  detected_levels: DetectedLevel[];
};

export type CombinedAnalysisResponse = {
  ticker: string;
  normalized_ticker: string;
  market: MarketCode;
  window: AnalysisWindow;
  as_of: string;
  analysis_config: AnalysisConfig;
  chart: AnalysisChart;
  quantedge: QuantEdgeSection;
  swingpulse: SwingPulseSection;
  chartmap: ChartMapSection;
  regime: RegimeDiagnostics;
  location: LocationDiagnostics;
  trigger: TriggerDiagnostics;
  setup_interpretation: SetupInterpretation;
  entry_gate: EntryGateDiagnostics;
  analysis_pipeline: AnalysisPipelineResult;
  strategy_mode_used: StrategyMode;
  interpreted_signals: Record<string, string>;
  indicator_summary: Record<string, unknown>;
  trade_plan_summary: string;
};

export type AnalysisResponse = {
  ticker: string;
  as_of: string;
  final_score: number;
  category_scores: CategoryScores;
  indicator_summary: Record<string, unknown>;
  interpreted_signals: Record<string, string>;
  swing_candidate: boolean;
  trade_plan: TradePlan;
};

export type ScoreResponse = {
  ticker: string;
  as_of: string;
  final_score: number;
  category_scores: CategoryScores;
  interpreted_signals: Record<string, string>;
};

export type TradePlanResponse = {
  ticker: string;
  as_of: string;
  final_score: number;
  swing_candidate: boolean;
  trade_plan: TradePlan;
};

export type BacktestTrade = {
  trade_id: number;
  entry_date: string;
  exit_date: string;
  entry_price: number;
  exit_price: number;
  stop_loss: number | null;
  take_profit: number | null;
  return_pct: number;
  hold_days: number;
  result: string;
  entry_reason: string | null;
  exit_reason: string | null;
  threshold_used: number | null;
  score_at_entry: number | null;
  score_at_exit: number | null;
  major_conditions_met: string[];
  score_exit_threshold: number | null;
  strategy_mode_used: StrategyMode;
  regime_valid: boolean;
  location_valid: boolean;
  trigger_valid: boolean;
  trigger_type: string | null;
  regime_reason: string | null;
  location_reason: string | null;
  trigger_reason: string | null;
  support_distance_pct: number | null;
  resistance_distance_pct: number | null;
  overextended_flag: boolean;
  entry_quality_score: number | null;
  trend_state: string | null;
  setup_status: string | null;
  trigger_state: string | null;
  reasoning_tags: string[];
};

export type BacktestMarker = {
  date: string;
  price: number;
  marker_type: string;
  label: string;
  hover_text: string | null;
  trade_id: number | null;
};

export type SkippedEntrySignal = {
  date: string;
  final_score: number;
  threshold_used: number;
  setup_status: string;
  first_failed_gate: string | null;
  reason: string;
  reason_detail: string | null;
  swing_candidate: boolean;
  strategy_mode_used: StrategyMode;
  regime_valid: boolean | null;
  location_valid: boolean | null;
  trigger_valid: boolean | null;
  trigger_state: string | null;
  trigger_score: number | null;
  trend_state: string | null;
  support_distance_pct: number | null;
  resistance_room_pct: number | null;
  price_vs_ema200_pct: number | null;
  ema200_slope_state: string | null;
  ema_stack_alignment: string | null;
  regime_reason_code: string | null;
};

export type BacktestResponse = {
  ticker: string;
  period_start: string;
  period_end: string;
  analysis_config: AnalysisConfig;
  trades: number;
  win_rate: number;
  average_return: number;
  max_drawdown: number;
  average_hold_days: number;
  expectancy: number;
  score_threshold_used: number;
  strategy_mode_used: StrategyMode;
  generated_at: string;
  sample_trades: BacktestTrade[];
};

export type BacktestFromAnalysisRequest = {
  ticker: string;
  market: MarketCode;
  window: AnalysisWindow;
  analysis_as_of: string;
  analysis_config?: AnalysisConfig;
  quantedge_final_score: number;
  category_scores: CategoryScores;
  swing_candidate: boolean;
  trade_plan: TradePlan;
  backtest_score_threshold?: number;
  strategy_mode?: StrategyMode;
  backtest_history_window?: BacktestHistoryWindow;
  visible_chart_window?: AnalysisWindow;
};

export type BacktestFromAnalysisResponse = {
  ticker: string;
  normalized_ticker: string;
  market: MarketCode;
  window: AnalysisWindow;
  generated_from_analysis: boolean;
  analysis_as_of: string;
  analysis_config: AnalysisConfig;
  period_start: string;
  period_end: string;
  trades: number;
  win_rate: number;
  average_return: number;
  max_drawdown: number;
  average_hold_days: number;
  expectancy: number;
  score_threshold_used: number;
  strategy_mode_used: StrategyMode;
  evaluation_history_window: BacktestHistoryWindow;
  visible_chart_window: AnalysisWindow;
  evaluation_start: string;
  evaluation_end: string;
  warmup_bars_used: number;
  evaluated_bars: number;
  visible_start: string;
  visible_end: string;
  entries_considered: number;
  entries_triggered: number;
  skipped_due_to_threshold: number;
  skipped_due_to_setup: number;
  skipped_regime: number;
  skipped_location: number;
  skipped_trigger: number;
  skipped_overextended: number;
  skipped_resistance_room: number;
  actionable_setups: number;
  watchlist_setups: number;
  avoid_setups: number;
  generated_at: string;
  trades_table: BacktestTrade[];
  skipped_signals_sample: SkippedEntrySignal[];
  decision_log_sample: SkippedEntrySignal[];
  chart: AnalysisChart;
  markers: BacktestMarker[];
};
