import { AnalysisResponse } from "@/lib/types";
import { Panel, SectionTitle } from "@/components/ui";

type IndicatorCard = {
  label: string;
  value: string;
  interpretation: string;
};

function pickIndicators(analysis: AnalysisResponse): IndicatorCard[] {
  const summary = analysis.indicator_summary ?? {};
  const signals = analysis.interpreted_signals ?? {};
  return [
    {
      label: "RSI",
      value: Number(summary.rsi ?? 0).toFixed(2),
      interpretation: signals.rsi_state ?? "neutral"
    },
    {
      label: "MACD",
      value: Number(summary.macd_line ?? 0).toFixed(3),
      interpretation: signals.macd_state ?? "neutral"
    },
    {
      label: "OBV Slope",
      value: Number(summary.obv_slope ?? 0).toFixed(0),
      interpretation: signals.obv_state ?? "neutral"
    },
    {
      label: "ADX",
      value: Number(summary.adx ?? 0).toFixed(2),
      interpretation: signals.adx_state ?? "neutral"
    },
    {
      label: "ATR",
      value: Number(summary.atr ?? 0).toFixed(2),
      interpretation: signals.atr_state ?? "neutral"
    },
    {
      label: "Bollinger",
      value: Number(summary.bb_bandwidth ?? 0).toFixed(3),
      interpretation: signals.bollinger_state ?? "neutral"
    },
    {
      label: "Trend Alignment",
      value: String(summary.weekly_trend_aligned ?? false),
      interpretation: signals.weekly_alignment_state ?? "neutral"
    }
  ];
}

export function IndicatorCards({ analysis }: { analysis: AnalysisResponse }) {
  const cards = pickIndicators(analysis);
  return (
    <div className="rounded-2xl border border-stroke bg-panel p-4 md:p-5">
      <SectionTitle title="Indicator Interpretation" subtitle="Deterministic signal states from backend rules" />
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {cards.map((card) => (
          <Panel key={card.label} className="bg-panelSoft">
            <p className="text-xs uppercase tracking-wide text-slate-400">{card.label}</p>
            <p className="mt-1 text-xl font-semibold">{card.value}</p>
            <p className="mt-2 text-sm capitalize text-cyan">{card.interpretation.replaceAll("_", " ")}</p>
          </Panel>
        ))}
      </div>
    </div>
  );
}

