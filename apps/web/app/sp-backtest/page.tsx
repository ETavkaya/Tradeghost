"use client";

import { useMemo, useState } from "react";
import { TickerControls } from "@/components/ticker-controls";
import { api } from "@/lib/api";
import { BacktestResponse } from "@/lib/types";
import { Panel, SectionTitle } from "@/components/ui";
import { BacktestSummaryCards } from "@/components/backtest-summary-cards";
import { EquityCurve } from "@/components/equity-curve";
import { TradesTable } from "@/components/trades-table";

export default function SPBacktestPage() {
  const [ticker, setTicker] = useState("AMD");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<BacktestResponse | null>(null);

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

  const outcomes = useMemo(() => {
    if (!data) return { wins: 0, losses: 0 };
    const wins = data.sample_trades.filter((t) => t.return_pct > 0).length;
    return { wins, losses: data.sample_trades.length - wins };
  }, [data]);

  return (
    <main className="space-y-4">
      <TickerControls ticker={ticker} onTickerChange={setTicker} onSubmit={run} loading={loading} />
      {error ? (
        <Panel className="border-red/40 bg-red/10">
          <p className="text-red">{error}</p>
        </Panel>
      ) : null}
      {!data && !loading ? (
        <Panel>
          <SectionTitle title="SP Backtest" subtitle="SwingPulse-style backtest view focused on entry and exit outcomes." />
        </Panel>
      ) : null}
      {data ? (
        <>
          <BacktestSummaryCards data={data} />
          <Panel className="grid gap-3 sm:grid-cols-2">
            <Panel className="bg-panelSoft">
              <p className="text-xs text-slate-400">Winning Sample Trades</p>
              <p className="text-3xl font-bold text-green">{outcomes.wins}</p>
            </Panel>
            <Panel className="bg-panelSoft">
              <p className="text-xs text-slate-400">Losing Sample Trades</p>
              <p className="text-3xl font-bold text-red">{outcomes.losses}</p>
            </Panel>
          </Panel>
          <EquityCurve data={data} />
          <TradesTable trades={data.sample_trades} />
        </>
      ) : null}
    </main>
  );
}

