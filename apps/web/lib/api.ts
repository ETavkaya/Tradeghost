import {
  AnalysisResponse,
  MarketCode,
  AnalysisWindow,
  StrategyMode,
  AnalysisConfig,
  BacktestFromAnalysisRequest,
  BacktestFromAnalysisResponse,
  BacktestSnapshot,
  ScannerCategory,
  ScannerDuration,
  ScannerRequest,
  ScannerResponse,
  ScannerUniverseScope,
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
  analyzeCombined: (ticker: string, market: MarketCode, window: AnalysisWindow, config?: Partial<AnalysisConfig>) => {
    const strategyMode = config?.strategy_mode ?? "balanced";
    const params = new URLSearchParams({
      ticker,
      market,
      window,
      strategy_mode: strategyMode,
    });
    if (config?.score_threshold !== undefined) params.set("score_threshold", String(config.score_threshold));
    if (config?.warmup_bars !== undefined) params.set("warmup_bars", String(config.warmup_bars));
    if (config?.regime_filter?.regime_mode) params.set("regime_mode", config.regime_filter.regime_mode);
    if (config?.location_filter?.max_support_distance_pct !== undefined) params.set("max_support_distance_pct", String(config.location_filter.max_support_distance_pct));
    if (config?.location_filter?.min_resistance_room_pct !== undefined) params.set("min_resistance_room_pct", String(config.location_filter.min_resistance_room_pct));
    if (config?.trigger_filter?.min_trigger_score !== undefined) params.set("min_trigger_score", String(config.trigger_filter.min_trigger_score));
    if (config?.location_filter?.max_overextension_ema20_pct !== undefined) params.set("max_overextension_ema20_pct", String(config.location_filter.max_overextension_ema20_pct));
    if (config?.location_filter?.max_overextension_ema50_pct !== undefined) params.set("max_overextension_ema50_pct", String(config.location_filter.max_overextension_ema50_pct));
    if (config?.location_filter?.max_overextension_ema100_pct !== undefined) params.set("max_overextension_ema100_pct", String(config.location_filter.max_overextension_ema100_pct));
    if (config?.location_filter?.max_overextension_ema200_pct !== undefined) params.set("max_overextension_ema200_pct", String(config.location_filter.max_overextension_ema200_pct));
    return fetchJson<CombinedAnalysisResponse>(`/api/analyze-combined?${params.toString()}`);
  },
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
  saveBacktestSnapshot: (result: BacktestFromAnalysisResponse, reviewStatus = "exploratory", experimentGroup?: string) =>
    fetchJson<BacktestSnapshot>("/api/backtest-snapshots", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        result,
        review_status: reviewStatus,
        experiment_group: experimentGroup ?? null
      })
    }),
  listBacktestSnapshots: () => fetchJson<BacktestSnapshot[]>("/api/backtest-snapshots"),
  getBacktestSnapshot: (snapshotId: string) => fetchJson<BacktestSnapshot>(`/api/backtest-snapshots/${encodeURIComponent(snapshotId)}`),
  addBacktestSnapshotComment: (snapshotId: string, commentator: string, content: string, tags: string[] = []) =>
    fetchJson<BacktestSnapshot>(`/api/backtest-snapshots/${encodeURIComponent(snapshotId)}/comments`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ commentator, content, tags })
    }),
  scanner: (payload: ScannerRequest) =>
    fetchJson<ScannerResponse>("/api/scanner", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    }),
  health: () => fetchJson<{ status: string; app: string }>("/api/health")
};
