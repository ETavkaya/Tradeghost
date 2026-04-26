"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Panel, SectionTitle, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import {
  AlertProfileSuggestionRule,
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
  Watchlist,
} from "@/lib/types";

const recommendedDurationByCategory: Record<ScannerCategory, ScannerDuration> = {
  trend_mode: "2y",
  build_up: "2y",
  momentum_mode: "1y",
  value_rebuild: "2y",
  overextended: "1y",
};

const rationaleByCategory: Record<ScannerCategory, string> = {
  trend_mode: "2Y is recommended to evaluate continuation quality with enough context.",
  build_up: "2Y is recommended to evaluate EMA200 reclaim/rebuild behavior before breakout.",
  momentum_mode: "1Y is recommended to prioritize recent expansion dynamics while preserving enough trend context.",
  value_rebuild: "2Y is recommended so rebuild and valuation-recovery structure can be observed with enough context.",
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
  value_rebuild: {
    title: "Value Rebuild / Cheap Reversal",
    desc: "Potentially cheap, washed-out names rebuilding above EMA100/EMA200 with improving structure and confluence.",
    bias: "rebuild / reversal bias",
  },
  overextended: {
    title: "Overextended",
    desc: "Stocks already stretched after strong moves; useful for caution, monitoring, and pullback planning.",
    bias: "caution / monitor bias",
  },
};

const sortOptions: Array<{ key: keyof ScannerResult; label: string }> = [
  { key: "scanner_score", label: "Score" },
  { key: "current_score", label: "Current" },
  { key: "score_delta_short", label: "D(5)" },
  { key: "score_delta_medium", label: "D(20)" },
  { key: "price_vs_ema200_pct", label: "Price vs EMA200" },
  { key: "support_distance_pct", label: "Support%" },
  { key: "resistance_room_pct", label: "Room%" },
  { key: "volume_ratio_20", label: "VolRatio20" },
  { key: "resistance_test_count", label: "Res Tests" },
  { key: "ema200_test_count", label: "EMA200 Tests" },
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
  const [selectedWatchlistId, setSelectedWatchlistId] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [result, setResult] = useState<ScannerResponse | null>(null);
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);

  const [sortKey, setSortKey] = useState<keyof ScannerResult>("scanner_score");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [useCustomRules, setUseCustomRules] = useState(false);
  const [customRules, setCustomRules] = useState<ScannerCustomRule[]>([]);
  const [rangeStart, setRangeStart] = useState("");
  const [rangeEnd, setRangeEnd] = useState("");
  const [alertPlanRow, setAlertPlanRow] = useState<ScannerResult | null>(null);
  const [alertPlanRules, setAlertPlanRules] = useState<AlertProfileSuggestionRule[]>([]);
  const [alertPlanLoading, setAlertPlanLoading] = useState(false);
  const [alertPlanNotificationEnabled, setAlertPlanNotificationEnabled] = useState(false);
  const [alertPlanNotifyEmail, setAlertPlanNotifyEmail] = useState("");
  const [userLabel, setUserLabel] = useState("local-user");

  const recommended = recommendedDurationByCategory[category];

  useEffect(() => {
    const loadWatchlists = async () => {
      try {
        const rows = await api.listWatchlists();
        setWatchlists(rows);
        if (rows.length > 0) {
          setSelectedWatchlistId((prev) => prev || rows[0].id);
        }
      } catch {
        setWatchlists([]);
      }
    };
    loadWatchlists();
  }, []);

  useEffect(() => {
    if (!notice) return;
    const id = setTimeout(() => setNotice(null), 2500);
    return () => clearTimeout(id);
  }, [notice]);

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
        ...(selectedWatchlistId && universeScope === "watchlist"
          ? {
              symbol_overrides: (watchlists.find((wl) => wl.id === selectedWatchlistId)?.items ?? [])
                .filter((it) => it.market === market)
                .map((it) => it.symbol),
            }
          : {}),
      };
      const response = await api.scanner(payload);
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scanner request failed.");
    } finally {
      setLoading(false);
    }
  };

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
    setCustomRules((prev) => [...prev, { ...ruleDefaultByField.price_vs_ema200_pct }]);
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

  const addToWatchlist = async (symbol: string) => {
    if (!selectedWatchlistId) {
      setNotice("Select a target watchlist first.");
      return;
    }
    try {
      await api.addWatchlistItem(selectedWatchlistId, symbol, market);
      setNotice(`${symbol} added to watchlist.`);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Failed to add symbol to watchlist.");
    }
  };

  const openAlertPlan = async (row: ScannerResult) => {
    try {
      setAlertPlanLoading(true);
      const response = await api.suggestAlertProfile({
        symbol: row.symbol,
        market,
        scanner_category: result?.scope.category ?? category,
        watchlist_id: selectedWatchlistId || null,
        shortlisted_by: userLabel || "local-user",
        created_by: userLabel || "local-user",
        notification_enabled: alertPlanNotificationEnabled,
        notify_email: alertPlanNotifyEmail || null,
      });
      setAlertPlanRow(row);
      setAlertPlanRules(response.rules);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Failed to load alert profile suggestions.");
    } finally {
      setAlertPlanLoading(false);
    }
  };

  const updateAlertPlanRule = (index: number, patch: Partial<AlertProfileSuggestionRule>) => {
    setAlertPlanRules((prev) => prev.map((rule, i) => (i === index ? { ...rule, ...patch } : rule)));
  };

  const applyAlertPlan = async () => {
    if (!alertPlanRow) return;
    try {
      const created = await api.applyAlertProfile({
        scope_type: "symbol",
        scope_ref: alertPlanRow.symbol,
        symbol: alertPlanRow.symbol,
        market,
        scanner_category: result?.scope.category ?? category,
        watchlist_id: selectedWatchlistId || null,
        shortlisted_by: userLabel || "local-user",
        created_by: userLabel || "local-user",
        notification_enabled: alertPlanNotificationEnabled,
        notify_email: alertPlanNotifyEmail || null,
        rules: alertPlanRules,
      });
      setNotice(`Created ${created.length} alert rules for ${alertPlanRow.symbol}.`);
      setAlertPlanRow(null);
      setAlertPlanRules([]);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Failed to apply alert profile.");
    }
  };

  return (
    <main className="space-y-4">
      <Panel>
        <SectionTitle title="Stock Scanner" subtitle="Bounded deterministic discovery layer" />
        <p className="text-sm text-slate-300">Scanner = discovery shortlist. Use Monitor tab for persistent watchlists and alert tracking.</p>
      </Panel>

      {notice ? (
        <Panel className="border-cyan/30 bg-cyan/10">
          <p className="text-sm text-cyan">{notice}</p>
        </Panel>
      ) : null}

      {alertPlanRow ? (
        <Panel>
          <SectionTitle title={`Alert Plan: ${alertPlanRow.symbol}`} subtitle="Category-aware suggested rules. Select, edit, and apply." />
          <div className="grid gap-2 md:grid-cols-3">
            <label className="space-y-1 text-xs text-slate-300">
              <span>User Label</span>
              <input value={userLabel} onChange={(event) => setUserLabel(event.target.value)} className="h-9 w-full rounded-lg border border-stroke bg-bg px-2" />
            </label>
            <label className="space-y-1 text-xs text-slate-300">
              <span>Notify Email (optional)</span>
              <input value={alertPlanNotifyEmail} onChange={(event) => setAlertPlanNotifyEmail(event.target.value)} placeholder="name@example.com" className="h-9 w-full rounded-lg border border-stroke bg-bg px-2" />
            </label>
            <label className="mt-6 inline-flex items-center gap-2 text-xs text-slate-300">
              <input type="checkbox" checked={alertPlanNotificationEnabled} onChange={(event) => setAlertPlanNotificationEnabled(event.target.checked)} />
              Enable notification-ready status
            </label>
          </div>
          <div className="mt-3 space-y-2">
            {alertPlanRules.map((rule, index) => (
              <div key={rule.temp_id} className="grid gap-2 rounded-lg border border-stroke/70 bg-panelSoft p-2 md:grid-cols-[auto_1fr_220px_120px_120px]">
                <label className="inline-flex items-center gap-2 text-xs">
                  <input type="checkbox" checked={rule.selected} onChange={(event) => updateAlertPlanRule(index, { selected: event.target.checked })} />
                  use
                </label>
                <div>
                  <p className="text-sm text-slate-100">{rule.name}</p>
                  <p className="text-xs text-slate-400">{rule.rationale}</p>
                </div>
                <input value={rule.parameters ? JSON.stringify(rule.parameters) : "{}"} onChange={(event) => {
                  try {
                    const parsed = JSON.parse(event.target.value);
                    updateAlertPlanRule(index, { parameters: parsed });
                  } catch {
                    // keep existing value until valid json
                  }
                }} className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs" />
                <select value={rule.severity} onChange={(event) => updateAlertPlanRule(index, { severity: event.target.value as AlertProfileSuggestionRule["severity"] })} className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs">
                  <option value="info">info</option>
                  <option value="watch">watch</option>
                  <option value="important">important</option>
                  <option value="critical">critical</option>
                </select>
                <input type="number" min={0} max={1440} value={rule.cooldown_minutes} onChange={(event) => updateAlertPlanRule(index, { cooldown_minutes: Number(event.target.value) })} className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs" />
              </div>
            ))}
          </div>
          <div className="mt-3 flex gap-2">
            <button type="button" onClick={() => setAlertPlanRules((prev) => prev.map((row) => ({ ...row, selected: true })))} className="rounded-lg border border-stroke px-3 py-2 text-xs hover:text-cyan">Select All</button>
            <button type="button" onClick={applyAlertPlan} className="rounded-lg border border-stroke px-3 py-2 text-xs hover:text-cyan">Apply Selected</button>
            <button type="button" onClick={() => { setAlertPlanRow(null); setAlertPlanRules([]); }} className="rounded-lg border border-stroke px-3 py-2 text-xs">Close</button>
          </div>
        </Panel>
      ) : null}

      <Panel>
        <SectionTitle title="Scanner Inputs" subtitle="Single-pass bounded scan across selected scope" />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
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
              <option value="value_rebuild">Value Rebuild</option>
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
          <label className="space-y-1 text-sm">
            <span className="text-xs text-slate-400">Target Watchlist</span>
            <select value={selectedWatchlistId} onChange={(event) => setSelectedWatchlistId(event.target.value)} className="h-10 w-full rounded-lg border border-stroke bg-bg px-3">
              <option value="">Select watchlist</option>
              {watchlists.map((wl) => (
                <option key={wl.id} value={wl.id}>{wl.name}</option>
              ))}
            </select>
          </label>
        </div>

        <div className="mt-3 rounded-xl border border-stroke/70 bg-panelSoft p-3 text-xs text-slate-300">
          Selected duration: {duration.toUpperCase()} | Recommended duration for {categoryDefinition[category].title}: {recommended.toUpperCase()}. Reason: {rationaleByCategory[category]}
        </div>
        <label className="mt-3 inline-flex items-center gap-2 text-xs text-slate-300">
          <input type="checkbox" checked={keepManualDuration} onChange={(event) => setKeepManualDuration(event.target.checked)} />
          Keep manual duration when category changes
        </label>

        <div className="mt-4 rounded-xl border border-stroke/70 bg-panelSoft p-3">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-semibold text-slate-200">Optional Custom Filters (AND conditions)</p>
            <label className="inline-flex items-center gap-2 text-xs text-slate-300">
              <input type="checkbox" checked={useCustomRules} onChange={(event) => setUseCustomRules(event.target.checked)} />
              Enable custom filters
            </label>
          </div>
          {useCustomRules ? (
            <div className="mt-3 space-y-2">
              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={() => addPresetRule("price_vs_ema200_pct")} className="rounded-lg border border-stroke px-2 py-1 text-xs hover:text-cyan">Above EMA200</button>
                <button type="button" onClick={() => addPresetRule("distance_to_ema20_pct")} className="rounded-lg border border-stroke px-2 py-1 text-xs hover:text-cyan">Near EMA20</button>
                <button type="button" onClick={() => addPresetRule("volume_ratio_20")} className="rounded-lg border border-stroke px-2 py-1 text-xs hover:text-cyan">Volume Expansion</button>
                <button type="button" onClick={() => addPresetRule("rsi_14")} className="rounded-lg border border-stroke px-2 py-1 text-xs hover:text-cyan">Oversold RSI</button>
                <button type="button" onClick={addBuildUpPreset} className="rounded-lg border border-stroke px-2 py-1 text-xs hover:text-cyan">Build-up Basic</button>
              </div>
              {customRules.map((rule, index) => {
                const fieldMeta = ruleFieldOptions.find((f) => f.value === rule.field) ?? ruleFieldOptions[0];
                return (
                  <div key={`${rule.field}-${index}`} className="grid gap-2 rounded-lg border border-stroke/60 p-2 md:grid-cols-4">
                    <select value={rule.field} onChange={(event) => setRuleFieldWithDefault(index, event.target.value as ScannerRuleField)} className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs">
                      {ruleFieldOptions.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                    </select>
                    <select value={rule.operator} onChange={(event) => updateRule(index, { operator: event.target.value as ScannerRuleOperator })} className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs">
                      {operatorOptions.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                    </select>
                    {fieldMeta.numeric && rule.operator !== "in" ? (
                      <input type="number" value={rule.value_number ?? 0} onChange={(event) => updateRule(index, { value_number: Number(event.target.value), value_text: null, value_list: [] })} className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs" />
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
                        placeholder={rule.operator === "in" ? "rising,flat" : "value"}
                        className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs"
                      />
                    )}
                    <button type="button" onClick={() => removeRule(index)} className="h-9 rounded-lg border border-stroke px-2 text-xs text-red">Remove</button>
                  </div>
                );
              })}
              <button type="button" onClick={addRule} className="rounded-lg border border-stroke px-3 py-2 text-xs text-slate-200 hover:text-cyan">Add Rule</button>
            </div>
          ) : null}
        </div>

        <button type="button" onClick={runScan} disabled={loading} className="mt-4 h-11 rounded-lg bg-cyan px-6 text-sm font-semibold text-bg transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50">
          {loading ? "Scanning..." : "Run Scanner"}
        </button>
        <button type="button" onClick={() => router.push("/monitor")} className="ml-2 mt-4 h-11 rounded-lg border border-stroke px-4 text-sm text-slate-300 hover:text-cyan">
          Open Monitor Workspace
        </button>
      </Panel>

      <Panel>
        <SectionTitle title="Category Definitions" subtitle="Scanner is candidate discovery, not direct execution" />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
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
            <p className="text-xs text-slate-300">Diagnostics: eligible {result.scope.category_eligible_count}, relaxed eligible {result.scope.relaxed_eligible_count}, custom-filtered {result.scope.custom_filtered_count}, ranked {result.scope.ranked_count}, returned {result.scope.final_returned_count}.</p>
          </Panel>

          <Panel>
            <SectionTitle title="Scanner Results" subtitle="Ranked shortlist for next analysis step" />
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-stroke text-left text-slate-400">
                    <th className="sticky left-0 z-20 bg-panel px-2 py-2 shadow-[8px_0_12px_-12px_rgba(0,0,0,0.6)]">Symbol</th>
                    {sortOptions.map((option) => (
                      <th key={option.key} className="px-2 py-2">
                        <button type="button" onClick={() => toggleSort(option.key)} className="inline-flex items-center gap-1 hover:text-slate-200">
                          {option.label}
                          {sortKey === option.key ? (sortDirection === "asc" ? "up" : "down") : ""}
                        </button>
                      </th>
                    ))}
                    <th className="px-2 py-2">Dynamics</th>
                    <th className="px-2 py-2">Momentum Fit</th>
                    <th className="px-2 py-2">Ext State</th>
                    <th className="px-2 py-2">Mom Candidate</th>
                    <th className="px-2 py-2">Opportunity</th>
                    <th className="px-2 py-2">Fib Confluence</th>
                    <th className="px-2 py-2">Fib Room%</th>
                    <th className="px-2 py-2">P/B</th>
                    <th className="px-2 py-2">P/E</th>
                    <th className="px-2 py-2">Priority</th>
                    <th className="px-2 py-2">Category</th>
                    <th className="px-2 py-2">Reason</th>
                    <th className="px-2 py-2">Trend State</th>
                    <th className="px-2 py-2">EMA200 Slope</th>
                    <th className="px-2 py-2">Rep Tests</th>
                    <th className="px-2 py-2 whitespace-nowrap">TV</th>
                    <th className="px-2 py-2 whitespace-nowrap">Open</th>
                    <th className="px-2 py-2 whitespace-nowrap">Track</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedResults.length === 0 ? (
                    <tr>
                      <td className="sticky left-0 z-10 bg-panel px-2 py-3 text-slate-400 shadow-[8px_0_12px_-12px_rgba(0,0,0,0.6)]">No candidates found for selected scope.</td>
                      <td className="px-2 py-3 text-slate-400" colSpan={26}></td>
                    </tr>
                  ) : (
                    sortedResults.map((row) => (
                      <tr key={row.normalized_symbol} className="border-b border-stroke/50">
                        <td className="sticky left-0 z-10 bg-panel px-2 py-2 shadow-[8px_0_12px_-12px_rgba(0,0,0,0.6)]">
                          <div className="font-medium text-slate-100">{row.symbol}</div>
                          <div className="text-[11px] text-slate-400">Score {row.scanner_score.toFixed(1)} | {row.priority}</div>
                        </td>
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
                        <td className="px-2 py-2">{row.momentum_fit_score.toFixed(2)}</td>
                        <td className="px-2 py-2">{row.extension_state.replaceAll("_", " ")}</td>
                        <td className="px-2 py-2">{row.momentum_continuation_candidate ? "yes" : "no"}</td>
                        <td className="px-2 py-2">{row.opportunity_type.replaceAll("_", " ")}</td>
                        <td className="px-2 py-2">{row.fib_ema_confluence_score?.toFixed(1) ?? "n/a"}</td>
                        <td className="px-2 py-2">{row.fib_target_room_pct?.toFixed(2) ?? "n/a"}</td>
                        <td className="px-2 py-2">{row.price_to_book?.toFixed(2) ?? "n/a"}</td>
                        <td className="px-2 py-2">{row.price_to_earnings?.toFixed(2) ?? "n/a"}</td>
                        <td className="px-2 py-2 capitalize">{row.priority}</td>
                        <td className="px-2 py-2">{row.category_tag.replaceAll("_", " ")}</td>
                        <td className="max-w-[260px] px-2 py-2 text-xs text-slate-300">{row.short_reason}</td>
                        <td className="px-2 py-2">{row.trend_state}</td>
                        <td className="px-2 py-2">{row.ema200_slope_state}</td>
                        <td className="px-2 py-2">{row.repeated_test_count}</td>
                        <td className="px-2 py-2 whitespace-nowrap">
                          <a href={row.tradingview_url} target="_blank" rel="noreferrer" className="rounded-md border border-stroke px-2 py-1 text-xs text-slate-300 hover:text-cyan">TradingView</a>
                        </td>
                        <td className="px-2 py-2 whitespace-nowrap">
                          <button
                            type="button"
                            onClick={() =>
                              router.push(
                                `/analysis?ticker=${encodeURIComponent(row.symbol)}&market=${encodeURIComponent(result.scope.market)}&window=${encodeURIComponent(result.scope.duration)}&scanner_category=${encodeURIComponent(result.scope.category)}&scanner_score=${encodeURIComponent(row.scanner_score.toFixed(2))}&scanner_current_score=${encodeURIComponent(row.current_score.toFixed(2))}&scanner_delta_short=${encodeURIComponent(row.score_delta_short.toFixed(2))}&scanner_delta_medium=${encodeURIComponent(row.score_delta_medium.toFixed(2))}&scanner_dynamics_state=${encodeURIComponent(row.score_dynamics_state)}&scanner_reason=${encodeURIComponent(row.short_reason)}&scanner_momentum_fit=${encodeURIComponent(row.momentum_fit_score.toFixed(2))}&scanner_extension_state=${encodeURIComponent(row.extension_state)}&scanner_momentum_candidate=${encodeURIComponent(String(row.momentum_continuation_candidate))}`
                              )
                            }
                            className="rounded-md border border-stroke px-2 py-1 text-xs text-slate-300 hover:text-cyan"
                          >
                            Open Analysis
                          </button>
                        </td>
                        <td className="px-2 py-2 whitespace-nowrap">
                          <div className="flex gap-1">
                            <button type="button" onClick={() => addToWatchlist(row.symbol)} className="rounded-md border border-stroke px-2 py-1 text-xs text-slate-300 hover:text-cyan">Add WL</button>
                            <button type="button" onClick={() => openAlertPlan(row)} disabled={alertPlanLoading} className="rounded-md border border-stroke px-2 py-1 text-xs text-slate-300 hover:text-cyan disabled:opacity-60">{alertPlanLoading ? "Loading..." : "Alert Plan"}</button>
                          </div>
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
