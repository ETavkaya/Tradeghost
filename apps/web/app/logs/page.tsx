"use client";

import { useEffect, useMemo, useState } from "react";
import { Panel, SectionTitle, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import { LogFileEntry, LogFileReadResponse, LogFilesResponse, LogsStatusResponse } from "@/lib/types";

function fmt(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value);
}

function dt(value: string | null | undefined): string {
  if (!value) return "-";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function errorText(err: unknown, fallback: string): string {
  if (!(err instanceof Error)) return fallback;
  try {
    const parsed = JSON.parse(err.message) as Record<string, unknown>;
    const detail = parsed.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") {
      const obj = detail as Record<string, unknown>;
      return String(obj.error_message ?? obj.detail ?? obj.error ?? fallback);
    }
  } catch {
    // keep normal error text
  }
  return err.message || fallback;
}

export default function LogsPage() {
  const [status, setStatus] = useState<LogsStatusResponse | null>(null);
  const [files, setFiles] = useState<LogFilesResponse | null>(null);
  const [selectedPath, setSelectedPath] = useState("");
  const [selectedLevel, setSelectedLevel] = useState("");
  const [tail, setTail] = useState(200);
  const [logText, setLogText] = useState<LogFileReadResponse | null>(null);
  const [selectedCohortId, setSelectedCohortId] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const allFiles = useMemo(() => {
    const groups = files?.groups ?? {};
    return Object.entries(groups).flatMap(([group, entries]) => entries.map((entry) => ({ ...entry, group })));
  }, [files]);

  const load = async () => {
    setError(null);
    try {
      const [statusRes, filesRes] = await Promise.all([api.getLogsStatus(), api.listLogFiles()]);
      setStatus(statusRes);
      setFiles(filesRes);
      const firstCohort = statusRes.active_followup_cohorts[0]?.cohort_id ?? "";
      setSelectedCohortId((prev) => prev || firstCohort);
      const firstFile = Object.values(filesRes.groups).flat()[0]?.path ?? "";
      setSelectedPath((prev) => prev || firstFile);
    } catch (err) {
      setError(errorText(err, "Failed to load logs."));
    }
  };

  const readSelectedLog = async () => {
    if (!selectedPath) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.readLogFile(selectedPath, tail, selectedLevel);
      setLogText(res);
      setNotice(`Loaded ${res.tail} lines from ${res.path}.`);
    } catch (err) {
      setError(errorText(err, "Failed to read log file."));
    } finally {
      setLoading(false);
    }
  };

  const runDailyFollowup = async () => {
    if (!selectedCohortId) {
      setError("Select an active follow-up cohort first.");
      return;
    }
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const res = await api.runCohortDailyReport(selectedCohortId, { include_llm: true, backfill: false });
      const firstReport = res.reports[0];
      setNotice(
        `Daily follow-up run complete: generated=${res.generated}, skipped=${res.skipped}, failed=${res.failed}, row_upserted=${res.generated > 0 ? "yes" : "no"}, report_date=${res.report_dates[0] ?? "-"}, export=${firstReport?.export_path ?? "-"}, fallback=${fmt(firstReport?.fallback_used)}${res.errors.length ? `, error=${res.errors.join("; ")}` : ""}`
      );
      await load();
    } catch (err) {
      setError(errorText(err, "Daily follow-up manual run failed."));
    } finally {
      setLoading(false);
    }
  };

  const backfillMissingFollowupDays = async () => {
    if (!selectedCohortId) {
      setError("Select an active follow-up cohort first.");
      return;
    }
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const res = await api.backfillCohortFollowup(selectedCohortId, { include_llm: false });
      setNotice(
        `Backfill complete: generated=${res.generated}, skipped=${res.skipped}, failed=${res.failed}, dates=${res.report_dates.length}${res.errors.length ? `, error=${res.errors.join("; ")}` : ""}`
      );
      await load();
    } catch (err) {
      setError(errorText(err, "Backfill missing follow-up days failed."));
    } finally {
      setLoading(false);
    }
  };

  const copyLogText = async () => {
    if (!logText?.text) return;
    await navigator.clipboard.writeText(logText.text);
    setNotice("Log text copied.");
  };

  const downloadLogText = () => {
    if (!logText) return;
    const blob = new Blob([logText.text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = logText.path.split("/").pop() || "tradeghost-log.txt";
    a.click();
    URL.revokeObjectURL(url);
  };

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    if (selectedPath) void readSelectedLog();
  }, [selectedPath]);

  const scheduler = status?.scheduler;
  const postgres = status?.daily_reports.postgres;

  return (
    <main className="space-y-4">
      <Panel>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <SectionTitle title="Logs" subtitle="Scheduled follow-up visibility, Postgres proof, backend errors, and raw log inspection." />
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => void load()} disabled={loading} className="rounded-lg border border-stroke px-3 py-2 text-xs hover:text-cyan">
              Refresh
            </button>
            <button type="button" onClick={runDailyFollowup} disabled={loading || !selectedCohortId} className="rounded-lg border border-cyan/50 bg-cyan/10 px-3 py-2 text-xs text-cyan">
              Run Daily Follow-up Now
            </button>
            <button type="button" onClick={backfillMissingFollowupDays} disabled={loading || !selectedCohortId} className="rounded-lg border border-amber-300/50 bg-amber-300/10 px-3 py-2 text-xs text-amber-200">
              Backfill Missing Follow-up Days
            </button>
          </div>
        </div>
        {notice ? <p className="mt-3 rounded-lg border border-cyan/40 bg-cyan/10 p-3 text-sm text-cyan">{notice}</p> : null}
        {error ? <p className="mt-3 rounded-lg border border-red/40 bg-red/10 p-3 text-sm text-red">{error}</p> : null}
      </Panel>

      <div className="grid gap-3 md:grid-cols-4 xl:grid-cols-8">
        <StatCard label="Scheduler" value={scheduler?.scheduler_running ? "Running" : "Stopped"} />
        <StatCard label="Next Run" value={dt(scheduler?.next_run_at)} />
        <StatCard label="Active Tracking" value={fmt(scheduler?.active_tracking_count)} />
        <StatCard label="Mature Tracking" value={fmt(scheduler?.mature_tracking_count)} />
        <StatCard label="Paused" value={fmt(scheduler?.paused_followup_count)} />
        <StatCard label="Manually Archived" value={fmt(scheduler?.manually_archived_count)} />
        <StatCard label="28D Review Ready" value={fmt(scheduler?.review_ready_28d_count)} />
        <StatCard label="Reports Persisted" value={fmt(postgres?.total_daily_reports)} />
      </div>

      <Panel>
        <SectionTitle title="Scheduler Status" subtitle="Daily cohort follow-up loop and latest heartbeat." />
        <div className="grid gap-3 text-sm md:grid-cols-4">
          <div>enabled: <span className="text-slate-100">{fmt(scheduler?.scheduler_enabled)}</span></div>
          <div>running: <span className="text-slate-100">{fmt(scheduler?.scheduler_running)}</span></div>
          <div>timezone: <span className="text-slate-100">{fmt(scheduler?.timezone)}</span></div>
          <div>configured_run_time: <span className="text-slate-100">{fmt(scheduler?.configured_run_time)}</span></div>
          <div>last_tick_at: <span className="text-slate-100">{dt(scheduler?.last_tick_at)}</span></div>
          <div>last_run_at: <span className="text-slate-100">{dt(scheduler?.last_run_at)}</span></div>
          <div>last_success_at: <span className="text-slate-100">{dt(scheduler?.last_success_at)}</span></div>
          <div>last_failure_at: <span className="text-slate-100">{dt(scheduler?.last_failure_at)}</span></div>
          <div>last_error: <span className="text-red">{fmt(scheduler?.last_error_message)}</span></div>
        </div>
      </Panel>

      <Panel>
        <SectionTitle title="Postgres Daily Report Confirmation" subtitle="Proof from cohort_daily_reports, not just a markdown file." />
        <div className="grid gap-3 text-sm md:grid-cols-3">
          <div>configured: <span className="text-slate-100">{fmt(postgres?.configured)}</span></div>
          <div>latest_report_date: <span className="text-slate-100">{fmt(postgres?.latest_report_date)}</span></div>
          <div>fallback_used: <span className="text-slate-100">{fmt(postgres?.fallback_used)}</span></div>
          <div>created_at: <span className="text-slate-100">{dt(postgres?.latest_report_created_at)}</span></div>
          <div>updated_at: <span className="text-slate-100">{dt(postgres?.latest_report_updated_at)}</span></div>
          <div>error_message: <span className="text-red">{fmt(postgres?.error_message)}</span></div>
          <div className="md:col-span-3">latest_export_path: <span className="text-slate-100">{fmt(postgres?.latest_export_path)}</span></div>
        </div>
      </Panel>

      <Panel>
        <SectionTitle title="Daily Cohort Reports" subtitle="Latest stored rows from cohort_daily_reports." />
        <div className="overflow-auto">
          <table className="min-w-full text-left text-xs">
            <thead className="text-slate-400">
              <tr><th className="px-2 py-2">Date</th><th className="px-2 py-2">Cohort</th><th className="px-2 py-2">Day</th><th className="px-2 py-2">Candidates</th><th className="px-2 py-2">Snapshots</th><th className="px-2 py-2">Model</th><th className="px-2 py-2">Fallback</th><th className="px-2 py-2">Export</th><th className="px-2 py-2">Updated</th></tr>
            </thead>
            <tbody>
              {(status?.daily_reports.latest_rows ?? []).map((row) => (
                <tr key={`${row.cohort_id}-${row.report_date}`} className="border-t border-stroke/60">
                  <td className="px-2 py-2">{row.report_date}</td>
                  <td className="px-2 py-2">{row.cohort_name ?? row.cohort_id.slice(0, 8)}</td>
                  <td className="px-2 py-2">{fmt(row.followup_day_number)}</td>
                  <td className="px-2 py-2">{row.candidate_count}</td>
                  <td className="px-2 py-2">{row.followup_snapshot_count}</td>
                  <td className="px-2 py-2">{row.llm_model ?? "-"}</td>
                  <td className="px-2 py-2">{fmt(row.fallback_used)}</td>
                  <td className="px-2 py-2 max-w-[280px] truncate" title={row.export_path ?? ""}>{row.export_path ?? "-"}</td>
                  <td className="px-2 py-2">{dt(row.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {status?.daily_reports.latest_rows.length === 0 ? <p className="py-4 text-sm text-slate-400">No daily reports found yet.</p> : null}
        </div>
      </Panel>

      <Panel>
        <SectionTitle title="Tracking Cohorts" subtitle="Active and mature cohorts remain scheduled until paused or manually archived." />
        <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
          <span className="text-slate-400">Manual run target</span>
          <select value={selectedCohortId} onChange={(event) => setSelectedCohortId(event.target.value)} className="h-9 rounded-lg border border-stroke bg-bg px-2">
            {(status?.active_followup_cohorts ?? []).map((cohort) => (
              <option key={cohort.cohort_id} value={cohort.cohort_id}>{cohort.cohort_name}</option>
            ))}
          </select>
        </div>
        <div className="grid gap-2 md:grid-cols-2">
          {(status?.active_followup_cohorts ?? []).map((cohort) => (
            <div key={cohort.cohort_id} className="rounded-xl border border-stroke/70 bg-bg/40 p-3 text-xs">
              <p className="font-semibold text-slate-100">{cohort.cohort_name}</p>
              <p className="text-slate-400">id={cohort.cohort_id}</p>
              <p className="mt-2">status={cohort.followup_status} enabled={fmt(cohort.followup_enabled)} review_checkpoint={cohort.followup_target_days}D current_day={cohort.current_followup_day}</p>
              <p>start={fmt(cohort.followup_started_at ?? cohort.followup_start_date)} last_report={fmt(cohort.last_report_date)} review_ready_28d={fmt(cohort.review_ready_28d)}</p>
              <p>latest_horizon={cohort.latest_available_horizon_days ? `${cohort.latest_available_horizon_days}D` : "-"} next={cohort.next_horizon_due_days ? `${cohort.next_horizon_due_days}D ${cohort.next_horizon_due_date ?? ""}` : "-"}</p>
            </div>
          ))}
          {status?.active_followup_cohorts.length === 0 ? <p className="text-sm text-slate-400">No active or mature tracking cohorts are scheduled.</p> : null}
        </div>
      </Panel>

      <Panel>
        <SectionTitle title="Latest Backend Errors" subtitle="Recent intelligence, scheduler, LLM provider, monitoring, and review errors." />
        <div className="space-y-2">
          {(status?.latest_errors ?? []).map((row, idx) => (
            <div key={`${String(row.timestamp)}-${idx}`} className="rounded-lg border border-red/30 bg-red/5 p-3 text-xs">
              <p className="text-red">{fmt(row.source)} | {fmt(row.level)} | {dt(String(row.timestamp ?? ""))}</p>
              <p className="mt-1 text-slate-200">{fmt(row.message)}</p>
              <p className="mt-1 text-slate-500">{JSON.stringify(row)}</p>
            </div>
          ))}
          {status?.latest_errors.length === 0 ? <p className="text-sm text-slate-400">No backend errors recorded.</p> : null}
        </div>
      </Panel>

      <Panel>
        <SectionTitle title="Raw Log Viewer" subtitle="Safe reader limited to the project logs directory." />
        <div className="grid gap-3 md:grid-cols-4">
          <select value={selectedPath} onChange={(event) => setSelectedPath(event.target.value)} className="h-10 rounded-lg border border-stroke bg-bg px-2 text-sm md:col-span-2">
            <option value="">Select log file</option>
            {allFiles.map((file: LogFileEntry & { group: string }) => (
              <option key={file.path} value={file.path}>{file.group}/{file.name}</option>
            ))}
          </select>
          <select value={selectedLevel} onChange={(event) => setSelectedLevel(event.target.value)} className="h-10 rounded-lg border border-stroke bg-bg px-2 text-sm">
            <option value="">all levels</option>
            <option value="ERROR">ERROR</option>
            <option value="WARNING">WARNING</option>
            <option value="INFO">INFO</option>
          </select>
          <input type="number" min={1} max={2000} value={tail} onChange={(event) => setTail(Number(event.target.value))} className="h-10 rounded-lg border border-stroke bg-bg px-2 text-sm" />
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <button type="button" onClick={readSelectedLog} disabled={loading || !selectedPath} className="rounded-lg border border-stroke px-3 py-2 text-xs hover:text-cyan">Read Last Lines</button>
          <button type="button" onClick={copyLogText} disabled={!logText?.text} className="rounded-lg border border-stroke px-3 py-2 text-xs hover:text-cyan">Copy Log Text</button>
          <button type="button" onClick={downloadLogText} disabled={!logText?.text} className="rounded-lg border border-stroke px-3 py-2 text-xs hover:text-cyan">Download Raw</button>
        </div>
        <pre className="mt-3 max-h-[520px] overflow-auto whitespace-pre-wrap rounded-xl border border-stroke/70 bg-black/30 p-3 text-xs text-slate-200">{logText?.text || "No log selected."}</pre>
      </Panel>
    </main>
  );
}
