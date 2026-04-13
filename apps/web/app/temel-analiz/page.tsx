"use client";

import { useState } from "react";
import { TickerControls } from "@/components/ticker-controls";
import { api } from "@/lib/api";
import { AnalysisResponse } from "@/lib/types";
import { decisionBadgeClass, decisionFromScore, fmtNumber } from "@/lib/format";
import { Panel, Pill, SectionTitle } from "@/components/ui";

export default function TemelAnalizPage() {
  const [ticker, setTicker] = useState("MSFT");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      setAnalysis(await api.analyze(ticker));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch context.");
    } finally {
      setLoading(false);
    }
  };

  const marketCap = Number(analysis?.indicator_summary?.market_cap ?? NaN);
  const rangePos = Number(analysis?.indicator_summary?.range_pos_52w ?? 0.5);
  const close = Number(analysis?.indicator_summary?.close ?? 0);

  return (
    <main className="space-y-4">
      <TickerControls ticker={ticker} onTickerChange={setTicker} onSubmit={run} loading={loading} />

      {error ? (
        <Panel className="border-red/40 bg-red/10">
          <p className="text-red">{error}</p>
        </Panel>
      ) : null}

      {!analysis ? (
        <Panel>
          <SectionTitle title="Temel Analiz" subtitle="Context and basic stock information from deterministic backend output." />
        </Panel>
      ) : (
        <>
          <Panel className="grid gap-4 md:grid-cols-2">
            <div>
              <SectionTitle title={`${analysis.ticker} Context`} subtitle="Company name field not provided yet by backend metadata." />
              <p className="text-sm text-slate-400">Ticker</p>
              <p className="text-2xl font-bold">{analysis.ticker}</p>
              <p className="mt-3 text-sm text-slate-400">Current Price</p>
              <p className="text-2xl font-semibold">${fmtNumber(close)}</p>
              <p className="mt-3 text-sm text-slate-400">Market Cap</p>
              <p className="text-xl font-semibold">{Number.isFinite(marketCap) ? `$${fmtNumber(marketCap, 0)}` : "N/A"}</p>
              <div className="mt-4">
                <Pill className={decisionBadgeClass(analysis.final_score)}>{decisionFromScore(analysis.final_score)}</Pill>
              </div>
            </div>
            <Panel className="bg-bg">
              <p className="text-xs uppercase tracking-wide text-slate-400">52 Week Range Position</p>
              <div className="mt-4 h-3 rounded-full bg-panelSoft">
                <div className="h-3 rounded-full bg-gradient-to-r from-violet to-cyan" style={{ width: `${rangePos * 100}%` }} />
              </div>
              <p className="mt-2 text-sm text-slate-300">{(rangePos * 100).toFixed(1)}% within 52-week range</p>
              <p className="mt-4 text-xs text-slate-400">Context Score</p>
              <p className="text-3xl font-bold text-cyan">{fmtNumber(analysis.category_scores.context_score, 1)}/100</p>
            </Panel>
          </Panel>
          <Panel>
            <SectionTitle title="Fundamental / Context Summary" />
            <p className="text-sm text-slate-200">
              Context score is {fmtNumber(analysis.category_scores.context_score, 1)} with range position at{" "}
              {(rangePos * 100).toFixed(1)}%. Market cap is {Number.isFinite(marketCap) ? "available" : "not available"} in current
              feed.
            </p>
          </Panel>
        </>
      )}
    </main>
  );
}

