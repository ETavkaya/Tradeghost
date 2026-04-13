import { AnalysisResponse } from "@/lib/types";
import { Panel, SectionTitle } from "@/components/ui";

export function AnalysisSummary({ analysis }: { analysis: AnalysisResponse }) {
  const trend = analysis.category_scores.trend_score;
  const momentum = analysis.category_scores.momentum_score;
  const structure = analysis.category_scores.structure_score;
  const decision = analysis.swing_candidate ? "qualifies as a swing candidate" : "does not qualify as a swing candidate";

  const narrative = `Trend score is ${trend.toFixed(1)}, momentum is ${momentum.toFixed(
    1
  )}, and structure is ${structure.toFixed(1)}. Based on the deterministic rules, ${analysis.ticker} currently ${decision}.`;

  return (
    <Panel>
      <SectionTitle title="Deterministic Summary" subtitle="Generated directly from current backend outputs" />
      <p className="text-sm leading-7 text-slate-200">{narrative}</p>
    </Panel>
  );
}

