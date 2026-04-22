"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Panel, SectionTitle, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import {
  MarketCode,
  ScannerCustomRule,
  ScannerCategory,
  ScannerDuration,
  ScannerRequest,
  ScannerResponse,
  ScannerResult,
  ScannerRuleField,
  ScannerRuleOperator,
  ScannerUniverseScope,
} from "@/lib/types";

const recommendedDurationByCategory: Record<ScannerCategory, ScannerDuration> = {
  trend_mode: "2y",
  build_up: "2y",
  momentum_mode: "1y",
  overextended: "1y",
};

const rationaleByCategory: Record<ScannerCategory, string> = {
  trend_mode: "2Y is recommended to evaluate continuation quality with enough context.",
  build_up: "2Y is recommended to evaluate EMA200 reclaim/rebuild behavior before breakout.",
  momentum_mode: "1Y is recommended to prioritize recent expansion dynamics while preserving enough trend context.",
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
  momentum_mode: {
    title: "Momentum Mode",
    desc: "Stocks already breaking out or expanding with strong structure and improving score dynamics.",
    bias: "expansion / continuation bias",
  },
  overextended: {
    title: "Overextended",
    desc: "Stocks already stretched after strong moves; useful for caution, monitoring, and pullback planning.",
    bias: "caution / monitor bias",
  },
};

const sortOptions: Array<{ key: keyof ScannerResult; label: string; numeric?: boolean }> = [
  { key: "scanner_score", label: "Score", numeric: true },
  { key: "current_score", label: "Current", numeric: true },
  { key: "score_delta_short", label: "D(5)", numeric: true },
  { key: "score_delta_medium", label: "D(20)", numeric: true },
  { key: "price_vs_ema200_pct", label: "Price vs EMA200", numeric: true },
  { key: "support_distance_pct", label: "Support%", numeric: true },
  { key: "resistance_room_pct", label: "Room%", numeric: true },
  { key: "volume_ratio_20", label: "VolRatio20", numeric: true },
  { key: "resistance_test_count", label: "Res Tests", numeric: true },
  { key: "ema200_test_count", label: "EMA200 Tests", numeric: true },
];

const ruleFieldOptions: Array<{ value: ScannerRuleField; label: string; numeric: boolean }> = [
  { value: "price_vs_ema200_pct", label: "Price vs EMA200 %", numeric: true },
  { value: "distance_to_ema20_pct", label: "Distance to EMA20 %", numeric: true },
  { value: "distance_to_ema50_pct", label: "Distance to EMA50 %", numeric: true },
  { value: "rsi_14", label: "RSI 14", numeric: true },
  { value: "volume_ratio_20", label: "Volume Ratio 20", numeric: true },
  { value: "support_distance_pct", label: "Support Distance %", numeric: true },
  { value: "resistance_room_pct", label: "Resistance Room %", numeric: true },
  { value: "ema200_slope_state", label: "EMA200 Slope State", numeric: false },
  { value: "trend_state", label: "Trend State", numeric: false },
];

const operatorOptions: Array<{ value: ScannerRuleOperator; label: string }> = [
  { value: "gt", label: ">" },
  { value: "gte", label: ">=" },
  { value: "lt", label: "<" },
  { value: "lte", label: "<=" },
  { value: "eq", label: "=" },
  { value: "in", label: "in (csv)" },
];

const ruleDefaultByField: Record<ScannerRuleField, ScannerCustomRule> = {
  price_vs_ema200_pct: { field: "price_vs_ema200_pct", operator: "gt", value_number: 0 },
  distance_to_ema20_pct: { field: "distance_to_ema20_pct", operator: "lt", value_number: 5 },
  distance_to_ema50_pct: { field: "distance_to_ema50_pct", operator: "lt", value_number: 8 },
  rsi_14: { field: "rsi_14", operator: "lt", value_number: 35 },
  volume_ratio_20: { field: "volume_ratio_20", operator: "gt", value_number: 1.5 },
  support_distance_pct: { field: "support_distance_pct", operator: "lt", value_number: 6 },
  resistance_room_pct: { field: "resistance_room_pct", operator: "gt", value_number: 2 },
  ema200_slope_state: { field: "ema200_slope_state", operator: "eq", value_text: "rising" },
  trend_state: { field: "trend_state", operator: "eq", value_text: "bullish_trend" },
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
  const [sortKey, setSortKey] = useState<keyof ScannerResult>("scanner_score");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [useCustomRules, setUseCustomRules] = useState(false);
  const [customRules, setCustomRules] = useState<ScannerCustomRule[]>([]);
  const [rangeStart, setRangeStart] = useState("");
  const [rangeEnd, setRangeEnd] = useState("");

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
      const payload: ScannerRequest = {
        market,
        duration,
        category,
        max_results: maxResults,
        universe_scope: universeScope,
        use_custom_rules: useCustomRules && customRules.length > 0,
        ...(useCustomRules && customRules.length > 0 ? { custom_rules: customRules } : {}),
        ...(rangeStart && rangeEnd ? { range_start: rangeStart, range_end: rangeEnd } : {}),
      };
      const response = await api.scanner(payload);
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

  const sortedResults = useMemo(() => {
    if (!result) return [];
    const next = [...result.results];
    next.sort((a, b) => {
      const av = a[sortKey] as number | string | null;
      const bv = b[sortKey] as number | string | null;
      if (av === null && bv === null) return 0;
      if (av === null) return 1;
      if (bv === null) return -1;
      if (typeof av === "number" && typeof bv === "number") {
        return sortDirection === "asc" ? av - bv : bv - av;
      }
      const cmp = String(av).localeCompare(String(bv));
      return sortDirection === "asc" ? cmp : -cmp;
    });
    return next;
  }, [result, sortKey, sortDirection]);

  const toggleSort = (key: keyof ScannerResult) => {
    if (sortKey === key) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setSortDirection("desc");
  };

  const addRule = () => {
    setUseCustomRules(true);
    setCustomRules((prev) => [
      ...prev,
      { ...ruleDefaultByField.price_vs_ema200_pct },
    ]);
  };

  const updateRule = (index: number, patch: Partial<ScannerCustomRule>) => {
    setCustomRules((prev) => prev.map((rule, i) => (i === index ? { ...rule, ...patch } : rule)));
  };

  const setRuleFieldWithDefault = (index: number, field: ScannerRuleField) => {
    const template = ruleDefaultByField[field];
    updateRule(index, {
      field,
      operator: template.operator,
      value_number: template.value_number ?? null,
      value_text: template.value_text ?? null,
      value_list: template.value_list ?? [],
    });
  };

  const addPresetRule = (field: ScannerRuleField) => {
    setUseCustomRules(true);
    setCustomRules((prev) => [...prev, { ...ruleDefaultByField[field] }]);
  };

  const addBuildUpPreset = () => {
    setUseCustomRules(true);
    setCustomRules((prev) => [
      ...prev,
      { ...ruleDefaultByField.price_vs_ema200_pct },
      { ...ruleDefaultByField.distance_to_ema20_pct },
      { ...ruleDefaultByField.volume_ratio_20 },
    ]);
  };

  const removeRule = (index: number) => {
    setCustomRules((prev) => prev.filter((_, i) => i !== index));
  };

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
              <option value="momentum_mode">Momentum Mode</option>
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

        <div className="mt-4 rounded-xl border border-stroke/70 bg-panelSoft p-3">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-semibold text-slate-200">Optional Custom Filters (AND conditions)</p>
            <label className="inline-flex items-center gap-2 text-xs text-slate-300">
              <input type="checkbox" checked={useCustomRules} onChange={(event) => setUseCustomRules(event.target.checked)} />
              Enable custom filters
            </label>
          </div>
          <p className="mt-1 text-xs text-slate-300">Custom filters refine the selected category results. They do not replace the selected category.</p>
          <p className="mt-1 text-xs text-slate-300">Each symbol must satisfy all enabled rules in addition to the selected category.</p>
          {useCustomRules ? (
            <div className="mt-3 space-y-2">
              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={() => addPresetRule("price_vs_ema200_pct")} className="rounded-lg border border-stroke px-2 py-1 text-xs hover:text-cyan">Above EMA200</button>
                <button type="button" onClick={() => addPresetRule("distance_to_ema20_pct")} className="rounded-lg border border-stroke px-2 py-1 text-xs hover:text-cyan">Near EMA20</button>
                <button type="button" onClick={() => addPresetRule("volume_ratio_20")} className="rounded-lg border border-stroke px-2 py-1 text-xs hover:text-cyan">Volume Expansion</button>
                <button type="button" onClick={() => addPresetRule("rsi_14")} className="rounded-lg border border-stroke px-2 py-1 text-xs hover:text-cyan">Oversold RSI</button>
                <button type="button" onClick={addBuildUpPreset} className="rounded-lg border border-stroke px-2 py-1 text-xs hover:text-cyan">Build-up Basic</button>
              </div>
              {customRules.length === 0 ? <p className="text-xs text-slate-400">No custom rules yet.</p> : null}
              {customRules.map((rule, index) => {
                const fieldMeta = ruleFieldOptions.find((f) => f.value === rule.field) ?? ruleFieldOptions[0];
                return (
                  <div key={`${rule.field}-${index}`} className="grid gap-2 rounded-lg border border-stroke/60 p-2 md:grid-cols-4">
                    <select
                      value={rule.field}
                      onChange={(event) => setRuleFieldWithDefault(index, event.target.value as ScannerRuleField)}
                      className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs"
                    >
                      {ruleFieldOptions.map((opt) => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                    <select
                      value={rule.operator}
                      onChange={(event) => updateRule(index, { operator: event.target.value as ScannerRuleOperator })}
                      className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs"
                    >
                      {operatorOptions.map((opt) => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                    {fieldMeta.numeric && rule.operator !== "in" ? (
                      <input
                        type="number"
                        value={rule.value_number ?? 0}
                        onChange={(event) => updateRule(index, { value_number: Number(event.target.value), value_text: null, value_list: [] })}
                        className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs"
                      />
                    ) : (
                      <input
                        type="text"
                        value={rule.operator === "in" ? (rule.value_list ?? []).join(",") : (rule.value_text ?? "")}
                        onChange={(event) => {
                          const raw = event.target.value;
                          if (rule.operator === "in") {
                            updateRule(index, {
                              value_list: raw.split(",").map((v) => v.trim()).filter(Boolean),
                              value_text: null,
                              value_number: null,
                            });
                            return;
                          }
                          updateRule(index, { value_text: raw, value_number: null, value_list: [] });
                        }}
                        placeholder={rule.operator === "in" ? "rising,flat" : "value (ex: rising)"}
                        className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs"
                      />
                    )}
                    <button type="button" onClick={() => removeRule(index)} className="h-9 rounded-lg border border-stroke px-2 text-xs text-red">
                      Remove
                    </button>
                  </div>
                );
              })}
              <button type="button" onClick={addRule} className="rounded-lg border border-stroke px-3 py-2 text-xs text-slate-200 hover:text-cyan">
                Add Rule
              </button>
            </div>
          ) : null}
        </div>

        <div className="mt-3 rounded-xl border border-stroke/70 bg-panelSoft p-3">
          <p className="text-sm font-semibold text-slate-200">Manual Relative Range Comparison (optional)</p>
          <p className="mt-1 text-xs text-slate-300">Set a date range to compute current distance from that range low/high for each symbol.</p>
          <div className="mt-2 grid gap-2 md:grid-cols-2">
            <label className="space-y-1 text-xs text-slate-300">
              <span>Range Start</span>
              <input type="date" value={rangeStart} onChange={(event) => setRangeStart(event.target.value)} className="h-9 w-full rounded-lg border border-stroke bg-bg px-2" />
            </label>
            <label className="space-y-1 text-xs text-slate-300">
              <span>Range End</span>
              <input type="date" value={rangeEnd} onChange={(event) => setRangeEnd(event.target.value)} className="h-9 w-full rounded-lg border border-stroke bg-bg px-2" />
            </label>
          </div>
        </div>

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
            <p className="mt-1 text-xs text-slate-300">
              Custom filters: {useCustomRules && customRules.length > 0 ? `${customRules.length} active` : "off"} | Manual range: {rangeStart && rangeEnd ? `${rangeStart} to ${rangeEnd}` : "off"}
            </p>
            <p className="mt-1 text-xs text-slate-300">
              Diagnostics: eligible {result.scope.category_eligible_count}, relaxed eligible {result.scope.relaxed_eligible_count}, custom-filtered {result.scope.custom_filtered_count}, ranked {result.scope.ranked_count}, returned {result.scope.final_returned_count}.
            </p>
            {result.scope.used_relaxed_fallback ? (
              <p className="mt-1 text-xs text-amber-300">Relaxed fallback was used because strict category eligibility returned zero symbols.</p>
            ) : null}
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
                    {sortOptions.map((option) => (
                      <th key={option.key} className="px-2 py-2">
                        <button type="button" onClick={() => toggleSort(option.key)} className="inline-flex items-center gap-1 hover:text-slate-200">
                          {option.label}
                          {sortKey === option.key ? (sortDirection === "asc" ? "up" : "down") : ""}
                        </button>
                      </th>
                    ))}
                    <th className="px-2 py-2">Dynamics</th>
                    <th className="px-2 py-2">Priority</th>
                    <th className="px-2 py-2">Category</th>
                    <th className="px-2 py-2">Reason</th>
                    <th className="px-2 py-2">Trend State</th>
                    <th className="px-2 py-2">EMA200 Slope</th>
                    <th className="px-2 py-2">Rep Tests</th>
                    <th className="px-2 py-2">Range Low%</th>
                    <th className="px-2 py-2">Range High%</th>
                    <th className="px-2 py-2">TV</th>
                    <th className="px-2 py-2">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedResults.length === 0 ? (
                    <tr>
                      <td className="px-2 py-3 text-slate-400" colSpan={20}>No candidates found for selected scope.</td>
                    </tr>
                  ) : (
                    sortedResults.map((row) => (
                      <tr key={row.normalized_symbol} className="border-b border-stroke/50">
                        <td className="px-2 py-2">{row.symbol}</td>
                        <td className="px-2 py-2">{row.scanner_score.toFixed(2)}</td>
                        <td className="px-2 py-2">{row.current_score.toFixed(2)}</td>
                        <td className={`px-2 py-2 ${row.score_delta_short >= 0 ? "text-green" : "text-red"}`}>{row.score_delta_short.toFixed(2)}</td>
                        <td className={`px-2 py-2 ${row.score_delta_medium >= 0 ? "text-green" : "text-red"}`}>{row.score_delta_medium.toFixed(2)}</td>
                        <td className="px-2 py-2">{row.price_vs_ema200_pct.toFixed(2)}%</td>
                        <td className="px-2 py-2">{row.support_distance_pct.toFixed(2)}%</td>
                        <td className="px-2 py-2">{row.resistance_room_pct.toFixed(2)}%</td>
                        <td className="px-2 py-2">{row.volume_ratio_20.toFixed(2)}</td>
                        <td className="px-2 py-2">{row.resistance_test_count}</td>
                        <td className="px-2 py-2">{row.ema200_test_count}</td>
                        <td className="px-2 py-2">{row.score_dynamics_state}</td>
                        <td className="px-2 py-2 capitalize">{row.priority}</td>
                        <td className="px-2 py-2">{row.category_tag.replaceAll("_", " ")}</td>
                        <td className="max-w-[300px] px-2 py-2 text-xs text-slate-300">{row.short_reason}</td>
                        <td className="px-2 py-2">{row.trend_state}</td>
                        <td className="px-2 py-2">{row.ema200_slope_state}</td>
                        <td className="px-2 py-2">{row.repeated_test_count}</td>
                        <td className="px-2 py-2">{row.distance_from_range_low_pct !== null ? `${row.distance_from_range_low_pct.toFixed(2)}%` : "n/a"}</td>
                        <td className="px-2 py-2">{row.distance_to_range_high_pct !== null ? `${row.distance_to_range_high_pct.toFixed(2)}%` : "n/a"}</td>
                        <td className="px-2 py-2">
                          <a href={row.tradingview_url} target="_blank" rel="noreferrer" className="rounded-md border border-stroke px-2 py-1 text-xs text-slate-300 hover:text-cyan">
                            TradingView
                          </a>
                        </td>
                        <td className="px-2 py-2">
                          <button
                            type="button"
                            onClick={() =>
                              router.push(
                                `/analysis?ticker=${encodeURIComponent(row.symbol)}&market=${encodeURIComponent(result.scope.market)}&window=${encodeURIComponent(result.scope.duration)}&scanner_category=${encodeURIComponent(result.scope.category)}&scanner_score=${encodeURIComponent(row.scanner_score.toFixed(2))}&scanner_current_score=${encodeURIComponent(row.current_score.toFixed(2))}&scanner_delta_short=${encodeURIComponent(row.score_delta_short.toFixed(2))}&scanner_delta_medium=${encodeURIComponent(row.score_delta_medium.toFixed(2))}&scanner_dynamics_state=${encodeURIComponent(row.score_dynamics_state)}&scanner_reason=${encodeURIComponent(row.short_reason)}`
                              )
                            }
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
