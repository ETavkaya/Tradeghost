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
          <p>Backtest scope workflow: evaluation history window, evaluation range, fetched/warmup data range, visible chart window, and visible chart range are reported separately.</p>
          <p>Trade scope workflow: summary trade count is across full evaluation history; chart markers are only for trades inside visible chart window.</p>
          <p>Decision map workflow: sampled skip decisions are evenly distributed across evaluated bars, then filtered by visible chart dates and selected gate filter.</p>
          <p>EMA200 regime diagnostics: reason code, price vs EMA200, EMA200 slope state, stack alignment, and bars since reclaim are emitted deterministically.</p>
          <p>Early trend transition rule: recent EMA200 reclaim setups can be tradeable when transition conditions pass stricter trigger checks; otherwise they are logged as transition-related skips.</p>
          <p>Mode logic: aggressive/balanced/conservative pullback presets, plus momentum_continuation and custom. Custom fields are explicit threshold/filter values, no hidden LLM rules.</p>
          <p>Momentum continuation path: controlled extension can be accepted when trend, dynamics, trigger, and volume checks pass; blowoff extension is rejected deterministically.</p>
          <p>Backtest review log workflow: each saved snapshot stores config, metrics, skip summary, and comment thread under logs/backtest_reviews for reproducible audits.</p>
        </div>
      </Panel>

      <Panel>
        <SectionTitle title="Glossary" subtitle="Strategy modes, setups, indicators, scanner metrics, alerts, and ratios" />
        <div className="space-y-3 text-sm text-slate-300">
          <p><strong>Strategy modes:</strong> aggressive/balanced/conservative are pullback-biased. momentum_continuation allows controlled extension when trend + dynamics + trigger align. custom exposes deterministic overrides.</p>
          <p><strong>Setup types:</strong> pullback continuation, momentum continuation, value rebuild, second breakout attempt, overextended monitor. Setup type is descriptive context, not an automatic trade command.</p>
          <p><strong>Indicators:</strong> EMA20/50/100/200 are trend anchors. RSI14 tracks momentum stretch. Volume Ratio 20 compares current volume to its 20-bar baseline.</p>
          <p><strong>Scanner metrics:</strong> Score = current structural quality. Dynamics = improving/accelerating/stable/weakening/deteriorating. vs EMA200 = price distance to long regime anchor.</p>
          <p><strong>Location metrics:</strong> Support% = distance to nearest support. Room% = upside room to nearest resistance. Higher room generally means better upside space.</p>
          <p><strong>Alert terms:</strong> Alert Rule = condition being watched. Alert Event = rule trigger instance. Triggered value = numeric/string value that caused the trigger.</p>
          <p><strong>Alert meaning types:</strong> opportunity, risk warning, exit watch, momentum watch, info. Each event now includes plain-English meaning + suggested action.</p>
          <p><strong>Watchlist terms:</strong> Watchlist stores symbols and monitoring metrics. last_checked shows most recent monitoring update for that symbol.</p>
          <p><strong>Financial ratios:</strong> PD/DD (price/book), F/K (price/earnings). Lower valuation can support value-rebuild context, but never overrides structure checks by itself.</p>
          <p><strong>P/L:</strong> watchlist profit/loss since added price. If original tick price is unavailable, nearest close is used and marked estimated.</p>
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
            <p>Momentum config: min score {analysis.analysis_config.momentum_continuation.momentum_min_score.toFixed(1)} | min volume ratio {analysis.analysis_config.momentum_continuation.momentum_min_volume_ratio.toFixed(2)} | required dynamics {analysis.analysis_config.momentum_continuation.required_dynamics_state.join(", ")}.</p>
            <p>Mode presets: aggressive (50 / relaxed / support 7.5 / resistance 1.5 / trigger 55), balanced (60 / medium / 5.0 / 2.5 / 65), conservative (72 / strict / 3.5 / 3.5 / 75), momentum_continuation (66 / medium / support 8.5 / resistance 1.0 / trigger 70), custom (editable shared config).</p>
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
