import { CategoryScores } from "@/lib/types";
import { SectionTitle } from "@/components/ui";

const labels: [keyof CategoryScores, string][] = [
  ["momentum_score", "Momentum"],
  ["trend_score", "Trend"],
  ["volatility_score", "Volatility"],
  ["structure_score", "Structure"],
  ["context_score", "Context"]
];

export function ScoreBars({ scores }: { scores: CategoryScores }) {
  return (
    <div className="rounded-2xl border border-stroke bg-panel p-4 md:p-5">
      <SectionTitle title="Category Scores" subtitle="Normalized 0-100 category scores" />
      <div className="space-y-3">
        {labels.map(([key, label]) => {
          const value = Math.max(0, Math.min(100, scores[key]));
          return (
            <div key={key}>
              <div className="mb-1 flex items-center justify-between text-sm">
                <span className="text-slate-300">{label}</span>
                <span className="font-medium text-cyan">{value.toFixed(1)}</span>
              </div>
              <div className="h-2 rounded-full bg-bg">
                <div
                  className="h-2 rounded-full bg-gradient-to-r from-violet to-cyan"
                  style={{ width: `${value}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

