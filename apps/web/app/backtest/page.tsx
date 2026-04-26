"use client";

import { useEffect, useMemo, useState } from "react";
import { useAnalysisContext } from "@/components/analysis-context";
import { UnifiedAnalysisChart } from "@/components/unified-analysis-chart";
import { Panel, SectionTitle, StatCard } from "@/components/ui";
import { TradesTable } from "@/components/trades-table";
import { api } from "@/lib/api";
import {
  AnalysisConfig,
  AnalysisWindow,
  BacktestFromAnalysisResponse,
  BacktestHistoryWindow,
  BacktestMarker,
  BacktestSnapshot,
  SkippedEntrySignal
} from "@/lib/types";

type ChartTab = "trades" | "decision";
type DecisionFilter = "all" | "watchlist" | "threshold" | "regime" | "location" | "trigger";
type ReviewStatus = "exploratory" | "candidate_strategy" | "issue_detected" | "approved_baseline";

function InfoHint({ label, text }: { label: string; text: string }) {
  return (
    <div className="group relative">
      <span className="text-xs text-slate-400">{label}</span>
      <span className="ml-1 inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-stroke text-[10px] text-slate-300">?</span>
      <div className="pointer-events-none absolute left-0 top-5 z-10 hidden w-64 rounded-lg border border-stroke bg-bg p-2 text-xs text-slate-300 shadow-2xl group-hover:block">
        {text}
      </div>
    </div>
  );
}

function decisionMarkerType(row: SkippedEntrySignal): string {
  if ((row.regime_reason_code ?? "").includes("transition") || (row.regime_reason_code ?? "") === "early_trend_rebuild") return "early_transition_skip";
  if ((row.first_failed_gate ?? "").includes("overextended")) return "overextended_fail";
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
      `Price vs EMA200: ${row.price_vs_ema200_pct?.toFixed(2) ?? "n/a"}%<br>` +
      `EMA200 slope: ${row.ema200_slope_state ?? "n/a"}<br>` +
      `EMA stack: ${row.ema_stack_alignment ?? "n/a"}<br>` +
      `Regime code: ${row.regime_reason_code ?? "n/a"}<br>` +
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
  const { analysis, setAnalysis } = useAnalysisContext();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BacktestFromAnalysisResponse | null>(null);
  const [chartTab, setChartTab] = useState<ChartTab>("trades");
  const [decisionFilter, setDecisionFilter] = useState<DecisionFilter>("all");
  const [historyWindow, setHistoryWindow] = useState<BacktestHistoryWindow>("2y");

  const [threshold, setThreshold] = useState(60);
  const [regimeMode, setRegimeMode] = useState("medium");
  const [supportMaxDistance, setSupportMaxDistance] = useState(5);
  const [minResistanceRoom, setMinResistanceRoom] = useState(2.5);
  const [minTriggerScore, setMinTriggerScore] = useState(65);
  const [over20, setOver20] = useState(5);
  const [over50, setOver50] = useState(8);
  const [over100, setOver100] = useState(11);
  const [over200, setOver200] = useState(15);
  const [snapshots, setSnapshots] = useState<BacktestSnapshot[]>([]);
  const [snapshotsLoading, setSnapshotsLoading] = useState(false);
  const [snapshotError, setSnapshotError] = useState<string | null>(null);
  const [savingSnapshot, setSavingSnapshot] = useState(false);
  const [selectedSnapshotId, setSelectedSnapshotId] = useState("");
  const [selectedSnapshot, setSelectedSnapshot] = useState<BacktestSnapshot | null>(null);
  const [reviewStatus, setReviewStatus] = useState<ReviewStatus>("exploratory");
  const [experimentGroup, setExperimentGroup] = useState("");
  const [commentator, setCommentator] = useState("local-user");
  const [commentText, setCommentText] = useState("");
  const [commentTags, setCommentTags] = useState("");
  const [addingComment, setAddingComment] = useState(false);

  const loadSnapshots = async () => {
    setSnapshotsLoading(true);
    setSnapshotError(null);
    try {
      const rows = await api.listBacktestSnapshots();
      setSnapshots(rows);
      if (!selectedSnapshotId && rows.length > 0) {
        setSelectedSnapshotId(rows[0].id);
        setSelectedSnapshot(rows[0]);
      }
    } catch (err) {
      setSnapshotError(err instanceof Error ? err.message : "Failed to load snapshots.");
    } finally {
      setSnapshotsLoading(false);
    }
  };

  useEffect(() => {
    void loadSnapshots();
  }, []);

  useEffect(() => {
    if (!analysis) return;
    setThreshold(analysis.analysis_config.score_threshold);
    setRegimeMode(analysis.analysis_config.regime_filter.regime_mode);
    setSupportMaxDistance(analysis.analysis_config.location_filter.max_support_distance_pct);
    setMinResistanceRoom(analysis.analysis_config.location_filter.min_resistance_room_pct);
    setMinTriggerScore(analysis.analysis_config.trigger_filter.min_trigger_score);
    setOver20(analysis.analysis_config.location_filter.max_overextension_ema20_pct);
    setOver50(analysis.analysis_config.location_filter.max_overextension_ema50_pct);
    setOver100(analysis.analysis_config.location_filter.max_overextension_ema100_pct);
    setOver200(analysis.analysis_config.location_filter.max_overextension_ema200_pct);
  }, [analysis]);

  const buildTunedConfig = (): AnalysisConfig | null => {
    if (!analysis) return null;
    return {
      ...analysis.analysis_config,
      score_threshold: threshold,
      regime_filter: { regime_mode: regimeMode },
      location_filter: {
        ...analysis.analysis_config.location_filter,
        max_support_distance_pct: supportMaxDistance,
        min_resistance_room_pct: minResistanceRoom,
        max_overextension_ema20_pct: over20,
        max_overextension_ema50_pct: over50,
        max_overextension_ema100_pct: over100,
        max_overextension_ema200_pct: over200,
      },
      trigger_filter: {
        ...analysis.analysis_config.trigger_filter,
        min_trigger_score: minTriggerScore,
      },
    };
  };

  const runBacktest = async () => {
    if (!analysis) return;
    const tunedConfig = buildTunedConfig();
    if (!tunedConfig) return;

    setLoading(true);
    setError(null);
    try {
      setAnalysis({
        ...analysis,
        analysis_config: tunedConfig,
        strategy_mode_used: tunedConfig.strategy_mode,
      });

      const response = await api.backtestFromAnalysis({
        ticker: analysis.ticker,
        market: analysis.market,
        window: analysis.window,
        analysis_as_of: analysis.as_of,
        analysis_config: tunedConfig,
        quantedge_final_score: analysis.quantedge.final_score,
        category_scores: analysis.quantedge.category_scores,
        swing_candidate: analysis.swingpulse.swing_candidate,
        backtest_score_threshold: tunedConfig.score_threshold,
        strategy_mode: tunedConfig.strategy_mode,
        backtest_history_window: historyWindow,
        visible_chart_window: historyWindow as AnalysisWindow,
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

  const saveSnapshot = async () => {
    if (!result) return;
    setSavingSnapshot(true);
    setSnapshotError(null);
    try {
      const created = await api.saveBacktestSnapshot(result, reviewStatus, experimentGroup || undefined);
      setSnapshots((prev) => [created, ...prev.filter((row) => row.id !== created.id)]);
      setSelectedSnapshotId(created.id);
      setSelectedSnapshot(created);
    } catch (err) {
      setSnapshotError(err instanceof Error ? err.message : "Failed to save snapshot.");
    } finally {
      setSavingSnapshot(false);
    }
  };

  const onSnapshotChange = async (snapshotId: string) => {
    setSelectedSnapshotId(snapshotId);
    if (!snapshotId) {
      setSelectedSnapshot(null);
      return;
    }
    try {
      const row = await api.getBacktestSnapshot(snapshotId);
      setSelectedSnapshot(row);
      setSnapshots((prev) => prev.map((item) => (item.id === row.id ? row : item)));
    } catch (err) {
      setSnapshotError(err instanceof Error ? err.message : "Failed to load snapshot.");
    }
  };

  const addComment = async () => {
    if (!selectedSnapshotId || !commentText.trim()) return;
    setAddingComment(true);
    setSnapshotError(null);
    try {
      const tags = commentTags
        .split(",")
        .map((item) => item.trim())
        .filter((item) => item.length > 0);
      const updated = await api.addBacktestSnapshotComment(selectedSnapshotId, commentator, commentText, tags);
      setSelectedSnapshot(updated);
      setSnapshots((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setCommentText("");
      setCommentTags("");
    } catch (err) {
      setSnapshotError(err instanceof Error ? err.message : "Failed to add comment.");
    } finally {
      setAddingComment(false);
    }
  };

  const contextLabel = useMemo(() => {
    if (!analysis) return "No active analysis context.";
    return `${analysis.ticker} | ${analysis.market.toUpperCase()} | Analysis window ${analysis.window.toUpperCase()} | Analysis date ${analysis.as_of}`;
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

  const renderedDecisionMarkerCount = chartTab === "decision" ? activeMarkers.length : 0;
  const decisionClusterStats = useMemo(() => {
    if (!result) return { regime: 0, overextended: 0, transition: 0 };
    const rows = result.decision_log_sample;
    return {
      regime: rows.filter((row) => (row.first_failed_gate ?? "") === "regime_filter").length,
      overextended: rows.filter((row) => (row.first_failed_gate ?? "") === "overextended_filter").length,
      transition: rows.filter((row) => (row.regime_reason_code ?? "").includes("transition") || (row.regime_reason_code ?? "") === "early_trend_rebuild").length,
    };
  }, [result]);
  const visibleTradeCount = useMemo(() => {
    if (!result) return 0;
    const visibleStart = new Date(result.visible_start);
    const visibleEnd = new Date(result.visible_end);
    const ids = new Set<number>();
    for (const trade of result.trades_table) {
      const entryInRange = new Date(trade.entry_date) >= visibleStart && new Date(trade.entry_date) <= visibleEnd;
      const exitInRange = new Date(trade.exit_date) >= visibleStart && new Date(trade.exit_date) <= visibleEnd;
      if (entryInRange || exitInRange) {
        ids.add(trade.trade_id);
      }
    }
    return ids.size;
  }, [result]);

  const tunedConfig = useMemo(() => buildTunedConfig(), [
    analysis,
    threshold,
    regimeMode,
    supportMaxDistance,
    minResistanceRoom,
    minTriggerScore,
    over20,
    over50,
    over100,
    over200,
  ]);

  const pendingChanges = useMemo(() => {
    if (!result || !tunedConfig) return false;
    return JSON.stringify(tunedConfig) !== JSON.stringify(result.analysis_config);
  }, [result, tunedConfig]);

  return (
    <main className="space-y-4">
      <Panel className={pendingChanges ? "border-amber-400/40" : undefined}>
        <SectionTitle title="Backtest Tuning (Editable)" subtitle="Edit pending parameters, then run to apply them into engine state" />
        <p className="text-sm text-slate-300">{contextLabel}</p>
        <div className="mt-2">
          <span className={`rounded-md px-2 py-1 text-xs ${pendingChanges ? "bg-amber-500/15 text-amber-300 border border-amber-400/40" : "bg-slate-800 text-slate-300 border border-stroke"}`}>
            {pendingChanges ? "Pending changes (not applied yet)" : "No pending changes"}
          </span>
        </div>
        <div className="mt-3 grid gap-3 md:grid-cols-4">
          <label className="space-y-1 text-sm">
            <InfoHint label="Evaluation History" text="How much history is evaluated by the strategy engine (1Y to 5Y)." />
            <select
              value={historyWindow}
              onChange={(event) => setHistoryWindow(event.target.value as BacktestHistoryWindow)}
              className="h-10 w-full rounded-lg border border-stroke bg-bg px-3"
            >
              <option value="1y">1Y</option>
              <option value="2y">2Y</option>
              <option value="3y">3Y</option>
              <option value="4y">4Y</option>
              <option value="5y">5Y</option>
            </select>
          </label>
          <StatCard label="Visible Chart Window" value={historyWindow.toUpperCase()} />
          <StatCard label="Mode" value={analysis?.analysis_config.strategy_mode ?? "n/a"} />
          <StatCard label="Threshold (pending)" value={`${threshold.toFixed(1)}`} />
        </div>

        <div className="mt-3 grid gap-3 md:grid-cols-3 xl:grid-cols-5">
          <label className="space-y-1 text-sm">
            <InfoHint label="Threshold" text="Minimum final score required before additional entry gates can pass." />
            <input className="h-10 w-full rounded-lg border border-stroke bg-bg px-3" type="number" value={threshold} onChange={(event) => setThreshold(Number(event.target.value))} />
          </label>
          <label className="space-y-1 text-sm">
            <InfoHint label="Regime Strictness" text="EMA regime filter strictness. Relaxed allows transitions, strict needs stronger alignment." />
            <select className="h-10 w-full rounded-lg border border-stroke bg-bg px-3" value={regimeMode} onChange={(event) => setRegimeMode(event.target.value)}>
              <option value="relaxed">Relaxed</option>
              <option value="medium">Medium</option>
              <option value="strict">Strict</option>
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <InfoHint label="Support Max %" text="Maximum allowed distance from nearest support before location quality fails." />
            <input className="h-10 w-full rounded-lg border border-stroke bg-bg px-3" type="number" step="0.1" value={supportMaxDistance} onChange={(event) => setSupportMaxDistance(Number(event.target.value))} />
          </label>
          <label className="space-y-1 text-sm">
            <InfoHint label="Min Resistance %" text="Required upside room to nearest resistance level before entry is allowed." />
            <input className="h-10 w-full rounded-lg border border-stroke bg-bg px-3" type="number" step="0.1" value={minResistanceRoom} onChange={(event) => setMinResistanceRoom(Number(event.target.value))} />
          </label>
          <label className="space-y-1 text-sm">
            <InfoHint label="Trigger Min" text="Minimum trigger score required for timing confirmation." />
            <input className="h-10 w-full rounded-lg border border-stroke bg-bg px-3" type="number" step="0.1" value={minTriggerScore} onChange={(event) => setMinTriggerScore(Number(event.target.value))} />
          </label>
          <label className="space-y-1 text-sm">
            <InfoHint label="Overext EMA20 %" text="Maximum extension above EMA20 before overextension filtering triggers." />
            <input className="h-10 w-full rounded-lg border border-stroke bg-bg px-3" type="number" step="0.1" value={over20} onChange={(event) => setOver20(Number(event.target.value))} />
          </label>
          <label className="space-y-1 text-sm">
            <InfoHint label="Overext EMA50 %" text="Maximum extension above EMA50 before overextension filtering triggers." />
            <input className="h-10 w-full rounded-lg border border-stroke bg-bg px-3" type="number" step="0.1" value={over50} onChange={(event) => setOver50(Number(event.target.value))} />
          </label>
          <label className="space-y-1 text-sm">
            <InfoHint label="Overext EMA100 %" text="Maximum extension above EMA100 before overextension filtering triggers." />
            <input className="h-10 w-full rounded-lg border border-stroke bg-bg px-3" type="number" step="0.1" value={over100} onChange={(event) => setOver100(Number(event.target.value))} />
          </label>
          <label className="space-y-1 text-sm">
            <InfoHint label="Overext EMA200 %" text="Maximum extension above EMA200 before overextension filtering triggers." />
            <input className="h-10 w-full rounded-lg border border-stroke bg-bg px-3" type="number" step="0.1" value={over200} onChange={(event) => setOver200(Number(event.target.value))} />
          </label>
        </div>
        <p className="mt-2 text-xs text-slate-400">Editable values are pending until rerun. Effective engine config updates only after a completed backtest run.</p>

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
          <Panel>
            <SectionTitle title="Backtest Scope" subtitle="Evaluation, fetched warmup, and visible windows are separated" />
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
              <StatCard label="Evaluation History" value={result.evaluation_history_window.toUpperCase()} />
              <StatCard label="Evaluation Range" value={`${result.evaluation_start} > ${result.evaluation_end}`} />
              <StatCard label="Fetched/Warmup Data" value={`${result.fetched_data_range_start} > ${result.fetched_data_range_end}`} />
              <StatCard label="Visible Chart Window" value={result.visible_chart_window.toUpperCase()} />
              <StatCard label="Visible Chart Range" value={`${result.visible_start} > ${result.visible_end}`} />
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard label="Warmup Bars" value={`${result.warmup_bars_used}`} />
              <StatCard label="Evaluated Bars" value={`${result.evaluated_bars}`} />
              <StatCard label="Max Hold Days Used" value={`${result.max_hold_days_used}`} />
              <StatCard label="Decision Rows (sample)" value={`${result.decision_log_sample.length}`} />
              <StatCard label="Rendered Decision Markers" value={`${renderedDecisionMarkerCount}`} />
            </div>
          </Panel>

          <Panel>
            <SectionTitle title="Effective Engine Config (Read-only Snapshot)" subtitle="This is the exact config used by the most recent run" />
            <div className="rounded-xl border border-stroke/70 bg-panelSoft p-3 text-xs text-slate-300">
              Market: {result.analysis_config.market.toUpperCase()} | Mode: {result.analysis_config.strategy_mode} | Threshold: {result.analysis_config.score_threshold.toFixed(1)} | Warmup bars: {result.analysis_config.warmup_bars} | Regime: {result.analysis_config.regime_filter.regime_mode}.{" "}
              Support max: {result.analysis_config.location_filter.max_support_distance_pct.toFixed(2)}%. Resistance min room: {result.analysis_config.location_filter.min_resistance_room_pct.toFixed(2)}%.
              Overextension caps (EMA20/50/100/200):{" "}
              {result.analysis_config.location_filter.max_overextension_ema20_pct.toFixed(2)}% / {result.analysis_config.location_filter.max_overextension_ema50_pct.toFixed(2)}% / {result.analysis_config.location_filter.max_overextension_ema100_pct.toFixed(2)}% / {result.analysis_config.location_filter.max_overextension_ema200_pct.toFixed(2)}%.
              Trigger minimum score: {result.analysis_config.trigger_filter.min_trigger_score.toFixed(1)}.
            </div>
          </Panel>

          <Panel className="bg-panelSoft">
            <p className="text-sm text-slate-300">
              Backtest for {result.ticker} ({result.window.toUpperCase()}) on {result.market.toUpperCase()} using {result.strategy_mode_used} mode and threshold {result.score_threshold_used.toFixed(1)}.
            </p>
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              <p className="text-xs text-slate-300">Total trades (evaluation history): {result.trades}</p>
              <p className="text-xs text-slate-300">Visible in chart window: {visibleTradeCount}</p>
            </div>
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
                  <option value="watchlist">Watchlist</option>
                  <option value="threshold">Threshold</option>
                  <option value="regime">Regime</option>
                  <option value="location">Location</option>
                  <option value="trigger">Trigger</option>
                </select>
              ) : null}
            </div>
            <UnifiedAnalysisChart
              chart={result.chart}
              markers={activeMarkers}
              title={`${result.ticker} ${chartTab === "trades" ? "Trades" : "Decision Map"}`}
              markerMode={chartTab}
            />
            {chartTab === "decision" ? (
              <div className="mt-2 grid gap-2 sm:grid-cols-3">
                <p className="rounded-md border border-stroke/70 bg-panelSoft px-2 py-1 text-xs text-slate-300">Regime skip cluster: {decisionClusterStats.regime}</p>
                <p className="rounded-md border border-stroke/70 bg-panelSoft px-2 py-1 text-xs text-slate-300">Overextended cluster: {decisionClusterStats.overextended}</p>
                <p className="rounded-md border border-stroke/70 bg-panelSoft px-2 py-1 text-xs text-slate-300">EMA200 transition cluster: {decisionClusterStats.transition}</p>
              </div>
            ) : null}
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
              <StatCard label="Skipped: Blowoff Ext" value={`${result.skipped_blowoff_extension}`} />
              <StatCard label="Skipped: Mom Dynamics" value={`${result.skipped_momentum_dynamics}`} />
              <StatCard label="Skipped: Resist. Room" value={`${result.skipped_resistance_room}`} />
              <StatCard label="Skipped: EMA200 Transition" value={`${result.skipped_ema200_transition}`} />
              <StatCard label="Transition Skip Share" value={`${result.early_transition_skip_share_pct.toFixed(2)}%`} />
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard label="Actionable Setups" value={`${result.actionable_setups}`} />
              <StatCard label="Watchlist Setups" value={`${result.watchlist_setups}`} />
              <StatCard label="Avoid Setups" value={`${result.avoid_setups}`} />
              <StatCard label="Early Transition Entries" value={`${result.early_trend_transition_entries}`} />
              <StatCard label="Momentum Entries" value={`${result.momentum_continuation_entries}`} />
              <StatCard label="Controlled Ext Entries" value={`${result.controlled_extension_entries}`} />
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              <StatCard label="Exit: Stop Loss" value={`${result.exit_stop_loss_count}`} />
              <StatCard label="Exit: Take Profit" value={`${result.exit_take_profit_count}`} />
              <StatCard label="Exit: Timeout" value={`${result.exit_timeout_count}`} />
              <StatCard label="Exit: Structure Break" value={`${result.exit_structure_break_count}`} />
              <StatCard label="Exit: Trailing EMA" value={`${result.exit_trailing_ema_count}`} />
            </div>
            <p className="mt-3 text-xs text-slate-300">
              Insight: {result.early_transition_skip_share_pct.toFixed(2)}% of skipped setups were EMA200 transition related.
            </p>
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
                    <th className="px-2 py-2">Setup Type</th>
                    <th className="px-2 py-2">Extension</th>
                    <th className="px-2 py-2">Support%</th>
                    <th className="px-2 py-2">Room%</th>
                    <th className="px-2 py-2">Trigger</th>
                    <th className="px-2 py-2">Trend</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredDecisionRows.length === 0 ? (
                    <tr>
                      <td className="px-2 py-3 text-slate-400" colSpan={13}>No skipped setups sampled.</td>
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
                        <td className="px-2 py-2">{row.setup_type ?? "n/a"}</td>
                        <td className="px-2 py-2">{(row.extension_state ?? "n/a").replaceAll("_", " ")}</td>
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
          <Panel>
            <SectionTitle title="Backtest Review Log" subtitle="Secondary workflow: save snapshots and annotate findings" />
            <div className="grid gap-3 md:grid-cols-4">
              <label className="space-y-1 text-sm">
                <span className="text-xs text-slate-400">Review Status</span>
                <select className="h-10 w-full rounded-lg border border-stroke bg-bg px-3" value={reviewStatus} onChange={(event) => setReviewStatus(event.target.value as ReviewStatus)}>
                  <option value="exploratory">exploratory</option>
                  <option value="candidate_strategy">candidate_strategy</option>
                  <option value="issue_detected">issue_detected</option>
                  <option value="approved_baseline">approved_baseline</option>
                </select>
              </label>
              <label className="space-y-1 text-sm md:col-span-2">
                <span className="text-xs text-slate-400">Experiment Group (optional)</span>
                <input className="h-10 w-full rounded-lg border border-stroke bg-bg px-3" value={experimentGroup} onChange={(event) => setExperimentGroup(event.target.value)} placeholder="ema200-transition-tests" />
              </label>
              <div className="flex items-end">
                <button type="button" onClick={saveSnapshot} disabled={savingSnapshot} className="h-10 w-full rounded-lg bg-cyan px-3 text-sm font-semibold text-bg disabled:opacity-50">
                  {savingSnapshot ? "Saving..." : "Save Snapshot"}
                </button>
              </div>
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <label className="space-y-1 text-sm">
                <span className="text-xs text-slate-400">Snapshot Selector</span>
                <select className="h-10 w-full rounded-lg border border-stroke bg-bg px-3" value={selectedSnapshotId} onChange={(event) => void onSnapshotChange(event.target.value)}>
                  <option value="">Select a snapshot</option>
                  {snapshots.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.timestamp.slice(0, 19)} | {row.symbol} | {row.mode} | {row.review_status}
                    </option>
                  ))}
                </select>
              </label>
              <div className="flex items-end">
                <button type="button" onClick={() => void loadSnapshots()} className="h-10 rounded-lg border border-stroke px-4 text-sm text-slate-300 hover:text-cyan">
                  {snapshotsLoading ? "Refreshing..." : "Refresh Logs"}
                </button>
              </div>
            </div>
            {snapshotError ? <p className="mt-2 text-xs text-red">{snapshotError}</p> : null}

            {selectedSnapshot ? (
              <div className="mt-3 space-y-3">
                <div className="rounded-xl border border-stroke/70 bg-panelSoft p-3 text-xs text-slate-300">
                  Snapshot {selectedSnapshot.id.slice(0, 8)} | trades {selectedSnapshot.metrics.total_trades} | win rate {selectedSnapshot.metrics.win_rate.toFixed(2)}% | expectancy {selectedSnapshot.metrics.expectancy.toFixed(2)}%.
                  Review: {selectedSnapshot.review_status}. Evaluation history: {selectedSnapshot.evaluation_history.toUpperCase()}. Visible window: {selectedSnapshot.visible_window.toUpperCase()}.
                </div>
                <div className="grid gap-3 md:grid-cols-3">
                  <label className="space-y-1 text-sm">
                    <span className="text-xs text-slate-400">Commentator</span>
                    <input className="h-10 w-full rounded-lg border border-stroke bg-bg px-3" value={commentator} onChange={(event) => setCommentator(event.target.value)} />
                  </label>
                  <label className="space-y-1 text-sm md:col-span-2">
                    <span className="text-xs text-slate-400">Tags (comma separated)</span>
                    <input className="h-10 w-full rounded-lg border border-stroke bg-bg px-3" value={commentTags} onChange={(event) => setCommentTags(event.target.value)} placeholder="entry_logic,ema200,overextension" />
                  </label>
                  <label className="space-y-1 text-sm md:col-span-3">
                    <span className="text-xs text-slate-400">Comment</span>
                    <textarea className="min-h-[88px] w-full rounded-lg border border-stroke bg-bg p-3" value={commentText} onChange={(event) => setCommentText(event.target.value)} placeholder="Write what should be tuned and why." />
                  </label>
                </div>
                <button type="button" onClick={addComment} disabled={addingComment || !commentText.trim()} className="h-10 rounded-lg border border-stroke px-4 text-sm text-slate-300 hover:text-cyan disabled:opacity-50">
                  {addingComment ? "Adding comment..." : "Add Comment"}
                </button>
                <div className="space-y-2">
                  <p className="text-sm text-slate-300">Comments</p>
                  {selectedSnapshot.comments.length === 0 ? (
                    <p className="text-xs text-slate-400">No comments yet.</p>
                  ) : (
                    selectedSnapshot.comments.map((row) => (
                      <div key={row.id} className="rounded-lg border border-stroke/70 bg-bg/30 p-2 text-xs text-slate-300">
                        <p>
                          <span className="font-semibold">{row.commentator}</span> | {row.timestamp.slice(0, 19)} | tags: {row.tags.join(", ") || "none"}
                        </p>
                        <p className="mt-1">{row.content}</p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            ) : null}
          </Panel>
        </>
      ) : null}
    </main>
  );
}
