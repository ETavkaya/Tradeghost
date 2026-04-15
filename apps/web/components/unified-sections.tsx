import { CombinedAnalysisResponse } from "@/lib/types";
import { fmtNumber } from "@/lib/format";
import { Panel, Pill, SectionTitle } from "@/components/ui";
import { ScoreBars } from "@/components/score-bars";

export function QuantEdgeSectionCard({ analysis }: { analysis: CombinedAnalysisResponse }) {
  return (
    <Panel>
      <SectionTitle title="QuantEdge" subtitle="Score engine and interpretation" />
      <div className="grid gap-3 md:grid-cols-2">
        <Panel className="bg-panelSoft">
          <p className="text-xs text-slate-400">Final Score</p>
          <p className="mt-1 text-4xl font-bold text-cyan">{fmtNumber(analysis.quantedge.final_score, 1)}/100</p>
          <p className="mt-2 text-sm text-slate-300">{analysis.quantedge.summary_interpretation}</p>
        </Panel>
        <Panel className="bg-panelSoft">
          <p className="text-xs text-slate-400">Structured Breakdown</p>
          <div className="mt-2 space-y-2 text-sm text-slate-200">
            {Object.entries(analysis.quantedge.structured_score_breakdown).map(([key, value]) => (
              <div key={key} className="flex items-center justify-between">
                <span className="capitalize">{key}</span>
                <span className="font-semibold text-cyan">{fmtNumber(value * 100, 2)}%</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>
      <div className="mt-3">
        <ScoreBars scores={analysis.quantedge.category_scores} />
      </div>
    </Panel>
  );
}

export function SwingPulseSectionCard({ analysis }: { analysis: CombinedAnalysisResponse }) {
  const swing = analysis.swingpulse;
  return (
    <Panel>
      <SectionTitle title="SwingPulse" subtitle="Setup and trade levels" />
      <div className="mb-3 flex items-center gap-3">
        <Pill className={swing.swing_candidate ? "border-green/40 bg-green/15 text-green" : "border-red/40 bg-red/15 text-red"}>
          {swing.swing_candidate ? "Swing Candidate" : "No Valid Setup"}
        </Pill>
        <span className="text-sm text-slate-300">Setup quality: {fmtNumber(swing.setup_quality, 1)}</span>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <Panel className="bg-panelSoft">
          <p className="text-xs text-slate-400">Entry Zone</p>
          <p className="mt-1 font-semibold">
            ${fmtNumber(swing.entry_zone[0])} - ${fmtNumber(swing.entry_zone[1])}
          </p>
        </Panel>
        <Panel className="bg-panelSoft">
          <p className="text-xs text-slate-400">Stop Loss</p>
          <p className="mt-1 font-semibold text-red">${fmtNumber(swing.stop_loss)}</p>
        </Panel>
        <Panel className="bg-panelSoft">
          <p className="text-xs text-slate-400">Risk / Reward</p>
          <p className="mt-1 font-semibold">{fmtNumber(swing.risk_reward, 2)}</p>
        </Panel>
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <Panel className="bg-panelSoft">
          <p className="text-xs text-slate-400">Take Profit Levels</p>
          <p className="mt-1 font-semibold text-green">
            {swing.take_profit_levels.map((price) => `$${fmtNumber(price)}`).join(" / ")}
          </p>
        </Panel>
        <Panel className="bg-panelSoft">
          <p className="text-xs text-slate-400">Invalidation</p>
          <p className="mt-1 text-sm text-slate-200">{swing.invalidation_note}</p>
        </Panel>
      </div>
    </Panel>
  );
}

export function ChartMapSectionCard({ analysis }: { analysis: CombinedAnalysisResponse }) {
  const map = analysis.chartmap;
  return (
    <Panel>
      <SectionTitle title="ChartMap" subtitle="Structure and level mapping" />
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <Panel className="bg-panelSoft">
          <p className="text-xs text-slate-400">EMA Proximity</p>
          <p className="mt-1 text-sm text-slate-200">{map.ema_proximity_summary}</p>
        </Panel>
        <Panel className="bg-panelSoft">
          <p className="text-xs text-slate-400">Nearest Support</p>
          <p className="mt-1 font-semibold">{map.nearest_support ? `$${fmtNumber(map.nearest_support)}` : "N/A"}</p>
        </Panel>
        <Panel className="bg-panelSoft">
          <p className="text-xs text-slate-400">Nearest Resistance</p>
          <p className="mt-1 font-semibold">{map.nearest_resistance ? `$${fmtNumber(map.nearest_resistance)}` : "N/A"}</p>
        </Panel>
        <Panel className="bg-panelSoft">
          <p className="text-xs text-slate-400">Nearest Fib Zone</p>
          <p className="mt-1 font-semibold">{map.nearest_fib_zone ?? "N/A"}</p>
        </Panel>
        <Panel className="bg-panelSoft">
          <p className="text-xs text-slate-400">State</p>
          <p className="mt-1 font-semibold capitalize">{map.market_state}</p>
        </Panel>
        <Panel className="bg-panelSoft">
          <p className="text-xs text-slate-400">Candle Confirmation</p>
          <p className="mt-1 text-sm text-slate-200">{map.candle_confirmation_summary}</p>
        </Panel>
      </div>
      <div className="mt-3 overflow-x-auto rounded-xl border border-stroke">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="border-b border-stroke bg-bg text-left text-slate-400">
              <th className="px-3 py-2">Level</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Value</th>
            </tr>
          </thead>
          <tbody>
            {map.detected_levels.map((row, idx) => (
              <tr key={`${row.level_name}-${idx}`} className="border-b border-stroke/40">
                <td className="px-3 py-2">{row.level_name}</td>
                <td className="px-3 py-2 capitalize">{row.level_type}</td>
                <td className="px-3 py-2">${fmtNumber(row.value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
