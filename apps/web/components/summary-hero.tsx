import { decisionBadgeClass, decisionFromScore, fmtNumber } from "@/lib/format";
import { AnalysisResponse } from "@/lib/types";
import { Pill, Panel } from "@/components/ui";

type Props = {
  analysis: AnalysisResponse;
};

export function SummaryHero({ analysis }: Props) {
  const close = Number(analysis.indicator_summary?.close ?? 0);
  const badgeText = decisionFromScore(analysis.final_score);
  return (
    <Panel className="bg-gradient-to-r from-panelSoft to-panel">
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <p className="text-sm text-slate-400">Swing Suitability Overview</p>
          <h2 className="mt-1 text-3xl font-bold tracking-tight">{analysis.ticker}</h2>
          <p className="mt-2 text-slate-300">As of {analysis.as_of}</p>
          <div className="mt-4">
            <Pill className={decisionBadgeClass(analysis.final_score)}>{badgeText}</Pill>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Panel className="bg-bg">
            <p className="text-xs uppercase tracking-wide text-slate-400">Final Score</p>
            <p className="mt-2 text-4xl font-bold text-cyan">{fmtNumber(analysis.final_score, 1)}/100</p>
          </Panel>
          <Panel className="bg-bg">
            <p className="text-xs uppercase tracking-wide text-slate-400">Current Price</p>
            <p className="mt-2 text-3xl font-semibold">${fmtNumber(close)}</p>
          </Panel>
        </div>
      </div>
    </Panel>
  );
}

