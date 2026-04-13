"use client";

import { useState } from "react";
import { TickerControls } from "@/components/ticker-controls";
import { api } from "@/lib/api";
import { BacktestResponse } from "@/lib/types";
import { Panel, SectionTitle } from "@/components/ui";
import { BacktestSummaryCards } from "@/components/backtest-summary-cards";
import { EquityCurve } from "@/components/equity-curve";
import { TradesTable } from "@/components/trades-table";

export default function QEBacktestPage() {
  const [ticker, setTicker] = useState("TSLA");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<BacktestResponse | null>(null);
  const [fromDate, setFromDate] = useState("2023-01-01");
  const [toDate, setToDate] = useState("2026-01-01");

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.backtest(ticker));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Backtest request failed.");
    } finally {
      setLoading(false);
    }
  };

  const controls = (
    <>
      <input
        type="date"
        value={fromDate}
        onChange={(event) => setFromDate(event.target.value)}
        className="h-11 rounded-lg border border-stroke bg-bg px-3 text-sm"
      />
      <input
        type="date"
        value={toDate}
        onChange={(event) => setToDate(event.target.value)}
        className="h-11 rounded-lg border border-stroke bg-bg px-3 text-sm"
      />
    </>
  );

  return (
    <main className="space-y-4">
      <TickerControls ticker={ticker} onTickerChange={setTicker} onSubmit={run} loading={loading} extraControls={controls} />
      <Panel className="bg-panelSoft">
        <p className="text-xs text-slate-400">Date range controls are UI-ready. Current backend uses its default history window.</p>
      </Panel>
      {error ? (
        <Panel className="border-red/40 bg-red/10">
          <p className="text-red">{error}</p>
        </Panel>
      ) : null}
      {!data && !loading ? (
        <Panel>
          <SectionTitle title="QE Backtest" subtitle="Run QuantEdge-style historical score and strategy simulation." />
        </Panel>
      ) : null}
      {data ? (
        <>
          <BacktestSummaryCards data={data} />
          <EquityCurve data={data} />
          <TradesTable trades={data.sample_trades} />
        </>
      ) : null}
    </main>
  );
}

