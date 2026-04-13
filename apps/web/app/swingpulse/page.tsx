"use client";

import { useMemo, useState } from "react";
import { TickerControls } from "@/components/ticker-controls";
import { api } from "@/lib/api";
import { AnalysisResponse } from "@/lib/types";
import { Panel, Pill, SectionTitle } from "@/components/ui";
import { TradePlanCard } from "@/components/trade-plan-card";
import { fmtNumber } from "@/lib/format";

const holdOptions = ["1 week", "2 weeks", "1 month"];
const rrOptions = ["1:1.5", "1:2", "1:3"];
const atrOptions = ["1.5x", "2x", "2.5x"];

export default function SwingPulsePage() {
  const [ticker, setTicker] = useState("NVDA");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [holdPeriod, setHoldPeriod] = useState(holdOptions[0]);
  const [rrPreset, setRrPreset] = useState(rrOptions[1]);
  const [atrPreset, setAtrPreset] = useState(atrOptions[0]);

  const setupQuality = useMemo(() => {
    if (!analysis) return 0;
    const { momentum_score, trend_score, structure_score, volatility_score } = analysis.category_scores;
    return (momentum_score * 0.3 + trend_score * 0.35 + structure_score * 0.2 + volatility_score * 0.15).toFixed(1);
  }, [analysis]);

  const runAnalysis = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.analyze(ticker);
      setAnalysis(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch setup.");
    } finally {
      setLoading(false);
    }
  };

  const controls = (
    <>
      <select
        value={holdPeriod}
        onChange={(event) => setHoldPeriod(event.target.value)}
        className="h-11 rounded-lg border border-stroke bg-bg px-3 text-sm"
      >
        {holdOptions.map((option) => (
          <option key={option}>{option}</option>
        ))}
      </select>
      <select
        value={rrPreset}
        onChange={(event) => setRrPreset(event.target.value)}
        className="h-11 rounded-lg border border-stroke bg-bg px-3 text-sm"
      >
        {rrOptions.map((option) => (
          <option key={option}>{option}</option>
        ))}
      </select>
      <select
        value={atrPreset}
        onChange={(event) => setAtrPreset(event.target.value)}
        className="h-11 rounded-lg border border-stroke bg-bg px-3 text-sm"
      >
        {atrOptions.map((option) => (
          <option key={option}>{option}</option>
        ))}
      </select>
    </>
  );

  return (
    <main className="space-y-4">
      <TickerControls ticker={ticker} onTickerChange={setTicker} onSubmit={runAnalysis} loading={loading} extraControls={controls} />

      <Panel className="bg-panelSoft">
        <p className="text-xs text-slate-400">
          Presets are active at UI level for planning workflow. Current backend trade plan remains deterministic and fixed-rule.
        </p>
      </Panel>

      {error ? (
        <Panel className="border-red/40 bg-red/10">
          <p className="text-sm text-red">{error}</p>
        </Panel>
      ) : null}

      {analysis ? (
        <>
          <Panel className="grid gap-3 md:grid-cols-2">
            <div>
              <SectionTitle title="Trade Candidate" subtitle={`Ticker ${analysis.ticker}`} />
              <Pill className={analysis.swing_candidate ? "border-green/40 bg-green/20 text-green" : "border-red/40 bg-red/20 text-red"}>
                {analysis.swing_candidate ? "Candidate" : "No Setup"}
              </Pill>
              <p className="mt-3 text-sm text-slate-300">Final score: {fmtNumber(analysis.final_score, 1)}/100</p>
            </div>
            <Panel className="bg-bg">
              <p className="text-xs text-slate-400">Setup Quality Score</p>
              <p className="mt-1 text-4xl font-bold text-cyan">{setupQuality}/100</p>
              <p className="mt-2 text-xs text-slate-400">Momentum/trend/structure/volatility weighted blend</p>
            </Panel>
          </Panel>

          <TradePlanCard plan={analysis.trade_plan} title="SwingPulse Trade Setup" />

          <Panel>
            <SectionTitle title="Setup Confirmation" />
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <Panel className="bg-panelSoft">
                <p className="text-xs text-slate-400">Momentum Confirmation</p>
                <p className="mt-1 text-xl font-semibold">{fmtNumber(analysis.category_scores.momentum_score, 1)}</p>
              </Panel>
              <Panel className="bg-panelSoft">
                <p className="text-xs text-slate-400">Trend Confirmation</p>
                <p className="mt-1 text-xl font-semibold">{fmtNumber(analysis.category_scores.trend_score, 1)}</p>
              </Panel>
              <Panel className="bg-panelSoft">
                <p className="text-xs text-slate-400">Structure Confirmation</p>
                <p className="mt-1 text-xl font-semibold">{fmtNumber(analysis.category_scores.structure_score, 1)}</p>
              </Panel>
              <Panel className="bg-panelSoft">
                <p className="text-xs text-slate-400">Volatility Suitability</p>
                <p className="mt-1 text-xl font-semibold">{fmtNumber(analysis.category_scores.volatility_score, 1)}</p>
              </Panel>
            </div>
          </Panel>
        </>
      ) : (
        <Panel>
          <SectionTitle title="SwingPulse" subtitle="Analyze a ticker to evaluate setup quality and trade levels." />
        </Panel>
      )}
    </main>
  );
}

