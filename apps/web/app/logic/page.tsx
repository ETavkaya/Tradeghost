"use client";

import { useAnalysisContext } from "@/components/analysis-context";
import { Panel, SectionTitle } from "@/components/ui";

export default function LogicPage() {
  const { analysis } = useAnalysisContext();

  return (
    <main className="space-y-4">
      <Panel>
        <SectionTitle title="Engine Logic" subtitle="Deterministic workflow transparency" />
        <div className="space-y-2 text-sm text-slate-300">
          <p>Official pipeline:</p>
          <p>1) fetch_data 2) calculate_indicators 3) calculate_category_scores 4) evaluate_threshold_gate 5) evaluate_regime_gate 6) evaluate_location_gate 7) evaluate_trigger_gate 8) compute_final_entry_decision</p>
          <p>Shared config model: analysis and backtest both use the same AnalysisConfig object. Backtest tuning rewrites this shared object before rerun.</p>
          <p>Backtest scope workflow: evaluation history window (1Y-5Y) can differ from visible chart window. This is intentional and shown in Backtest Scope.</p>
          <p>Trade scope workflow: summary trade count is across full evaluation history; chart markers are only for trades inside visible chart window.</p>
          <p>Decision map workflow: sampled skip decisions are evenly distributed across evaluated bars, then filtered by visible chart dates and selected gate filter.</p>
          <p>EMA200 regime diagnostics: reason code, price vs EMA200, EMA200 slope state, stack alignment, and bars since reclaim are emitted deterministically.</p>
          <p>Mode logic: aggressive/balanced/conservative presets plus custom. Custom fields are explicit threshold/filter values, no hidden LLM rules.</p>
        </div>
      </Panel>

      {analysis ? (
        <Panel>
          <SectionTitle title="Active Config" subtitle="Current thresholds and filters from analysis context" />
          <div className="space-y-2 text-sm text-slate-300">
            <p>Mode: {analysis.analysis_config.strategy_mode} | Threshold: {analysis.analysis_config.score_threshold.toFixed(1)} | Warmup: {analysis.analysis_config.warmup_bars}</p>
            <p>Regime strictness: {analysis.analysis_config.regime_filter.regime_mode}</p>
            <p>Support max distance: {analysis.analysis_config.location_filter.max_support_distance_pct.toFixed(2)}%</p>
            <p>Minimum resistance room: {analysis.analysis_config.location_filter.min_resistance_room_pct.toFixed(2)}%</p>
            <p>Trigger minimum score: {analysis.analysis_config.trigger_filter.min_trigger_score.toFixed(1)}</p>
            <p>Overextension caps EMA20/50/100/200: {analysis.analysis_config.location_filter.max_overextension_ema20_pct.toFixed(2)}% / {analysis.analysis_config.location_filter.max_overextension_ema50_pct.toFixed(2)}% / {analysis.analysis_config.location_filter.max_overextension_ema100_pct.toFixed(2)}% / {analysis.analysis_config.location_filter.max_overextension_ema200_pct.toFixed(2)}%</p>
          </div>
        </Panel>
      ) : (
        <Panel>
          <p className="text-sm text-slate-400">Run analysis to view active thresholds, mode, and filter values here.</p>
        </Panel>
      )}
    </main>
  );
}
