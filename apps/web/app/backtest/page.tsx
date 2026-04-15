"use client";

import { useMemo, useState } from "react";
import { useAnalysisContext } from "@/components/analysis-context";
import { UnifiedAnalysisChart } from "@/components/unified-analysis-chart";
import { Panel, SectionTitle, StatCard } from "@/components/ui";
import { TradesTable } from "@/components/trades-table";
import { api } from "@/lib/api";
import { BacktestFromAnalysisResponse } from "@/lib/types";

export default function BacktestPage() {
  const { analysis } = useAnalysisContext();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BacktestFromAnalysisResponse | null>(null);

  const runBacktest = async () => {
    if (!analysis) return;
    setLoading(true);
    setError(null);
    try {
      const response = await api.backtestFromAnalysis({
        ticker: analysis.ticker,
        window: analysis.window,
        analysis_as_of: analysis.as_of,
        quantedge_final_score: analysis.quantedge.final_score,
        category_scores: analysis.quantedge.category_scores,
        swing_candidate: analysis.swingpulse.swing_candidate,
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
    return `${analysis.ticker} | ${analysis.window.toUpperCase()} | Analysis date ${analysis.as_of}`;
  }, [analysis]);

  return (
    <main className="space-y-4">
      <Panel>
        <SectionTitle title="Backtest" subtitle="Runs from active analysis context only" />
        <p className="text-sm text-slate-300">{contextLabel}</p>
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
              This backtest was generated from the current analysis configuration for {result.ticker} ({result.window.toUpperCase()})
              , anchored to analysis date {result.analysis_as_of}.
            </p>
          </Panel>
          <UnifiedAnalysisChart chart={result.chart} markers={result.markers} title={`${result.ticker} Backtest Chart`} />
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <StatCard label="Trades" value={`${result.trades}`} />
            <StatCard label="Win Rate" value={`${result.win_rate.toFixed(2)}%`} />
            <StatCard label="Average Return" value={`${result.average_return.toFixed(2)}%`} />
            <StatCard label="Max Drawdown" value={`${result.max_drawdown.toFixed(2)}%`} />
            <StatCard label="Average Hold" value={`${result.average_hold_days.toFixed(2)} days`} />
            <StatCard label="Expectancy" value={`${result.expectancy.toFixed(2)}%`} />
          </div>
          <TradesTable trades={result.trades_table} />
        </>
      ) : null}
    </main>
  );
}
