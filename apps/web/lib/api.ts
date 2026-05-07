import {
  AnalysisResponse,
  MarketCode,
  AnalysisWindow,
  StrategyMode,
  AnalysisConfig,
  BacktestFromAnalysisRequest,
  BacktestFromAnalysisResponse,
  BacktestSnapshot,
  Watchlist,
  AlertRule,
  AlertEvent,
  AlertProfileSuggestionResponse,
  DailyBriefing,
  IntelligenceReviewApproval,
  IntelligenceRunReport,
  IntelligenceRunReportExport,
  IntelligenceDashboardResponse,
  IntelligenceRunResponse,
  LLMConnectionStatus,
  LLMDebugLog,
  LLMResponseTestResult,
  PipelineDebugEvent,
  MonitoringSchedule,
  MonitoringRunSummary,
  ScannerCategory,
  ScannerDuration,
  ScannerRequest,
  ScannerResponse,
  ScannerUniverseScope,
  BacktestResponse,
  CombinedAnalysisResponse,
  ScoreResponse,
  SymbolContextBatchResponse,
  SystemReview,
  TradePlanResponse
} from "@/lib/types";

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { cache: "no-store", ...init });
  if (!response.ok) {
    const text = await response.text();
    let detail: unknown = text || `Request failed with status ${response.status}`;
    try {
      detail = JSON.parse(text);
    } catch {
      // keep raw text
    }
    throw new Error(JSON.stringify({ status: response.status, path, detail }));
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
  health: () => fetchJson<{ status: string; app: string }>("/api/health"),
  listWatchlists: () => fetchJson<Watchlist[]>("/api/watchlists"),
  createWatchlist: (name: string) =>
    fetchJson<Watchlist>("/api/watchlists", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name })
    }),
  renameWatchlist: (watchlistId: string, name: string) =>
    fetchJson<Watchlist>(`/api/watchlists/${encodeURIComponent(watchlistId)}`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name })
    }),
  deleteWatchlist: (watchlistId: string) =>
    fetchJson<{ status: string }>(`/api/watchlists/${encodeURIComponent(watchlistId)}`, { method: "DELETE" }),
  addWatchlistItem: (watchlistId: string, symbol: string, market: MarketCode, notes?: string) =>
    fetchJson<Watchlist>(`/api/watchlists/${encodeURIComponent(watchlistId)}/items`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ symbol, market, notes: notes ?? null })
    }),
  removeWatchlistItem: (watchlistId: string, symbol: string, market: MarketCode) =>
    fetchJson<Watchlist>(`/api/watchlists/${encodeURIComponent(watchlistId)}/items?symbol=${encodeURIComponent(symbol)}&market=${encodeURIComponent(market)}`, { method: "DELETE" }),
  refreshWatchlistMetrics: (watchlistId: string) =>
    fetchJson<Watchlist>(`/api/watchlists/${encodeURIComponent(watchlistId)}/refresh-metrics`, {
      method: "POST"
    }),
  listAlertRules: (filters?: { symbol?: string; watchlist_id?: string; severity?: string; enabled?: boolean }) => {
    const params = new URLSearchParams();
    if (filters?.symbol) params.set("symbol", filters.symbol);
    if (filters?.watchlist_id) params.set("watchlist_id", filters.watchlist_id);
    if (filters?.severity) params.set("severity", filters.severity);
    if (filters?.enabled !== undefined) params.set("enabled", String(filters.enabled));
    return fetchJson<AlertRule[]>(`/api/alert-rules${params.toString() ? `?${params.toString()}` : ""}`);
  },
  createAlertRule: (payload: Record<string, unknown>) =>
    fetchJson<AlertRule>("/api/alert-rules", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    }),
  suggestAlertProfile: (payload: Record<string, unknown>) =>
    fetchJson<AlertProfileSuggestionResponse>("/api/alert-profiles/suggest", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    }),
  applyAlertProfile: (payload: Record<string, unknown>) =>
    fetchJson<AlertRule[]>("/api/alert-profiles/apply", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    }),
  updateAlertRule: (ruleId: string, payload: Record<string, unknown>) =>
    fetchJson<AlertRule>(`/api/alert-rules/${encodeURIComponent(ruleId)}`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    }),
  deleteAlertRule: (ruleId: string) =>
    fetchJson<{ status: string }>(`/api/alert-rules/${encodeURIComponent(ruleId)}`, { method: "DELETE" }),
  listAlertEvents: (status?: string, severity?: string, symbol?: string) => {
    const params = new URLSearchParams();
    if (status) params.set("status", status);
    if (severity) params.set("severity", severity);
    if (symbol) params.set("symbol", symbol);
    return fetchJson<AlertEvent[]>(`/api/alert-events${params.toString() ? `?${params.toString()}` : ""}`);
  },
  updateAlertEventStatus: (eventId: string, status: "new" | "seen" | "archived") =>
    fetchJson<AlertEvent>(`/api/alert-events/${encodeURIComponent(eventId)}/status`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ status })
    }),
  runMonitoring: (payload: Record<string, unknown>) =>
    fetchJson<MonitoringRunSummary>("/api/monitoring/run", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    }),
  runDueMonitoring: (maxRuntimeSeconds = 30) =>
    fetchJson<MonitoringRunSummary>("/api/monitoring/run-due", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ max_runtime_seconds: maxRuntimeSeconds })
    }),
  listMonitoringSchedules: () => fetchJson<MonitoringSchedule[]>("/api/monitoring/schedules"),
  createMonitoringSchedule: (payload: Record<string, unknown>) =>
    fetchJson<MonitoringSchedule>("/api/monitoring/schedules", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    }),
  updateMonitoringSchedule: (scheduleId: string, payload: Record<string, unknown>) =>
    fetchJson<MonitoringSchedule>(`/api/monitoring/schedules/${encodeURIComponent(scheduleId)}`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    }),
  deleteMonitoringSchedule: (scheduleId: string) =>
    fetchJson<{ status: string }>(`/api/monitoring/schedules/${encodeURIComponent(scheduleId)}`, { method: "DELETE" }),
  getIntelligenceDashboard: () => fetchJson<IntelligenceDashboardResponse>("/api/intelligence/dashboard"),
  runDailyPipeline: (payload: Record<string, unknown>) =>
    fetchJson<IntelligenceRunResponse>("/api/intelligence/daily-pipeline", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    }),
  generateSymbolContexts: (payload: Record<string, unknown>) =>
    fetchJson<SymbolContextBatchResponse>("/api/intelligence/symbol-contexts", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    }),
  generateDailyBriefing: (payload: Record<string, unknown>) =>
    fetchJson<DailyBriefing>("/api/intelligence/daily-briefing", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    }),
  runSystemReview: (payload: Record<string, unknown>) =>
    fetchJson<SystemReview>("/api/intelligence/review", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    }),
  getIntelligenceRunReport: (runId: string) =>
    fetchJson<IntelligenceRunReport>(`/api/intelligence/report/${encodeURIComponent(runId)}`),
  exportIntelligenceRunReport: (runId: string) =>
    fetchJson<IntelligenceRunReportExport>(`/api/intelligence/report/${encodeURIComponent(runId)}/export`),
  approveIntelligenceRunReport: (payload: Record<string, unknown>) =>
    fetchJson<IntelligenceReviewApproval>("/api/intelligence/report/approve", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload)
    }),
  getLLMStatus: () => fetchJson<LLMConnectionStatus>("/api/intelligence/llm/status"),
  getLLMLogs: (limit = 200) => fetchJson<LLMDebugLog[]>(`/api/intelligence/llm/logs?limit=${encodeURIComponent(String(limit))}`),
  getPipelineEvents: (limit = 250) => fetchJson<PipelineDebugEvent[]>(`/api/intelligence/pipeline-events?limit=${encodeURIComponent(String(limit))}`),
  testLLMResponse: (payload?: Record<string, unknown>) =>
    fetchJson<LLMResponseTestResult>("/api/intelligence/llm/test", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload ?? {})
    }),
};
