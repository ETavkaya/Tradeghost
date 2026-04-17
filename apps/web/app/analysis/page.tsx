"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { UnifiedAnalysisChart } from "@/components/unified-analysis-chart";
import { ChartMapSectionCard, QuantEdgeSectionCard, SwingPulseSectionCard } from "@/components/unified-sections";
import { useAnalysisContext } from "@/components/analysis-context";
import { TickerControls } from "@/components/ticker-controls";
import { Panel, SectionTitle, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import { AnalysisWindow, MarketCode, StrategyMode } from "@/lib/types";

export default function AnalysisPage() {
  const router = useRouter();
  const { analysis, setAnalysis } = useAnalysisContext();
  const [ticker, setTicker] = useState(analysis?.ticker ?? "TSLA");
  const [market, setMarket] = useState<MarketCode>(analysis?.market ?? "us");
  const [window, setWindow] = useState<AnalysisWindow>(analysis?.window ?? "6m");
  const [strategyMode, setStrategyMode] = useState<StrategyMode>(analysis?.strategy_mode_used ?? "balanced");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onAnalyze = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.analyzeCombined(ticker, market, window, strategyMode);
      setAnalysis(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run analysis.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="space-y-4">
      <TickerControls
        ticker={ticker}
        onTickerChange={setTicker}
        market={market}
        onMarketChange={(nextMarket) => {
          setMarket(nextMarket);
          if (nextMarket === "bist" && ticker.endsWith(".IS")) {
            setTicker(ticker.replace(".IS", ""));
          }
        }}
        window={window}
        onWindowChange={setWindow}
        onSubmit={onAnalyze}
        loading={loading}
        buttonLabel="Analyze"
        extraControls={
          <select
            value={strategyMode}
            onChange={(event) => setStrategyMode(event.target.value as StrategyMode)}
            className="h-11 rounded-lg border border-stroke bg-bg px-3 text-sm"
            aria-label="Strategy mode"
          >
            <option value="aggressive">Aggressive</option>
            <option value="balanced">Balanced</option>
            <option value="conservative">Conservative</option>
            <option value="custom">Custom</option>
          </select>
        }
      />

      {error ? (
        <Panel className="border-red/40 bg-red/10">
          <SectionTitle title="Request Error" />
          <p className="text-sm text-red">{error}</p>
        </Panel>
      ) : null}

      {!analysis && !loading ? (
        <Panel>
          <SectionTitle title="Unified Analysis" subtitle="Run one analysis flow to generate QuantEdge, SwingPulse, and ChartMap together." />
          <p className="text-sm text-slate-300">Backtest is unlocked after a successful analysis run.</p>
        </Panel>
      ) : null}

      {analysis ? (
        <>
          <UnifiedAnalysisChart
            chart={analysis.chart}
            title={`${analysis.ticker} Unified Analysis (${analysis.market.toUpperCase()} - ${analysis.window.toUpperCase()})`}
          />

          <Panel className="flex flex-col gap-3 bg-gradient-to-r from-panelSoft to-panel md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-sm text-slate-400">Context</p>
              <p className="text-sm text-slate-200">
                Combined analysis generated for {analysis.ticker} ({analysis.market.toUpperCase()} - {analysis.window.toUpperCase()}) as of {analysis.as_of}. Strategy mode: {analysis.strategy_mode_used}.
              </p>
            </div>
            <button
              type="button"
              onClick={() => router.push("/backtest")}
              className="h-10 rounded-lg bg-cyan px-5 text-sm font-semibold text-bg transition hover:brightness-110"
            >
              Open Backtest From This Analysis
            </button>
          </Panel>

          <Panel>
            <SectionTitle title="Analysis Config" subtitle="Official shared config and entry gate result" />
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
              <StatCard label="Market" value={analysis.analysis_config.market.toUpperCase()} />
              <StatCard label="Window" value={analysis.analysis_config.lookback_window.toUpperCase()} />
              <StatCard label="Mode" value={analysis.analysis_config.strategy_mode} />
              <StatCard label="Threshold" value={`${analysis.analysis_config.score_threshold.toFixed(1)}`} />
              <StatCard label="Warmup Bars" value={`${analysis.analysis_config.warmup_bars}`} />
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
              <StatCard label="Threshold Passed" value={analysis.analysis_pipeline.threshold_passed ? "Yes" : "No"} />
              <StatCard label="Regime Valid" value={analysis.analysis_pipeline.regime_valid ? "Yes" : "No"} />
              <StatCard label="Location Valid" value={analysis.analysis_pipeline.location_valid ? "Yes" : "No"} />
              <StatCard label="Trigger Valid" value={analysis.analysis_pipeline.trigger_valid ? "Yes" : "No"} />
              <StatCard label="Final Entry" value={analysis.analysis_pipeline.final_entry_decision ? "Yes" : "No"} />
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard label="Trend State" value={analysis.setup_interpretation.trend_state} />
              <StatCard label="Pullback State" value={analysis.setup_interpretation.pullback_state} />
              <StatCard label="Trigger State" value={analysis.setup_interpretation.trigger_state} />
              <StatCard label="Setup Status" value={analysis.setup_interpretation.setup_status} />
            </div>
            <div className="mt-3 rounded-xl border border-stroke/70 bg-panelSoft p-3 text-xs text-slate-300">
              Regime mode: {analysis.analysis_config.regime_filter.regime_mode}. Support max: {analysis.analysis_config.location_filter.max_support_distance_pct.toFixed(2)}%.
              Resistance min room: {analysis.analysis_config.location_filter.min_resistance_room_pct.toFixed(2)}%. Overextension caps (EMA20/50/100):
              {" "}{analysis.analysis_config.location_filter.max_overextension_ema20_pct.toFixed(2)}% /
              {" "}{analysis.analysis_config.location_filter.max_overextension_ema50_pct.toFixed(2)}% /
              {" "}{analysis.analysis_config.location_filter.max_overextension_ema100_pct.toFixed(2)}%.
              Trigger minimum score: {analysis.analysis_config.trigger_filter.min_trigger_score.toFixed(1)}.
            </div>
          </Panel>

          <QuantEdgeSectionCard analysis={analysis} />
          <SwingPulseSectionCard analysis={analysis} />
          <ChartMapSectionCard analysis={analysis} />
        </>
      ) : null}
    </main>
  );
}
