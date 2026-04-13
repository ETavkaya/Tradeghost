"use client";

import { useState } from "react";
import { TickerControls } from "@/components/ticker-controls";
import { api } from "@/lib/api";
import { AnalysisResponse } from "@/lib/types";
import { SummaryHero } from "@/components/summary-hero";
import { ScoreBars } from "@/components/score-bars";
import { IndicatorCards } from "@/components/indicator-cards";
import { AnalysisSummary } from "@/components/analysis-summary";
import { TradePlanCard } from "@/components/trade-plan-card";
import { Panel, SectionTitle } from "@/components/ui";

export default function QuantEdgePage() {
  const [ticker, setTicker] = useState("TSLA");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);

  const runAnalysis = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.analyze(ticker);
      setAnalysis(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run analysis.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="space-y-4">
      <TickerControls ticker={ticker} onTickerChange={setTicker} onSubmit={runAnalysis} loading={loading} />

      {error ? (
        <Panel className="border-red/40 bg-red/10">
          <SectionTitle title="Request Error" />
          <p className="text-sm text-red">{error}</p>
        </Panel>
      ) : null}

      {!analysis && !loading ? (
        <Panel>
          <SectionTitle title="QuantEdge" subtitle="Start with a ticker to generate a full suitability profile." />
        </Panel>
      ) : null}

      {loading ? (
        <Panel>
          <SectionTitle title="Analyzing..." subtitle="Fetching data, indicators, interpretation, and score." />
        </Panel>
      ) : null}

      {analysis ? (
        <>
          <SummaryHero analysis={analysis} />
          <div className="grid gap-4 xl:grid-cols-2">
            <ScoreBars scores={analysis.category_scores} />
            <TradePlanCard plan={analysis.trade_plan} />
          </div>
          <IndicatorCards analysis={analysis} />
          <AnalysisSummary analysis={analysis} />
        </>
      ) : null}
    </main>
  );
}

