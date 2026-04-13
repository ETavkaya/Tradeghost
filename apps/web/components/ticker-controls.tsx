"use client";

const samples = ["TSLA", "NVDA", "AMD", "MSFT", "META", "AMZN", "AAPL", "GOOGL"];

type Props = {
  ticker: string;
  onTickerChange: (value: string) => void;
  onSubmit: () => void;
  loading?: boolean;
  extraControls?: React.ReactNode;
};

export function TickerControls({ ticker, onTickerChange, onSubmit, loading, extraControls }: Props) {
  return (
    <div className="space-y-3 rounded-2xl border border-stroke bg-panel p-4 md:p-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <input
          value={ticker}
          onChange={(event) => onTickerChange(event.target.value.toUpperCase())}
          className="h-11 w-full rounded-lg border border-stroke bg-bg px-3 text-sm outline-none ring-cyan/20 focus:ring-2 lg:max-w-md"
          placeholder="Enter ticker (e.g. TSLA)"
        />
        <button
          type="button"
          onClick={onSubmit}
          disabled={loading || !ticker}
          className="h-11 rounded-lg bg-cyan px-6 text-sm font-semibold text-bg transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Analyzing..." : "Analyze"}
        </button>
        {extraControls ? <div className="flex flex-wrap gap-2">{extraControls}</div> : null}
      </div>
      <div className="flex flex-wrap gap-2">
        {samples.map((sample) => (
          <button
            key={sample}
            type="button"
            onClick={() => onTickerChange(sample)}
            className="rounded-full border border-stroke bg-panelSoft px-3 py-1 text-xs text-slate-300 transition hover:border-cyan/40 hover:text-cyan"
          >
            {sample}
          </button>
        ))}
      </div>
    </div>
  );
}

