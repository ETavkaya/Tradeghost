"use client";

import { Fragment, useEffect, useState } from "react";
import { Panel, SectionTitle, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import {
  IntelligenceDashboardResponse,
  LLMDebugLog,
  LLMConnectionStatus,
  LLMResponseTestResult,
  MarketCode,
  PipelineDebugEvent,
  ScannerCategory,
  ScannerDuration,
  ScannerUniverseScope,
} from "@/lib/types";

export default function IntelligencePage() {
  const [dashboard, setDashboard] = useState<IntelligenceDashboardResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [market, setMarket] = useState<MarketCode>("us");
  const [duration, setDuration] = useState<ScannerDuration>("1y");
  const [scope, setScope] = useState<ScannerUniverseScope>("full_universe");
  const [debugCappedUniverse, setDebugCappedUniverse] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [maxUniverseSymbols, setMaxUniverseSymbols] = useState(60);
  const [topNPerCategory, setTopNPerCategory] = useState(5);
  const [scannerResultCap, setScannerResultCap] = useState(30);
  const [categories, setCategories] = useState<ScannerCategory[]>(["trend_mode", "build_up", "momentum_mode", "value_rebuild", "overextended"]);

  const [llmConcurrency, setLlmConcurrency] = useState(1);
  const [contextSymbolLimit, setContextSymbolLimit] = useState(3);
  const [contextTimeout, setContextTimeout] = useState(120);
  const [liveStreamDebug, setLiveStreamDebug] = useState(false);
  const [reviewDays, setReviewDays] = useState(28);

  const [showLLMConsole, setShowLLMConsole] = useState(false);
  const [llmStatus, setLLMStatus] = useState<LLMConnectionStatus | null>(null);
  const [llmTest, setLlmTest] = useState<LLMResponseTestResult | null>(null);
  const [llmLogs, setLLMLogs] = useState<LLMDebugLog[]>([]);
  const [pipelineEvents, setPipelineEvents] = useState<PipelineDebugEvent[]>([]);
  const [expandedLogIds, setExpandedLogIds] = useState<Record<string, boolean>>({});
  const [backendConnected, setBackendConnected] = useState(false);

  const formatError = (err: unknown, stage: string): string => {
    if (!(err instanceof Error)) return `${stage} failed.`;
    try {
      const parsed = JSON.parse(err.message) as Record<string, unknown>;
      const status = parsed.status ? ` status=${String(parsed.status)}` : "";
      const detailObj = parsed.detail as Record<string, unknown> | string | undefined;
      if (detailObj && typeof detailObj === "object") {
        const detail = String(detailObj.detail ?? `${stage} failed`);
        const failedStage = detailObj.failed_stage ? ` failed_stage=${String(detailObj.failed_stage)}` : "";
        const failedSymbol = detailObj.failed_symbol ? ` failed_symbol=${String(detailObj.failed_symbol)}` : "";
        const model = detailObj.model ? ` model=${String(detailObj.model)}` : "";
        const errorType = detailObj.error_type ? ` error_type=${String(detailObj.error_type)}` : "";
        const errorMessage = detailObj.error_message ? ` error_message=${String(detailObj.error_message)}` : "";
        const endpoint = detailObj.endpoint ? ` endpoint=${String(detailObj.endpoint)}` : "";
        const method = detailObj.method ? ` method=${String(detailObj.method)}` : "";
        const backendError = detailObj.error ? ` error=${String(detailObj.error)}` : "";
        return `${detail}.${status}${method}${endpoint}${backendError}${failedStage}${failedSymbol}${model}${errorType}${errorMessage}`;
      }
      return `${String(detailObj ?? `${stage} failed`)}.${status}`;
    } catch {
      return err.message;
    }
  };

  const load = async () => {
    const [dataR, statusR, logsR, eventsR, healthR] = await Promise.allSettled([
      api.getIntelligenceDashboard(),
      api.getLLMStatus(),
      api.getLLMLogs(120),
      api.getPipelineEvents(250),
      api.health(),
    ]);
    if (dataR.status === "fulfilled") setDashboard(dataR.value);
    if (statusR.status === "fulfilled") setLLMStatus(statusR.value);
    if (logsR.status === "fulfilled") setLLMLogs(logsR.value);
    if (eventsR.status === "fulfilled") setPipelineEvents(eventsR.value);
    if (healthR.status === "fulfilled") setBackendConnected(healthR.value.status === "ok");
    else setBackendConnected(false);
  };

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    if (!showLLMConsole && !loading) return;
    const t = setInterval(() => {
      void load();
    }, 2500);
    return () => clearInterval(t);
  }, [showLLMConsole, loading]);

  const latestRun = dashboard?.runs?.[0] ?? null;
  const latestRunDate = latestRun?.date ?? null;
  const latestRunContextCount = latestRunDate
    ? (dashboard?.latest_contexts ?? []).filter((row) => row.date === latestRunDate && row.status === "generated").length
    : 0;

  const canRunContexts = Boolean(latestRun) && Boolean(llmStatus?.connected);
  const canRunBriefing = Boolean(latestRun) && latestRunContextCount > 0 && Boolean(llmStatus?.connected);
  const canRunReview = (dashboard?.runs.length ?? 0) > 0;
  const selectedCategoryCount = categories.length;
  const rawExpected = selectedCategoryCount * topNPerCategory;
  const autoFinalShortlistLimit = rawExpected;

  const runPipeline = async () => {
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      const response = await api.runDailyPipeline({
        market,
        duration,
        categories,
        max_universe_symbols: maxUniverseSymbols,
        top_n_per_category: topNPerCategory,
        max_candidates: autoFinalShortlistLimit,
        scanner_max_results: scannerResultCap,
        scanner_universe_scope: debugCappedUniverse ? "capped_universe" : scope,
      });
      setNotice(`Daily pipeline completed: ${response.run.symbols_count} symbols stored.`);
      await load();
    } catch (err) {
      setError(formatError(err, "Daily pipeline"));
    } finally {
      setLoading(false);
    }
  };

  const runContexts = async () => {
    if (!latestRun) {
      setError("Run daily pipeline first.");
      return;
    }
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      const response = await api.generateSymbolContexts({
        run_id: latestRun.id,
        context_symbol_limit: contextSymbolLimit,
        max_concurrency: llmConcurrency,
        timeout_seconds: contextTimeout,
        model: "llama3.2:3b",
        sequential_mode: true,
        short_context_mode: true,
        debug_stream: liveStreamDebug,
      });
      setNotice(`Symbol context completed: generated ${response.generated}, failed ${response.failed}.`);
      await load();
    } catch (err) {
      setError(formatError(err, "Generate Symbol Contexts"));
    } finally {
      setLoading(false);
    }
  };

  const runBriefing = async () => {
    if (!latestRun) {
      setError("Run daily pipeline first.");
      return;
    }
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      const response = await api.generateDailyBriefing({
        run_id: latestRun.id,
        model: "llama3.2:3b",
        timeout_seconds: contextTimeout,
        short_briefing_mode: true,
      });
      setNotice(`Daily briefing ${response.status === "generated" ? "generated" : "failed"}.`);
      await load();
    } catch (err) {
      setError(formatError(err, "Generate Daily Briefing"));
    } finally {
      setLoading(false);
    }
  };

  const runReview = async () => {
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      const response = await api.runSystemReview({
        days: reviewDays,
        model: "llama3.2:3b",
        max_concurrency: llmConcurrency,
        timeout_seconds: contextTimeout,
      });
      setNotice(`System review ${response.status === "generated" ? "generated" : "failed"} for ${response.period}.`);
      await load();
    } catch (err) {
      setError(formatError(err, "Run System Review"));
    } finally {
      setLoading(false);
    }
  };

  const runLLMResponseTest = async () => {
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      const result = await api.testLLMResponse({
        model: "llama3.2:3b",
        timeout_seconds: 30,
        threshold_seconds: 20,
      });
      setLlmTest(result);
      setNotice(
        result.ok
          ? `LLM test success: ${result.response_time_ms} ms (${result.within_threshold ? "within" : "above"} 20s threshold).`
          : `LLM test failed: ${result.error ?? "unknown error"}`,
      );
      await load();
    } catch (err) {
      setError(formatError(err, "LLM response test"));
    } finally {
      setLoading(false);
    }
  };

  const toggleCategory = (category: ScannerCategory) => {
    setCategories((prev) => (prev.includes(category) ? prev.filter((x) => x !== category) : [...prev, category]));
  };

  return (
    <main className="space-y-4">
      <Panel>
        <SectionTitle title="Intelligence Layer" subtitle="Deterministic pipeline + optional LLM interpretation layer" />
        <div className="mt-2 flex flex-wrap gap-2 text-xs">
          <span className={`rounded-md border px-2 py-1 ${backendConnected ? "border-green/60 text-green" : "border-red/60 text-red"}`}>
            Backend API: {backendConnected ? "Connected" : "Not reachable"}
          </span>
          <span className={`rounded-md border px-2 py-1 ${llmStatus?.connected ? "border-green/60 text-green" : "border-red/60 text-red"}`}>
            LLM/Ollama: {llmStatus?.connected ? "Connected" : "Not reachable"}
          </span>
          <button type="button" onClick={() => setShowLLMConsole((prev) => !prev)} className="rounded-md border border-stroke px-2 py-1 hover:text-cyan">
            {showLLMConsole ? "Hide LLM Console" : "Show LLM Console"}
          </button>
          <button type="button" onClick={runLLMResponseTest} disabled={loading || !backendConnected || !llmStatus?.connected} className="rounded-md border border-stroke px-2 py-1 hover:text-cyan disabled:opacity-60">
            Test Ollama Response
          </button>
          <button type="button" onClick={load} className="rounded-md border border-stroke px-2 py-1 hover:text-cyan">Refresh</button>
        </div>
        {llmTest ? (
          <p className={`mt-2 text-xs ${llmTest.ok && llmTest.within_threshold ? "text-green" : llmTest.ok ? "text-yellow-300" : "text-red"}`}>
            LLM test: {llmTest.status} | model={llmTest.model} | latency={llmTest.response_time_ms} ms | threshold={llmTest.threshold_ms} ms
            {llmTest.error ? ` | error=${llmTest.error}` : ""}
          </p>
        ) : null}
        {llmStatus && !llmStatus.connected ? (
          <p className="mt-2 text-xs text-red">LLM check endpoint: {llmStatus.base_url}. Error: {llmStatus.error ?? "unknown"}. Suggested fix: ensure Ollama is running and reachable from backend.</p>
        ) : null}
        {llmStatus?.connected ? (
          <p className="mt-2 text-xs text-slate-300">
            Ollama model: {llmStatus.model_used ?? "-"} | available: {llmStatus.model_available === null ? "unknown" : llmStatus.model_available ? "yes" : "no"}
          </p>
        ) : null}
      </Panel>

      {dashboard ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="Daily Runs" value={String(dashboard.runs.length)} />
          <StatCard label="Latest Symbols" value={String(dashboard.latest_run_results.length)} />
          <StatCard label="Contexts Loaded" value={String(dashboard.latest_contexts.length)} />
          <StatCard label="Latest Review" value={dashboard.latest_review?.period ?? "-"} />
        </div>
      ) : null}

      <Panel>
        <SectionTitle title="Run Controls" subtitle="Clear parameters for deterministic + LLM phases" />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3 text-xs text-slate-300">
          <label>Market<select value={market} onChange={(e) => setMarket(e.target.value as MarketCode)} className="mt-1 h-10 w-full rounded-lg border border-stroke bg-bg px-2 text-sm"><option value="us">US</option><option value="bist">BIST</option></select></label>
          <label>Analysis Window<select value={duration} onChange={(e) => setDuration(e.target.value as ScannerDuration)} className="mt-1 h-10 w-full rounded-lg border border-stroke bg-bg px-2 text-sm"><option value="1y">1Y</option><option value="2y">2Y</option><option value="3y">3Y</option></select></label>
          <label>Universe<select value={scope} onChange={(e) => setScope(e.target.value as ScannerUniverseScope)} className="mt-1 h-10 w-full rounded-lg border border-stroke bg-bg px-2 text-sm"><option value="full_universe">Full Universe</option><option value="watchlist">Watchlist</option></select></label>
          <label>Top N Per Category<input type="number" min={1} max={20} value={topNPerCategory} onChange={(e) => setTopNPerCategory(Number(e.target.value))} className="mt-1 h-10 w-full rounded-lg border border-stroke bg-bg px-2 text-sm" /></label>
          <label>Final Shortlist Limit (auto)<input type="text" readOnly value={`${selectedCategoryCount} x ${topNPerCategory} = ${autoFinalShortlistLimit}`} className="mt-1 h-10 w-full rounded-lg border border-stroke bg-bg px-2 text-sm text-slate-300" /></label>
        </div>

        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          {(["trend_mode", "build_up", "momentum_mode", "value_rebuild", "overextended"] as ScannerCategory[]).map((cat) => (
            <button key={cat} type="button" onClick={() => toggleCategory(cat)} className={`rounded-md border px-2 py-1 ${categories.includes(cat) ? "border-cyan/60 text-cyan" : "border-stroke text-slate-300"}`}>{cat}</button>
          ))}
        </div>
        <p className="mt-2 text-xs text-slate-400">
          Daily Intelligence runs each selected category separately, selects Top N per category, merges duplicates, then optionally sends final candidates to Ollama for context.
        </p>
        <p className="mt-1 text-xs text-slate-400">
          Debug mode sends symbols to Ollama one by one using short JSON context prompt mode.
        </p>
        <button type="button" onClick={() => setShowAdvanced((prev) => !prev)} className="mt-3 rounded-md border border-stroke px-2 py-1 text-xs hover:text-cyan">
          {showAdvanced ? "Hide Advanced Settings" : "Show Advanced Settings"}
        </button>
        {showAdvanced ? (
          <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3 text-xs text-slate-300 rounded-lg border border-stroke/70 p-3">
            <label>Debug capped universe<input type="checkbox" checked={debugCappedUniverse} onChange={(e) => setDebugCappedUniverse(e.target.checked)} className="ml-2" /></label>
            <label>Max Universe Symbols<input type="number" min={10} max={500} value={maxUniverseSymbols} onChange={(e) => setMaxUniverseSymbols(Number(e.target.value))} className="mt-1 h-10 w-full rounded-lg border border-stroke bg-bg px-2 text-sm" /></label>
            <label>Scanner Result Cap<input type="number" min={5} max={100} value={scannerResultCap} onChange={(e) => setScannerResultCap(Number(e.target.value))} className="mt-1 h-10 w-full rounded-lg border border-stroke bg-bg px-2 text-sm" /></label>
            <label>LLM Concurrency<input type="number" min={1} max={8} value={llmConcurrency} onChange={(e) => setLlmConcurrency(Number(e.target.value))} className="mt-1 h-10 w-full rounded-lg border border-stroke bg-bg px-2 text-sm" /></label>
            <label>Context Symbol Limit<input type="number" min={1} max={100} value={contextSymbolLimit} onChange={(e) => setContextSymbolLimit(Number(e.target.value))} className="mt-1 h-10 w-full rounded-lg border border-stroke bg-bg px-2 text-sm" /></label>
            <label>LLM Timeout (sec)<input type="number" min={5} max={300} value={contextTimeout} onChange={(e) => setContextTimeout(Number(e.target.value))} className="mt-1 h-10 w-full rounded-lg border border-stroke bg-bg px-2 text-sm" /></label>
            <label>Live Stream Debug<input type="checkbox" checked={liveStreamDebug} onChange={(e) => setLiveStreamDebug(e.target.checked)} className="ml-2" /></label>
            <label>Review Period Days<input type="number" min={7} max={365} value={reviewDays} onChange={(e) => setReviewDays(Number(e.target.value))} className="mt-1 h-10 w-full rounded-lg border border-stroke bg-bg px-2 text-sm" /></label>
          </div>
        ) : null}

        <div className="mt-3 grid gap-2 md:grid-cols-2">
          <button type="button" onClick={runPipeline} disabled={loading || !backendConnected} className="h-10 rounded-lg bg-cyan px-3 text-sm font-semibold text-bg disabled:opacity-60">{loading ? "Running..." : "Run Daily Pipeline"}</button>
          <p className="text-xs text-slate-400">Runs deterministic scanner, analysis snapshots, and lightweight backtest summaries. Does not require LLM.</p>
          <button type="button" onClick={runContexts} disabled={loading || !canRunContexts} className="h-10 rounded-lg border border-stroke px-3 text-sm hover:text-cyan disabled:opacity-60">Generate Symbol Contexts</button>
          <p className="text-xs text-slate-400">Sends latest daily candidates to Ollama and generates bull/bear/risk summaries.</p>
          <button type="button" onClick={runBriefing} disabled={loading || !canRunBriefing} className="h-10 rounded-lg border border-stroke px-3 text-sm hover:text-cyan disabled:opacity-60">Generate Daily Briefing</button>
          <p className="text-xs text-slate-400">Summarises generated symbol contexts into one daily advisory report.</p>
          <button type="button" onClick={runReview} disabled={loading || !canRunReview} className="h-10 rounded-lg border border-stroke px-3 text-sm hover:text-cyan disabled:opacity-60">Run System Review</button>
          <p className="text-xs text-slate-400">Reviews stored daily runs and forward performance over the selected period.</p>
        </div>

        {!canRunContexts ? <p className="mt-2 text-xs text-slate-400">Generate Symbol Contexts requires a completed Daily Run and reachable Ollama.</p> : null}
        {!canRunBriefing ? <p className="mt-2 text-xs text-slate-400">Generate Daily Briefing requires generated symbol contexts for latest run and reachable Ollama.</p> : null}
        {!canRunReview ? <p className="mt-2 text-xs text-slate-400">Run System Review requires stored historical runs.</p> : null}

        {notice ? <p className="mt-3 text-xs text-green">{notice}</p> : null}
        {error ? <p className="mt-3 text-xs text-red">{error}</p> : null}
      </Panel>

      {showLLMConsole ? (
        <Panel>
          <SectionTitle title="Pipeline / LLM Console" subtitle="Live pipeline steps + Ollama request/response inspection" />
          {llmStatus ? (
            <p className="text-xs text-slate-400">
              Endpoint: {llmStatus.base_url} | Checked: {new Date(llmStatus.checked_at).toLocaleString()} | Status: {llmStatus.connected ? "connected" : `error: ${llmStatus.error ?? "unknown"}`}
            </p>
          ) : null}
          <div className="mt-3 max-h-[260px] overflow-auto rounded-lg border border-stroke/70">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-stroke text-left text-slate-400">
                  <th className="px-2 py-2">Time</th>
                  <th className="px-2 py-2">Step</th>
                  <th className="px-2 py-2">Status</th>
                  <th className="px-2 py-2">Category</th>
                  <th className="px-2 py-2">Symbol</th>
                  <th className="px-2 py-2">Duration ms</th>
                  <th className="px-2 py-2">Message</th>
                </tr>
              </thead>
              <tbody>
                {pipelineEvents.map((row) => (
                  <tr key={row.id} className={`border-b border-stroke/50 ${row.status === "failed" ? "bg-red/10" : ""}`}>
                    <td className="px-2 py-2">{new Date(row.timestamp).toLocaleTimeString()}</td>
                    <td className="px-2 py-2">{row.step_name}</td>
                    <td className={`px-2 py-2 ${row.status === "failed" ? "text-red" : row.status === "success" ? "text-green" : "text-yellow-300"}`}>{row.status}</td>
                    <td className="px-2 py-2">{row.category ?? "-"}</td>
                    <td className="px-2 py-2">{row.symbol ?? "-"}</td>
                    <td className="px-2 py-2">{row.duration_ms}</td>
                    <td className="px-2 py-2">{row.error_message ?? row.message ?? "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 max-h-[420px] overflow-auto rounded-lg border border-stroke/70">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-stroke text-left text-slate-400">
                  <th className="px-2 py-2">Time</th>
                  <th className="px-2 py-2">Symbol</th>
                  <th className="px-2 py-2">Type</th>
                  <th className="px-2 py-2">Status</th>
                  <th className="px-2 py-2">Duration ms</th>
                  <th className="px-2 py-2">Details</th>
                </tr>
              </thead>
              <tbody>
                {llmLogs.map((row) => (
                  <Fragment key={row.id}>
                    <tr className={`border-b border-stroke/50 ${row.status === "fail" ? "bg-red/10" : ""}`}>
                      <td className="px-2 py-2">{new Date(row.timestamp).toLocaleTimeString()}</td>
                      <td className="px-2 py-2">{row.symbol ?? "-"}</td>
                      <td className="px-2 py-2">{row.call_type}</td>
                      <td className={`px-2 py-2 ${row.status === "fail" ? "text-red" : "text-green"}`}>{row.status}</td>
                      <td className="px-2 py-2">{row.duration_ms}</td>
                      <td className="px-2 py-2"><button type="button" onClick={() => setExpandedLogIds((prev) => ({ ...prev, [row.id]: !prev[row.id] }))} className="rounded border border-stroke px-2 py-1 hover:text-cyan">{expandedLogIds[row.id] ? "Collapse" : "Expand"}</button></td>
                    </tr>
                    {expandedLogIds[row.id] ? (
                      <tr className="border-b border-stroke/40 bg-panelSoft/60">
                        <td className="px-2 py-2 text-slate-300" colSpan={6}>
                          {row.error_message ? <p className="mb-2 text-red">Error: {row.error_message}</p> : null}
                          <p className="font-semibold text-slate-200">Prompt</p>
                          <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded border border-stroke/60 bg-bg/50 p-2">{row.prompt}</pre>
                          <p className="mt-2 font-semibold text-slate-200">Raw Response</p>
                          <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded border border-stroke/60 bg-bg/50 p-2">{row.raw_response ?? "-"}</pre>
                          <p className="mt-2 font-semibold text-slate-200">Parsed/Used Output</p>
                          <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded border border-stroke/60 bg-bg/50 p-2">{JSON.stringify(row.parsed_output, null, 2)}</pre>
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      ) : null}

      <Panel>
        <SectionTitle title="Daily Runs" subtitle="Deterministic scanner -> analysis -> lightweight backtest snapshots" />
        <div className="max-h-[240px] overflow-auto rounded-lg border border-stroke/70">
          <table className="w-full text-xs">
            <thead><tr className="border-b border-stroke text-left text-slate-400"><th className="px-2 py-2">Date</th><th className="px-2 py-2">Symbols</th><th className="px-2 py-2">Categories</th><th className="px-2 py-2">Top N / Cat</th><th className="px-2 py-2">Raw Before Merge</th><th className="px-2 py-2">Final After Merge</th><th className="px-2 py-2">Status</th></tr></thead>
            <tbody>
              {(dashboard?.runs ?? []).map((row) => (
                <tr key={row.id} className="border-b border-stroke/50"><td className="px-2 py-2">{new Date(row.timestamp).toLocaleString()}</td><td className="px-2 py-2">{row.symbols_count}</td><td className="px-2 py-2">{row.scanner_categories.join(", ")}</td><td className="px-2 py-2">{row.top_n_per_category}</td><td className="px-2 py-2">{row.raw_candidates_before_merge}</td><td className="px-2 py-2">{row.final_candidates_after_merge}</td><td className="px-2 py-2">{row.status}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel>
        <SectionTitle title="Latest Merged Candidates" subtitle="Category-balanced merge, deduplication, and multi-category priority boost" />
        <div className="max-h-[360px] overflow-auto rounded-lg border border-stroke/70">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-stroke text-left text-slate-400">
                <th className="px-2 py-2">Merged Rank</th>
                <th className="px-2 py-2">Symbol</th>
                <th className="px-2 py-2">Category Source</th>
                <th className="px-2 py-2">Score / Category</th>
                <th className="px-2 py-2">Final Score</th>
                <th className="px-2 py-2">Multi-Category</th>
              </tr>
            </thead>
            <tbody>
              {(dashboard?.latest_run_results ?? []).map((row) => (
                <tr key={`${row.symbol}-${row.merged_rank}`} className="border-b border-stroke/50">
                  <td className="px-2 py-2">{row.merged_rank}</td>
                  <td className="px-2 py-2 font-semibold text-slate-100">{row.symbol}</td>
                  <td className="px-2 py-2">{row.category_tags.join(", ")}</td>
                  <td className="px-2 py-2">{Object.entries(row.score_by_category).map(([k, v]) => `${k}:${v.toFixed(1)}`).join(" | ")}</td>
                  <td className="px-2 py-2">{row.score.toFixed(2)} {row.priority_boost > 0 ? `(+${row.priority_boost.toFixed(1)} boost)` : ""}</td>
                  <td className="px-2 py-2">{row.multi_category ? <span className="rounded border border-cyan/60 px-2 py-1 text-cyan">multi-category</span> : "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel>
        <SectionTitle title="Daily Briefing" subtitle="LLM-generated advisory summary, never an execution signal" />
        <p className="text-sm text-slate-200 whitespace-pre-wrap">{dashboard?.latest_briefing?.summary_text ?? "No briefing generated yet."}</p>
      </Panel>

      <Panel>
        <SectionTitle title="Review" subtitle="System-level findings and recommendations from historical outcomes" />
        {dashboard?.latest_review ? (
          <div className="space-y-2 text-sm">
            <p><strong>Findings:</strong> {dashboard.latest_review.findings}</p>
            <p><strong>Mistakes:</strong> {dashboard.latest_review.mistakes}</p>
            <p><strong>Missed Patterns:</strong> {dashboard.latest_review.missed_patterns}</p>
            <p><strong>Recommendations:</strong> {dashboard.latest_review.recommendations}</p>
          </div>
        ) : (
          <p className="text-sm text-slate-300">No review generated yet.</p>
        )}
      </Panel>
    </main>
  );
}
