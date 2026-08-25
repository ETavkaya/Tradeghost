"use client";

import { useEffect, useMemo, useState } from "react";
import { Panel, Pill, SectionTitle, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import type { ResearchCohortReadiness, ResearchDashboardResponse } from "@/lib/types";

function fmt(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  return String(value);
}

function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? "-" : `${value.toFixed(2)}%`;
}

function dateList(values: string[]): string {
  return values.length ? values.join(", ") : "none";
}

function errorText(err: unknown, fallback: string): string {
  if (!(err instanceof Error)) return fallback;
  try {
    const parsed = JSON.parse(err.message) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
    if (parsed.detail && typeof parsed.detail === "object") return JSON.stringify(parsed.detail);
  } catch {
    // Keep ordinary Error text.
  }
  return err.message || fallback;
}

function messageClass(severity: string): string {
  if (severity === "error") return "border-red/40 bg-red/10 text-red";
  if (severity === "warning") return "border-amber-300/40 bg-amber-300/10 text-amber-100";
  return "border-cyan/40 bg-cyan/10 text-cyan";
}

export default function ResearchPage() {
  const [dashboard, setDashboard] = useState<ResearchDashboardResponse | null>(null);
  const [selectedCohortId, setSelectedCohortId] = useState("");
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.getResearchDashboard();
      setDashboard(result);
      setSelectedCohortId((current) => current || result.cohorts[0]?.cohort.id || "");
    } catch (err) {
      setError(errorText(err, "Failed to load the research dashboard."));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const selected = useMemo<ResearchCohortReadiness | null>(
    () => dashboard?.cohorts.find((row) => row.cohort.id === selectedCohortId) ?? dashboard?.cohorts[0] ?? null,
    [dashboard, selectedCohortId]
  );
  const incompletePaths = dashboard?.cohorts.filter((row) => !row.daily_path_review_complete).length ?? 0;
  const lifecycleCount = (status: string) => dashboard?.cohorts.filter((row) => row.cohort.followup_status === status).length ?? 0;

  const downloadAudit = async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.exportResearchAudit(selected?.cohort.id);
      const blob = new Blob([JSON.stringify(result.payload, null, 2)], { type: "application/json;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = result.filename;
      anchor.click();
      URL.revokeObjectURL(url);
      setNotice(`Downloaded ${result.filename}. The export is a read-only deterministic audit snapshot.`);
    } catch (err) {
      setError(errorText(err, "Failed to export the research audit."));
    } finally {
      setLoading(false);
    }
  };

  const reviewHypothesis = async (hypothesisId: string, action: "accept" | "reject") => {
    const reviewerId = window.prompt("Human reviewer ID:");
    if (!reviewerId?.trim()) return;
    const reviewerNotes = window.prompt("Review notes (stored in the audit trail):", "") ?? "";
    setLoading(true);
    setError(null);
    try {
      await api.reviewResearchHypothesis(hypothesisId, action, reviewerId.trim(), reviewerNotes);
      setNotice(`Hypothesis ${action === "accept" ? "accepted for release review" : "rejected"} by ${reviewerId.trim()}. No scanner rule was changed.`);
      await load();
    } catch (err) {
      setError(errorText(err, "Hypothesis review failed."));
    } finally {
      setLoading(false);
    }
  };

  const reviewPattern = async (patternId: string, action: "approve" | "reject") => {
    const reviewerId = window.prompt("Human reviewer ID:");
    if (!reviewerId?.trim()) return;
    const reviewerNotes = window.prompt("Review notes (stored in the audit trail):", "") ?? "";
    setLoading(true);
    setError(null);
    try {
      await api.reviewResearchPattern(patternId, action, reviewerId.trim(), reviewerNotes);
      setNotice(`Pattern ${action === "approve" ? "approved for read-only retrieval" : "rejected"} by ${reviewerId.trim()}. No rule or graph fact was changed.`);
      await load();
    } catch (err) {
      setError(errorText(err, "Pattern review failed."));
    } finally {
      setLoading(false);
    }
  };

  const changeFollowupLifecycle = async (cohortId: string, action: "pause-followup" | "resume-followup" | "archive-followup") => {
    const reviewerId = window.prompt("Human reviewer ID (stored in the lifecycle audit):");
    if (!reviewerId?.trim()) return;
    const reason = action === "archive-followup"
      ? window.prompt("Archive reason (required and retained with the cohort):", "")
      : window.prompt("Reason (optional):", "");
    if (action === "archive-followup" && !reason?.trim()) return;
    const notes = window.prompt("Notes (optional, stored in the audit trail):", "") ?? "";
    setLoading(true);
    setError(null);
    try {
      const cohort = await api.changeCohortFollowupLifecycle(cohortId, action, {
        reviewer_id: reviewerId.trim(),
        reason: reason?.trim() ?? "",
        notes,
      });
      setNotice(`${cohort.name}: ${cohort.followup_status.replaceAll("_", " ")}. Predictions, outcomes, reports, and snapshots were preserved.`);
      await load();
    } catch (err) {
      setError(errorText(err, "Cohort tracking lifecycle update failed."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="space-y-4">
      <Panel>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <SectionTitle title="Research Operations" subtitle="Read-only experiment evidence, outcome readiness, audit exports, and human-gated reviews." />
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => void load()} disabled={loading} className="rounded-lg border border-stroke px-3 py-2 text-xs hover:text-cyan">
              Refresh
            </button>
            <button type="button" onClick={() => void downloadAudit()} disabled={loading} className="rounded-lg border border-cyan/50 bg-cyan/10 px-3 py-2 text-xs text-cyan">
              Export Audit JSON
            </button>
          </div>
        </div>
        <p className="mt-2 text-xs text-slate-400">This workspace never runs the scanner, creates predictions, evaluates prices, invokes an LLM, or changes production rules.</p>
        {notice ? <p className="mt-3 rounded-lg border border-cyan/40 bg-cyan/10 p-3 text-sm text-cyan">{notice}</p> : null}
        {error ? <p className="mt-3 rounded-lg border border-red/40 bg-red/10 p-3 text-sm text-red">{error}</p> : null}
      </Panel>

      <div className="grid gap-3 md:grid-cols-6">
        <StatCard label="Research DB" value={dashboard?.database_configured ? "Configured" : "Unavailable"} />
        <StatCard label="Active Tracking" value={String(lifecycleCount("active_tracking"))} />
        <StatCard label="Mature Tracking" value={String(lifecycleCount("mature_tracking"))} />
        <StatCard label="Paused" value={String(lifecycleCount("paused"))} />
        <StatCard label="Manually Archived" value={String(lifecycleCount("archived_manual"))} />
        <StatCard label="28D Review Ready" value={String(dashboard?.cohorts.filter((row) => Boolean(row.cohort.review_ready_28d_at)).length ?? 0)} />
      </div>

      {(dashboard?.operational_messages ?? []).map((message, index) => (
        <p key={`${message.code}-${message.cohort_id ?? "global"}-${index}`} className={`rounded-lg border p-3 text-sm ${messageClass(message.severity)}`}>
          {message.message}
        </p>
      ))}

      <Panel>
        <SectionTitle title="Cohort Readiness" subtitle="28D outcome availability and daily snapshot completeness are intentionally separate." />
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <label className="text-sm text-slate-300" htmlFor="research-cohort">Cohort</label>
          <select
            id="research-cohort"
            value={selected?.cohort.id ?? ""}
            onChange={(event) => setSelectedCohortId(event.target.value)}
            className="min-w-72 rounded-lg border border-stroke bg-panelSoft px-3 py-2 text-sm"
          >
            {(dashboard?.cohorts ?? []).map((row) => <option key={row.cohort.id} value={row.cohort.id}>{row.cohort.name} ({row.cohort.id.slice(0, 8)})</option>)}
          </select>
          <Pill className={selected?.coverage.backfill_required ? "border-amber-300/50 text-amber-100" : "border-cyan/50 text-cyan"}>{selected?.coverage.status ?? "loading"}</Pill>
          <span className="text-xs text-slate-400">Incomplete paths: {incompletePaths}</span>
        </div>
        {selected ? (
          <>
            <div className="grid gap-3 md:grid-cols-4">
              <StatCard label="Predictions" value={String(selected.prediction_count)} />
              <StatCard label="28D Available" value={`${selected.horizon_28d_available_count}/${selected.prediction_count}`} />
              <StatCard label="Snapshot Coverage" value={`${selected.coverage.complete_followup_days}/${selected.coverage.expected_followup_days} (${selected.coverage.snapshot_coverage_pct.toFixed(1)}%)`} />
              <StatCard label="Daily Path" value={selected.daily_path_review_complete ? "Complete" : "Incomplete"} />
            </div>
            <div className="mt-4 grid gap-3 text-sm md:grid-cols-2">
              <p><span className="text-slate-400">Readiness:</span> {selected.coverage.readiness_message}</p>
              <p><span className="text-slate-400">Tracking:</span> {selected.cohort.followup_status.replaceAll("_", " ")}; starts {selected.cohort.followup_started_at ?? selected.cohort.followup_start_date ?? "-"}</p>
              <p><span className="text-slate-400">28D evaluation:</span> {selected.horizon_28d_complete ? "all predictions evaluated" : `${selected.horizon_28d_pending_count} prediction(s) pending`}; excluded={selected.data_quality_excluded_outcome_count}</p>
              <p><span className="text-slate-400">Horizons:</span> available {selected.available_horizon_days.length ? selected.available_horizon_days.map((value) => `${value}D`).join(", ") : "none"}; next {selected.next_horizon_due_days ? `${selected.next_horizon_due_days}D on ${selected.next_horizon_due_date ?? "-"}` : "-"}</p>
              <p><span className="text-slate-400">Missing dates:</span> {dateList(selected.coverage.missing_followup_dates)}</p>
              <p><span className="text-slate-400">Partial dates:</span> {dateList(selected.coverage.partial_followup_dates)}</p>
              <p><span className="text-slate-400">Backfill dates:</span> {dateList(selected.coverage.backfill_dates)}</p>
              <p><span className="text-slate-400">Duplicate-state dates:</span> {dateList(selected.coverage.duplicate_snapshot_dates)}</p>
            </div>
          </>
        ) : <p className="text-sm text-slate-400">No cohorts are available yet.</p>}
      </Panel>

      <Panel>
        <SectionTitle title="Cohort Tracking" subtitle="28D is a review checkpoint. Tracking remains active until a human pauses or archives a cohort." />
        <div className="overflow-auto">
          <table className="min-w-full text-left text-xs">
            <thead className="text-slate-400"><tr><th className="px-2 py-2">Cohort</th><th className="px-2 py-2">Status</th><th className="px-2 py-2">Started / Latest</th><th className="px-2 py-2">Days / Coverage</th><th className="px-2 py-2">28D / Horizons</th><th className="px-2 py-2">Truth</th><th className="px-2 py-2">Actions</th></tr></thead>
            <tbody>{(dashboard?.cohorts ?? []).map((row) => <tr key={row.cohort.id} className="border-t border-stroke/60 align-top"><td className="px-2 py-2 font-medium">{row.cohort.name}<br /><span className="text-slate-500">{row.cohort.id.slice(0, 8)}</span></td><td className="px-2 py-2">{row.cohort.followup_status.replaceAll("_", " ")}</td><td className="px-2 py-2">{row.cohort.followup_started_at ?? row.cohort.followup_start_date ?? "-"}<br />{row.cohort.latest_followup_date ?? "-"}</td><td className="px-2 py-2">{row.coverage.complete_followup_days}/{row.coverage.expected_followup_days}<br />{row.coverage.snapshot_coverage_pct.toFixed(1)}%</td><td className="px-2 py-2">{row.cohort.review_ready_28d_at ? `ready ${row.cohort.review_ready_28d_at}` : "pending"}<br />latest={row.latest_available_horizon_days ? `${row.latest_available_horizon_days}D` : "-"}; next={row.next_horizon_due_days ? `${row.next_horizon_due_days}D` : "-"}</td><td className="px-2 py-2">{row.coverage.status}<br />{row.coverage.backfill_required ? "backfill required" : "coverage reported"}</td><td className="px-2 py-2"><div className="flex flex-wrap gap-1">{row.cohort.followup_status === "paused" ? <button type="button" disabled={loading} onClick={() => void changeFollowupLifecycle(row.cohort.id, "resume-followup")} className="rounded border border-cyan/50 px-2 py-1 text-cyan">Resume</button> : row.cohort.followup_status !== "archived_manual" ? <button type="button" disabled={loading} onClick={() => void changeFollowupLifecycle(row.cohort.id, "pause-followup")} className="rounded border border-amber-300/50 px-2 py-1 text-amber-100">Pause</button> : null}{row.cohort.followup_status !== "archived_manual" ? <button type="button" disabled={loading} onClick={() => void changeFollowupLifecycle(row.cohort.id, "archive-followup")} className="rounded border border-red/50 px-2 py-1 text-red">Archive</button> : <span className="text-slate-500">preserved</span>}</div></td></tr>)}</tbody>
          </table>
        </div>
      </Panel>

      {selected ? <>
        <Panel>
          <SectionTitle title="Immutable Predictions" subtitle="Frozen selection facts and provenance; these identifiers are projected to Neo4j through the committed outbox." />
          <div className="overflow-auto">
            <table className="min-w-full text-left text-xs">
              <thead className="text-slate-400"><tr><th className="px-2 py-2">Symbol</th><th className="px-2 py-2">Selection</th><th className="px-2 py-2">Setup / Categories</th><th className="px-2 py-2">Blocker</th><th className="px-2 py-2">Versions</th><th className="px-2 py-2">Provenance</th></tr></thead>
              <tbody>{selected.predictions.map((row) => <tr key={row.id} className="border-t border-stroke/60 align-top"><td className="px-2 py-2 font-medium">{row.symbol}<br /><span className="text-slate-500">{row.id.slice(0, 8)}</span></td><td className="px-2 py-2">{row.selected_date}<br />{fmt(row.selected_price)}</td><td className="px-2 py-2">{row.setup_type || "-"}<br /><span className="text-slate-400">{row.categories.join(", ") || "-"}</span></td><td className="px-2 py-2">{row.blocked_by ?? "none"}</td><td className="px-2 py-2">r:{row.rule_version}<br />f:{row.feature_version}<br />d:{row.data_version}</td><td className="px-2 py-2">report:{row.source_report_id?.slice(0, 8) ?? "-"}<br />regime:{row.selection_market_regime_id?.slice(0, 8) ?? "-"}</td></tr>)}</tbody>
            </table>
          </div>
        </Panel>

        <Panel>
          <SectionTitle title="Outcomes by Horizon" subtitle="Each deterministic horizon is separately labeled; 28D is a checkpoint, not the end of tracking." />
          <div className="overflow-auto">
            <table className="min-w-full text-left text-xs">
              <thead className="text-slate-400"><tr><th className="px-2 py-2">Symbol</th><th className="px-2 py-2">Horizon</th><th className="px-2 py-2">Outcome</th><th className="px-2 py-2">Return</th><th className="px-2 py-2">Daily Path</th><th className="px-2 py-2">Attribution / Regime</th><th className="px-2 py-2">DQ Flags</th></tr></thead>
              <tbody>{selected.outcomes.map((row) => <tr key={row.id} className="border-t border-stroke/60 align-top"><td className="px-2 py-2 font-medium">{row.symbol}<br /><span className="text-slate-500">{row.id.slice(0, 8)}</span></td><td className="px-2 py-2">{row.horizon_days}D</td><td className="px-2 py-2">{row.outcome_label}<br /><span className="text-slate-400">{row.outcome_date ?? "pending"}</span></td><td className="px-2 py-2">{pct(row.return_pct)}</td><td className="px-2 py-2">{row.daily_snapshot_path_complete ? "complete" : "incomplete"}<br /><span className="text-slate-400">{row.daily_snapshot_coverage_pct.toFixed(1)}%</span></td><td className="px-2 py-2">{row.attribution_label ?? "-"}<br /><span className="text-slate-400">{row.outcome_market_regime_id?.slice(0, 8) ?? "-"}</span></td><td className="px-2 py-2">{row.data_quality_flags.join(", ") || "none"}</td></tr>)}</tbody>
            </table>
          </div>
        </Panel>

        <Panel>
          <SectionTitle title="Outcome Summaries" subtitle="Category, setup, and blocker summaries include outcome counts and excluded data-quality records." />
          <div className="overflow-auto">
            <table className="min-w-full text-left text-xs">
              <thead className="text-slate-400"><tr><th className="px-2 py-2">Grouping</th><th className="px-2 py-2">Value</th><th className="px-2 py-2">Predictions</th><th className="px-2 py-2">Available</th><th className="px-2 py-2">DQ Excluded</th><th className="px-2 py-2">Avg Return</th></tr></thead>
              <tbody>{selected.outcome_summaries.map((row) => <tr key={`${row.grouping}-${row.group_value}-${row.rule_version}`} className="border-t border-stroke/60"><td className="px-2 py-2">{row.grouping}</td><td className="px-2 py-2">{row.group_value}</td><td className="px-2 py-2">{row.prediction_count}</td><td className="px-2 py-2">{row.available_outcome_count}</td><td className="px-2 py-2">{row.data_quality_excluded_count}</td><td className="px-2 py-2">{pct(row.average_return_pct)}</td></tr>)}</tbody>
            </table>
          </div>
        </Panel>
      </> : null}

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel>
          <SectionTitle title="Hypothesis Review" subtitle="A human review creates an append-only audit event; release approval never updates the production scanner." />
          <div className="space-y-3">{(dashboard?.hypotheses ?? []).map((row) => <div key={row.id} className="rounded-lg border border-stroke/70 p-3 text-sm"><div className="flex flex-wrap items-start justify-between gap-2"><div><p className="font-medium">{row.title}</p><p className="mt-1 text-xs text-slate-400">{row.status} · validation={row.latest_validation_id?.slice(0, 8) ?? "not run"} · author={row.submitted_by}</p></div><div className="flex gap-2">{row.status === "validated" ? <button type="button" onClick={() => void reviewHypothesis(row.id, "accept")} disabled={loading} className="rounded border border-cyan/50 px-2 py-1 text-xs text-cyan">Human Accept</button> : null}{!["rejected", "approved_for_release"].includes(row.status) ? <button type="button" onClick={() => void reviewHypothesis(row.id, "reject")} disabled={loading} className="rounded border border-red/50 px-2 py-1 text-xs text-red">Reject</button> : null}</div></div><p className="mt-2 text-xs text-slate-400">reviewer={row.reviewed_by ?? "pending"} · r:{row.rule_version} f:{row.feature_version} d:{row.data_version}</p></div>)}</div>
        </Panel>
        <Panel>
          <SectionTitle title="Pattern Review" subtitle="Only a statistically eligible candidate can be approved for read-only retrieval; no Pattern graph node is created here." />
          <div className="space-y-3">{(dashboard?.patterns ?? []).map((row) => <div key={row.id} className="rounded-lg border border-stroke/70 p-3 text-sm"><div className="flex flex-wrap items-start justify-between gap-2"><div><p className="font-medium">{row.pattern_key}</p><p className="mt-1 text-xs text-slate-400">{row.status} · n={row.sample_size}, evaluable={row.evaluable_case_count}, success={pct(row.success_rate_pct)}</p></div><div className="flex gap-2">{row.status === "candidate" && row.approval_eligible ? <button type="button" onClick={() => void reviewPattern(row.id, "approve")} disabled={loading} className="rounded border border-cyan/50 px-2 py-1 text-xs text-cyan">Human Approve</button> : null}{row.status === "candidate" ? <button type="button" onClick={() => void reviewPattern(row.id, "reject")} disabled={loading} className="rounded border border-red/50 px-2 py-1 text-xs text-red">Reject</button> : null}</div></div><p className="mt-2 text-xs text-slate-400">eligible={String(row.approval_eligible)} · reviewer={row.reviewed_by ?? "pending"} · r:{row.rule_version} f:{row.feature_version} d:{row.data_version}</p></div>)}</div>
        </Panel>
      </div>

      <Panel>
        <SectionTitle title="Pipeline Errors" subtitle="Latest persisted failures from the research and follow-up pipeline." />
        {(dashboard?.recent_pipeline_errors ?? []).length ? <div className="space-y-2">{dashboard?.recent_pipeline_errors.map((row) => <div key={row.id} className="rounded border border-red/30 bg-red/5 p-2 text-xs text-slate-300"><span className="text-red">{row.timestamp}</span> · {row.step_name} · {row.error_message ?? row.message ?? "unknown failure"}</div>)}</div> : <p className="text-sm text-slate-400">No persisted pipeline errors.</p>}
      </Panel>
    </main>
  );
}
