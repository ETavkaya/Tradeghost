"use client";

import { useState } from "react";
import { BacktestTrade } from "@/lib/types";
import { Panel, SectionTitle } from "@/components/ui";

export function TradesTable({ trades }: { trades: BacktestTrade[] }) {
  const [openRows, setOpenRows] = useState<Record<number, boolean>>({});

  const toggleRow = (tradeId: number) => {
    setOpenRows((prev) => ({ ...prev, [tradeId]: !prev[tradeId] }));
  };

  return (
    <Panel>
      <SectionTitle title="Trade List" subtitle="Primary audit fields are always visible. Expand rows for secondary details." />
      {trades.length === 0 ? (
        <p className="text-sm text-slate-400">No trades found for current sample.</p>
      ) : (
        <div className="space-y-3">
          {trades.map((trade) => {
            const rowOpen = !!openRows[trade.trade_id];
            return (
              <div key={`${trade.trade_id}-${trade.entry_date}`} className="rounded-xl border border-stroke/70 bg-panelSoft p-3">
                <div className="grid gap-2 md:grid-cols-9">
                  <div>
                    <p className="text-[11px] text-slate-400">Trade</p>
                    <p className="text-sm font-semibold">#{trade.trade_id}</p>
                  </div>
                  <div>
                    <p className="text-[11px] text-slate-400">Entry</p>
                    <p className="text-sm">{trade.entry_date}</p>
                  </div>
                  <div>
                    <p className="text-[11px] text-slate-400">Exit</p>
                    <p className="text-sm">{trade.exit_date}</p>
                  </div>
                  <div>
                    <p className="text-[11px] text-slate-400">Return</p>
                    <p className={`text-sm font-semibold ${trade.return_pct >= 0 ? "text-green" : "text-red"}`}>{trade.return_pct.toFixed(2)}%</p>
                  </div>
                  <div>
                    <p className="text-[11px] text-slate-400">Score@Entry</p>
                    <p className="text-sm">{trade.score_at_entry?.toFixed(2) ?? "N/A"}</p>
                  </div>
                  <div>
                    <p className="text-[11px] text-slate-400">Setup</p>
                    <p className="text-sm capitalize">{trade.setup_status?.replaceAll("_", " ") ?? "n/a"}</p>
                  </div>
                  <div>
                    <p className="text-[11px] text-slate-400">Result</p>
                    <p className="text-sm capitalize">{trade.result.replaceAll("_", " ")}</p>
                  </div>
                  <div className="md:col-span-2 md:text-right">
                    <button
                      type="button"
                      onClick={() => toggleRow(trade.trade_id)}
                      className="rounded-md border border-stroke px-3 py-1 text-xs text-slate-300 hover:text-cyan"
                    >
                      {rowOpen ? "Hide details" : "Show details"}
                    </button>
                  </div>
                </div>

                <div className="mt-3 grid gap-2 md:grid-cols-2">
                  <div className="rounded-lg border border-stroke/60 bg-bg/30 p-2">
                    <p className="text-[11px] text-slate-400">Entry Reason</p>
                    <p className="mt-1 text-sm text-slate-200">{trade.entry_reason ?? "N/A"}</p>
                  </div>
                  <div className="rounded-lg border border-stroke/60 bg-bg/30 p-2">
                    <p className="text-[11px] text-slate-400">Exit Reason</p>
                    <p className="mt-1 text-sm text-slate-200">{trade.exit_reason ?? "N/A"}</p>
                  </div>
                </div>

                {rowOpen ? (
                  <div className="mt-3 grid gap-2 rounded-lg border border-stroke/60 bg-bg/20 p-2 text-xs text-slate-300 md:grid-cols-4">
                    <p>Mode: <span className="capitalize">{trade.strategy_mode_used}</span></p>
                    <p>Threshold: {trade.threshold_used?.toFixed(2) ?? "N/A"}</p>
                    <p>Trend: {trade.trend_state ?? "N/A"}</p>
                    <p>Trigger: {trade.trigger_type ?? "N/A"} ({trade.trigger_state ?? "n/a"})</p>
                    <p>Support %: {trade.support_distance_pct?.toFixed(2) ?? "N/A"}</p>
                    <p>Room %: {trade.resistance_distance_pct?.toFixed(2) ?? "N/A"}</p>
                    <p>Hold: {trade.hold_days}d</p>
                    <p>Entry/Exit: ${trade.entry_price.toFixed(2)} / ${trade.exit_price.toFixed(2)}</p>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
    </Panel>
  );
}
