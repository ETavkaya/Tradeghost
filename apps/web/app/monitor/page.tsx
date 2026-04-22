"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Panel, SectionTitle } from "@/components/ui";
import { api } from "@/lib/api";
import { AlertEvent, AlertEventStatus, AlertSeverity, AlertRule, MarketCode, Watchlist } from "@/lib/types";

type MonitorView = "watchlists" | "alerts";

export default function MonitorPage() {
  const router = useRouter();
  const [view, setView] = useState<MonitorView>("watchlists");
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [selectedWatchlistId, setSelectedWatchlistId] = useState("");
  const [newWatchlistName, setNewWatchlistName] = useState("");
  const [renameWatchlistName, setRenameWatchlistName] = useState("");

  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const [alertRules, setAlertRules] = useState<AlertRule[]>([]);
  const [alertSeverityFilter, setAlertSeverityFilter] = useState<string>("");
  const [alertStatusFilter, setAlertStatusFilter] = useState<string>("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedWatchlist = useMemo(
    () => watchlists.find((row) => row.id === selectedWatchlistId) ?? null,
    [watchlists, selectedWatchlistId]
  );

  const refresh = async () => {
    setError(null);
    try {
      const [watchlistRows, alertRows, ruleRows] = await Promise.all([
        api.listWatchlists(),
        api.listAlertEvents(alertStatusFilter || undefined, alertSeverityFilter || undefined, undefined),
        api.listAlertRules(),
      ]);
      setWatchlists(watchlistRows);
      setAlerts(alertRows);
      setAlertRules(ruleRows);
      if (watchlistRows.length > 0 && !watchlistRows.some((row) => row.id === selectedWatchlistId)) {
        setSelectedWatchlistId(watchlistRows[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load monitor workspace.");
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [alertSeverityFilter, alertStatusFilter]);

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
    setNotice(`Monitoring run completed: ${summary.events_created} events created.`);
    await refresh();
  };

  const updateEventStatus = async (eventId: string, status: AlertEventStatus) => {
    await api.updateAlertEventStatus(eventId, status);
    await refresh();
  };

  return (
    <main className="space-y-4">
      <Panel>
        <SectionTitle title="Monitor Workspace" subtitle="Persistent tracking for watchlists, alert rules, and alert logs" />
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

      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        <Panel className="h-fit">
          <SectionTitle title="Navigation" subtitle="Watchlists and alerts" />
          <div className="mb-3 flex gap-2">
            <button
              type="button"
              onClick={() => setView("watchlists")}
              className={`rounded-md border px-2 py-1 text-xs ${view === "watchlists" ? "border-cyan text-cyan" : "border-stroke text-slate-300"}`}
            >
              Watchlists
            </button>
            <button
              type="button"
              onClick={() => setView("alerts")}
              className={`rounded-md border px-2 py-1 text-xs ${view === "alerts" ? "border-cyan text-cyan" : "border-stroke text-slate-300"}`}
            >
              Alerts
            </button>
          </div>

          <div className="space-y-2">
            {watchlists.map((row) => (
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
            ))}
          </div>

          <div className="mt-4 rounded-lg border border-stroke/70 p-2 text-xs text-slate-300">
            Active rules: {alertRules.length}
            <br />
            Triggered events: {alerts.length}
          </div>
        </Panel>

        <Panel>
          {view === "watchlists" ? (
            <>
              <SectionTitle title="Watchlist Detail" subtitle="Symbols, quick actions, and management" />
              <div className="grid gap-2 md:grid-cols-[1fr_auto]">
                <input
                  value={newWatchlistName}
                  onChange={(event) => setNewWatchlistName(event.target.value)}
                  placeholder="Create new watchlist"
                  className="h-9 rounded-lg border border-stroke bg-bg px-2 text-sm"
                />
                <button type="button" onClick={createWatchlist} className="rounded-lg border border-stroke px-3 py-2 text-xs hover:text-cyan">Create</button>
              </div>

              <div className="mt-3 grid gap-2 md:grid-cols-[1fr_auto_auto]">
                <input
                  value={renameWatchlistName}
                  onChange={(event) => setRenameWatchlistName(event.target.value)}
                  placeholder="Rename selected watchlist"
                  className="h-9 rounded-lg border border-stroke bg-bg px-2 text-sm"
                />
                <button type="button" onClick={renameWatchlist} className="rounded-lg border border-stroke px-3 py-2 text-xs hover:text-cyan">Rename</button>
                <button type="button" onClick={deleteWatchlist} className="rounded-lg border border-red/40 px-3 py-2 text-xs text-red">Delete</button>
              </div>

              <div className="mt-4 rounded-lg border border-stroke/70 p-2">
                {!selectedWatchlist ? (
                  <p className="text-sm text-slate-400">Select a watchlist from the left panel.</p>
                ) : selectedWatchlist.items.length === 0 ? (
                  <p className="text-sm text-slate-400">No symbols in this watchlist yet.</p>
                ) : (
                  <div className="space-y-2">
                    {selectedWatchlist.items.map((item) => (
                      <div key={`${item.symbol}-${item.market}`} className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-stroke/60 p-2 text-xs">
                        <div>
                          <p className="text-slate-100">{item.symbol}</p>
                          <p className="text-slate-400">{item.market.toUpperCase()} | added {new Date(item.added_at).toLocaleDateString()}</p>
                        </div>
                        <div className="flex gap-1">
                          <button
                            type="button"
                            onClick={() => router.push(`/analysis?ticker=${encodeURIComponent(item.symbol)}&market=${encodeURIComponent(item.market)}&window=1y`)}
                            className="rounded border border-stroke px-2 py-1 text-slate-300 hover:text-cyan"
                          >
                            Analysis
                          </button>
                          <a
                            href={`https://www.tradingview.com/chart/?symbol=${item.market === "bist" ? "BIST" : "NASDAQ"}%3A${encodeURIComponent(item.symbol)}`}
                            target="_blank"
                            rel="noreferrer"
                            className="rounded border border-stroke px-2 py-1 text-slate-300 hover:text-cyan"
                          >
                            TV
                          </a>
                          <button type="button" onClick={() => createAlertForSymbol(item.symbol, item.market)} className="rounded border border-stroke px-2 py-1 text-slate-300 hover:text-cyan">
                            Alert
                          </button>
                          <button type="button" onClick={() => removeSymbol(item.symbol, item.market)} className="rounded border border-red/40 px-2 py-1 text-red">
                            Remove
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            <>
              <SectionTitle title="Alert Log" subtitle="Triggered events with status/severity filters" />
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

              <div className="mt-3 max-h-[520px] space-y-2 overflow-auto rounded-lg border border-stroke/70 p-2">
                {alerts.length === 0 ? (
                  <p className="text-sm text-slate-400">No alert events found.</p>
                ) : (
                  alerts.map((ev) => (
                    <div key={ev.id} className="rounded-md border border-stroke/60 p-2 text-xs">
                      <p className="text-slate-100">{ev.message}</p>
                      <p className="mt-1 text-slate-400">
                        {ev.symbol} | {ev.market.toUpperCase()} | {ev.severity} | {ev.status} | {new Date(ev.timestamp).toLocaleString()}
                      </p>
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
          )}
        </Panel>
      </div>
    </main>
  );
}
