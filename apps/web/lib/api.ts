import {
  AnalysisResponse,
  MarketCode,
  AnalysisWindow,
  StrategyMode,
  BacktestFromAnalysisRequest,
  BacktestFromAnalysisResponse,
  BacktestResponse,
  CombinedAnalysisResponse,
  ScoreResponse,
  TradePlanResponse
} from "@/lib/types";

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { cache: "no-store", ...init });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  analyze: (ticker: string) => fetchJson<AnalysisResponse>(`/api/analyze?ticker=${encodeURIComponent(ticker)}`),
  analyzeCombined: (
    ticker: string,
    market: MarketCode,
    window: AnalysisWindow,
    strategyMode: StrategyMode = "balanced",
    scoreThreshold?: number,
    warmupBars?: number
  ) =>
    fetchJson<CombinedAnalysisResponse>(
      `/api/analyze-combined?ticker=${encodeURIComponent(ticker)}&market=${encodeURIComponent(market)}&window=${encodeURIComponent(window)}&strategy_mode=${encodeURIComponent(strategyMode)}${
        scoreThreshold !== undefined ? `&score_threshold=${encodeURIComponent(scoreThreshold)}` : ""
      }${warmupBars !== undefined ? `&warmup_bars=${encodeURIComponent(warmupBars)}` : ""}`
    ),
  score: (ticker: string) => fetchJson<ScoreResponse>(`/api/score?ticker=${encodeURIComponent(ticker)}`),
  tradePlan: (ticker: string) =>
    fetchJson<TradePlanResponse>(`/api/trade-plan?ticker=${encodeURIComponent(ticker)}`),
  backtest: (
    ticker: string,
    market: MarketCode,
    window: AnalysisWindow = "6m",
    scoreThreshold?: number,
    strategyMode: StrategyMode = "balanced",
    warmupBars?: number
  ) =>
    fetchJson<BacktestResponse>(
      `/api/backtest?ticker=${encodeURIComponent(ticker)}&market=${encodeURIComponent(market)}&window=${encodeURIComponent(window)}${
        scoreThreshold !== undefined ? `&score_threshold=${encodeURIComponent(scoreThreshold)}` : ""
      }&strategy_mode=${encodeURIComponent(strategyMode)}${warmupBars !== undefined ? `&warmup_bars=${encodeURIComponent(warmupBars)}` : ""}`
    ),
  backtestFromAnalysis: (payload: BacktestFromAnalysisRequest) =>
    fetchJson<BacktestFromAnalysisResponse>("/api/backtest-from-analysis", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    }),
  health: () => fetchJson<{ status: string; app: string }>("/api/health")
};
