"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Panel, Pill, SectionTitle, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import type { DailyPipelineRequest, IntelligenceDashboardResponse, IntelligenceRunResponse, MarketCode, SymbolResult } from "@/lib/types";

const discoveryRequest: DailyPipelineRequest = {
  market: "us",
  duration: "1y",
  categories: ["trend_mode", "build_up", "momentum_mode", "value_rebuild", "overextended"],
  max_candidates: 25,
  top_n_per_category: 5,
  max_universe_symbols: 60,
  scanner_max_results: 30,
  scanner_universe_scope: "capped_universe",
  scanner_max_runtime_seconds: 18,
};

function errorMessage(error: unknown): string {
  if (!(error instanceof Error)) return "The request failed.";
  try {
    const payload = JSON.parse(error.message) as { detail?: unknown };
    if (typeof payload.detail === "string") return payload.detail;
    return JSON.stringify(payload.detail ?? payload);
  } catch {
    return error.message;
  }
}

function formatCategory(category: string): string {
  return category.replace(/_/g, " ");
}

function finalEntryState(result: SymbolResult): string {
  const value = result.structure_snapshot?.final_entry_decision;
  if (value === true) return "Eligible";
  if (value === false) return "Blocked";
  return result.entry_readiness || "Unknown";
}

export default function DiscoverPage() {
  const [dashboard, setDashboard] = useState<IntelligenceDashboardResponse | null>(null);
  const [results, setResults] = useState<SymbolResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [market, setMarket] = useState<MarketCode>("us");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.getIntelligenceDashboard();
      setDashboard(response);
      setResults(response.latest_run_results);
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const latestRun = useMemo(() => dashboard?.runs[0] ?? null, [dashboard]);

  const runDiscovery = async () => {
    setRunning(true);
    setError(null);
    setNotice(null);
    try {
      const response: IntelligenceRunResponse = await api.runDailyPipeline({ ...discoveryRequest, market });
      setResults(response.symbol_results);
      setNotice(`Deterministic ${market.toUpperCase()} discovery completed: ${response.run.final_candidates_after_merge} merged candidates in run ${response.run.id}.`);
      await load();
    } catch (requestError) {
      setError(errorMessage(requestError));
    } finally {
      setRunning(false);
    }
  };

  return (
    <main className="space-y-4">
      <Panel className="border-cyan/30 bg-gradient-to-r from-panel to-panelSoft">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-start">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-cyan">Deterministic candidate discovery</p>
            <h2 className="mt-1 text-2xl font-semibold">Discover</h2>
            <p className="mt-2 max-w-3xl text-sm text-slate-300">
              Run the established deterministic daily scanner and inspect its frozen candidate evidence. This page does not tune scores, categories, or entry gates.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-xs text-slate-300" htmlFor="discovery-market">Market</label>
            <select
              id="discovery-market"
              value={market}
              onChange={(event) => setMarket(event.target.value as MarketCode)}
              disabled={running}
              className="rounded-lg border border-stroke bg-bg px-3 py-2 text-sm text-slate-100 disabled:opacity-50"
            >
              <option value="us">US stocks</option>
              <option value="bist">BIST stocks</option>
            </select>
            <button
              type="button"
              onClick={() => void runDiscovery()}
              disabled={running}
              className="rounded-lg border border-cyan/50 bg-cyan/15 px-4 py-2 text-sm font-semibold text-cyan disabled:cursor-not-allowed disabled:opacity-50"
            >
              {running ? "Running deterministic discovery…" : "Run Discovery Now"}
            </button>
          </div>
        </div>
        <p className="mt-4 text-xs text-slate-400">
          Fixed request: selected US or BIST market, 1-year window, all five existing categories, capped 60-symbol universe, 18-second scanner limit. No LLM is invoked.
        </p>
      </Panel>

      {error ? <Panel className="border-red/50 text-sm text-red">{error}</Panel> : null}
      {notice ? <Panel className="border-green/50 text-sm text-green">{notice}</Panel> : null}

      <div className="grid gap-3 md:grid-cols-3">
        <StatCard label="Latest run" value={latestRun?.date ?? "No run"} />
        <StatCard label="Merged candidates" value={latestRun ? String(latestRun.final_candidates_after_merge) : "-"} />
        <StatCard label="Visible results" value={String(results.length)} />
      </div>

      <Panel>
        <SectionTitle title="Current deterministic candidates" subtitle="Frozen scanner output only. Use Monitor to watch symbols; advanced Scanner remains available for detailed inspection." />
        {loading ? <p className="text-sm text-slate-400">Loading latest discovery run…</p> : null}
        {!loading && results.length === 0 ? <p className="text-sm text-slate-400">No persisted daily-run candidates are available yet.</p> : null}
        {results.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-stroke text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="px-2 py-3">Symbol</th>
                  <th className="px-2 py-3">Categories</th>
                  <th className="px-2 py-3">Score</th>
                  <th className="px-2 py-3">Entry gate</th>
                  <th className="px-2 py-3">Blocker</th>
                  <th className="px-2 py-3">Context</th>
                </tr>
              </thead>
              <tbody>
                {results.map((result) => (
                  <tr key={`${result.symbol}-${result.merged_rank}`} className="border-b border-stroke/70 text-slate-200 last:border-0">
                    <td className="px-2 py-3 font-semibold">{result.symbol}</td>
                    <td className="px-2 py-3">
                      <div className="flex min-w-48 flex-wrap gap-1">
                        {result.category_tags.map((category) => <Pill key={category}>{formatCategory(category)}</Pill>)}
                      </div>
                    </td>
                    <td className="px-2 py-3">{result.score.toFixed(2)}</td>
                    <td className="px-2 py-3">
                      <Pill className={finalEntryState(result) === "Eligible" ? "border-green/40 text-green" : "border-amber/40 text-amber"}>
                        {finalEntryState(result)}
                      </Pill>
                    </td>
                    <td className="px-2 py-3 text-slate-300">{result.blocked_by || "-"}</td>
                    <td className="px-2 py-3">
                      <Link className="text-cyan hover:underline" href={`/analysis?ticker=${encodeURIComponent(result.symbol)}`}>
                        Inspect analysis
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Panel>
    </main>
  );
}
