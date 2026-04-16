"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { UnifiedAnalysisChart } from "@/components/unified-analysis-chart";
import { ChartMapSectionCard, QuantEdgeSectionCard, SwingPulseSectionCard } from "@/components/unified-sections";
import { useAnalysisContext } from "@/components/analysis-context";
import { TickerControls } from "@/components/ticker-controls";
import { Panel, SectionTitle } from "@/components/ui";
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
            title={`${analysis.ticker} Unified Analysis (${analysis.market.toUpperCase()} • ${analysis.window.toUpperCase()})`}
          />

          <Panel className="flex flex-col gap-3 bg-gradient-to-r from-panelSoft to-panel md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-sm text-slate-400">Context</p>
              <p className="text-sm text-slate-200">
                Combined analysis generated for {analysis.ticker} ({analysis.market.toUpperCase()} • {analysis.window.toUpperCase()}) as of {analysis.as_of}. Strategy mode: {analysis.strategy_mode_used}.
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

          <QuantEdgeSectionCard analysis={analysis} />
          <SwingPulseSectionCard analysis={analysis} />
          <ChartMapSectionCard analysis={analysis} />
        </>
      ) : null}
    </main>
  );
}
