"use client";

import { useEffect, useState } from "react";
import { Panel, SectionTitle, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import { IntelligenceDashboardResponse, MarketCode, ScannerCategory, ScannerDuration, ScannerUniverseScope } from "@/lib/types";

export default function IntelligencePage() {
  const [dashboard, setDashboard] = useState<IntelligenceDashboardResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [market, setMarket] = useState<MarketCode>("us");
  const [duration, setDuration] = useState<ScannerDuration>("1y");
  const [scope, setScope] = useState<ScannerUniverseScope>("capped_universe");
  const [maxCandidates, setMaxCandidates] = useState(20);
  const [maxResults, setMaxResults] = useState(20);
  const [categories, setCategories] = useState<ScannerCategory[]>(["trend_mode", "build_up", "momentum_mode", "value_rebuild", "overextended"]);

  const [contextConcurrency, setContextConcurrency] = useState(4);
  const [contextTimeout, setContextTimeout] = useState(20);
  const [reviewDays, setReviewDays] = useState(28);

  const load = async () => {
    const data = await api.getIntelligenceDashboard();
    setDashboard(data);
  };

  useEffect(() => {
    void load();
  }, []);

  const latestRun = dashboard?.runs?.[0] ?? null;

  const runPipeline = async () => {
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      const response = await api.runDailyPipeline({
        market,
        duration,
        categories,
        max_candidates: maxCandidates,
        scanner_max_results: maxResults,
        scanner_universe_scope: scope,
      });
      setNotice(`Daily pipeline completed: ${response.run.symbols_count} symbols stored.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Daily pipeline failed.");
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
        max_concurrency: contextConcurrency,
        timeout_seconds: contextTimeout,
        model: "llama3",
      });
      setNotice(`Symbol context completed: generated ${response.generated}, failed ${response.failed}.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Symbol context generation failed.");
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
        model: "llama3",
      });
      setNotice(`Daily briefing ${response.status === "generated" ? "generated" : "failed"}.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Daily briefing failed.");
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
        model: "llama3",
        max_concurrency: contextConcurrency,
        timeout_seconds: contextTimeout,
      });
      setNotice(`System review ${response.status === "generated" ? "generated" : "failed"} for ${response.period}.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "System review failed.");
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
        <SectionTitle title="Intelligence Layer" subtitle="Phase 2C deterministic tracking + Phase 3 LLM context and review (read-only advisory)" />
        <p className="text-xs text-slate-300">
          Safety boundary: LLM never opens trades, never modifies configs, and never overrides deterministic engine decisions.
        </p>
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
        <SectionTitle title="Run Controls" subtitle="Deterministic pipeline first, then optional LLM context and review" />
        <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
          <select value={market} onChange={(e) => setMarket(e.target.value as MarketCode)} className="h-10 rounded-lg border border-stroke bg-bg px-2 text-sm"><option value="us">US</option><option value="bist">BIST</option></select>
          <select value={duration} onChange={(e) => setDuration(e.target.value as ScannerDuration)} className="h-10 rounded-lg border border-stroke bg-bg px-2 text-sm"><option value="1y">1Y</option><option value="2y">2Y</option><option value="3y">3Y</option><option value="5y">5Y</option></select>
          <select value={scope} onChange={(e) => setScope(e.target.value as ScannerUniverseScope)} className="h-10 rounded-lg border border-stroke bg-bg px-2 text-sm"><option value="capped_universe">Capped</option><option value="full_universe">Full</option><option value="watchlist">Watchlist</option></select>
          <input type="number" min={5} max={60} value={maxCandidates} onChange={(e) => setMaxCandidates(Number(e.target.value))} className="h-10 rounded-lg border border-stroke bg-bg px-2 text-sm" placeholder="max candidates" />
          <input type="number" min={5} max={100} value={maxResults} onChange={(e) => setMaxResults(Number(e.target.value))} className="h-10 rounded-lg border border-stroke bg-bg px-2 text-sm" placeholder="scanner max rows" />
          <button type="button" onClick={runPipeline} disabled={loading} className="h-10 rounded-lg bg-cyan px-3 text-sm font-semibold text-bg disabled:opacity-60">{loading ? "Running..." : "Run Daily Pipeline"}</button>
        </div>
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          {(["trend_mode", "build_up", "momentum_mode", "value_rebuild", "overextended"] as ScannerCategory[]).map((cat) => (
            <button key={cat} type="button" onClick={() => toggleCategory(cat)} className={`rounded-md border px-2 py-1 ${categories.includes(cat) ? "border-cyan/60 text-cyan" : "border-stroke text-slate-300"}`}>{cat}</button>
          ))}
        </div>
        <div className="mt-3 grid gap-3 md:grid-cols-4">
          <input type="number" min={1} max={8} value={contextConcurrency} onChange={(e) => setContextConcurrency(Number(e.target.value))} className="h-10 rounded-lg border border-stroke bg-bg px-2 text-sm" placeholder="llm concurrency" />
          <input type="number" min={5} max={60} value={contextTimeout} onChange={(e) => setContextTimeout(Number(e.target.value))} className="h-10 rounded-lg border border-stroke bg-bg px-2 text-sm" placeholder="timeout sec" />
          <button type="button" onClick={runContexts} disabled={loading} className="h-10 rounded-lg border border-stroke px-3 text-sm hover:text-cyan disabled:opacity-60">Generate Symbol Contexts</button>
          <button type="button" onClick={runBriefing} disabled={loading} className="h-10 rounded-lg border border-stroke px-3 text-sm hover:text-cyan disabled:opacity-60">Generate Daily Briefing</button>
        </div>
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <input type="number" min={7} max={365} value={reviewDays} onChange={(e) => setReviewDays(Number(e.target.value))} className="h-10 rounded-lg border border-stroke bg-bg px-2 text-sm" />
          <button type="button" onClick={runReview} disabled={loading} className="h-10 rounded-lg border border-stroke px-3 text-sm hover:text-cyan disabled:opacity-60">Run System Review</button>
        </div>
        {notice ? <p className="mt-3 text-xs text-green">{notice}</p> : null}
        {error ? <p className="mt-3 text-xs text-red">{error}</p> : null}
      </Panel>

      <Panel>
        <SectionTitle title="Daily Runs" subtitle="Deterministic scanner -> analysis -> lightweight backtest snapshots" />
        <div className="max-h-[240px] overflow-auto rounded-lg border border-stroke/70">
          <table className="w-full text-xs">
            <thead><tr className="border-b border-stroke text-left text-slate-400"><th className="px-2 py-2">Date</th><th className="px-2 py-2">Symbols</th><th className="px-2 py-2">Categories</th><th className="px-2 py-2">Status</th></tr></thead>
            <tbody>
              {(dashboard?.runs ?? []).map((row) => (
                <tr key={row.id} className="border-b border-stroke/50"><td className="px-2 py-2">{new Date(row.timestamp).toLocaleString()}</td><td className="px-2 py-2">{row.symbols_count}</td><td className="px-2 py-2">{row.scanner_categories.join(", ")}</td><td className="px-2 py-2">{row.status}</td></tr>
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

