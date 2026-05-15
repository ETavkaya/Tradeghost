
"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Panel, SectionTitle, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import {
  AlertEvent,
  AlertEventStatus,
  AlertRule,
  AlertRuleType,
  AlertSeverity,
  MarketCode,
  MonitoringRunSummary,
  MonitoringSchedule,
  Watchlist,
} from "@/lib/types";

type MonitorView = "watchlists" | "rules" | "logs";
type PollMode = "auto" | "manual";
type PollInterval = "1m" | "5m" | "hourly" | "daily";

type AlertDraft = {
  symbol: string;
  market: MarketCode;
  preset: AlertRuleType;
  value: string;
};

const intervalToMs: Record<PollInterval, number> = {
  "1m": 60_000,
  "5m": 300_000,
  hourly: 3_600_000,
  daily: 86_400_000,
};

const presetDefaults: Record<AlertRuleType, { label: string; valueKey: string | null; defaultValue: string; severity: AlertSeverity }> = {
  near_ema20: { label: "Price near EMA20", valueKey: "threshold_pct", defaultValue: "3", severity: "watch" },
  near_ema50: { label: "Price near EMA50", valueKey: "threshold_pct", defaultValue: "3", severity: "watch" },
  near_ema100: { label: "Price near EMA100", valueKey: "threshold_pct", defaultValue: "5", severity: "watch" },
  near_ema200: { label: "Price near EMA200", valueKey: "threshold_pct", defaultValue: "5", severity: "important" },
  cross_above_ema100: { label: "Cross above EMA100", valueKey: null, defaultValue: "", severity: "important" },
  cross_above_ema200: { label: "Cross above EMA200", valueKey: null, defaultValue: "", severity: "important" },
  cross_below_ema100: { label: "Cross below EMA100", valueKey: null, defaultValue: "", severity: "watch" },
  cross_below_ema200: { label: "Cross below EMA200", valueKey: null, defaultValue: "", severity: "critical" },
  price_gte: { label: "Price >= X", valueKey: "value", defaultValue: "0", severity: "watch" },
  price_lte: { label: "Price <= X", valueKey: "value", defaultValue: "0", severity: "watch" },
  low_lte: { label: "Daily Low <= X", valueKey: "value", defaultValue: "0", severity: "important" },
  high_gte: { label: "Daily High >= X", valueKey: "value", defaultValue: "0", severity: "important" },
  near_weekly_ema100: { label: "Near Weekly EMA100", valueKey: "threshold_pct", defaultValue: "4", severity: "watch" },
  near_weekly_ema200: { label: "Near Weekly EMA200", valueKey: "threshold_pct", defaultValue: "5", severity: "watch" },
  cross_above_weekly_ema100: { label: "Cross Above Weekly EMA100", valueKey: null, defaultValue: "", severity: "important" },
  cross_above_weekly_ema200: { label: "Cross Above Weekly EMA200", valueKey: null, defaultValue: "", severity: "important" },
  trend_state_is: { label: "Trend state equals", valueKey: "state", defaultValue: "bullish_trend", severity: "important" },
  dynamics_state_is: { label: "Score dynamics equals", valueKey: "state", defaultValue: "accelerating", severity: "important" },
  scanner_top_n: { label: "Scanner top N", valueKey: "top_n", defaultValue: "20", severity: "watch" },
  reclaim_ema200: { label: "Reclaim EMA200", valueKey: "max_bars_since_reclaim", defaultValue: "5", severity: "important" },
  resistance_test_count_gte: { label: "Resistance tests >= X", valueKey: "count", defaultValue: "3", severity: "watch" },
  volume_ratio_20_gte: { label: "Volume ratio 20 >= X", valueKey: "value", defaultValue: "1.5", severity: "watch" },
  rsi14_lte: { label: "RSI14 <= X", valueKey: "value", defaultValue: "30", severity: "watch" },
  rsi14_gte: { label: "RSI14 >= X", valueKey: "value", defaultValue: "70", severity: "watch" },
  new_breakout_high: { label: "New breakout high", valueKey: "lookback_bars", defaultValue: "55", severity: "important" },
  blowoff_extension_warning: { label: "Blowoff extension warning", valueKey: null, defaultValue: "", severity: "critical" },
  fib_ema_confluence_reached: { label: "Fib/EMA confluence reached", valueKey: "max_distance_pct", defaultValue: "1.5", severity: "important" },
};

const US_EXCHANGE_FALLBACK: Record<string, string> = {
  NVDA: "NASDAQ",
  AMD: "NASDAQ",
  AAPL: "NASDAQ",
  ORCL: "NYSE",
  KO: "NYSE",
  GS: "NYSE",
};

function resolveTradingViewSymbol(symbol: string, market: MarketCode, exchange?: string | null): string {
  const normalized = (symbol ?? "").trim().toUpperCase();
  if (normalized.includes(":")) return normalized;
  if (market === "bist") return `BIST:${normalized}`;
  const ex = (exchange ?? "").trim().toUpperCase();
  if (ex) return `${ex}:${normalized}`;
  return `${US_EXCHANGE_FALLBACK[normalized] ?? "NASDAQ"}:${normalized}`;
}

function tvLink(symbol: string, market: MarketCode, exchange?: string | null): string {
  const tvSymbol = resolveTradingViewSymbol(symbol, market, exchange);
  return `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tvSymbol)}`;
}

function pct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "-";
  return `${v.toFixed(2)}%`;
}

function num(v: number | null | undefined): string {
  if (v === null || v === undefined) return "-";
  return v.toFixed(2);
}

function ruleCondition(rule: AlertRule): string {
  const p = rule.parameters ?? {};
  if (rule.rule_type === "near_ema20") return `Near EMA20 <= ${p.threshold_pct ?? "-"}%`;
  if (rule.rule_type === "near_ema50") return `Near EMA50 <= ${p.threshold_pct ?? "-"}%`;
  if (rule.rule_type === "near_ema100") return `Near EMA100 <= ${p.threshold_pct ?? "-"}%`;
  if (rule.rule_type === "near_ema200") return `Near EMA200 <= ${p.threshold_pct ?? "-"}%`;
  if (rule.rule_type === "cross_above_ema100") return "Cross above EMA100";
  if (rule.rule_type === "cross_above_ema200") return "Cross above EMA200";
  if (rule.rule_type === "cross_below_ema100") return "Cross below EMA100";
  if (rule.rule_type === "cross_below_ema200") return "Cross below EMA200";
  if (rule.rule_type === "low_lte") return `Daily low <= ${p.value ?? "-"}`;
  if (rule.rule_type === "high_gte") return `Daily high >= ${p.value ?? "-"}`;
  if (rule.rule_type === "near_weekly_ema100") return `Near weekly EMA100 <= ${p.threshold_pct ?? "-"}%`;
  if (rule.rule_type === "near_weekly_ema200") return `Near weekly EMA200 <= ${p.threshold_pct ?? "-"}%`;
  if (rule.rule_type === "cross_above_weekly_ema100") return "Cross above weekly EMA100";
  if (rule.rule_type === "cross_above_weekly_ema200") return "Cross above weekly EMA200";
  if (rule.rule_type === "dynamics_state_is") return `Dynamics = ${p.state ?? "-"}`;
  if (rule.rule_type === "rsi14_lte") return `RSI14 <= ${p.value ?? "-"}`;
  if (rule.rule_type === "rsi14_gte") return `RSI14 >= ${p.value ?? "-"}`;
  if (rule.rule_type === "volume_ratio_20_gte") return `Volume ratio >= ${p.value ?? "-"}`;
  if (rule.rule_type === "resistance_test_count_gte") return `Resistance tests >= ${p.count ?? p.value ?? "-"}`;
  if (rule.rule_type === "new_breakout_high") return `New breakout high (${p.lookback_bars ?? "-"} bars)`;
  if (rule.rule_type === "blowoff_extension_warning") return "Blowoff extension warning";
  if (rule.rule_type === "fib_ema_confluence_reached") return `Fib/EMA confluence <= ${p.max_distance_pct ?? "-"}%`;
  return rule.rule_type;
}
export default function MonitorPage() {
  const router = useRouter();
  const [view, setView] = useState<MonitorView>("watchlists");
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [selectedWatchlistId, setSelectedWatchlistId] = useState("");
  const [newWatchlistName, setNewWatchlistName] = useState("");
  const [renameWatchlistName, setRenameWatchlistName] = useState("");
  const [alertRules, setAlertRules] = useState<AlertRule[]>([]);
  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const [schedules, setSchedules] = useState<MonitoringSchedule[]>([]);
  const [lastRunSummary, setLastRunSummary] = useState<MonitoringRunSummary | null>(null);

  const [eventSeverityFilter, setEventSeverityFilter] = useState("");
  const [eventStatusFilter, setEventStatusFilter] = useState("");
  const [eventWatchlistFilter, setEventWatchlistFilter] = useState("");
  const [eventSymbolFilter, setEventSymbolFilter] = useState("");
  const [eventDateFilter, setEventDateFilter] = useState("");
  const [ruleSymbolFilter, setRuleSymbolFilter] = useState("");
  const [ruleWatchlistFilter, setRuleWatchlistFilter] = useState("");
  const [ruleSeverityFilter, setRuleSeverityFilter] = useState("");
  const [ruleEnabledFilter, setRuleEnabledFilter] = useState<"all" | "enabled" | "disabled">("all");

  const [pollMode, setPollMode] = useState<PollMode>("auto");
  const [pollInterval, setPollInterval] = useState<PollInterval>("5m");
  const [alertDraft, setAlertDraft] = useState<AlertDraft | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [manualSymbol, setManualSymbol] = useState("");
  const [manualMarket, setManualMarket] = useState<MarketCode>("us");

  const selectedWatchlist = useMemo(() => watchlists.find((w) => w.id === selectedWatchlistId) ?? null, [watchlists, selectedWatchlistId]);
  const enabledRules = useMemo(() => alertRules.filter((r) => r.is_enabled), [alertRules]);
  const filteredAlerts = useMemo(() => {
    return alerts.filter((event) => {
      if (eventWatchlistFilter && event.watchlist_id !== eventWatchlistFilter) return false;
      if (eventSymbolFilter && event.symbol.toUpperCase() !== eventSymbolFilter.toUpperCase()) return false;
      if (eventDateFilter && !event.timestamp.startsWith(eventDateFilter)) return false;
      return true;
    });
  }, [alerts, eventWatchlistFilter, eventSymbolFilter, eventDateFilter]);
  const latestAlertBySymbol = useMemo(() => {
    const map = new Map<string, AlertEvent>();
    for (const event of alerts) {
      const key = `${event.symbol}|${event.market}`;
      const current = map.get(key);
      if (!current || +new Date(event.timestamp) > +new Date(current.timestamp)) {
        map.set(key, event);
      }
    }
    return map;
  }, [alerts]);

  const latestScheduleRun = useMemo(() => {
    const times = schedules.map((s) => s.last_run_at).filter(Boolean) as string[];
    return times.length ? times.sort((a, b) => +new Date(b) - +new Date(a))[0] : null;
  }, [schedules]);
  const nextScheduledRun = useMemo(() => {
    const times = schedules.filter((s) => s.is_enabled && s.next_run_at).map((s) => s.next_run_at as string);
    return times.length ? times.sort((a, b) => +new Date(a) - +new Date(b))[0] : null;
  }, [schedules]);
  const lastRunAt = lastRunSummary?.finished_at ?? latestScheduleRun;

  const refresh = async () => {
    const [watchlistRows, eventRows, ruleRows, scheduleRows] = await Promise.all([
      api.listWatchlists(),
      api.listAlertEvents(eventStatusFilter || undefined, eventSeverityFilter || undefined, undefined),
      api.listAlertRules({
        symbol: ruleSymbolFilter || undefined,
        watchlist_id: ruleWatchlistFilter || undefined,
        severity: ruleSeverityFilter || undefined,
        enabled: ruleEnabledFilter === "all" ? undefined : ruleEnabledFilter === "enabled",
      }),
      api.listMonitoringSchedules(),
    ]);
    setWatchlists(watchlistRows);
    setAlerts(eventRows);
    setAlertRules(ruleRows);
    setSchedules(scheduleRows);
    if (watchlistRows.length > 0 && !watchlistRows.some((w) => w.id === selectedWatchlistId)) {
      setSelectedWatchlistId(watchlistRows[0].id);
    }
    if (scheduleRows[0]) {
      setPollMode((scheduleRows[0].mode as PollMode) || "auto");
      setPollInterval((scheduleRows[0].interval as PollInterval) || "5m");
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventSeverityFilter, eventStatusFilter, ruleSymbolFilter, ruleWatchlistFilter, ruleSeverityFilter, ruleEnabledFilter]);

  useEffect(() => {
    if (!notice) return;
    const id = setTimeout(() => setNotice(null), 2400);
    return () => clearTimeout(id);
  }, [notice]);

  useEffect(() => {
    if (pollMode !== "auto") return;
    const id = setInterval(async () => {
      try {
        const summary = await api.runMonitoring({
          watchlist_id: selectedWatchlistId || null,
          symbols: [],
          max_runtime_seconds: 30,
          max_symbols_per_batch: 200,
        });
        setLastRunSummary(summary);
        await refresh();
      } catch {
        // quiet retry on next interval
      }
    }, intervalToMs[pollInterval]);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pollMode, pollInterval, selectedWatchlistId]);

  const applyPollingConfig = async () => {
    const first = schedules[0];
    const payload = {
      name: first?.name ?? "Default Auto Polling",
      market: first?.market ?? "us",
      mode: pollMode,
      interval: pollInterval,
      frequency: pollInterval,
      watchlist_id: first?.watchlist_id ?? null,
      symbols: first?.symbols ?? [],
      category: first?.category ?? "trend_mode",
      duration: first?.duration ?? "1y",
      max_results: first?.max_results ?? 50,
      is_enabled: pollMode === "auto",
    };
    if (first) await api.updateMonitoringSchedule(first.id, payload);
    else await api.createMonitoringSchedule(payload);
    setNotice(`Polling set to ${pollMode} (${pollInterval}).`);
    await refresh();
  };

  const runMonitoring = async () => {
    const summary = await api.runMonitoring({ watchlist_id: selectedWatchlistId || null, symbols: [], max_runtime_seconds: 30, max_symbols_per_batch: 200 });
    setLastRunSummary(summary);
    if (selectedWatchlistId) await api.refreshWatchlistMetrics(selectedWatchlistId);
    setNotice(`Monitoring run completed: ${summary.events_created} events created.`);
    await refresh();
  };

  const refreshMetrics = async () => {
    await runMonitoring();
    setNotice("Monitoring cycle completed and metrics refreshed.");
  };

  const createWatchlist = async () => {
    if (!newWatchlistName.trim()) return;
    await api.createWatchlist(newWatchlistName.trim());
    setNewWatchlistName("");
    await refresh();
  };
  const renameWatchlist = async () => {
    if (!selectedWatchlistId || !renameWatchlistName.trim()) return;
    await api.renameWatchlist(selectedWatchlistId, renameWatchlistName.trim());
    setRenameWatchlistName("");
    await refresh();
  };
  const deleteWatchlist = async () => {
    if (!selectedWatchlistId) return;
    await api.deleteWatchlist(selectedWatchlistId);
    setSelectedWatchlistId("");
    await refresh();
  };
  const removeSymbol = async (symbol: string, market: MarketCode) => {
    if (!selectedWatchlistId) return;
    await api.removeWatchlistItem(selectedWatchlistId, symbol, market);
    await refresh();
  };
  const addManualSymbol = async () => {
    if (!selectedWatchlistId || !manualSymbol.trim()) return;
    await api.addWatchlistItem(selectedWatchlistId, manualSymbol.trim().toUpperCase(), manualMarket);
    setManualSymbol("");
    setNotice("Symbol added to watchlist.");
    await refresh();
  };

  const openPreset = (symbol: string, market: MarketCode) => {
    const d = presetDefaults.near_ema50;
    setAlertDraft({ symbol, market, preset: "near_ema50", value: d.defaultValue });
  };
  const changePreset = (preset: AlertRuleType) => {
    if (!alertDraft) return;
    setAlertDraft({ ...alertDraft, preset, value: presetDefaults[preset].defaultValue });
  };
  const createPresetAlert = async () => {
    if (!alertDraft) return;
    const preset = presetDefaults[alertDraft.preset];
    const parameters: Record<string, unknown> = {};
    if (preset.valueKey) parameters[preset.valueKey] = Number.isNaN(Number(alertDraft.value)) ? alertDraft.value : Number(alertDraft.value);
    if (alertDraft.preset === "dynamics_state_is") parameters.category = "momentum_mode";
    await api.createAlertRule({
      scope_type: "symbol",
      scope_ref: alertDraft.symbol,
      market: alertDraft.market,
      symbol: alertDraft.symbol,
      name: `${alertDraft.symbol} ${preset.label}`,
      rule_type: alertDraft.preset,
      parameters,
      timeframe: "daily",
      severity: preset.severity,
      color: preset.severity === "critical" ? "red" : preset.severity === "important" ? "orange" : "yellow",
      is_enabled: true,
      notification_enabled: false,
      notify_email: null,
      scanner_category: null,
      watchlist_id: selectedWatchlistId || null,
      shortlisted_by: "local-user",
      created_by: "local-user",
      cooldown_minutes: 60,
    });
    setAlertDraft(null);
    setNotice("Alert rule created.");
    await refresh();
  };

  const toggleRule = async (rule: AlertRule) => {
    await api.updateAlertRule(rule.id, { is_enabled: !rule.is_enabled });
    await refresh();
  };
  const deleteRule = async (ruleId: string) => {
    await api.deleteAlertRule(ruleId);
    await refresh();
  };
  const setEventStatus = async (id: string, status: AlertEventStatus) => {
    await api.updateAlertEventStatus(id, status);
    await refresh();
  };

  return (
    <main className="space-y-4">
      <Panel>
        <SectionTitle title="Monitor Workspace" subtitle="Watchlists = tracked symbols and performance | Alert Rules = conditions being watched | Alert Logs = things that triggered" />
      </Panel>
      {notice ? <Panel className="border-cyan/30 bg-cyan/10"><p className="text-sm text-cyan">{notice}</p></Panel> : null}

      {alertDraft ? (
        <Panel>
          <SectionTitle title="Create Alert Preset" subtitle={`${alertDraft.symbol} (${alertDraft.market.toUpperCase()})`} />
          <div className="grid gap-2 md:grid-cols-[1fr_220px_auto_auto]">
            <select value={alertDraft.preset} onChange={(e) => changePreset(e.target.value as AlertRuleType)} className="h-10 rounded-lg border border-stroke bg-bg px-3 text-sm">
              {(Object.keys(presetDefaults) as AlertRuleType[]).map((k) => <option key={k} value={k}>{presetDefaults[k].label}</option>)}
            </select>
            <input value={alertDraft.value} onChange={(e) => setAlertDraft((prev) => prev ? { ...prev, value: e.target.value } : prev)} className="h-10 rounded-lg border border-stroke bg-bg px-3 text-sm" placeholder="value/state" />
            <button type="button" onClick={createPresetAlert} className="rounded-lg border border-stroke px-3 py-2 text-xs hover:text-cyan">Create</button>
            <button type="button" onClick={() => setAlertDraft(null)} className="rounded-lg border border-stroke px-3 py-2 text-xs">Cancel</button>
          </div>
        </Panel>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
        <StatCard label="Polling Mode" value={pollMode} />
        <StatCard label="Interval" value={pollInterval} />
        <StatCard label="Last Run" value={lastRunAt ? new Date(lastRunAt).toLocaleString() : "-"} />
        <StatCard label="Next Run" value={nextScheduledRun ? new Date(nextScheduledRun).toLocaleString() : "-"} />
        <StatCard label="Symbols Checked" value={lastRunSummary ? String(lastRunSummary.evaluated_symbols) : "-"} />
        <StatCard label="Rules Checked" value={lastRunSummary ? String(lastRunSummary.processed_rules) : String(enabledRules.length)} />
      </div>

      <Panel>
        <div className="grid gap-2 md:grid-cols-[150px_150px_auto_auto_auto]">
          <select value={pollMode} onChange={(e) => setPollMode(e.target.value as PollMode)} className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs"><option value="auto">auto</option><option value="manual">manual</option></select>
          <select value={pollInterval} onChange={(e) => setPollInterval(e.target.value as PollInterval)} disabled={pollMode === "manual"} className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs"><option value="1m">1 min</option><option value="5m">5 min</option><option value="hourly">hourly</option><option value="daily">daily</option></select>
          <button type="button" onClick={applyPollingConfig} className="rounded-lg border border-stroke px-3 py-2 text-xs hover:text-cyan">Apply Polling</button>
          <button type="button" onClick={runMonitoring} className="rounded-lg border border-stroke px-3 py-2 text-xs hover:text-cyan">Run Monitoring</button>
          <button type="button" onClick={refreshMetrics} className="rounded-lg border border-stroke px-3 py-2 text-xs hover:text-cyan">Refresh Metrics</button>
        </div>
        <p className="mt-2 text-xs text-slate-400">Bounded safeguards: explicit interval, max symbols per batch, runtime timeout, and partial run notes.</p>
      </Panel>

      <div className="relative">
        <aside className="mb-4 xl:fixed xl:left-4 xl:top-44 xl:w-[300px] xl:z-20">
          <Panel className="h-fit max-h-[calc(100vh-12rem)] overflow-auto">
            <SectionTitle title="Monitor Navigation" subtitle="Persistent tracking workspace" />
            <div className="grid gap-2">
              <button type="button" onClick={() => setView("watchlists")} className={`rounded-md border px-3 py-2 text-left text-xs ${view === "watchlists" ? "border-cyan text-cyan" : "border-stroke text-slate-300"}`}>Watchlists ({watchlists.length})</button>
              <button type="button" onClick={() => setView("rules")} className={`rounded-md border px-3 py-2 text-left text-xs ${view === "rules" ? "border-cyan text-cyan" : "border-stroke text-slate-300"}`}>Alert Rules ({enabledRules.length} active)</button>
              <button type="button" onClick={() => setView("logs")} className={`rounded-md border px-3 py-2 text-left text-xs ${view === "logs" ? "border-cyan text-cyan" : "border-stroke text-slate-300"}`}>Alert Logs ({alerts.length})</button>
            </div>
            <div className="mt-3 space-y-2 rounded-lg border border-stroke/70 p-2">
              {watchlists.map((wl) => <button key={wl.id} type="button" onClick={() => { setSelectedWatchlistId(wl.id); setView("watchlists"); }} className={`w-full rounded-md border px-2 py-2 text-left text-xs ${selectedWatchlistId === wl.id ? "border-cyan text-cyan" : "border-stroke text-slate-300"}`}>{wl.name} ({wl.items.length})</button>)}
            </div>
          </Panel>
        </aside>

        <div className="min-w-0 space-y-4">
        <Panel className="min-w-0">
          {view === "watchlists" ? (
            <>
              <SectionTitle title="Watchlist Detail" subtitle="Tracked symbols and monitoring metrics" />
              <div className="grid gap-2 md:grid-cols-[1fr_auto_auto]">
                <input value={newWatchlistName} onChange={(e) => setNewWatchlistName(e.target.value)} placeholder="Create watchlist" className="h-9 rounded-lg border border-stroke bg-bg px-2 text-sm" />
                <button type="button" onClick={createWatchlist} className="rounded-lg border border-stroke px-3 py-2 text-xs">Create</button>
                <button type="button" onClick={deleteWatchlist} className="rounded-lg border border-red/40 px-3 py-2 text-xs text-red">Delete</button>
              </div>
              <div className="mt-2 grid gap-2 md:grid-cols-[1fr_auto]">
                <input value={renameWatchlistName} onChange={(e) => setRenameWatchlistName(e.target.value)} placeholder="Rename selected watchlist" className="h-9 rounded-lg border border-stroke bg-bg px-2 text-sm" />
                <button type="button" onClick={renameWatchlist} className="rounded-lg border border-stroke px-3 py-2 text-xs">Rename</button>
              </div>
              <div className="mt-2 grid gap-2 md:grid-cols-[160px_1fr_auto]">
                <select value={manualMarket} onChange={(e) => setManualMarket(e.target.value as MarketCode)} className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs"><option value="us">US</option><option value="bist">BIST</option></select>
                <input value={manualSymbol} onChange={(e) => setManualSymbol(e.target.value)} placeholder="Add symbol manually (e.g. NVDA / FROTO)" className="h-9 rounded-lg border border-stroke bg-bg px-2 text-sm" />
                <button type="button" onClick={addManualSymbol} className="rounded-lg border border-stroke px-3 py-2 text-xs">Add Symbol</button>
              </div>

              <div className="mt-3 overflow-x-auto rounded-lg border border-stroke/70">
                <table className="min-w-full text-xs">
                  <thead><tr className="border-b border-stroke text-left text-slate-400"><th className="px-2 py-2">Symbol</th><th className="px-2 py-2">Mkt</th><th className="px-2 py-2">Added</th><th className="px-2 py-2">Added Px</th><th className="px-2 py-2">Current</th><th className="px-2 py-2">P/L</th><th className="px-2 py-2">1M</th><th className="px-2 py-2">3M</th><th className="px-2 py-2">6M</th><th className="px-2 py-2">1Y</th><th className="px-2 py-2">Trend</th><th className="px-2 py-2">Score</th><th className="px-2 py-2">Dynamics</th><th className="px-2 py-2">vs EMA200</th><th className="px-2 py-2">Alerts</th><th className="px-2 py-2">Latest Log</th><th className="px-2 py-2">Last Checked</th><th className="px-2 py-2">Actions</th></tr></thead>
                  <tbody>
                    {(selectedWatchlist?.items ?? []).map((item) => {
                      const alertCount = enabledRules.filter((r) => r.market === item.market && ((r.scope_type === "symbol" && r.symbol?.toUpperCase() === item.symbol.toUpperCase()) || (r.scope_type === "watchlist" && r.scope_ref === selectedWatchlistId))).length;
                      const latestLog = latestAlertBySymbol.get(`${item.symbol}|${item.market}`);
                      return <tr key={`${item.symbol}|${item.market}`} className="border-b border-stroke/50"><td className="px-2 py-2 font-medium text-slate-100">{item.symbol}</td><td className="px-2 py-2">{item.market.toUpperCase()}</td><td className="px-2 py-2">{new Date(item.added_at).toLocaleDateString()}</td><td className="px-2 py-2">{num(item.added_price)}{item.added_price_estimated ? " (est)" : ""}</td><td className="px-2 py-2">{num(item.current_price)}</td><td className={`px-2 py-2 ${(item.pnl_since_added_pct ?? 0) >= 0 ? "text-green" : "text-red"}`}>{pct(item.pnl_since_added_pct)}</td><td className="px-2 py-2">{pct(item.return_1m_pct)}</td><td className="px-2 py-2">{pct(item.return_3m_pct)}</td><td className="px-2 py-2">{pct(item.return_6m_pct)}</td><td className="px-2 py-2">{pct(item.return_1y_pct)}</td><td className="px-2 py-2">{item.trend_state ?? "-"}</td><td className="px-2 py-2">{item.score !== null ? item.score.toFixed(1) : "-"}</td><td className="px-2 py-2">{item.score_dynamics_state ?? "-"}</td><td className="px-2 py-2">{pct(item.price_vs_ema200_pct)}</td><td className="px-2 py-2">{alertCount}</td><td className="px-2 py-2">{latestLog ? `${latestLog.message.slice(0, 42)}${latestLog.message.length > 42 ? "..." : ""}` : "-"}</td><td className="px-2 py-2">{item.last_checked ? new Date(item.last_checked).toLocaleString() : "-"}</td><td className="px-2 py-2"><div className="flex gap-1"><button type="button" onClick={() => router.push(`/analysis?ticker=${encodeURIComponent(item.symbol)}&market=${encodeURIComponent(item.market)}&window=1y`)} className="rounded border border-stroke px-2 py-1">Analysis</button><a href={tvLink(item.symbol, item.market, item.exchange)} target="_blank" rel="noreferrer" className="rounded border border-stroke px-2 py-1">TV</a><button type="button" onClick={() => { setRuleSymbolFilter(item.symbol); setView("rules"); }} className="rounded border border-stroke px-2 py-1">Edit Alerts</button><button type="button" onClick={() => openPreset(item.symbol, item.market)} className="rounded border border-stroke px-2 py-1">Alert</button><button type="button" onClick={() => removeSymbol(item.symbol, item.market)} className="rounded border border-red/40 px-2 py-1 text-red">Remove</button></div></td></tr>;
                    })}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}

          {view === "rules" ? (
            <>
              <SectionTitle title="Alert Rules" subtitle="All rules by default with filters" />
              <div className="grid gap-2 md:grid-cols-5"><input value={ruleSymbolFilter} onChange={(e) => setRuleSymbolFilter(e.target.value)} placeholder="symbol" className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs" /><select value={ruleWatchlistFilter} onChange={(e) => setRuleWatchlistFilter(e.target.value)} className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs"><option value="">all watchlists</option>{watchlists.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}</select><select value={ruleSeverityFilter} onChange={(e) => setRuleSeverityFilter(e.target.value)} className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs"><option value="">all severities</option><option value="info">info</option><option value="watch">watch</option><option value="important">important</option><option value="critical">critical</option></select><select value={ruleEnabledFilter} onChange={(e) => setRuleEnabledFilter(e.target.value as "all" | "enabled" | "disabled")} className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs"><option value="all">all states</option><option value="enabled">enabled</option><option value="disabled">disabled</option></select><button type="button" onClick={() => { setRuleSymbolFilter(""); setRuleWatchlistFilter(""); setRuleSeverityFilter(""); setRuleEnabledFilter("all"); }} className="rounded-lg border border-stroke px-3 py-2 text-xs">clear</button></div>
              <div className="mt-3 overflow-x-auto rounded-lg border border-stroke/70"><table className="min-w-full text-xs"><thead><tr className="border-b border-stroke text-left text-slate-400"><th className="px-2 py-2">Name</th><th className="px-2 py-2">Scope</th><th className="px-2 py-2">Condition</th><th className="px-2 py-2">TF</th><th className="px-2 py-2">Severity</th><th className="px-2 py-2">Enabled</th><th className="px-2 py-2">Last Checked</th><th className="px-2 py-2">Last Matched</th><th className="px-2 py-2">Actions</th></tr></thead><tbody>{alertRules.map((rule) => <tr key={rule.id} className="border-b border-stroke/50"><td className="px-2 py-2 text-slate-100">{rule.name}</td><td className="px-2 py-2">{rule.scope_type === "symbol" ? (rule.symbol ?? rule.scope_ref) : `WL:${rule.scope_ref}`}</td><td className="px-2 py-2">{ruleCondition(rule)}</td><td className="px-2 py-2">{rule.timeframe}</td><td className="px-2 py-2">{rule.severity}</td><td className="px-2 py-2">{rule.is_enabled ? "yes" : "no"}</td><td className="px-2 py-2">{rule.last_checked ? new Date(rule.last_checked).toLocaleString() : "-"}</td><td className="px-2 py-2">{rule.last_matched ? new Date(rule.last_matched).toLocaleString() : "-"}</td><td className="px-2 py-2"><div className="flex gap-1"><button type="button" onClick={() => toggleRule(rule)} className="rounded border border-stroke px-2 py-1">{rule.is_enabled ? "Disable" : "Enable"}</button><button type="button" onClick={() => deleteRule(rule.id)} className="rounded border border-red/40 px-2 py-1 text-red">Delete</button></div></td></tr>)}</tbody></table></div>
            </>
          ) : null}

          {view === "logs" ? (
            <>
              <SectionTitle title="Alert Logs" subtitle="Triggered events grouped and filterable" />
              <div className="grid gap-2 md:grid-cols-6"><select value={eventSeverityFilter} onChange={(e) => setEventSeverityFilter(e.target.value)} className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs"><option value="">all severities</option><option value="info">info</option><option value="watch">watch</option><option value="important">important</option><option value="critical">critical</option></select><select value={eventStatusFilter} onChange={(e) => setEventStatusFilter(e.target.value)} className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs"><option value="">all status</option><option value="new">new</option><option value="seen">seen</option><option value="archived">archived</option></select><select value={eventWatchlistFilter} onChange={(e) => setEventWatchlistFilter(e.target.value)} className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs"><option value="">all watchlists</option>{watchlists.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}</select><input value={eventSymbolFilter} onChange={(e) => setEventSymbolFilter(e.target.value)} placeholder="symbol" className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs" /><input type="date" value={eventDateFilter} onChange={(e) => setEventDateFilter(e.target.value)} className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs" /><button type="button" onClick={runMonitoring} className="rounded-lg border border-stroke px-3 py-2 text-xs">Run Monitoring</button></div>
              <div className="mt-3 space-y-2 rounded-lg border border-stroke/70 p-2 max-h-[520px] overflow-auto">{filteredAlerts.length === 0 ? <div className="text-xs text-slate-400">No rules matched yet. Last run: {lastRunAt ? new Date(lastRunAt).toLocaleString() : "-"}. Symbols checked: {lastRunSummary?.evaluated_symbols ?? 0}, rules checked: {lastRunSummary?.processed_rules ?? enabledRules.length}.</div> : filteredAlerts.map((ev) => <div key={ev.id} className={`rounded-md border p-2 text-xs ${ev.status === "new" ? "border-cyan/60 bg-cyan/5" : "border-stroke/60"}`}><p className="text-slate-100">{ev.message}</p><p className="mt-1 text-slate-400">{new Date(ev.timestamp).toLocaleString()} | {ev.symbol} | {ev.severity} | {ev.status} | {ev.signal_type}</p><p className="mt-1 text-slate-500">Triggered value: {ev.triggered_value !== null ? String(ev.triggered_value) : "-"} | watchlist: {ev.watchlist_id ?? "-"} | category: {ev.scanner_category ?? "-"}</p><p className="mt-1 text-slate-300">Meaning: {ev.plain_english_meaning}</p><p className="mt-1 text-slate-300">Suggested action: {ev.suggested_action}</p><p className="mt-1 text-slate-500">Last triggered: {ev.last_triggered_at ? new Date(ev.last_triggered_at).toLocaleString() : "-"} | Notification: {ev.notification_status}{ev.notified_to ? ` -> ${ev.notified_to}` : ""}</p><div className="mt-2 flex gap-1"><button type="button" onClick={() => setEventStatus(ev.id, "seen")} className="rounded border border-stroke px-2 py-1">Seen</button><button type="button" onClick={() => setEventStatus(ev.id, "archived")} className="rounded border border-stroke px-2 py-1">Archive</button><button type="button" onClick={() => router.push(`/analysis?ticker=${encodeURIComponent(ev.symbol)}&market=${encodeURIComponent(ev.market)}&window=1y`)} className="rounded border border-stroke px-2 py-1">Analysis</button></div></div>)}</div>
            </>
          ) : null}
        </Panel>
        </div>
      </div>
    </main>
  );
}
