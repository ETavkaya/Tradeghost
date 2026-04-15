import {
  AnalysisResponse,
  MarketCode,
  AnalysisWindow,
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
  analyzeCombined: (ticker: string, market: MarketCode, window: AnalysisWindow) =>
    fetchJson<CombinedAnalysisResponse>(
      `/api/analyze-combined?ticker=${encodeURIComponent(ticker)}&market=${encodeURIComponent(market)}&window=${encodeURIComponent(window)}`
    ),
  score: (ticker: string) => fetchJson<ScoreResponse>(`/api/score?ticker=${encodeURIComponent(ticker)}`),
  tradePlan: (ticker: string) =>
    fetchJson<TradePlanResponse>(`/api/trade-plan?ticker=${encodeURIComponent(ticker)}`),
  backtest: (ticker: string, market: MarketCode, window: AnalysisWindow = "6m") =>
    fetchJson<BacktestResponse>(
      `/api/backtest?ticker=${encodeURIComponent(ticker)}&market=${encodeURIComponent(market)}&window=${encodeURIComponent(window)}`
    ),
  backtestFromAnalysis: (payload: BacktestFromAnalysisRequest) =>
    fetchJson<BacktestFromAnalysisResponse>("/api/backtest-from-analysis", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    }),
  health: () => fetchJson<{ status: string; app: string }>("/api/health")
};
