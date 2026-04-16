"use client";

import { useMemo, useState } from "react";
import { useAnalysisContext } from "@/components/analysis-context";
import { UnifiedAnalysisChart } from "@/components/unified-analysis-chart";
import { Panel, SectionTitle, StatCard } from "@/components/ui";
import { TradesTable } from "@/components/trades-table";
import { api } from "@/lib/api";
import { BacktestFromAnalysisResponse, StrategyMode } from "@/lib/types";

const THRESHOLD_PRESETS = [
  { label: "Aggressive", value: 40 },
  { label: "Balanced", value: 60 },
  { label: "Conservative", value: 75 }
];

export default function BacktestPage() {
  const { analysis } = useAnalysisContext();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BacktestFromAnalysisResponse | null>(null);
  const [scoreThreshold, setScoreThreshold] = useState(60);
  const [strategyMode, setStrategyMode] = useState<StrategyMode>(analysis?.strategy_mode_used ?? "balanced");

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
        quantedge_final_score: analysis.quantedge.final_score,
        category_scores: analysis.quantedge.category_scores,
        swing_candidate: analysis.swingpulse.swing_candidate,
        backtest_score_threshold: scoreThreshold,
        strategy_mode: strategyMode,
        trade_plan: analysis.chart.trade_plan_overlay ?? {
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

  return (
    <main className="space-y-4">
      <Panel>
        <SectionTitle title="Backtest" subtitle="Runs from active analysis context only" />
        <p className="text-sm text-slate-300">{contextLabel}</p>

        <div className="mt-4 rounded-xl border border-stroke/70 bg-panelSoft p-3">
          <p className="text-xs text-slate-400">Strategy Mode</p>
          <div className="mt-2 grid gap-2 sm:grid-cols-3">
            <button
              type="button"
              onClick={() => setStrategyMode("aggressive")}
              className={`rounded-md px-3 py-1.5 text-xs font-semibold transition ${
                strategyMode === "aggressive" ? "bg-cyan text-bg" : "bg-bg text-slate-300 hover:bg-stroke/60"
              }`}
            >
              Aggressive
            </button>
            <button
              type="button"
              onClick={() => setStrategyMode("balanced")}
              className={`rounded-md px-3 py-1.5 text-xs font-semibold transition ${
                strategyMode === "balanced" ? "bg-cyan text-bg" : "bg-bg text-slate-300 hover:bg-stroke/60"
              }`}
            >
              Balanced
            </button>
            <button
              type="button"
              onClick={() => setStrategyMode("conservative")}
              className={`rounded-md px-3 py-1.5 text-xs font-semibold transition ${
                strategyMode === "conservative" ? "bg-cyan text-bg" : "bg-bg text-slate-300 hover:bg-stroke/60"
              }`}
            >
              Conservative
            </button>
          </div>
        </div>

        <div className="mt-4 rounded-xl border border-stroke/70 bg-panelSoft p-3">
          <p className="text-xs text-slate-400">Score Threshold (entry filter)</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {THRESHOLD_PRESETS.map((preset) => (
              <button
                key={preset.label}
                type="button"
                onClick={() => setScoreThreshold(preset.value)}
                className={`rounded-md px-3 py-1.5 text-xs font-semibold transition ${
                  scoreThreshold === preset.value ? "bg-cyan text-bg" : "bg-bg text-slate-300 hover:bg-stroke/60"
                }`}
              >
                {preset.label} ({preset.value})
              </button>
            ))}
          </div>
          <div className="mt-3 grid gap-2 md:grid-cols-[1fr_auto] md:items-center">
            <input
              type="range"
              min={20}
              max={90}
              value={scoreThreshold}
              onChange={(event) => setScoreThreshold(Number(event.target.value))}
              className="w-full"
            />
            <div className="rounded-md border border-stroke bg-bg px-3 py-1 text-sm font-semibold text-cyan">{scoreThreshold}</div>
          </div>
        </div>

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
              Backtest for {result.ticker} ({result.window.toUpperCase()}) on {result.market.toUpperCase()} using {result.strategy_mode_used} mode and threshold {result.score_threshold_used.toFixed(0)}.
              Visible range: {result.visible_start} to {result.visible_end}. Warm-up bars used: {result.warmup_bars_used}.
            </p>
          </Panel>
          <UnifiedAnalysisChart chart={result.chart} markers={result.markers} title={`${result.ticker} Backtest Chart`} />
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
              <StatCard label="Visible" value={`${result.visible_start} › ${result.visible_end}`} />
            </div>
          </Panel>
          <TradesTable trades={result.trades_table} />
        </>
      ) : null}
    </main>
  );
}
