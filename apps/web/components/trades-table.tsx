import { BacktestTrade } from "@/lib/types";
import { Panel, SectionTitle } from "@/components/ui";

export function TradesTable({ trades }: { trades: BacktestTrade[] }) {
  return (
    <Panel>
      <SectionTitle title="Trade List" subtitle="Sample trade outcomes from the backtest engine" />
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-stroke text-left text-slate-400">
              <th className="px-2 py-2">Entry Date</th>
              <th className="px-2 py-2">Exit Date</th>
              <th className="px-2 py-2">Entry</th>
              <th className="px-2 py-2">Exit</th>
              <th className="px-2 py-2">Return %</th>
              <th className="px-2 py-2">Hold</th>
              <th className="px-2 py-2">Result</th>
            </tr>
          </thead>
          <tbody>
            {trades.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-2 py-4 text-slate-400">
                  No trades found for current sample.
                </td>
              </tr>
            ) : (
              trades.map((trade, index) => (
                <tr key={`${trade.entry_date}-${index}`} className="border-b border-stroke/50">
                  <td className="px-2 py-2">{trade.entry_date}</td>
                  <td className="px-2 py-2">{trade.exit_date}</td>
                  <td className="px-2 py-2">${trade.entry_price.toFixed(2)}</td>
                  <td className="px-2 py-2">${trade.exit_price.toFixed(2)}</td>
                  <td className={`px-2 py-2 ${trade.return_pct >= 0 ? "text-green" : "text-red"}`}>
                    {trade.return_pct.toFixed(2)}%
                  </td>
                  <td className="px-2 py-2">{trade.hold_days}d</td>
                  <td className="px-2 py-2 capitalize">{trade.result.replaceAll("_", " ")}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

