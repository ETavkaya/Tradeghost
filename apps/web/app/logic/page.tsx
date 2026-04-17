import { Panel, SectionTitle } from "@/components/ui";

export default function LogicPage() {
  return (
    <main className="space-y-4">
      <Panel>
        <SectionTitle title="Engine Logic" subtitle="Phase 1 deterministic transparency" />
        <div className="space-y-2 text-sm text-slate-300">
          <p>Official pipeline:</p>
          <p>1) fetch_data 2) calculate_indicators 3) calculate_category_scores 4) evaluate_threshold_gate 5) evaluate_regime_gate 6) evaluate_location_gate 7) evaluate_trigger_gate 8) compute_final_entry_decision</p>
          <p>Strategy modes: aggressive, balanced, conservative, custom (custom inherits balanced values unless overridden).</p>
          <p>Setup status:</p>
          <p>actionable = gates aligned, watchlist = structure interesting but confirmation incomplete, avoid = weak/extended/limited room.</p>
          <p>Skip reasons include numeric details such as support distance, resistance room, trigger score, and threshold mismatch.</p>
          <p>Phase 1 is deterministic and rule-based. No LLM logic is used in decision flow.</p>
        </div>
      </Panel>
    </main>
  );
}
