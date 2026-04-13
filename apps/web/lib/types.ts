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
  return_pct: number;
  hold_days: number;
  result: string;
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

