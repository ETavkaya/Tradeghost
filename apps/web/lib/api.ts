import { AnalysisResponse, BacktestResponse, ScoreResponse, TradePlanResponse } from "@/lib/types";

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  analyze: (ticker: string) => fetchJson<AnalysisResponse>(`/api/analyze?ticker=${encodeURIComponent(ticker)}`),
  score: (ticker: string) => fetchJson<ScoreResponse>(`/api/score?ticker=${encodeURIComponent(ticker)}`),
  tradePlan: (ticker: string) =>
    fetchJson<TradePlanResponse>(`/api/trade-plan?ticker=${encodeURIComponent(ticker)}`),
  backtest: (ticker: string) => fetchJson<BacktestResponse>(`/api/backtest?ticker=${encodeURIComponent(ticker)}`),
  health: () => fetchJson<{ status: string; app: string }>("/api/health")
};

