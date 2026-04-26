export type AnalysisWindow = "5d" | "1m" | "3m" | "6m" | "1y" | "2y" | "3y" | "4y" | "5y" | "10y";
export type BacktestHistoryWindow = "1y" | "2y" | "3y" | "4y" | "5y";
export type MarketCode = "us" | "bist";
export type StrategyMode = "aggressive" | "balanced" | "conservative" | "momentum_continuation" | "custom";
export type ScannerCategory = "trend_mode" | "build_up" | "momentum_mode" | "value_rebuild" | "overextended";
export type ScannerDuration = "1y" | "2y" | "3y" | "5y";
export type ScannerUniverseScope = "full_universe" | "watchlist" | "capped_universe";
export type ScannerPriority = "high" | "medium" | "low";
export type ScannerRuleField =
  | "price_vs_ema200_pct"
  | "distance_to_ema20_pct"
  | "distance_to_ema50_pct"
  | "rsi_14"
  | "volume_ratio_20"
  | "support_distance_pct"
  | "resistance_room_pct"
  | "ema200_slope_state"
  | "trend_state";
export type ScannerRuleOperator = "gt" | "gte" | "lt" | "lte" | "eq" | "in";

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

export type ExtensionCapSettings = {
  ema20_pct: number;
  ema50_pct: number;
  ema100_pct: number;
  ema200_pct: number;
};

export type MomentumContinuationSettings = {
  momentum_min_score: number;
  momentum_min_volume_ratio: number;
  controlled_extension_caps: ExtensionCapSettings;
  blowoff_extension_caps: ExtensionCapSettings;
  allowed_trigger_types: string[];
  required_dynamics_state: string[];
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
  momentum_continuation: MomentumContinuationSettings;
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
  controlled_extension_flag: boolean;
  blowoff_extension_flag: boolean;
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
  setup_type: string;
  prior_breakout_failed: boolean;
  reclaim_attempt_count: number;
  second_attempt_breakout_candidate: boolean;
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
  transition_entry_allowed: boolean;
  momentum_continuation_entry_allowed: boolean;
  score_dynamics_state: string | null;
  volume_ratio_20: number | null;
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
  nearest_fib_level: number | null;
  distance_to_nearest_fib_pct: number | null;
  fib_ema_confluence_score: number | null;
  fib_support_confluence: boolean;
  next_fib_target: string | null;
  fib_target_room_pct: number | null;
  market_state: string;
  candle_confirmation_summary: string;
  opportunity_type: string | null;
  opportunity_interest_reason: string | null;
  opportunity_risk_reason: string | null;
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
  setup_type: string | null;
  extension_state: string | null;
  is_early_trend_transition: boolean;
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
  setup_type: string | null;
  extension_state: string | null;
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
  tested_setup_path?:
    | "all_eligible_paths"
    | "pullback_continuation"
    | "momentum_continuation"
    | "value_rebuild"
    | "second_breakout_attempt";
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
  fetched_data_range_start: string;
  fetched_data_range_end: string;
  evaluation_start: string;
  evaluation_end: string;
  warmup_bars_used: number;
  evaluated_bars: number;
  visible_start: string;
  visible_end: string;
  entries_considered: number;
  entries_triggered: number;
  max_hold_days_used: number;
  skipped_due_to_threshold: number;
  skipped_due_to_setup: number;
  skipped_regime: number;
  skipped_location: number;
  skipped_trigger: number;
  skipped_overextended: number;
  skipped_blowoff_extension: number;
  skipped_momentum_dynamics: number;
  skipped_resistance_room: number;
  skipped_ema200_transition: number;
  actionable_setups: number;
  watchlist_setups: number;
  avoid_setups: number;
  early_trend_transition_entries: number;
  early_trend_transition_wins: number;
  early_transition_skip_share_pct: number;
  momentum_continuation_entries: number;
  controlled_extension_entries: number;
  tested_setup_path:
    | "all_eligible_paths"
    | "pullback_continuation"
    | "momentum_continuation"
    | "value_rebuild"
    | "second_breakout_attempt";
  source_analysis_window: AnalysisWindow | null;
  path_diagnostics: Record<string, Record<string, number>>;
  fib_mode: string;
  fib_anchor_method: string;
  nearest_fib_level: number | null;
  fib_target_room_pct: number | null;
  fib_used_in_entry: boolean;
  fib_used_in_exit: boolean;
  exit_stop_loss_count: number;
  exit_take_profit_count: number;
  exit_timeout_count: number;
  exit_structure_break_count: number;
  exit_trailing_ema_count: number;
  generated_at: string;
  trades_table: BacktestTrade[];
  skipped_signals_sample: SkippedEntrySignal[];
  decision_log_sample: SkippedEntrySignal[];
  chart: AnalysisChart;
  markers: BacktestMarker[];
};

export type BacktestSnapshotMetrics = {
  total_trades: number;
  win_rate: number;
  expectancy: number;
  max_drawdown: number;
};

export type BacktestSnapshotSkipSummary = {
  threshold_fail: number;
  regime_fail: number;
  location_fail: number;
  trigger_fail: number;
  overextended_fail: number;
  resistance_room_fail: number;
  ema200_transition_fail: number;
};

export type BacktestSnapshotComment = {
  id: string;
  snapshot_id: string;
  commentator: string;
  timestamp: string;
  content: string;
  tags: string[];
};

export type BacktestSnapshot = {
  id: string;
  timestamp: string;
  symbol: string;
  market: MarketCode;
  mode: StrategyMode;
  review_status: string;
  experiment_group: string | null;
  evaluation_history: string;
  visible_window: string;
  config: AnalysisConfig;
  metrics: BacktestSnapshotMetrics;
  trades_summary: Record<string, unknown>;
  skip_summary: BacktestSnapshotSkipSummary;
  artifacts: Record<string, string>;
  comments: BacktestSnapshotComment[];
  github_mapping_hint: Record<string, string | null>;
};

export type ScannerScopeSummary = {
  market: MarketCode;
  category: ScannerCategory;
  duration: ScannerDuration;
  recommended_duration: ScannerDuration;
  universe_scope: ScannerUniverseScope;
  symbol_count: number;
  processed_count: number;
  max_results: number;
  runtime_seconds: number;
  partial_scan: boolean;
  partial_scan_note: string | null;
  category_eligible_count: number;
  relaxed_eligible_count: number;
  custom_filtered_count: number;
  ranked_count: number;
  final_returned_count: number;
  used_relaxed_fallback: boolean;
};

export type ScannerCustomRule = {
  field: ScannerRuleField;
  operator: ScannerRuleOperator;
  value_number?: number | null;
  value_text?: string | null;
  value_list?: string[];
};

export type ScannerRequest = {
  market: MarketCode;
  duration: ScannerDuration;
  category: ScannerCategory;
  max_results: number;
  universe_scope: ScannerUniverseScope;
  max_runtime_seconds?: number;
  use_custom_rules?: boolean;
  custom_rules?: ScannerCustomRule[];
  range_start?: string | null;
  range_end?: string | null;
  symbol_overrides?: string[];
};

export type ScannerResult = {
  symbol: string;
  normalized_symbol: string;
  scanner_score: number;
  category_tag: string;
  priority: ScannerPriority;
  short_reason: string;
  current_score: number;
  score_delta_short: number;
  score_delta_medium: number;
  score_dynamics_state: string;
  opportunity_type: string;
  momentum_fit_score: number;
  momentum_continuation_candidate: boolean;
  second_attempt_breakout_candidate: boolean;
  trend_state: string;
  setup_status: string;
  extension_state: string;
  nearest_fib_level: string | null;
  distance_to_nearest_fib_pct: number | null;
  fib_ema_confluence_score: number | null;
  fib_support_confluence: boolean;
  next_fib_target: string | null;
  fib_target_room_pct: number | null;
  price_to_book: number | null;
  price_to_earnings: number | null;
  market_cap: number | null;
  sector: string | null;
  price_vs_ema200_pct: number;
  ema200_slope_state: string;
  ema_stack_alignment: string;
  support_distance_pct: number;
  resistance_room_pct: number;
  volume_ratio_20: number;
  resistance_test_count: number;
  ema200_test_count: number;
  repeated_test_count: number;
  distance_from_range_low_pct: number | null;
  distance_to_range_high_pct: number | null;
  range_low: number | null;
  range_high: number | null;
  tradingview_url: string;
  bars_since_reclaim: number | null;
  compression_state: string;
};

export type ScannerResponse = {
  scope: ScannerScopeSummary;
  results: ScannerResult[];
  generated_at: string;
};

export type WatchlistItem = {
  watchlist_id: string;
  symbol: string;
  market: MarketCode;
  added_at: string;
  notes: string | null;
  added_price: number | null;
  added_price_estimated: boolean;
  current_price: number | null;
  pnl_since_added_pct: number | null;
  return_1m_pct: number | null;
  return_3m_pct: number | null;
  return_6m_pct: number | null;
  return_1y_pct: number | null;
  trend_state: string | null;
  score: number | null;
  score_dynamics_state: string | null;
  price_vs_ema200_pct: number | null;
  last_checked: string | null;
};

export type Watchlist = {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
  items: WatchlistItem[];
};

export type AlertSeverity = "info" | "watch" | "important" | "critical";
export type AlertScopeType = "symbol" | "watchlist";
export type AlertRuleType =
  | "near_ema20"
  | "near_ema50"
  | "near_ema100"
  | "near_ema200"
  | "cross_above_ema100"
  | "cross_above_ema200"
  | "cross_below_ema100"
  | "cross_below_ema200"
  | "price_gte"
  | "price_lte"
  | "trend_state_is"
  | "dynamics_state_is"
  | "scanner_top_n"
  | "reclaim_ema200"
  | "resistance_test_count_gte"
  | "volume_ratio_20_gte"
  | "rsi14_lte"
  | "rsi14_gte"
  | "new_breakout_high"
  | "blowoff_extension_warning"
  | "fib_ema_confluence_reached";

export type AlertRule = {
  id: string;
  scope_type: AlertScopeType;
  scope_ref: string;
  market: MarketCode;
  symbol: string | null;
  name: string;
  rule_type: AlertRuleType;
  parameters: Record<string, unknown>;
  timeframe: string;
  severity: AlertSeverity;
  color: string;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
  preferred_regime_mode: string | null;
  notification_email_enabled: boolean;
  notification_webhook_enabled: boolean;
  notification_enabled: boolean;
  notify_email: string | null;
  notification_status: string;
  scanner_category: ScannerCategory | null;
  watchlist_id: string | null;
  shortlisted_by: string | null;
  created_by: string | null;
  cooldown_minutes: number;
  last_checked: string | null;
  last_matched: string | null;
};

export type AlertEventStatus = "new" | "seen" | "archived";

export type AlertEvent = {
  id: string;
  alert_rule_id: string;
  timestamp: string;
  symbol: string;
  market: MarketCode;
  triggered_value: number | string | null;
  trigger_context: Record<string, unknown>;
  severity: AlertSeverity;
  status: AlertEventStatus;
  message: string;
  watchlist_id: string | null;
  scanner_category: ScannerCategory | null;
  shortlisted_by: string | null;
  notification_status: string;
  notified_to: string | null;
  notified_at: string | null;
  scanner_context: Record<string, unknown>;
  analysis_context: Record<string, unknown>;
};

export type AlertProfileSuggestionRule = {
  temp_id: string;
  name: string;
  rule_type: AlertRuleType;
  parameters: Record<string, unknown>;
  timeframe: string;
  severity: AlertSeverity;
  color: string;
  is_enabled: boolean;
  selected: boolean;
  rationale: string;
  cooldown_minutes: number;
};

export type AlertProfileSuggestionResponse = {
  symbol: string;
  market: MarketCode;
  scanner_category: ScannerCategory;
  watchlist_id: string | null;
  shortlisted_by: string | null;
  created_by: string | null;
  rules: AlertProfileSuggestionRule[];
};

export type MonitoringSchedule = {
  id: string;
  name: string;
  market: MarketCode;
  frequency: string;
  watchlist_id: string | null;
  symbols: string[];
  category: ScannerCategory;
  duration: ScannerDuration;
  max_results: number;
  is_enabled: boolean;
  mode: string;
  interval: string;
  created_at: string;
  updated_at: string;
  last_run_at: string | null;
  next_run_at: string | null;
};

export type MonitoringRunSummary = {
  started_at: string;
  finished_at: string;
  processed_rules: number;
  evaluated_symbols: number;
  events_created: number;
  partial_run: boolean;
  note: string | null;
};
