"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Panel, SectionTitle, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import {
  MarketCode,
  ScannerCategory,
  ScannerDuration,
  ScannerResponse,
  ScannerUniverseScope,
} from "@/lib/types";

const recommendedDurationByCategory: Record<ScannerCategory, ScannerDuration> = {
  trend_mode: "2y",
  build_up: "2y",
  overextended: "1y",
};

const rationaleByCategory: Record<ScannerCategory, string> = {
  trend_mode: "2Y is recommended to evaluate continuation quality with enough context.",
  build_up: "2Y is recommended to evaluate EMA200 reclaim/rebuild behavior before breakout.",
  overextended: "1Y is recommended to focus on recent stretched moves and caution zones.",
};

const categoryDefinition: Record<ScannerCategory, { title: string; desc: string; bias: string }> = {
  trend_mode: {
    title: "Trend Mode",
    desc: "Stocks already in constructive uptrend with favorable EMA alignment and continuation potential.",
    bias: "continuation bias",
  },
  build_up: {
    title: "Build-up",
    desc: "Stocks preparing for larger moves: EMA200 reclaim attempts, repeated tests, compression, and structure rebuilding.",
    bias: "pre-breakout bias",
  },
  overextended: {
    title: "Overextended",
    desc: "Stocks already stretched after strong moves; useful for caution, monitoring, and pullback planning.",
    bias: "caution / monitor bias",
  },
};

export default function ScannerPage() {
  const router = useRouter();
  const [market, setMarket] = useState<MarketCode>("us");
  const [category, setCategory] = useState<ScannerCategory>("trend_mode");
  const [duration, setDuration] = useState<ScannerDuration>("2y");
  const [keepManualDuration, setKeepManualDuration] = useState(false);
  const [maxResults, setMaxResults] = useState(20);
  const [universeScope, setUniverseScope] = useState<ScannerUniverseScope>("capped_universe");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ScannerResponse | null>(null);

  const recommended = recommendedDurationByCategory[category];

  const onCategoryChange = (next: ScannerCategory) => {
    setCategory(next);
    if (!keepManualDuration) {
      setDuration(recommendedDurationByCategory[next]);
    }
  };

  const runScan = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await api.scanner(market, duration, category, maxResults, universeScope);
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scanner request failed.");
    } finally {
      setLoading(false);
    }
  };

  const scopeLabel = useMemo(() => {
    return `Scanner finds candidates. Analysis explains structure. Backtest validates historical behavior.`;
  }, []);

  return (
    <main className="space-y-4">
      <Panel>
        <SectionTitle title="Stock Scanner" subtitle="Bounded deterministic discovery layer feeding analysis/backtest workflow" />
        <p className="text-sm text-slate-300">{scopeLabel}</p>
      </Panel>

      <Panel>
        <SectionTitle title="Scanner Inputs" subtitle="Single-pass bounded scan across selected universe" />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          <label className="space-y-1 text-sm">
            <span className="text-xs text-slate-400">Stock Type</span>
            <select value={market} onChange={(event) => setMarket(event.target.value as MarketCode)} className="h-10 w-full rounded-lg border border-stroke bg-bg px-3">
              <option value="us">US</option>
              <option value="bist">BIST</option>
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-xs text-slate-400">Scan Category</span>
            <select value={category} onChange={(event) => onCategoryChange(event.target.value as ScannerCategory)} className="h-10 w-full rounded-lg border border-stroke bg-bg px-3">
              <option value="trend_mode">Trend Mode</option>
              <option value="build_up">Build-up</option>
              <option value="overextended">Overextended</option>
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-xs text-slate-400">Duration</span>
            <select value={duration} onChange={(event) => { setDuration(event.target.value as ScannerDuration); setKeepManualDuration(true); }} className="h-10 w-full rounded-lg border border-stroke bg-bg px-3">
              <option value="1y">1Y</option>
              <option value="2y">2Y</option>
              <option value="3y">3Y</option>
              <option value="5y">5Y</option>
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-xs text-slate-400">Max Results</span>
            <select value={maxResults} onChange={(event) => setMaxResults(Number(event.target.value))} className="h-10 w-full rounded-lg border border-stroke bg-bg px-3">
              <option value={20}>20</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-xs text-slate-400">Universe Scope</span>
            <select value={universeScope} onChange={(event) => setUniverseScope(event.target.value as ScannerUniverseScope)} className="h-10 w-full rounded-lg border border-stroke bg-bg px-3">
              <option value="full_universe">Full Universe</option>
              <option value="watchlist">Watchlist / Favorites</option>
              <option value="capped_universe">Capped Universe</option>
            </select>
          </label>
        </div>

        <div className="mt-3 rounded-xl border border-stroke/70 bg-panelSoft p-3 text-xs text-slate-300">
          Selected duration: {duration.toUpperCase()} | Recommended duration for {categoryDefinition[category].title}: {recommended.toUpperCase()}.
          {" "}Reason: {rationaleByCategory[category]}
        </div>
        <label className="mt-3 inline-flex items-center gap-2 text-xs text-slate-300">
          <input type="checkbox" checked={keepManualDuration} onChange={(event) => setKeepManualDuration(event.target.checked)} />
          Keep manual duration when category changes
        </label>
        <p className="mt-2 text-xs text-slate-300">
          Planned scan scope: {market.toUpperCase()} | {categoryDefinition[category].title} | {duration.toUpperCase()} | {universeScope.replaceAll("_", " ")} | top {maxResults}.
        </p>

        <button type="button" onClick={runScan} disabled={loading} className="mt-4 h-11 rounded-lg bg-cyan px-6 text-sm font-semibold text-bg transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50">
          {loading ? "Scanning..." : "Run Scanner"}
        </button>
      </Panel>

      <Panel>
        <SectionTitle title="Category Definitions" subtitle="Scanner is candidate discovery, not direct execution" />
        <div className="grid gap-3 md:grid-cols-3">
          {(Object.keys(categoryDefinition) as ScannerCategory[]).map((key) => (
            <div key={key} className="rounded-xl border border-stroke/70 bg-panelSoft p-3">
              <p className="text-sm font-semibold text-slate-100">{categoryDefinition[key].title}</p>
              <p className="mt-1 text-xs text-slate-300">{categoryDefinition[key].desc}</p>
              <p className="mt-2 text-xs text-cyan">Bias: {categoryDefinition[key].bias}</p>
            </div>
          ))}
        </div>
      </Panel>

      {error ? (
        <Panel className="border-red/40 bg-red/10">
          <p className="text-sm text-red">{error}</p>
        </Panel>
      ) : null}

      {result ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
            <StatCard label="Stock Type" value={result.scope.market.toUpperCase()} />
            <StatCard label="Category" value={result.scope.category.replaceAll("_", " ")} />
            <StatCard label="Duration" value={result.scope.duration.toUpperCase()} />
            <StatCard label="Universe Size" value={`${result.scope.symbol_count}`} />
            <StatCard label="Processed" value={`${result.scope.processed_count}`} />
            <StatCard label="Runtime" value={`${result.scope.runtime_seconds.toFixed(2)}s`} />
          </div>
          <Panel className="bg-panelSoft">
            <p className="text-xs text-slate-300">
              Scope summary: {result.scope.universe_scope.replaceAll("_", " ")}, max results {result.scope.max_results}, recommended duration {result.scope.recommended_duration.toUpperCase()}.
            </p>
            {result.scope.partial_scan ? (
              <p className="mt-1 text-xs text-amber-300">{result.scope.partial_scan_note}</p>
            ) : null}
          </Panel>

          <Panel>
            <SectionTitle title="Scanner Results" subtitle="Ranked shortlist for next analysis step" />
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-stroke text-left text-slate-400">
                    <th className="px-2 py-2">Symbol</th>
                    <th className="px-2 py-2">Score</th>
                    <th className="px-2 py-2">Priority</th>
                    <th className="px-2 py-2">Category</th>
                    <th className="px-2 py-2">Reason</th>
                    <th className="px-2 py-2">Trend State</th>
                    <th className="px-2 py-2">Price vs EMA200</th>
                    <th className="px-2 py-2">EMA200 Slope</th>
                    <th className="px-2 py-2">Support%</th>
                    <th className="px-2 py-2">Room%</th>
                    <th className="px-2 py-2">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {result.results.length === 0 ? (
                    <tr>
                      <td className="px-2 py-3 text-slate-400" colSpan={11}>No candidates found for selected scope.</td>
                    </tr>
                  ) : (
                    result.results.map((row) => (
                      <tr key={row.normalized_symbol} className="border-b border-stroke/50">
                        <td className="px-2 py-2">{row.symbol}</td>
                        <td className="px-2 py-2">{row.scanner_score.toFixed(2)}</td>
                        <td className="px-2 py-2 capitalize">{row.priority}</td>
                        <td className="px-2 py-2">{row.category_tag.replaceAll("_", " ")}</td>
                        <td className="max-w-[300px] px-2 py-2 text-xs text-slate-300">{row.short_reason}</td>
                        <td className="px-2 py-2">{row.trend_state}</td>
                        <td className="px-2 py-2">{row.price_vs_ema200_pct.toFixed(2)}%</td>
                        <td className="px-2 py-2">{row.ema200_slope_state}</td>
                        <td className="px-2 py-2">{row.support_distance_pct.toFixed(2)}%</td>
                        <td className="px-2 py-2">{row.resistance_room_pct.toFixed(2)}%</td>
                        <td className="px-2 py-2">
                          <button
                            type="button"
                            onClick={() => router.push(`/analysis?ticker=${encodeURIComponent(row.symbol)}&market=${encodeURIComponent(result.scope.market)}&window=${encodeURIComponent(result.scope.duration)}`)}
                            className="rounded-md border border-stroke px-2 py-1 text-xs text-slate-300 hover:text-cyan"
                          >
                            Open Analysis
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </Panel>
        </>
      ) : null}
    </main>
  );
}
