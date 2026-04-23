"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Panel, SectionTitle, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import {
  AlertEvent,
  AlertEventStatus,
  AlertRule,
  AlertSeverity,
  MarketCode,
  MonitoringRunSummary,
  MonitoringSchedule,
  ScannerResult,
  Watchlist,
} from "@/lib/types";

type MonitorView = "watchlists" | "rules" | "events";

function formatRuleCondition(rule: AlertRule): string {
  const params = rule.parameters ?? {};
  const threshold = Number(params.threshold_pct ?? 0);
  const value = params.value;
  const state = params.state;
  const topN = Number(params.top_n ?? 0);

  switch (rule.rule_type) {
    case "near_ema20":
      return `Near EMA20 within ${threshold.toFixed(1)}%`;
    case "near_ema50":
      return `Near EMA50 within ${threshold.toFixed(1)}%`;
    case "near_ema200":
      return `Near EMA200 within ${threshold.toFixed(1)}%`;
    case "price_gte":
      return `Price >= ${value ?? "-"}`;
    case "price_lte":
      return `Price <= ${value ?? "-"}`;
    case "trend_state_is":
      return `Trend state = ${state ?? "-"}`;
    case "dynamics_state_is":
      return `Dynamics = ${state ?? "-"}`;
    case "scanner_top_n":
      return `Scanner top ${topN || "-"}`;
    case "reclaim_ema200":
      return "EMA200 reclaim";
    case "resistance_test_count_gte":
      return `Resistance tests >= ${value ?? "-"}`;
    case "volume_ratio_20_gte":
      return `Volume ratio 20 >= ${value ?? "-"}`;
    case "rsi14_lte":
      return `RSI14 <= ${value ?? "-"}`;
    case "rsi14_gte":
      return `RSI14 >= ${value ?? "-"}`;
    default:
      return rule.rule_type;
  }
}

function toTradingViewSymbol(symbol: string, market: MarketCode): string {
  const prefix = market === "bist" ? "BIST" : "NASDAQ";
  return `${prefix}%3A${encodeURIComponent(symbol)}`;
}

export default function MonitorPage() {
  const router = useRouter();

  const [view, setView] = useState<MonitorView>("watchlists");
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [selectedWatchlistId, setSelectedWatchlistId] = useState("");
  const [newWatchlistName, setNewWatchlistName] = useState("");
  const [renameWatchlistName, setRenameWatchlistName] = useState("");

  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const [alertRules, setAlertRules] = useState<AlertRule[]>([]);
  const [schedules, setSchedules] = useState<MonitoringSchedule[]>([]);
  const [lastRunSummary, setLastRunSummary] = useState<MonitoringRunSummary | null>(null);

  const [alertSeverityFilter, setAlertSeverityFilter] = useState<string>("");
  const [alertStatusFilter, setAlertStatusFilter] = useState<string>("");
  const [ruleSymbolFilter, setRuleSymbolFilter] = useState("");

  const [watchMetrics, setWatchMetrics] = useState<Record<string, ScannerResult>>({});
  const [loadingMetrics, setLoadingMetrics] = useState(false);

  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedWatchlist = useMemo(
    () => watchlists.find((row) => row.id === selectedWatchlistId) ?? null,
    [watchlists, selectedWatchlistId]
  );

  const enabledRules = useMemo(() => alertRules.filter((row) => row.is_enabled), [alertRules]);

  const latestEventByRule = useMemo(() => {
    const map: Record<string, AlertEvent> = {};
    for (const event of alerts) {
      const prev = map[event.alert_rule_id];
      if (!prev || new Date(event.timestamp).getTime() > new Date(prev.timestamp).getTime()) {
        map[event.alert_rule_id] = event;
      }
    }
    return map;
  }, [alerts]);

  const watchlistAlertCountBySymbol = useMemo(() => {
    const map: Record<string, number> = {};
    if (!selectedWatchlist) return map;

    for (const item of selectedWatchlist.items) {
      const count = enabledRules.filter((rule) => {
        if (rule.market !== item.market) return false;
        if (rule.scope_type === "symbol" && rule.symbol) {
          return rule.symbol.toUpperCase() === item.symbol.toUpperCase();
        }
        return rule.scope_type === "watchlist" && rule.scope_ref === selectedWatchlist.id;
      }).length;
      map[`${item.symbol}|${item.market}`] = count;
    }
    return map;
  }, [enabledRules, selectedWatchlist]);

  const filteredRules = useMemo(() => {
    const symbolFilter = ruleSymbolFilter.trim().toUpperCase();
    return alertRules.filter((rule) => {
      if (!symbolFilter) return true;
      const candidate = (rule.symbol ?? rule.scope_ref).toUpperCase();
      return candidate.includes(symbolFilter);
    });
  }, [alertRules, ruleSymbolFilter]);

  const refresh = async () => {
    setError(null);
    try {
      const [watchlistRows, alertRows, ruleRows, scheduleRows] = await Promise.all([
        api.listWatchlists(),
        api.listAlertEvents(alertStatusFilter || undefined, alertSeverityFilter || undefined, undefined),
        api.listAlertRules(),
        api.listMonitoringSchedules(),
      ]);
      setWatchlists(watchlistRows);
      setAlerts(alertRows);
      setAlertRules(ruleRows);
      setSchedules(scheduleRows);
      if (watchlistRows.length > 0 && !watchlistRows.some((row) => row.id === selectedWatchlistId)) {
        setSelectedWatchlistId(watchlistRows[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load monitor workspace.");
    }
  };

  const refreshWatchlistMetrics = async () => {
    if (!selectedWatchlist || selectedWatchlist.items.length === 0) {
      setWatchMetrics({});
      return;
    }

    setLoadingMetrics(true);
    try {
      const marketGroups = selectedWatchlist.items.reduce<Record<MarketCode, string[]>>(
        (acc, item) => {
          acc[item.market] = [...(acc[item.market] ?? []), item.symbol];
          return acc;
        },
        { us: [], bist: [] }
      );

      const requests = (Object.entries(marketGroups) as Array<[MarketCode, string[]]>)
        .filter(([, symbols]) => symbols.length > 0)
        .map(([market, symbols]) =>
          api.scanner({
            market,
            category: "trend_mode",
            duration: "1y",
            max_results: Math.max(symbols.length, 20),
            universe_scope: "watchlist",
            symbol_overrides: symbols,
            use_custom_rules: false,
          })
        );

      const responses = await Promise.all(requests);
      const metricMap: Record<string, ScannerResult> = {};
      for (const response of responses) {
        for (const row of response.results) {
          metricMap[`${row.symbol}|${response.scope.market}`] = row;
        }
      }
      setWatchMetrics(metricMap);
      setNotice("Watchlist quick metrics refreshed.");
    } catch {
      setNotice("Metrics refresh failed. Showing available watchlist data.");
      setWatchMetrics({});
    } finally {
      setLoadingMetrics(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [alertSeverityFilter, alertStatusFilter]);

  useEffect(() => {
    refreshWatchlistMetrics();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedWatchlistId]);

  useEffect(() => {
    if (!notice) return;
    const id = setTimeout(() => setNotice(null), 2500);
    return () => clearTimeout(id);
  }, [notice]);

  const createWatchlist = async () => {
    if (!newWatchlistName.trim()) return;
    await api.createWatchlist(newWatchlistName.trim());
    setNewWatchlistName("");
    setNotice("Watchlist created.");
    await refresh();
  };

  const renameWatchlist = async () => {
    if (!selectedWatchlistId || !renameWatchlistName.trim()) return;
    await api.renameWatchlist(selectedWatchlistId, renameWatchlistName.trim());
    setRenameWatchlistName("");
    setNotice("Watchlist renamed.");
    await refresh();
  };

  const deleteWatchlist = async () => {
    if (!selectedWatchlistId) return;
    await api.deleteWatchlist(selectedWatchlistId);
    setNotice("Watchlist deleted.");
    setSelectedWatchlistId("");
    await refresh();
  };

  const removeSymbol = async (symbol: string, market: MarketCode) => {
    if (!selectedWatchlistId) return;
    await api.removeWatchlistItem(selectedWatchlistId, symbol, market);
    setNotice(`${symbol} removed from watchlist.`);
    await refresh();
    await refreshWatchlistMetrics();
  };

  const createAlertForSymbol = async (symbol: string, market: MarketCode) => {
    await api.createAlertRule({
      scope_type: "symbol",
      scope_ref: symbol,
      market,
      symbol,
      name: `${symbol} near EMA50`,
      rule_type: "near_ema50",
      parameters: { threshold_pct: 3.0 },
      timeframe: "daily",
      severity: "watch",
      color: "yellow",
      is_enabled: true,
    });
    setNotice(`Alert created for ${symbol}.`);
    await refresh();
  };

  const runMonitoring = async () => {
    const summary = await api.runMonitoring({
      watchlist_id: selectedWatchlistId || null,
      symbols: [],
    });
    setLastRunSummary(summary);
    setNotice(`Monitoring run completed: ${summary.events_created} events created.`);
    await refresh();
  };

  const updateEventStatus = async (eventId: string, status: AlertEventStatus) => {
    await api.updateAlertEventStatus(eventId, status);
    await refresh();
  };

  const toggleRuleEnabled = async (rule: AlertRule) => {
    await api.updateAlertRule(rule.id, { is_enabled: !rule.is_enabled });
    setNotice(`${rule.name} ${rule.is_enabled ? "disabled" : "enabled"}.`);
    await refresh();
  };

  const removeRule = async (ruleId: string) => {
    await api.deleteAlertRule(ruleId);
    setNotice("Alert rule deleted.");
    await refresh();
  };

  const modeLabel = useMemo(() => {
    const enabled = schedules.filter((row) => row.is_enabled);
    if (enabled.length === 0) return "manual";
    if (enabled.some((row) => row.frequency.toLowerCase().includes("hour"))) return "hourly";
    if (enabled.some((row) => row.frequency.toLowerCase().includes("day"))) return "daily";
    return "scheduled";
  }, [schedules]);

  const latestScheduleRun = useMemo(() => {
    const timestamps = schedules.map((row) => row.last_run_at).filter(Boolean) as string[];
    if (timestamps.length === 0) return null;
    return timestamps.sort((a, b) => new Date(b).getTime() - new Date(a).getTime())[0];
  }, [schedules]);

  const nextScheduledRun = useMemo(() => {
    const timestamps = schedules
      .filter((row) => row.is_enabled && row.next_run_at)
      .map((row) => row.next_run_at as string);
    if (timestamps.length === 0) return null;
    return timestamps.sort((a, b) => new Date(a).getTime() - new Date(b).getTime())[0];
  }, [schedules]);

  const lastRunAtDisplay = lastRunSummary?.finished_at ?? latestScheduleRun;

  return (
    <main className="space-y-4">
      <Panel>
        <SectionTitle title="Monitor Workspace" subtitle="Persistent tracking for watchlists, alert rules, and alert events" />
        <p className="text-sm text-slate-300">Scanner = discovery. Monitor = tracking and event review.</p>
      </Panel>

      {notice ? (
        <Panel className="border-cyan/30 bg-cyan/10">
          <p className="text-sm text-cyan">{notice}</p>
        </Panel>
      ) : null}
      {error ? (
        <Panel className="border-red/40 bg-red/10">
          <p className="text-sm text-red">{error}</p>
        </Panel>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
        <StatCard label="Polling Mode" value={modeLabel} />
        <StatCard label="Last Run" value={lastRunAtDisplay ? new Date(lastRunAtDisplay).toLocaleString() : "-"} />
        <StatCard label="Next Run" value={nextScheduledRun ? new Date(nextScheduledRun).toLocaleString() : "-"} />
        <StatCard label="Symbols Checked" value={lastRunSummary ? String(lastRunSummary.evaluated_symbols) : "-"} />
        <StatCard label="Rules Checked" value={lastRunSummary ? String(lastRunSummary.processed_rules) : String(enabledRules.length)} />
        <StatCard label="Events Generated" value={lastRunSummary ? String(lastRunSummary.events_created) : "-"} />
      </div>

      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        <Panel className="h-fit">
          <SectionTitle title="Monitor Navigation" subtitle="Watchlists, rules, and event history" />
          <div className="mb-3 grid gap-2">
            <button
              type="button"
              onClick={() => setView("watchlists")}
              className={`rounded-md border px-3 py-2 text-left text-xs ${view === "watchlists" ? "border-cyan text-cyan" : "border-stroke text-slate-300"}`}
            >
              Watchlists ({watchlists.length})
            </button>
            <button
              type="button"
              onClick={() => setView("rules")}
              className={`rounded-md border px-3 py-2 text-left text-xs ${view === "rules" ? "border-cyan text-cyan" : "border-stroke text-slate-300"}`}
            >
              Alert Rules ({enabledRules.length} active)
            </button>
            <button
              type="button"
              onClick={() => setView("events")}
              className={`rounded-md border px-3 py-2 text-left text-xs ${view === "events" ? "border-cyan text-cyan" : "border-stroke text-slate-300"}`}
            >
              Alert Events ({alerts.length})
            </button>
          </div>

          <div className="space-y-2 rounded-lg border border-stroke/70 p-2">
            <p className="text-xs text-slate-400">Watchlists</p>
            {watchlists.length === 0 ? (
              <p className="text-xs text-slate-500">No watchlists yet.</p>
            ) : (
              watchlists.map((row) => (
                <button
                  key={row.id}
                  type="button"
                  onClick={() => {
                    setSelectedWatchlistId(row.id);
                    setView("watchlists");
                  }}
                  className={`w-full rounded-md border px-2 py-2 text-left text-xs ${selectedWatchlistId === row.id ? "border-cyan text-cyan" : "border-stroke text-slate-300"}`}
                >
                  {row.name} ({row.items.length})
                </button>
              ))
            )}
          </div>

          <button type="button" onClick={runMonitoring} className="mt-3 w-full rounded-lg border border-stroke px-3 py-2 text-xs hover:text-cyan">
            Run Monitoring Now
          </button>
        </Panel>

        <Panel>
          {view === "watchlists" ? (
            <>
              <SectionTitle title="Watchlist Detail" subtitle="Symbols with quick metrics, active alert counts, and actions" />
              <div className="grid gap-2 md:grid-cols-[1fr_auto]">
                <input
                  value={newWatchlistName}
                  onChange={(event) => setNewWatchlistName(event.target.value)}
                  placeholder="Create new watchlist"
                  className="h-9 rounded-lg border border-stroke bg-bg px-2 text-sm"
                />
                <button type="button" onClick={createWatchlist} className="rounded-lg border border-stroke px-3 py-2 text-xs hover:text-cyan">Create</button>
              </div>

              <div className="mt-3 grid gap-2 md:grid-cols-[1fr_auto_auto_auto]">
                <input
                  value={renameWatchlistName}
                  onChange={(event) => setRenameWatchlistName(event.target.value)}
                  placeholder="Rename selected watchlist"
                  className="h-9 rounded-lg border border-stroke bg-bg px-2 text-sm"
                />
                <button type="button" onClick={renameWatchlist} className="rounded-lg border border-stroke px-3 py-2 text-xs hover:text-cyan">Rename</button>
                <button type="button" onClick={refreshWatchlistMetrics} className="rounded-lg border border-stroke px-3 py-2 text-xs hover:text-cyan" disabled={loadingMetrics}>
                  {loadingMetrics ? "Refreshing..." : "Refresh Metrics"}
                </button>
                <button type="button" onClick={deleteWatchlist} className="rounded-lg border border-red/40 px-3 py-2 text-xs text-red">Delete</button>
              </div>

              <div className="mt-3 overflow-x-auto rounded-lg border border-stroke/70">
                {!selectedWatchlist ? (
                  <p className="p-3 text-sm text-slate-400">Select a watchlist from the left panel.</p>
                ) : selectedWatchlist.items.length === 0 ? (
                  <p className="p-3 text-sm text-slate-400">No symbols in this watchlist yet. Add symbols from Scanner using Add WL.</p>
                ) : (
                  <table className="min-w-full text-xs">
                    <thead>
                      <tr className="border-b border-stroke text-left text-slate-400">
                        <th className="px-2 py-2">Symbol</th>
                        <th className="px-2 py-2">Market</th>
                        <th className="px-2 py-2">Added</th>
                        <th className="px-2 py-2">Last Checked</th>
                        <th className="px-2 py-2">Current Price</th>
                        <th className="px-2 py-2">Trend</th>
                        <th className="px-2 py-2">Price vs EMA200</th>
                        <th className="px-2 py-2">Score</th>
                        <th className="px-2 py-2">Dynamics</th>
                        <th className="px-2 py-2">Support%</th>
                        <th className="px-2 py-2">Room%</th>
                        <th className="px-2 py-2">Active Alerts</th>
                        <th className="px-2 py-2">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedWatchlist.items.map((item) => {
                        const metric = watchMetrics[`${item.symbol}|${item.market}`];
                        const activeAlertCount = watchlistAlertCountBySymbol[`${item.symbol}|${item.market}`] ?? 0;
                        return (
                          <tr key={`${item.symbol}-${item.market}`} className="border-b border-stroke/50">
                            <td className="px-2 py-2 font-medium text-slate-100">{item.symbol}</td>
                            <td className="px-2 py-2">{item.market.toUpperCase()}</td>
                            <td className="px-2 py-2">{new Date(item.added_at).toLocaleDateString()}</td>
                            <td className="px-2 py-2">{lastRunAtDisplay ? new Date(lastRunAtDisplay).toLocaleString() : "-"}</td>
                            <td className="px-2 py-2">--</td>
                            <td className="px-2 py-2">{metric?.trend_state ?? "-"}</td>
                            <td className="px-2 py-2">{metric ? `${metric.price_vs_ema200_pct.toFixed(2)}%` : "-"}</td>
                            <td className="px-2 py-2">{metric ? metric.current_score.toFixed(1) : "-"}</td>
                            <td className="px-2 py-2">{metric?.score_dynamics_state ?? "-"}</td>
                            <td className="px-2 py-2">{metric ? `${metric.support_distance_pct.toFixed(2)}%` : "-"}</td>
                            <td className="px-2 py-2">{metric ? `${metric.resistance_room_pct.toFixed(2)}%` : "-"}</td>
                            <td className="px-2 py-2">{activeAlertCount}</td>
                            <td className="px-2 py-2">
                              <div className="flex flex-wrap gap-1 whitespace-nowrap">
                                <button
                                  type="button"
                                  onClick={() => router.push(`/analysis?ticker=${encodeURIComponent(item.symbol)}&market=${encodeURIComponent(item.market)}&window=1y`)}
                                  className="rounded border border-stroke px-2 py-1 text-slate-300 hover:text-cyan"
                                >
                                  Analysis
                                </button>
                                <a
                                  href={`https://www.tradingview.com/chart/?symbol=${toTradingViewSymbol(item.symbol, item.market)}`}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="rounded border border-stroke px-2 py-1 text-slate-300 hover:text-cyan"
                                >
                                  TV
                                </a>
                                <button
                                  type="button"
                                  onClick={() => {
                                    setRuleSymbolFilter(item.symbol);
                                    setView("rules");
                                  }}
                                  className="rounded border border-stroke px-2 py-1 text-slate-300 hover:text-cyan"
                                >
                                  Edit Alerts
                                </button>
                                <button type="button" onClick={() => createAlertForSymbol(item.symbol, item.market)} className="rounded border border-stroke px-2 py-1 text-slate-300 hover:text-cyan">
                                  Alert
                                </button>
                                <button type="button" onClick={() => removeSymbol(item.symbol, item.market)} className="rounded border border-red/40 px-2 py-1 text-red">
                                  Remove
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>
            </>
          ) : null}

          {view === "rules" ? (
            <>
              <SectionTitle title="Alert Rules" subtitle="Visible rule inventory with scope, condition, and match activity" />
              <div className="grid gap-2 md:grid-cols-[1fr_auto]">
                <input
                  value={ruleSymbolFilter}
                  onChange={(event) => setRuleSymbolFilter(event.target.value)}
                  placeholder="Filter by symbol"
                  className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs"
                />
                <button type="button" onClick={runMonitoring} className="rounded-lg border border-stroke px-3 py-2 text-xs hover:text-cyan">Run Monitoring</button>
              </div>

              <div className="mt-3 overflow-x-auto rounded-lg border border-stroke/70">
                <table className="min-w-full text-xs">
                  <thead>
                    <tr className="border-b border-stroke text-left text-slate-400">
                      <th className="px-2 py-2">Name</th>
                      <th className="px-2 py-2">Scope</th>
                      <th className="px-2 py-2">Condition</th>
                      <th className="px-2 py-2">Timeframe</th>
                      <th className="px-2 py-2">Severity</th>
                      <th className="px-2 py-2">Enabled</th>
                      <th className="px-2 py-2">Last Checked</th>
                      <th className="px-2 py-2">Last Matched</th>
                      <th className="px-2 py-2">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredRules.length === 0 ? (
                      <tr>
                        <td className="px-2 py-3 text-slate-400" colSpan={9}>No alert rules found for current filters.</td>
                      </tr>
                    ) : (
                      filteredRules.map((rule) => {
                        const latestMatch = latestEventByRule[rule.id];
                        return (
                          <tr key={rule.id} className="border-b border-stroke/50">
                            <td className="px-2 py-2 text-slate-100">{rule.name}</td>
                            <td className="px-2 py-2">{rule.scope_type === "symbol" ? `${rule.scope_ref}` : `Watchlist ${rule.scope_ref}`}</td>
                            <td className="px-2 py-2">{formatRuleCondition(rule)}</td>
                            <td className="px-2 py-2">{rule.timeframe}</td>
                            <td className="px-2 py-2">{rule.severity}</td>
                            <td className="px-2 py-2">{rule.is_enabled ? "yes" : "no"}</td>
                            <td className="px-2 py-2">{lastRunAtDisplay ? new Date(lastRunAtDisplay).toLocaleString() : "-"}</td>
                            <td className="px-2 py-2">{latestMatch ? new Date(latestMatch.timestamp).toLocaleString() : "-"}</td>
                            <td className="px-2 py-2">
                              <div className="flex gap-1 whitespace-nowrap">
                                <button type="button" onClick={() => toggleRuleEnabled(rule)} className="rounded border border-stroke px-2 py-1 text-slate-300 hover:text-cyan">
                                  {rule.is_enabled ? "Disable" : "Enable"}
                                </button>
                                <button type="button" onClick={() => removeRule(rule.id)} className="rounded border border-red/40 px-2 py-1 text-red">
                                  Delete
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}

          {view === "events" ? (
            <>
              <SectionTitle title="Alert Events" subtitle="Triggered log with severity and status tracking" />
              <div className="grid gap-2 md:grid-cols-[auto_auto_auto]">
                <select value={alertSeverityFilter} onChange={(event) => setAlertSeverityFilter(event.target.value)} className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs">
                  <option value="">All severities</option>
                  {(["info", "watch", "important", "critical"] as AlertSeverity[]).map((sev) => (
                    <option key={sev} value={sev}>{sev}</option>
                  ))}
                </select>
                <select value={alertStatusFilter} onChange={(event) => setAlertStatusFilter(event.target.value)} className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs">
                  <option value="">All status</option>
                  <option value="new">new</option>
                  <option value="seen">seen</option>
                  <option value="archived">archived</option>
                </select>
                <button type="button" onClick={runMonitoring} className="rounded-lg border border-stroke px-3 py-2 text-xs hover:text-cyan">Run Monitoring</button>
              </div>

              <div className="mt-3 max-h-[560px] space-y-2 overflow-auto rounded-lg border border-stroke/70 p-2">
                {alerts.length === 0 ? (
                  <div className="rounded-md border border-stroke/60 p-3 text-xs text-slate-400">
                    <p>No matching events yet for current filters.</p>
                    <p className="mt-1">Last run checked {lastRunSummary?.evaluated_symbols ?? 0} symbols and {lastRunSummary?.processed_rules ?? enabledRules.length} rules.</p>
                    <p className="mt-1">Create or enable alert rules, then run monitoring to populate this log.</p>
                  </div>
                ) : (
                  alerts.map((ev) => (
                    <div key={ev.id} className="rounded-md border border-stroke/60 p-2 text-xs">
                      <p className="text-slate-100">{ev.message}</p>
                      <p className="mt-1 text-slate-400">
                        {new Date(ev.timestamp).toLocaleString()} | {ev.symbol} | {ev.market.toUpperCase()} | {ev.severity} | {ev.status}
                      </p>
                      <p className="mt-1 text-slate-500">Rule: {alertRules.find((row) => row.id === ev.alert_rule_id)?.name ?? ev.alert_rule_id}</p>
                      <div className="mt-2 flex gap-1">
                        <button type="button" onClick={() => updateEventStatus(ev.id, "seen")} className="rounded border border-stroke px-2 py-1 text-slate-300 hover:text-cyan">Mark Seen</button>
                        <button type="button" onClick={() => updateEventStatus(ev.id, "archived")} className="rounded border border-stroke px-2 py-1 text-slate-300 hover:text-cyan">Archive</button>
                        <button type="button" onClick={() => router.push(`/analysis?ticker=${encodeURIComponent(ev.symbol)}&market=${encodeURIComponent(ev.market)}&window=1y`)} className="rounded border border-stroke px-2 py-1 text-slate-300 hover:text-cyan">Open Analysis</button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </>
          ) : null}
        </Panel>
      </div>
    </main>
  );
}
