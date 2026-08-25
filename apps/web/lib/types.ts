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
  | "distance_to_ema100_pct"
  | "distance_to_ema200_pct"
  | "abs_distance_to_ema20_pct"
  | "abs_distance_to_ema50_pct"
  | "abs_distance_to_ema100_pct"
  | "abs_distance_to_ema200_pct"
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
  universe_source: string | null;
};
export type ScannerRuleImpact = {
  rule_name: string;
  before_count: number;
  after_count: number;
  removed_count: number;
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
  sector_filter?: string[];
  industry_filter?: string[];
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
  company_name: string | null;
  sector: string | null;
  industry: string | null;
  sector_key: string | null;
  industry_key: string | null;
  metadata_source: string | null;
  metadata_data_quality_status: string;
  exchange: string | null;
  price_vs_ema200_pct: number;
  ema200_slope_state: string;
  ema_stack_alignment: string;
  support_distance_pct: number;
  resistance_room_pct: number;
  volume_ratio_20: number;
  resistance_test_count: number;
  ema200_test_count: number;
  repeated_test_count: number;
  support_zone: [number, number] | null;
  resistance_zone: [number, number] | null;
  test_count: number;
  distance_to_zone_pct: number | null;
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
  sector_summary: Array<{
    sector: string;
    candidate_count: number;
    average_score: number;
    category_distribution: Record<string, number>;
  }>;
  top_sector_by_candidate_count: string | null;
  rule_impact: ScannerRuleImpact[];
  generated_at: string;
};

export type ScannerLLMQRequest = {
  market: MarketCode;
  category: ScannerCategory;
  duration: ScannerDuration;
  row: ScannerResult;
};

export type ScannerLLMQResponse = {
  symbol: string;
  provider_used: string;
  model_used: string;
  external_news_available: boolean;
  fallback_only: boolean;
  warning_message: string | null;
  report_text: string;
};

export type LLMQChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export type ScannerLLMQChatResponse = {
  provider: string;
  model: string;
  status: string;
  fallback_used: boolean;
  answer: string;
  error_message: string | null;
  warning_message: string | null;
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
  company_name: string | null;
  sector: string | null;
  industry: string | null;
  exchange: string | null;
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
  | "low_lte"
  | "high_gte"
  | "near_weekly_ema100"
  | "near_weekly_ema200"
  | "cross_above_weekly_ema100"
  | "cross_above_weekly_ema200"
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
export type AlertSignalType = "opportunity" | "risk_warning" | "exit_watch" | "momentum_watch" | "info";

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
  signal_type: AlertSignalType;
  plain_english_meaning: string;
  suggested_action: string;
  last_triggered_at: string | null;
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

export type SymbolBacktestSummary = {
  trades: number;
  win_rate: number;
  expectancy: number;
  average_return: number;
  max_drawdown: number;
};

export type DailyRun = {
  id: string;
  date: string;
  timestamp: string;
  symbols_count: number;
  scanner_categories: ScannerCategory[];
  top_n_per_category: number;
  raw_candidates_before_merge: number;
  final_candidates_after_merge: number;
  status: string;
  note: string | null;
};

export type SymbolResult = {
  symbol: string;
  market: MarketCode;
  category_tags: ScannerCategory[];
  score_by_category: Record<string, number>;
  merged_rank: number;
  multi_category: boolean;
  priority_boost: number;
  base_score: number;
  category_boost: number;
  data_quality_penalty: number;
  final_score_raw: number;
  final_score_capped: number;
  score: number;
  trend: string;
  ema_distances: Record<string, number>;
  setup_type: string;
  candidate_type: string;
  entry_readiness: string;
  blocked_by: string;
  readiness_explanation: string;
  main_opportunity_reason: string;
  main_risk_reason: string;
  confirm_entry_condition: string;
  invalidation_condition: string;
  analysis_snapshot: Record<string, unknown>;
  backtest_summary: SymbolBacktestSummary;
  why_selected: string;
  structure_snapshot: Record<string, unknown>;
  daily_change: Record<string, unknown>;
  risk_flags: string[];
  data_quality_flags: string[];
  price_at_selection: number | null;
  selection_date: string | null;
  benchmark_symbol: string | null;
  return_1d: number | null;
  return_3d: number | null;
  return_7d: number | null;
  return_14d: number | null;
  max_drawdown_after_selection: number | null;
  max_runup_after_selection: number | null;
  company_name: string | null;
  sector: string | null;
  industry: string | null;
  sector_key: string | null;
  industry_key: string | null;
  metadata_source: string | null;
  metadata_data_quality_status: string;
  exchange: string | null;
};

export type SymbolContext = {
  symbol: string;
  run_id: string | null;
  cohort_id: string | null;
  selected_at: string | null;
  date: string;
  bull_case: string;
  bear_case: string;
  risks: string;
  summary: string;
  model: string;
  status: string;
  error: string | null;
};

export type DailyBriefing = {
  date: string;
  run_id: string | null;
  cohort_id: string | null;
  summary_text: string;
  model: string;
  generated_at: string;
  status: string;
  error: string | null;
};

export type SystemReview = {
  id: string;
  period: string;
  findings: string;
  mistakes: string;
  missed_patterns: string;
  recommendations: string;
  model: string;
  generated_at: string;
  status: string;
  error: string | null;
};

export type IntelligenceReviewApproval = {
  id: string;
  run_id: string;
  reviewer: string;
  status: string;
  notes: string;
  created_at: string;
};

export type IntelligenceRunReport = {
  run: DailyRun;
  symbol_results: SymbolResult[];
  contexts: SymbolContext[];
  briefing: DailyBriefing | null;
  review: SystemReview | null;
  approval: IntelligenceReviewApproval | null;
  llm_logs: LLMDebugLog[];
  pipeline_events: PipelineDebugEvent[];
};

export type IntelligenceRunReportExport = {
  run_id: string;
  filename: string;
  report_mode?: string | null;
  cohort_id?: string | null;
  selected_cohort_id_used?: string | null;
  exported_at?: string;
  start_date?: string | null;
  latest_followup_date?: string | null;
  calendar_days_elapsed?: number;
  trading_days_elapsed?: number;
  valid_followup_snapshot_days?: number;
  expected_followup_days?: number;
  snapshot_coverage_pct?: number;
  missing_followup_days_count?: number;
  missing_followup_dates?: string[];
  followup_snapshot_count?: number;
  markdown: string;
};

export type IntelligenceRunResponse = {
  run: DailyRun;
  symbol_results: SymbolResult[];
};

export type CandidateCohortStatus = "active" | "completed" | "archived";

export type CandidateCohort = {
  id: string;
  name: string;
  created_at: string;
  start_date: string;
  market: MarketCode;
  analysis_window: ScannerDuration;
  selected_categories: ScannerCategory[];
  top_n_per_category: number;
  status: CandidateCohortStatus;
  notes: string;
  symbols_count: number;
  latest_followup_date: string | null;
  short_id: string | null;
  followup_enabled: boolean;
  followup_start_date: string | null;
  followup_started_at: string | null;
  followup_target_days: number;
  followup_schedule: string | null;
  followup_completed: boolean;
  followup_status: "active_tracking" | "mature_tracking" | "paused" | "archived_manual";
  followup_paused_at: string | null;
  followup_archived_at: string | null;
  followup_archive_reason: string | null;
  review_ready_28d_at: string | null;
  latest_available_horizon_days: number | null;
  next_horizon_due_days: number | null;
  next_horizon_due_date: string | null;
};

export type CohortCleanupDuplicateResponse = {
  dry_run: boolean;
  duplicate_groups: Array<{
    group_id: string;
    cohort_ids: string[];
    keep_cohort_id: string;
    archive_cohort_ids: string[];
    reasons: string[];
    details: Array<{
      cohort_id: string;
      name: string;
      created_at: string;
      candidates: number;
      snapshots: number;
      latest_followup_date: string | null;
    }>;
  }>;
  archived_cohort_ids: string[];
};

export type CohortDeleteResponse = {
  cohort_id: string;
  deleted: boolean;
  removed_candidates: number;
  removed_snapshots: number;
  removed_contexts: number;
  removed_briefings: number;
  removed_reviews: number;
};

export type CohortStatusUpdateResponse = {
  cohort_id: string;
  status: CandidateCohortStatus;
  changed_at: string;
};

export type CohortCandidate = {
  cohort_id: string;
  symbol: string;
  market: MarketCode;
  selected_at: string;
  selected_price: number | null;
  selected_rank: number;
  selected_score: number;
  selected_base_score: number;
  selected_category_boost: number;
  selected_final_score_raw: number;
  selected_final_score_capped: number;
  selected_categories: ScannerCategory[];
  selected_setup_type: string;
  selected_candidate_type: string;
  selected_entry_readiness: string;
  selected_blocked_by: string;
  selected_readiness_explanation: string;
  selected_trend_state: string;
  selected_score_dynamics: string | null;
  selected_reason: string;
  selected_main_opportunity_reason: string;
  selected_main_risk_reason: string;
  selected_confirm_entry_condition: string;
  selected_invalidation_condition: string;
  selected_structure_snapshot: Record<string, unknown>;
  selected_risk_flags: string[];
  selected_data_quality_flags: string[];
  selected_data_quality_penalty: number;
  selected_displayed_score: number;
  selected_company_name: string | null;
  selected_sector: string | null;
  selected_industry: string | null;
};

export type CohortDailySnapshot = {
  cohort_id: string;
  symbol: string;
  snapshot_date: string;
  current_price: number | null;
  current_score: number | null;
  current_rank_if_discovered_today: number | null;
  current_categories: ScannerCategory[];
  current_setup_type: string | null;
  current_trend_state: string | null;
  current_score_dynamics: string | null;
  current_trigger_state: string | null;
  current_trigger_score: number | null;
  price_change_since_selection: number | null;
  return_since_selection: number | null;
  return_1d: number | null;
  return_3d: number | null;
  return_7d: number | null;
  return_14d: number | null;
  return_28d: number | null;
  max_runup_since_selection: number | null;
  max_drawdown_since_selection: number | null;
  still_valid_candidate: boolean | null;
  validity_state: string;
  invalidation_reason: string | null;
  entry_readiness: string;
  blocked_by: string;
  readiness_explanation: string;
  data_quality_flags: string[];
};

export type LatestCohortState = {
  cohort_id: string;
  symbol: string;
  latest_followup_date: string | null;
  selected_rank: number;
  selected_score: number;
  selected_setup_type: string;
  selected_reason: string;
  selected_company_name: string | null;
  selected_sector: string | null;
  selected_industry: string | null;
  selected_categories: ScannerCategory[];
  current_price: number | null;
  current_score: number | null;
  current_setup_type: string | null;
  current_trend_state: string | null;
  current_score_dynamics: string | null;
  current_trigger_state: string | null;
  current_trigger_score: number | null;
  return_since_selection: number | null;
  return_1d: number | null;
  return_3d: number | null;
  return_7d: number | null;
  return_14d: number | null;
  return_28d: number | null;
  validity_state: string;
  invalidation_reason: string | null;
  entry_readiness: string;
  blocked_by: string;
  readiness_explanation: string;
  data_quality_flags: string[];
};

export type CohortDetail = {
  cohort: CandidateCohort;
  candidates: CohortCandidate[];
  snapshots: CohortDailySnapshot[];
  latest_states: LatestCohortState[];
};

export type CohortFollowupResponse = {
  cohort_id: string;
  snapshot_date: string;
  snapshots: CohortDailySnapshot[];
};

export type CohortReviewResponse = {
  cohort_id: string | null;
  readiness_message: string;
  days_collected: number;
  days_required: number;
  days_remaining: number;
  start_date: string | null;
  latest_followup_date: string | null;
  calendar_days_elapsed: number;
  trading_days_elapsed: number;
  valid_followup_snapshot_days: number;
  expected_followup_days: number;
  snapshot_coverage_pct: number;
  missing_followup_days_count: number;
  missing_followup_dates: string[];
  horizon_28d_available: boolean;
  horizon_outcome_review_available: boolean;
  daily_path_review_complete: boolean;
  snapshot_coverage_warning: string | null;
  deterministic_stats: {
    average_return_by_category: Record<string, number>;
    return_since_selection_by_category: Record<string, number>;
    return_7d_by_category: Record<string, number>;
    return_14d_by_category: Record<string, number>;
    return_28d_by_category: Record<string, number>;
    best_candidate: string | null;
    worst_candidate: string | null;
    best_category: string | null;
    worst_category: string | null;
    horizon_28d_available: boolean;
    horizon_28d_candidate_count: number;
    horizon_28d_missing_count: number;
    horizon_28d_positive_count: number;
    horizon_28d_negative_count: number;
    best_candidate_by_28d: string | null;
    worst_candidate_by_28d: string | null;
    best_category_by_28d: string | null;
    worst_category_by_28d: string | null;
    multi_category_avg_return_7d: number | null;
    false_positives: number;
    missed_follow_through: number;
    stayed_valid: number;
    invalidated_quickly: number;
    pending_validation_count: number;
    needs_data_check_count: number;
    snapshots_collected: number;
    pending_horizon_count: number;
    early_return_1d_avg: number | null;
    insufficient_data: boolean;
    score_delta_vs_return_note: string;
    average_return_by_sector_7d: Record<string, number>;
    best_sector_by_1d: string | null;
    worst_sector_by_1d: string | null;
    best_sector_by_3d: string | null;
    worst_sector_by_3d: string | null;
    best_sector_by_7d: string | null;
    worst_sector_by_7d: string | null;
    sector_concentration_warning: string | null;
    sector_candidate_distribution: Record<string, number>;
  };
  llm_summary: string | null;
};

export type CohortDailyReportSummary = {
  id: string | null;
  cohort_id: string;
  cohort_name: string | null;
  report_date: string;
  report_mode: string;
  followup_day_number: number | null;
  candidate_count: number;
  followup_snapshot_count: number;
  deterministic_stats_json: Record<string, unknown>;
  market_context_json: Record<string, unknown>;
  llm_model: string | null;
  fallback_used: boolean;
  export_path: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type CohortDailyReportDetail = CohortDailyReportSummary & {
  candidate_followup_json: Array<Record<string, unknown>>;
  llm_context_summary: string | null;
  report_markdown: string | null;
  engine_version: string | null;
  git_commit: string | null;
  llm_provider: string | null;
  prompt_version: string | null;
  error_message: string | null;
};

export type CohortDailyReportRunResponse = {
  job_name: string;
  run_at: string;
  requested_cohort_id: string | null;
  report_dates: string[];
  generated: number;
  skipped: number;
  failed: number;
  reports: CohortDailyReportSummary[];
  errors: string[];
};

export type LogsSchedulerStatus = {
  scheduler_enabled: boolean;
  scheduler_running: boolean;
  timezone: string;
  configured_run_time: string;
  next_run_at: string | null;
  last_tick_at: string | null;
  last_run_at: string | null;
  last_success_at: string | null;
  last_failure_at: string | null;
  last_error_message: string | null;
  active_followup_cohorts_count: number;
  active_tracking_count: number;
  mature_tracking_count: number;
  paused_followup_count: number;
  manually_archived_count: number;
  review_ready_28d_count: number;
};

export type LogsActiveFollowupCohort = {
  cohort_id: string;
  cohort_name: string;
  followup_enabled: boolean;
  followup_start_date: string | null;
  followup_started_at: string | null;
  followup_status: string;
  followup_target_days: number;
  current_followup_day: number;
  last_report_date: string | null;
  review_ready_28d: boolean;
  latest_available_horizon_days: number | null;
  next_horizon_due_days: number | null;
  next_horizon_due_date: string | null;
};

export type LogsStatusResponse = {
  scheduler: LogsSchedulerStatus;
  daily_reports: {
    postgres: {
      configured: boolean;
      total_daily_reports: number;
      latest_report_date: string | null;
      latest_report_created_at: string | null;
      latest_report_updated_at: string | null;
      latest_export_path: string | null;
      fallback_used: boolean | null;
      error_message: string | null;
    };
    latest_rows: CohortDailyReportSummary[];
  };
  active_followup_cohorts: LogsActiveFollowupCohort[];
  latest_errors: Array<Record<string, unknown>>;
};

export type LogFileEntry = {
  path: string;
  name: string;
  size_bytes: number;
  updated_at: string;
};

export type LogFilesResponse = {
  root: string;
  groups: Record<string, LogFileEntry[]>;
};

export type LogFileReadResponse = {
  path: string;
  tail: number;
  total_lines: number;
  level: string;
  text: string;
};

export type SymbolContextBatchResponse = {
  run_id: string;
  generated: number;
  failed: number;
  contexts: SymbolContext[];
  failed_symbols: string[];
  request_id: string | null;
  provider: string | null;
  model: string | null;
  endpoint: string | null;
  fallback_used: boolean;
  error_message: string | null;
};

export type IntelligenceDashboardResponse = {
  runs: DailyRun[];
  latest_run_results: SymbolResult[];
  latest_contexts: SymbolContext[];
  latest_briefing: DailyBriefing | null;
  latest_review: SystemReview | null;
  pipeline_events: PipelineDebugEvent[];
  cohorts: CandidateCohort[];
  cohort_details: CohortDetail[];
  review_readiness: {
    runs_collected: number;
    unique_days: number;
    symbols_tracked: number;
    days_until_28_day_review: number;
    ready_for_28_day_review: boolean;
    message: string;
  };
  deterministic_review_stats: {
    best_category_by_7d: string | null;
    worst_category_by_7d: string | null;
    highest_false_positive_group: string | null;
    repeated_candidates: number;
    strong_score_poor_return: number;
    low_score_strong_return: number;
    average_return_by_setup_type: Record<string, number>;
  };
};

export type ResearchPredictionRecord = {
  id: string;
  cohort_id: string;
  symbol: string;
  market: string;
  selected_at: string;
  selected_date: string;
  selected_price: number | null;
  categories: string[];
  setup_type: string;
  blocked_by: string | null;
  invalidation_conditions: Record<string, unknown>;
  source_run_id: string | null;
  source_report_id: string | null;
  rule_version: string;
  feature_version: string;
  data_version: string;
  selection_market_regime_id: string | null;
};

export type ResearchOutcomeRecord = {
  id: string;
  prediction_id: string;
  symbol: string;
  horizon_days: number;
  outcome_date: string | null;
  evaluated_at: string;
  outcome_status: string;
  outcome_label: string;
  return_pct: number | null;
  daily_snapshot_path_complete: boolean;
  daily_snapshot_coverage_pct: number;
  data_quality_flags: string[];
  selection_market_regime_id: string | null;
  outcome_market_regime_id: string | null;
  attribution_label: string | null;
};

export type ResearchOutcomeSummary = {
  grouping: string;
  group_value: string;
  horizon_days: number;
  prediction_count: number;
  available_outcome_count: number;
  data_quality_excluded_count: number;
  positive_count: number;
  negative_count: number;
  average_return_pct: number | null;
  rule_version: string;
  feature_version: string;
  data_version: string;
};

export type ResearchCohortReadiness = {
  cohort: CandidateCohort;
  coverage: {
    cohort_id: string;
    expected_followup_days: number;
    complete_followup_days: number;
    partial_followup_days: number;
    missing_followup_days: number;
    snapshot_coverage_pct: number;
    missing_followup_dates: string[];
    partial_followup_dates: string[];
    duplicate_snapshot_dates: string[];
    backfill_required: boolean;
    backfill_dates: string[];
    duplicate_repair_required: boolean;
    status: string;
    readiness_message: string;
  };
  prediction_count: number;
  predictions: ResearchPredictionRecord[];
  horizon_28d_available_count: number;
  horizon_28d_pending_count: number;
  available_horizon_days: number[];
  latest_available_horizon_days: number | null;
  next_horizon_due_days: number | null;
  next_horizon_due_date: string | null;
  data_quality_excluded_outcome_count: number;
  horizon_28d_complete: boolean;
  daily_path_review_complete: boolean;
  outcomes: ResearchOutcomeRecord[];
  outcome_summaries: ResearchOutcomeSummary[];
};

export type ResearchHypothesis = {
  id: string;
  title: string;
  status: string;
  generated_by: string;
  submitted_by: string;
  latest_validation_id: string | null;
  reviewed_by: string | null;
  review_notes: string | null;
  rule_version: string;
  feature_version: string;
  data_version: string;
};

export type ResearchPattern = {
  id: string;
  pattern_key: string;
  status: string;
  market: string;
  sample_size: number;
  evaluable_case_count: number;
  success_rate_pct: number | null;
  approval_eligible: boolean;
  reviewed_by: string | null;
  review_notes: string | null;
  rule_version: string;
  feature_version: string;
  data_version: string;
};

export type ResearchDashboardResponse = {
  generated_at: string;
  database_configured: boolean;
  knowledge_graph: Record<string, unknown>;
  cohorts: ResearchCohortReadiness[];
  hypotheses: ResearchHypothesis[];
  hypothesis_status_counts: Record<string, number>;
  patterns: ResearchPattern[];
  pattern_status_counts: Record<string, number>;
  recent_pipeline_errors: PipelineDebugEvent[];
  operational_messages: Array<{
    code: string;
    severity: string;
    message: string;
    cohort_id: string | null;
  }>;
};

export type ResearchAuditExport = {
  filename: string;
  exported_at: string;
  cohort_id: string | null;
  payload: Record<string, unknown>;
};

export type LLMConnectionStatus = {
  connected: boolean;
  base_url: string;
  checked_at: string;
  error: string | null;
  model_used: string | null;
  model_available: boolean | null;
  installed_models: string[];
  primary_provider: string | null;
  fallback_provider: string | null;
  primary_model: string | null;
  fallback_model: string | null;
  primary_connected: boolean | null;
  fallback_connected: boolean | null;
  last_response_duration_ms: number | null;
  last_fallback_used: boolean | null;
};

export type LLMDebugLog = {
  id: string;
  timestamp: string;
  symbol: string | null;
  endpoint: string;
  call_type: string;
  prompt: string;
  raw_response: string | null;
  parsed_output: Record<string, unknown>;
  status: string;
  error_message: string | null;
  duration_ms: number;
  provider: string | null;
  model: string | null;
  fallback_used: boolean;
  fallback_provider: string | null;
  token_estimate: number;
  prompt_preview: string | null;
  response_preview: string | null;
  prompt_version: string | null;
};

export type LLMResponseTestResult = {
  ok: boolean;
  model: string;
  endpoint: string;
  response_time_ms: number;
  threshold_ms: number;
  within_threshold: boolean;
  status: string;
  response_preview: string | null;
  error: string | null;
  checked_at: string;
};

export type PipelineDebugEvent = {
  id: string;
  timestamp: string;
  step_name: string;
  status: string;
  duration_ms: number;
  run_id: string | null;
  cohort_id: string | null;
  cohort_name: string | null;
  symbol: string | null;
  provider: string | null;
  category: string | null;
  message: string | null;
  error_message: string | null;
};
