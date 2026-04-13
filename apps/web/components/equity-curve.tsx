import { BacktestResponse } from "@/lib/types";
import { Panel, SectionTitle } from "@/components/ui";

export function EquityCurve({ data }: { data: BacktestResponse }) {
  const points = data.sample_trades.reduce<number[]>((acc, trade, index) => {
    const prev = index === 0 ? 100 : acc[index - 1];
    const next = prev * (1 + trade.return_pct / 100);
    acc.push(next);
    return acc;
  }, []);

  const values = [100, ...points];
  const max = Math.max(...values, 100);
  const min = Math.min(...values, 100);
  const range = Math.max(1, max - min);
  const width = 760;
  const height = 220;

  const polyline = values
    .map((value, i) => {
      const x = (i / Math.max(1, values.length - 1)) * (width - 20) + 10;
      const y = height - ((value - min) / range) * (height - 20) - 10;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <Panel>
      <SectionTitle
        title="Equity Curve"
        subtitle="Curve uses cumulative returns from sampled trades provided by backend."
      />
      <div className="rounded-xl border border-stroke bg-bg p-3">
        <svg viewBox={`0 0 ${width} ${height}`} className="h-56 w-full">
          <defs>
            <linearGradient id="eqLine" x1="0" x2="1" y1="0" y2="0">
              <stop offset="0%" stopColor="#8F7CFF" />
              <stop offset="100%" stopColor="#19D3F3" />
            </linearGradient>
          </defs>
          <polyline fill="none" stroke="url(#eqLine)" strokeWidth="3" points={polyline} />
        </svg>
      </div>
    </Panel>
  );
}

