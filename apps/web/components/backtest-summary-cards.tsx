import { BacktestResponse } from "@/lib/types";
import { StatCard } from "@/components/ui";

export function BacktestSummaryCards({ data }: { data: BacktestResponse }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      <StatCard label="Number of Trades" value={`${data.trades}`} />
      <StatCard label="Win Rate" value={`${data.win_rate.toFixed(2)}%`} />
      <StatCard label="Average Return" value={`${data.average_return.toFixed(2)}%`} />
      <StatCard label="Max Drawdown" value={`${data.max_drawdown.toFixed(2)}%`} />
      <StatCard label="Average Hold Duration" value={`${data.average_hold_days.toFixed(2)} days`} />
      <StatCard label="Expectancy" value={`${data.expectancy.toFixed(2)}%`} />
      <StatCard label="Score Threshold" value={`${data.score_threshold_used.toFixed(0)}`} />
      <StatCard label="Strategy Mode" value={data.strategy_mode_used} />
    </div>
  );
}
