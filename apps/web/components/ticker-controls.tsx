"use client";

import { AnalysisWindow, MarketCode } from "@/lib/types";
import clsx from "clsx";

const MARKET_LABELS: Record<MarketCode, string> = {
  us: "US Stocks",
  bist: "BIST"
};

const QUICK_TICKERS: Record<MarketCode, string[]> = {
  us: ["TSLA", "NVDA", "AMD", "MSFT", "META", "AMZN", "AAPL", "GOOGL", "PLTR", "AVGO", "MU", "SMCI"],
  bist: ["THYAO", "EREGL", "ASELS", "TUPRS", "BIMAS", "SAHOL", "KCHOL", "AKBNK", "GARAN", "SISE", "KOZAL", "PETKM"]
};

const windows: { value: AnalysisWindow; label: string }[] = [
  { value: "5d", label: "5D" },
  { value: "1m", label: "1M" },
  { value: "3m", label: "3M" },
  { value: "6m", label: "6M" },
  { value: "1y", label: "1Y" },
  { value: "5y", label: "5Y" },
  { value: "10y", label: "10Y" }
];

type Props = {
  ticker: string;
  onTickerChange: (value: string) => void;
  onSubmit: () => void;
  market: MarketCode;
  onMarketChange: (market: MarketCode) => void;
  window?: AnalysisWindow;
  onWindowChange?: (window: AnalysisWindow) => void;
  buttonLabel?: string;
  loading?: boolean;
  disabled?: boolean;
  extraControls?: React.ReactNode;
};

export function TickerControls({
  ticker,
  onTickerChange,
  onSubmit,
  market,
  onMarketChange,
  window,
  onWindowChange,
  buttonLabel = "Analyze",
  loading,
  disabled,
  extraControls
}: Props) {
  const marketSamples = QUICK_TICKERS[market];

  return (
    <div className="space-y-3 rounded-2xl border border-stroke bg-panel p-4 md:p-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <input
          value={ticker}
          onChange={(event) => onTickerChange(event.target.value.toUpperCase())}
          className="h-11 w-full rounded-lg border border-stroke bg-bg px-3 text-sm outline-none ring-cyan/20 focus:ring-2 lg:max-w-sm"
          placeholder={market === "bist" ? "Enter symbol (e.g. THYAO)" : "Enter ticker (e.g. TSLA)"}
          list="analysis-ticker-suggestions"
        />
        <datalist id="analysis-ticker-suggestions">
          {marketSamples.map((sample) => (
            <option key={sample} value={sample} />
          ))}
        </datalist>

        <select
          value={market}
          onChange={(event) => onMarketChange(event.target.value as MarketCode)}
          className="h-11 rounded-lg border border-stroke bg-bg px-3 text-sm"
          aria-label="Market"
        >
          <option value="us">US Stocks</option>
          <option value="bist">BIST</option>
        </select>

        {window && onWindowChange ? (
          <select
            value={window}
            onChange={(event) => onWindowChange(event.target.value as AnalysisWindow)}
            className="h-11 rounded-lg border border-stroke bg-bg px-3 text-sm"
            aria-label="Lookback window"
          >
            {windows.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        ) : null}

        <button
          type="button"
          onClick={onSubmit}
          disabled={loading || !ticker || disabled}
          className="h-11 rounded-lg bg-cyan px-6 text-sm font-semibold text-bg transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Running..." : buttonLabel}
        </button>
        {extraControls ? <div className="flex flex-wrap gap-2">{extraControls}</div> : null}
      </div>

      <div className="flex items-center justify-between">
        <p className="text-xs text-slate-400">Quick symbols: {MARKET_LABELS[market]}</p>
        <div className="text-xs text-slate-500">Recent and favorites placeholders ready for phase 2</div>
      </div>

      <div className="flex flex-wrap gap-2">
        {marketSamples.map((sample) => {
          const isActive = ticker === sample;
          return (
            <button
              key={sample}
              type="button"
              onClick={() => onTickerChange(sample)}
              className={clsx(
                "rounded-full border px-3 py-1 text-xs transition",
                isActive
                  ? "border-cyan/60 bg-cyan/20 text-cyan"
                  : "border-stroke bg-panelSoft text-slate-300 hover:border-cyan/40 hover:text-cyan"
              )}
            >
              {sample}
            </button>
          );
        })}
      </div>
    </div>
  );
}
