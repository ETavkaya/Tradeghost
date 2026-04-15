export type AnalysisWindow = "5d" | "1m" | "3m" | "6m" | "1y" | "5y" | "10y";

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
  window: AnalysisWindow;
  as_of: string;
  chart: AnalysisChart;
  quantedge: QuantEdgeSection;
  swingpulse: SwingPulseSection;
  chartmap: ChartMapSection;
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
  entry_date: string;
  exit_date: string;
  entry_price: number;
  exit_price: number;
  stop_loss: number | null;
  take_profit: number | null;
  return_pct: number;
  hold_days: number;
  result: string;
};

export type BacktestMarker = {
  date: string;
  price: number;
  marker_type: string;
  label: string;
};

export type BacktestResponse = {
  ticker: string;
  period_start: string;
  period_end: string;
  trades: number;
  win_rate: number;
  average_return: number;
  max_drawdown: number;
  average_hold_days: number;
  expectancy: number;
  generated_at: string;
  sample_trades: BacktestTrade[];
};

export type BacktestFromAnalysisRequest = {
  ticker: string;
  window: AnalysisWindow;
  analysis_as_of: string;
  quantedge_final_score: number;
  category_scores: CategoryScores;
  swing_candidate: boolean;
  trade_plan: TradePlan;
};

export type BacktestFromAnalysisResponse = {
  ticker: string;
  window: AnalysisWindow;
  generated_from_analysis: boolean;
  analysis_as_of: string;
  period_start: string;
  period_end: string;
  trades: number;
  win_rate: number;
  average_return: number;
  max_drawdown: number;
  average_hold_days: number;
  expectancy: number;
  generated_at: string;
  trades_table: BacktestTrade[];
  chart: AnalysisChart;
  markers: BacktestMarker[];
};
