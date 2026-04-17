"use client";

import { useMemo, useState } from "react";
import { useAnalysisContext } from "@/components/analysis-context";
import { UnifiedAnalysisChart } from "@/components/unified-analysis-chart";
import { Panel, SectionTitle, StatCard } from "@/components/ui";
import { TradesTable } from "@/components/trades-table";
import { api } from "@/lib/api";
import { BacktestFromAnalysisResponse, BacktestMarker, SkippedEntrySignal } from "@/lib/types";

type ChartTab = "trades" | "decision";
type DecisionFilter = "all" | "threshold" | "regime" | "location" | "trigger" | "watchlist";

function decisionMarkerType(row: SkippedEntrySignal): string {
  if (row.setup_status === "watchlist") return "watchlist";
  if ((row.first_failed_gate ?? "").includes("threshold")) return "threshold_fail";
  if ((row.first_failed_gate ?? "").includes("regime")) return "regime_fail";
  if ((row.first_failed_gate ?? "").includes("trigger")) return "trigger_fail";
  return "location_fail";
}

function toDecisionMarkers(rows: SkippedEntrySignal[], visibleDates: Set<string>): BacktestMarker[] {
  const inRange = rows.filter((row) => visibleDates.has(row.date));
  return inRange.map((row) => ({
    date: row.date,
    price: 0,
    marker_type: decisionMarkerType(row),
    label: row.first_failed_gate ?? row.setup_status,
    hover_text:
      `Date: ${row.date}<br>` +
      `Score: ${row.final_score.toFixed(2)} / ${row.threshold_used.toFixed(2)}<br>` +
      `Setup: ${row.setup_status}<br>` +
      `Failed gate: ${row.first_failed_gate ?? "n/a"}<br>` +
      `Reason: ${row.reason_detail ?? row.reason}<br>` +
      `Support distance: ${row.support_distance_pct?.toFixed(2) ?? "n/a"}%<br>` +
      `Resistance room: ${row.resistance_room_pct?.toFixed(2) ?? "n/a"}%<br>` +
      `Trigger: ${row.trigger_state ?? "n/a"} (${row.trigger_score?.toFixed(2) ?? "n/a"})<br>` +
      `Trend: ${row.trend_state ?? "n/a"}`,
    trade_id: null,
  }));
}

function filterDecisionRows(rows: SkippedEntrySignal[], filter: DecisionFilter): SkippedEntrySignal[] {
  if (filter === "all") return rows;
  if (filter === "watchlist") return rows.filter((row) => row.setup_status === "watchlist");
  return rows.filter((row) => (row.first_failed_gate ?? "").includes(filter));
}

export default function BacktestPage() {
  const { analysis } = useAnalysisContext();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BacktestFromAnalysisResponse | null>(null);
  const [chartTab, setChartTab] = useState<ChartTab>("trades");
  const [decisionFilter, setDecisionFilter] = useState<DecisionFilter>("all");

  const runBacktest = async () => {
    if (!analysis) return;
    setLoading(true);
    setError(null);
    try {
      const response = await api.backtestFromAnalysis({
        ticker: analysis.ticker,
        market: analysis.market,
        window: analysis.window,
        analysis_as_of: analysis.as_of,
        analysis_config: analysis.analysis_config,
        quantedge_final_score: analysis.quantedge.final_score,
        category_scores: analysis.quantedge.category_scores,
        swing_candidate: analysis.swingpulse.swing_candidate,
        backtest_score_threshold: analysis.analysis_config.score_threshold,
        strategy_mode: analysis.analysis_config.strategy_mode,
        trade_plan:
          analysis.chart.trade_plan_overlay ?? {
            bias: "neutral",
            entry_zone: [0, 0],
            stop_loss: 0,
            take_profit_1: 0,
            take_profit_2: 0,
            risk_reward: 0,
            invalidation_note: "No trade plan available"
          }
      });
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backtest failed.");
    } finally {
      setLoading(false);
    }
  };

  const contextLabel = useMemo(() => {
    if (!analysis) return "No active analysis context.";
    return `${analysis.ticker} | ${analysis.market.toUpperCase()} | ${analysis.window.toUpperCase()} | Analysis date ${analysis.as_of}`;
  }, [analysis]);

  const filteredDecisionRows = useMemo(
    () => (result ? filterDecisionRows(result.decision_log_sample, decisionFilter) : []),
    [result, decisionFilter]
  );

  const activeMarkers = useMemo(() => {
    if (!result) return [];
    if (chartTab === "trades") return result.markers;
    const visibleDates = new Set(result.chart.candles.map((c) => c.date));
    return toDecisionMarkers(filteredDecisionRows, visibleDates);
  }, [result, chartTab, filteredDecisionRows]);

  return (
    <main className="space-y-4">
      <Panel>
        <SectionTitle title="Backtest" subtitle="Runs from active analysis context only" />
        <p className="text-sm text-slate-300">{contextLabel}</p>
        {analysis ? (
          <>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
              <StatCard label="Market" value={analysis.analysis_config.market.toUpperCase()} />
              <StatCard label="Window" value={analysis.analysis_config.lookback_window.toUpperCase()} />
              <StatCard label="Mode" value={analysis.analysis_config.strategy_mode} />
              <StatCard label="Threshold" value={`${analysis.analysis_config.score_threshold.toFixed(1)}`} />
              <StatCard label="Warmup Bars" value={`${analysis.analysis_config.warmup_bars}`} />
            </div>
            <div className="mt-3 rounded-xl border border-stroke/70 bg-panelSoft p-3 text-xs text-slate-300">
              Regime mode: {analysis.analysis_config.regime_filter.regime_mode}. Support max: {analysis.analysis_config.location_filter.max_support_distance_pct.toFixed(2)}%.
              Resistance min room: {analysis.analysis_config.location_filter.min_resistance_room_pct.toFixed(2)}%. Overextension caps (EMA20/50/100/200):
              {" "}{analysis.analysis_config.location_filter.max_overextension_ema20_pct.toFixed(2)}% /
              {" "}{analysis.analysis_config.location_filter.max_overextension_ema50_pct.toFixed(2)}% /
              {" "}{analysis.analysis_config.location_filter.max_overextension_ema100_pct.toFixed(2)}% /
              {" "}{analysis.analysis_config.location_filter.max_overextension_ema200_pct.toFixed(2)}%.
              Trigger minimum score: {analysis.analysis_config.trigger_filter.min_trigger_score.toFixed(1)}.
            </div>
          </>
        ) : null}

        <button
          type="button"
          onClick={runBacktest}
          disabled={!analysis || loading}
          className="mt-4 h-11 rounded-lg bg-cyan px-6 text-sm font-semibold text-bg transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Running Backtest..." : "Run Backtest From Analysis"}
        </button>
        {!analysis ? <p className="mt-3 text-xs text-slate-400">Run Analysis first to enable this action.</p> : null}
      </Panel>

      {error ? (
        <Panel className="border-red/40 bg-red/10">
          <p className="text-sm text-red">{error}</p>
        </Panel>
      ) : null}

      {result ? (
        <>
          <Panel className="bg-panelSoft">
            <p className="text-sm text-slate-300">
              Backtest for {result.ticker} ({result.window.toUpperCase()}) on {result.market.toUpperCase()} using {result.strategy_mode_used} mode and threshold {result.score_threshold_used.toFixed(1)}.
              Warmup bars {result.analysis_config.warmup_bars}. Visible range: {result.visible_start} to {result.visible_end}.
            </p>
          </Panel>

          <Panel>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <button className={`h-9 rounded-lg px-3 text-sm ${chartTab === "trades" ? "bg-cyan text-bg" : "border border-stroke text-slate-300"}`} onClick={() => setChartTab("trades")}>
                Trades
              </button>
              <button className={`h-9 rounded-lg px-3 text-sm ${chartTab === "decision" ? "bg-cyan text-bg" : "border border-stroke text-slate-300"}`} onClick={() => setChartTab("decision")}>
                Skipped / Decision Map
              </button>
              {chartTab === "decision" ? (
                <select
                  value={decisionFilter}
                  onChange={(event) => setDecisionFilter(event.target.value as DecisionFilter)}
                  className="h-9 rounded-lg border border-stroke bg-bg px-3 text-sm"
                >
                  <option value="all">All</option>
                  <option value="threshold">Threshold</option>
                  <option value="regime">Regime</option>
                  <option value="location">Location</option>
                  <option value="trigger">Trigger</option>
                  <option value="watchlist">Watchlist</option>
                </select>
              ) : null}
            </div>
            <UnifiedAnalysisChart
              chart={result.chart}
              markers={activeMarkers}
              title={`${result.ticker} ${chartTab === "trades" ? "Trades" : "Decision Map"}`}
              markerMode={chartTab}
            />
          </Panel>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Trades" value={`${result.trades}`} />
            <StatCard label="Win Rate" value={`${result.win_rate.toFixed(2)}%`} />
            <StatCard label="Average Return" value={`${result.average_return.toFixed(2)}%`} />
            <StatCard label="Max Drawdown" value={`${result.max_drawdown.toFixed(2)}%`} />
            <StatCard label="Average Hold" value={`${result.average_hold_days.toFixed(2)} days`} />
            <StatCard label="Expectancy" value={`${result.expectancy.toFixed(2)}%`} />
            <StatCard label="Entries Checked" value={`${result.entries_considered}`} />
            <StatCard label="Triggered Entries" value={`${result.entries_triggered}`} />
          </div>
          <Panel>
            <SectionTitle title="Scan Diagnostics" subtitle="Why setups were skipped" />
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard label="Skipped: Threshold" value={`${result.skipped_due_to_threshold}`} />
              <StatCard label="Skipped: Regime" value={`${result.skipped_regime}`} />
              <StatCard label="Skipped: Location" value={`${result.skipped_location}`} />
              <StatCard label="Skipped: Trigger" value={`${result.skipped_trigger}`} />
              <StatCard label="Skipped: Overextended" value={`${result.skipped_overextended}`} />
              <StatCard label="Skipped: Resist. Room" value={`${result.skipped_resistance_room}`} />
              <StatCard label="Skipped: Setup" value={`${result.skipped_due_to_setup}`} />
              <StatCard label="Visible" value={`${result.visible_start} > ${result.visible_end}`} />
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard label="Actionable Setups" value={`${result.actionable_setups}`} />
              <StatCard label="Watchlist Setups" value={`${result.watchlist_setups}`} />
              <StatCard label="Avoid Setups" value={`${result.avoid_setups}`} />
              <StatCard label="Pipeline Setup Status" value={analysis?.analysis_pipeline.setup_status ?? "n/a"} />
            </div>
          </Panel>
          <TradesTable trades={result.trades_table} />
          <Panel>
            <SectionTitle title="Decision Log (Sample)" subtitle="Skipped setups with numeric reasons" />
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-stroke text-left text-slate-400">
                    <th className="px-2 py-2">Date</th>
                    <th className="px-2 py-2">Score</th>
                    <th className="px-2 py-2">Mode</th>
                    <th className="px-2 py-2">Threshold</th>
                    <th className="px-2 py-2">Setup</th>
                    <th className="px-2 py-2">Failed Gate</th>
                    <th className="px-2 py-2">Reason</th>
                    <th className="px-2 py-2">Support%</th>
                    <th className="px-2 py-2">Room%</th>
                    <th className="px-2 py-2">Trigger</th>
                    <th className="px-2 py-2">Trend</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredDecisionRows.length === 0 ? (
                    <tr>
                      <td className="px-2 py-3 text-slate-400" colSpan={11}>No skipped setups sampled.</td>
                    </tr>
                  ) : (
                    filteredDecisionRows.map((row, idx) => (
                      <tr key={`${row.date}-${idx}`} className="border-b border-stroke/50">
                        <td className="px-2 py-2">{row.date}</td>
                        <td className="px-2 py-2">{row.final_score.toFixed(2)}</td>
                        <td className="px-2 py-2 capitalize">{row.strategy_mode_used}</td>
                        <td className="px-2 py-2">{row.threshold_used.toFixed(2)}</td>
                        <td className="px-2 py-2 capitalize">{row.setup_status.replaceAll("_", " ")}</td>
                        <td className="px-2 py-2">{row.first_failed_gate ?? "n/a"}</td>
                        <td className="max-w-[360px] px-2 py-2 text-xs text-slate-300">{row.reason_detail ?? row.reason}</td>
                        <td className="px-2 py-2">{row.support_distance_pct?.toFixed(2) ?? "n/a"}</td>
                        <td className="px-2 py-2">{row.resistance_room_pct?.toFixed(2) ?? "n/a"}</td>
                        <td className="px-2 py-2">{row.trigger_state ?? "n/a"} ({row.trigger_score?.toFixed(1) ?? "n/a"})</td>
                        <td className="px-2 py-2">{row.trend_state ?? "n/a"}</td>
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
