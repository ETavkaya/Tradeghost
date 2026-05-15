"use client";

import { Fragment, useEffect, useState } from "react";
import { Panel, SectionTitle, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import {
  CohortDetail,
  CohortCleanupDuplicateResponse,
  CohortReviewResponse,
  IntelligenceDashboardResponse,
  LLMDebugLog,
  LLMConnectionStatus,
  LLMResponseTestResult,
  MarketCode,
  PipelineDebugEvent,
  ScannerCategory,
  ScannerDuration,
  ScannerUniverseScope,
} from "@/lib/types";

export default function IntelligencePage() {
  const [dashboard, setDashboard] = useState<IntelligenceDashboardResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [market, setMarket] = useState<MarketCode>("us");
  const [duration, setDuration] = useState<ScannerDuration>("1y");
  const [scope, setScope] = useState<ScannerUniverseScope>("full_universe");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [topNPerCategory, setTopNPerCategory] = useState(5);
  const scannerResultCap = 30;
  const [categories, setCategories] = useState<ScannerCategory[]>(["trend_mode", "build_up", "momentum_mode", "value_rebuild", "overextended"]);

  const [llmConcurrency, setLlmConcurrency] = useState(1);
  const [contextTimeout, setContextTimeout] = useState(120);
  const [reviewDays, setReviewDays] = useState(28);

  const [llmConsoleExpanded, setLlmConsoleExpanded] = useState(false);
  const [consoleTab, setConsoleTab] = useState<"pipeline" | "llm">("pipeline");
  const [llmStatusFilter, setLlmStatusFilter] = useState<"all" | "success" | "fail">("all");
  const [llmProviderFilter, setLlmProviderFilter] = useState<"all" | "openai" | "ollama">("all");
  const [llmStatus, setLLMStatus] = useState<LLMConnectionStatus | null>(null);
  const [llmTest, setLlmTest] = useState<LLMResponseTestResult | null>(null);
  const [llmLogs, setLLMLogs] = useState<LLMDebugLog[]>([]);
  const [pipelineEvents, setPipelineEvents] = useState<PipelineDebugEvent[]>([]);
  const [expandedLogIds, setExpandedLogIds] = useState<Record<string, boolean>>({});
  const [expandedPipelineIds, setExpandedPipelineIds] = useState<Record<string, boolean>>({});
  const [backendConnected, setBackendConnected] = useState(false);
  const [cohortName, setCohortName] = useState("Momentum Milestone");
  const [cohortNotes, setCohortNotes] = useState("");
  const [selectedCohortId, setSelectedCohortId] = useState<string>("");
  const [selectedCohortDetail, setSelectedCohortDetail] = useState<CohortDetail | null>(null);
  const [cohortReview, setCohortReview] = useState<CohortReviewResponse | null>(null);
  const [cohortContextFailedSymbols, setCohortContextFailedSymbols] = useState<string[]>([]);
  const [cohortActionSuccess, setCohortActionSuccess] = useState<Record<string, { followup?: boolean; contexts?: boolean; briefing?: boolean; review?: boolean; export?: boolean }>>({});
  const [exportMode, setExportMode] = useState<"initial" | "followup" | "lifecycle" | "review_28d">("followup");
  const [cohortFilter, setCohortFilter] = useState<"active" | "archived" | "all">("active");
  const [duplicateStrategy, setDuplicateStrategy] = useState<"use_existing" | "archive_existing_create_new" | "create_duplicate_anyway">("use_existing");
  const [cleanupResult, setCleanupResult] = useState<CohortCleanupDuplicateResponse | null>(null);

  const formatError = (err: unknown, stage: string): string => {
    if (!(err instanceof Error)) return `${stage} failed.`;
    try {
      const parsed = JSON.parse(err.message) as Record<string, unknown>;
      const status = parsed.status ? ` status=${String(parsed.status)}` : "";
      const detailObj = parsed.detail as Record<string, unknown> | string | Array<Record<string, unknown>> | undefined;
      if (Array.isArray(detailObj)) {
        const first = detailObj[0] ?? {};
        const loc = Array.isArray(first.loc) ? first.loc.join(".") : "unknown";
        const msg = String(first.msg ?? "validation error");
        const type = first.type ? ` type=${String(first.type)}` : "";
        return `${stage} failed: ${msg} (field=${loc}).${status}${type}`;
      }
      if (detailObj && typeof detailObj === "object") {
        const detail =
          typeof detailObj.detail === "string"
            ? detailObj.detail
            : detailObj.error_message
              ? String(detailObj.error_message)
              : `${stage} failed`;
        const failedStage = detailObj.failed_stage ? ` failed_stage=${String(detailObj.failed_stage)}` : "";
        const failedSymbol = detailObj.failed_symbol ? ` failed_symbol=${String(detailObj.failed_symbol)}` : "";
        const model = detailObj.model ? ` model=${String(detailObj.model)}` : "";
        const llmProvider = detailObj.llm_provider ? ` llm_provider=${String(detailObj.llm_provider)}` : "";
        const llmFallbackProvider = detailObj.llm_fallback_provider ? ` llm_fallback_provider=${String(detailObj.llm_fallback_provider)}` : "";
        const errorType = detailObj.error_type ? ` error_type=${String(detailObj.error_type)}` : "";
        const errorMessage = detailObj.error_message ? ` error_message=${String(detailObj.error_message)}` : "";
        const endpoint = detailObj.endpoint ? ` endpoint=${String(detailObj.endpoint)}` : "";
        const method = detailObj.method ? ` method=${String(detailObj.method)}` : "";
        const backendError = detailObj.error ? ` error=${String(detailObj.error)}` : "";
        const suggestedAction = detailObj.suggested_action ? ` suggested_action=${String(detailObj.suggested_action)}` : "";
        const conflictingCohortId = detailObj.conflicting_cohort_id ? ` conflicting_cohort_id=${String(detailObj.conflicting_cohort_id)}` : "";
        return `${detail}.${status}${method}${endpoint}${backendError}${failedStage}${failedSymbol}${model}${llmProvider}${llmFallbackProvider}${errorType}${errorMessage}${conflictingCohortId}${suggestedAction}`;
      }
      return `${String(detailObj ?? `${stage} failed`)}.${status}`;
    } catch {
      return err.message;
    }
  };

  const load = async () => {
    const [dataR, statusR, logsR, eventsR, healthR] = await Promise.allSettled([
      api.getIntelligenceDashboard(),
      api.getLLMStatus(),
      api.getLLMLogs(120),
      api.getPipelineEvents(250),
      api.health(),
    ]);
    if (dataR.status === "fulfilled") setDashboard(dataR.value);
    if (statusR.status === "fulfilled") setLLMStatus(statusR.value);
    if (logsR.status === "fulfilled") setLLMLogs(logsR.value);
    if (eventsR.status === "fulfilled") setPipelineEvents(eventsR.value);
    if (healthR.status === "fulfilled") setBackendConnected(healthR.value.status === "ok");
    else setBackendConnected(false);
    if (selectedCohortId) {
      try {
        setSelectedCohortDetail(await api.getCohortDetail(selectedCohortId));
      } catch {
        setSelectedCohortDetail(null);
      }
    }
  };

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    if (!llmConsoleExpanded && !loading) return;
    const t = setInterval(() => {
      void load();
    }, 2500);
    return () => clearInterval(t);
  }, [llmConsoleExpanded, loading]);

  useEffect(() => {
    const first = dashboard?.cohorts?.[0]?.id ?? "";
    if (!selectedCohortId && first) setSelectedCohortId(first);
  }, [dashboard?.cohorts, selectedCohortId]);

  useEffect(() => {
    if (!selectedCohortId) {
      setSelectedCohortDetail(null);
      return;
    }
    void (async () => {
      try {
        setSelectedCohortDetail(await api.getCohortDetail(selectedCohortId));
      } catch {
        setSelectedCohortDetail(null);
      }
    })();
  }, [selectedCohortId]);

  useEffect(() => {
    if (!selectedCohortId) return;
    setCohortActionSuccess((prev) => ({ ...prev, [selectedCohortId]: prev[selectedCohortId] ?? {} }));
  }, [selectedCohortId]);

  const activeModel = llmStatus?.model_used ?? "llama3.2:3b";
  const selectedCohortMeta = (dashboard?.cohorts ?? []).find((x) => x.id === selectedCohortId) ?? null;
  const filteredCohorts = (dashboard?.cohorts ?? []).filter((row) => cohortFilter === "all" ? true : row.status === cohortFilter);
  const cohortContexts = (dashboard?.latest_contexts ?? []).filter((row) => row.cohort_id === selectedCohortId);
  const generatedCohortContextCount = cohortContexts.filter((row) => row.status === "generated").length;
  const latestCohortSnapshotCount = selectedCohortDetail?.snapshots?.length ?? 0;
  const selectedCohortCandidateCount = selectedCohortDetail?.candidates?.length ?? 0;
  const selectedIsActive = selectedCohortMeta?.status === "active";
  const selectedIsArchived = selectedCohortMeta?.status === "archived";
  const canCreateCohort = Boolean(market && duration && categories.length > 0 && cohortName.trim().length > 0);
  const canRunFollowup = Boolean(selectedCohortId) && selectedIsActive && selectedCohortCandidateCount > 0;
  const canRunCohortContexts = Boolean(selectedCohortId) && selectedIsActive && selectedCohortCandidateCount > 0 && Boolean(llmStatus?.connected);
  const canRunCohortBriefing = Boolean(selectedCohortId) && generatedCohortContextCount > 0 && Boolean(llmStatus?.connected);
  const canRunCohortReview = Boolean(selectedCohortId) && latestCohortSnapshotCount > 0;
  const canExportCohortReport = Boolean(selectedCohortId);
  const followupDone = Boolean(cohortActionSuccess[selectedCohortId ?? ""]?.followup);
  const contextsDone = Boolean(cohortActionSuccess[selectedCohortId ?? ""]?.contexts);
  const briefingDone = Boolean(cohortActionSuccess[selectedCohortId ?? ""]?.briefing);
  const reviewDone = Boolean(cohortActionSuccess[selectedCohortId ?? ""]?.review);
  const exportDone = Boolean(cohortActionSuccess[selectedCohortId ?? ""]?.export);
  const selectedCategoryCount = categories.length;
  const rawExpected = selectedCategoryCount * topNPerCategory;
  const autoFinalShortlistLimit = rawExpected;
  const filteredLlmLogs = llmLogs.filter((row) => {
    if (llmStatusFilter !== "all" && row.status !== llmStatusFilter) return false;
    if (llmProviderFilter !== "all" && row.provider !== llmProviderFilter) return false;
    return true;
  });

  const createDiscoveryCohort = async () => {
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      const detail = await api.createDiscoveryCohort({
        name: cohortName,
        notes: cohortNotes,
        market,
        duration,
        categories,
        max_universe_symbols: 500,
        top_n_per_category: topNPerCategory,
        max_candidates: autoFinalShortlistLimit,
        scanner_max_results: scannerResultCap,
        scanner_universe_scope: scope,
        duplicate_strategy: duplicateStrategy,
      });
      setSelectedCohortId(detail.cohort.id);
      setNotice(`Discovery/Create Cohort completed: ${detail.cohort.name} (${detail.cohort.id.slice(0, 8)}).`);
      await load();
    } catch (err) {
      setError(formatError(err, "Create Cohort"));
    } finally {
      setLoading(false);
    }
  };

  const runCohortFollowup = async () => {
    if (!selectedCohortId) return;
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      const response = await api.runCohortFollowup({ cohort_id: selectedCohortId });
      setNotice(`Follow-up completed for cohort_id=${response.cohort_id} snapshots=${response.snapshots.length}.`);
      setCohortActionSuccess((prev) => ({ ...prev, [selectedCohortId]: { ...(prev[selectedCohortId] ?? {}), followup: true } }));
      await load();
    } catch (err) {
      setError(formatError(err, "Run Cohort Follow-up"));
    } finally {
      setLoading(false);
    }
  };

  const runCohortReview = async () => {
    if (!selectedCohortId) return;
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      const response = await api.runCohortReview({ cohort_id: selectedCohortId, days_required: reviewDays, model: activeModel, timeout_seconds: contextTimeout });
      setCohortReview(response);
      setNotice(response.readiness_message);
      setCohortActionSuccess((prev) => ({ ...prev, [selectedCohortId]: { ...(prev[selectedCohortId] ?? {}), review: true } }));
    } catch (err) {
      setError(formatError(err, "Run Cohort Review"));
    } finally {
      setLoading(false);
    }
  };

  const exportCohortReport = async () => {
    if (!selectedCohortId) return;
    setError(null);
    try {
      const report = await api.exportCohortReport(selectedCohortId, exportMode);
      const blob = new Blob([report.markdown], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = report.filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      setNotice(`Cohort report exported: ${report.filename} (mode=${report.report_mode ?? exportMode}).`);
      setCohortActionSuccess((prev) => ({ ...prev, [selectedCohortId]: { ...(prev[selectedCohortId] ?? {}), export: true } }));
    } catch (err) {
      setError(formatError(err, "Export cohort report"));
    }
  };

  const archiveSelectedCohort = async () => {
    if (!selectedCohortId) return;
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      const res = await api.archiveCohort(selectedCohortId);
      setNotice(`Cohort archived: ${res.cohort_id}`);
      await load();
    } catch (err) {
      setError(formatError(err, "Archive Cohort"));
    } finally {
      setLoading(false);
    }
  };

  const activateSelectedCohort = async () => {
    if (!selectedCohortId) return;
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      const res = await api.activateCohort(selectedCohortId);
      setNotice(`Cohort re-activated: ${res.cohort_id}`);
      await load();
    } catch (err) {
      setError(formatError(err, "Activate Cohort"));
    } finally {
      setLoading(false);
    }
  };

  const deleteSelectedCohort = async () => {
    if (!selectedCohortId) return;
    const ok = window.confirm("Delete this cohort and all linked follow-up/context/review data?");
    if (!ok) return;
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      const res = await api.deleteCohort(selectedCohortId);
      setNotice(`Cohort deleted: ${res.cohort_id} (candidates=${res.removed_candidates}, snapshots=${res.removed_snapshots}, contexts=${res.removed_contexts}).`);
      setSelectedCohortId("");
      setSelectedCohortDetail(null);
      await load();
    } catch (err) {
      setError(formatError(err, "Delete Cohort"));
    } finally {
      setLoading(false);
    }
  };

  const cleanupDuplicateCohortsDryRun = async () => {
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      const res = await api.cleanupDuplicateCohorts({ dry_run: true, apply_archive: false });
      setCleanupResult(res);
      setNotice(`Duplicate cleanup dry-run completed. groups=${res.duplicate_groups.length}`);
    } catch (err) {
      setError(formatError(err, "Cleanup Duplicate Cohorts"));
    } finally {
      setLoading(false);
    }
  };

  const runCohortContexts = async (retryFailedOnly = false) => {
    if (!selectedCohortId) {
      setError("Select cohort first.");
      return;
    }
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      const response = await api.generateCohortSymbolContexts({
        cohort_id: selectedCohortId,
        context_symbol_limit: retryFailedOnly
          ? Math.max(1, cohortContextFailedSymbols.length)
          : Math.max(1, selectedCohortDetail?.candidates.length ?? 200),
        max_concurrency: llmConcurrency,
        timeout_seconds: contextTimeout,
        model: activeModel,
        sequential_mode: true,
        short_context_mode: true,
        debug_stream: false,
        symbols: retryFailedOnly ? cohortContextFailedSymbols : [],
      });
      setCohortContextFailedSymbols(response.failed_symbols ?? []);
      setNotice(`Cohort contexts completed: generated ${response.generated}, failed ${response.failed}.${response.failed > 0 ? ` failed symbols: ${response.failed_symbols.join(", ")}` : ""}`);
      if (response.generated > 0) {
        setCohortActionSuccess((prev) => ({ ...prev, [selectedCohortId]: { ...(prev[selectedCohortId] ?? {}), contexts: true } }));
      }
      await load();
    } catch (err) {
      setError(formatError(err, "Generate Cohort Symbol Contexts"));
    } finally {
      setLoading(false);
    }
  };

  const runCohortBriefing = async () => {
    if (!selectedCohortId) {
      setError("Select cohort first.");
      return;
    }
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      const response = await api.generateCohortBriefing({
        cohort_id: selectedCohortId,
        model: activeModel,
        timeout_seconds: contextTimeout,
        short_briefing_mode: true,
      });
      setNotice(`Cohort briefing ${response.status === "generated" ? "generated" : "failed"}.`);
      if (response.status === "generated") {
        setCohortActionSuccess((prev) => ({ ...prev, [selectedCohortId]: { ...(prev[selectedCohortId] ?? {}), briefing: true } }));
      }
      await load();
    } catch (err) {
      setError(formatError(err, "Generate Cohort Briefing"));
    } finally {
      setLoading(false);
    }
  };


  const runLLMResponseTest = async () => {
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      const result = await api.testLLMResponse({
        model: activeModel,
        timeout_seconds: 30,
        threshold_seconds: 20,
      });
      setLlmTest(result);
      setNotice(
        result.ok
          ? `LLM test success: ${result.response_time_ms} ms (${result.within_threshold ? "within" : "above"} 20s threshold).`
          : `LLM test failed: ${result.error ?? "unknown error"}`,
      );
      await load();
    } catch (err) {
      setError(formatError(err, "LLM response test"));
    } finally {
      setLoading(false);
    }
  };

  const toggleCategory = (category: ScannerCategory) => {
    setCategories((prev) => (prev.includes(category) ? prev.filter((x) => x !== category) : [...prev, category]));
  };

  const jumpTo = (id: string) => {
    const el = document.getElementById(id);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const actionButtonClass = (done: boolean) =>
    `h-10 rounded-lg border px-3 text-sm disabled:opacity-60 ${
      done ? "border-green/70 bg-green/20 text-green" : "border-stroke hover:text-cyan"
    }`;

  const getRelatedLogForEvent = (event: PipelineDebugEvent): LLMDebugLog | null => {
    const eventTs = new Date(event.timestamp).getTime();
    const candidates = llmLogs.filter((log) => {
      if (event.symbol && log.symbol && log.symbol !== event.symbol) return false;
      const delta = Math.abs(new Date(log.timestamp).getTime() - eventTs);
      if (delta > 45_000) return false;
      if (event.step_name.includes("symbol_context") && !log.call_type.includes("symbol_context")) return false;
      if (event.status === "failed" && log.status !== "fail") return false;
      return true;
    });
    if (!candidates.length) return null;
    return candidates.sort((a, b) => {
      const da = Math.abs(new Date(a.timestamp).getTime() - eventTs);
      const db = Math.abs(new Date(b.timestamp).getTime() - eventTs);
      return da - db;
    })[0];
  };

  return (
    <main className="relative">
      <aside className="mb-4 xl:fixed xl:left-4 xl:top-44 xl:w-[208px] xl:z-20">
        <div className="max-h-[calc(100vh-12rem)] overflow-auto rounded-lg border border-stroke/70 bg-panel p-3">
          <p className="mb-2 text-xs font-semibold text-slate-300">Intelligence Menu</p>
          <div className="flex gap-2 overflow-x-auto xl:flex-col xl:overflow-visible">
            <button type="button" onClick={() => jumpTo("intelligence-layer")} className="rounded border border-stroke px-2 py-1 text-xs hover:text-cyan whitespace-nowrap">Intelligence Layer</button>
            <button type="button" onClick={() => jumpTo("workflow-steps")} className="rounded border border-stroke px-2 py-1 text-xs hover:text-cyan whitespace-nowrap">Workflow Steps</button>
            <button type="button" onClick={() => jumpTo("discovery")} className="rounded border border-stroke px-2 py-1 text-xs hover:text-cyan whitespace-nowrap">Discovery</button>
            <button type="button" onClick={() => jumpTo("active-cohorts")} className="rounded border border-stroke px-2 py-1 text-xs hover:text-cyan whitespace-nowrap">Active Cohorts</button>
            <button type="button" onClick={() => { setLlmConsoleExpanded(true); jumpTo("cohort-console"); }} className="rounded border border-stroke px-2 py-1 text-xs hover:text-cyan whitespace-nowrap">LLM Console</button>
            <button type="button" onClick={() => jumpTo("candidates")} className="rounded border border-stroke px-2 py-1 text-xs hover:text-cyan whitespace-nowrap">Latest Candidates</button>
            <button type="button" onClick={() => jumpTo("review-readiness")} className="rounded border border-stroke px-2 py-1 text-xs hover:text-cyan whitespace-nowrap">Review Readiness</button>
          </div>
        </div>
      </aside>

      <div className="space-y-4">
      {notice ? (
        <div className="rounded-lg border border-green/40 bg-green/10 px-3 py-2 text-xs text-green">{notice}</div>
      ) : null}
      {error ? (
        <div className="rounded-lg border border-red/40 bg-red/10 px-3 py-2 text-xs text-red">{error}</div>
      ) : null}
      <section id="intelligence-layer">
      <Panel>
        <SectionTitle title="Intelligence Layer" subtitle="Deterministic pipeline + optional LLM interpretation layer" />
        <div className="mt-2 flex flex-wrap gap-2 text-xs">
          <span className={`rounded-md border px-2 py-1 ${backendConnected ? "border-green/60 text-green" : "border-red/60 text-red"}`}>
            Backend API: {backendConnected ? "Connected" : "Not reachable"}
          </span>
          <span className={`rounded-md border px-2 py-1 ${llmStatus?.primary_connected ? "border-green/60 text-green" : "border-red/60 text-red"}`}>
            Primary Provider: {(llmStatus?.primary_provider ?? "n/a").toUpperCase()} | Model: {llmStatus?.model_used ?? "-"} | Status: {llmStatus?.primary_connected ? "Connected" : "Not reachable"}
          </span>
          <span className={`rounded-md border px-2 py-1 ${llmStatus?.fallback_connected ? "border-green/60 text-green" : "border-red/60 text-red"}`}>
            Fallback Provider: {(llmStatus?.fallback_provider ?? "n/a").toUpperCase()} | Model: {llmStatus?.fallback_model ?? "-"} | Status: {llmStatus?.fallback_connected ? "Connected" : "Not reachable"}
          </span>
          <button type="button" onClick={() => setLlmConsoleExpanded((prev) => !prev)} className="rounded-md border border-stroke px-2 py-1 hover:text-cyan">
            {llmConsoleExpanded ? "Minimize LLM Console" : "Expand LLM Console"}
          </button>
          <button type="button" onClick={() => { setLlmConsoleExpanded(true); jumpTo("cohort-console"); }} className="rounded-md border border-stroke px-2 py-1 hover:text-cyan">
            Jump to Console
          </button>
          <button type="button" onClick={runLLMResponseTest} disabled={loading || !backendConnected || !llmStatus?.connected} className="rounded-md border border-stroke px-2 py-1 hover:text-cyan disabled:opacity-60">
            Test LLM Response
          </button>
          <button type="button" onClick={load} className="rounded-md border border-stroke px-2 py-1 hover:text-cyan">Refresh</button>
        </div>
        {llmTest ? (
          <p className={`mt-2 text-xs ${llmTest.ok && llmTest.within_threshold ? "text-green" : llmTest.ok ? "text-yellow-300" : "text-red"}`}>
            LLM test: {llmTest.status} | model={llmTest.model} | latency={llmTest.response_time_ms} ms | threshold={llmTest.threshold_ms} ms
            {llmTest.error ? ` | error=${llmTest.error}` : ""}
          </p>
        ) : null}
        {llmStatus && !llmStatus.connected ? (
          <p className="mt-2 text-xs text-red">LLM check endpoint: {llmStatus.base_url}. Error: {llmStatus.error ?? "unknown"}. Suggested fix: ensure primary provider credentials/endpoint are valid or fallback provider is reachable.</p>
        ) : null}
        {llmStatus?.connected ? (
          <p className="mt-2 text-xs text-slate-300">
            Primary model: {llmStatus.model_used ?? "-"} | available: {llmStatus.model_available === null ? "unknown" : llmStatus.model_available ? "yes" : "no"} | last duration: {llmStatus.last_response_duration_ms ?? "-"} ms | last fallback: {llmStatus.last_fallback_used === null ? "-" : llmStatus.last_fallback_used ? "yes" : "no"}
          </p>
        ) : null}
        {llmStatus?.model_available === false ? (
          <p className="mt-1 text-xs text-red">Model not found on primary provider. Pull/install or select an available model.</p>
        ) : null}
      </Panel>
      </section>

      {dashboard ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <StatCard label="Daily Runs" value={String(dashboard.runs.length)} />
          <StatCard label="Latest Symbols" value={String(dashboard.latest_run_results.length)} />
          <StatCard label="Contexts Loaded" value={String(dashboard.latest_contexts.length)} />
          <StatCard label="Latest Review" value={dashboard.latest_review?.period ?? "-"} />
          <StatCard label="Review Readiness" value={dashboard.review_readiness?.ready_for_28_day_review ? "Ready" : `${dashboard.review_readiness?.days_until_28_day_review ?? 28}d left`} />
        </div>
      ) : null}

      <section id="workflow-steps">
      <Panel>
        <SectionTitle title="Workflow Steps" subtitle="Cohort-first workflow: deterministic path stays usable even if LLM fails" />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4 text-xs">
          <div className="rounded-lg border border-stroke/70 p-3">
            <p className="font-semibold">Step 1: Create Candidate Cohort</p>
            <p className="mt-1 text-slate-400">Finds new symbols and freezes why-selected snapshots.</p>
            <p className="mt-2">Status: {canCreateCohort ? "ready" : "blocked"}</p>
          </div>
          <div className="rounded-lg border border-stroke/70 p-3">
            <p className="font-semibold">Step 2: Run Follow-up</p>
            <p className="mt-1 text-slate-400">Tracks same symbols only with score/price/performance updates.</p>
            <p className="mt-2">Status: {canRunFollowup ? (latestCohortSnapshotCount > 0 ? "completed" : "ready") : "blocked"} {canRunFollowup ? "" : "(select cohort)"}</p>
          </div>
          <div className="rounded-lg border border-stroke/70 p-3">
            <p className="font-semibold">Step 3: Generate Contexts (Optional)</p>
            <p className="mt-1 text-slate-400">LLM commentary for cohort symbols only.</p>
            <p className="mt-2">Status: {canRunCohortContexts ? (generatedCohortContextCount > 0 ? "completed" : "ready") : "blocked"} {canRunCohortContexts ? "" : "(LLM/cohort required)"}</p>
          </div>
          <div className="rounded-lg border border-stroke/70 p-3">
            <p className="font-semibold">Step 4: Review Cohort</p>
            <p className="mt-1 text-slate-400">Evaluates whether original selections worked.</p>
            <p className="mt-2">Status: {canRunCohortReview ? "ready" : "blocked"} {canRunCohortReview ? "" : "(follow-up required)"}</p>
          </div>
        </div>
      </Panel>
      </section>

      <section id="discovery">
      <Panel>
        <SectionTitle title="Discovery" subtitle="Discovery Run finds new candidates and creates an immutable Candidate Cohort snapshot" />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3 text-xs text-slate-300">
          <label>Market<select value={market} onChange={(e) => setMarket(e.target.value as MarketCode)} className="mt-1 h-10 w-full rounded-lg border border-stroke bg-bg px-2 text-sm"><option value="us">US</option><option value="bist">BIST</option></select></label>
          <label>Analysis Window<select value={duration} onChange={(e) => setDuration(e.target.value as ScannerDuration)} className="mt-1 h-10 w-full rounded-lg border border-stroke bg-bg px-2 text-sm"><option value="1y">1Y</option><option value="2y">2Y</option><option value="3y">3Y</option></select></label>
          <label>Universe<select value={scope} onChange={(e) => setScope(e.target.value as ScannerUniverseScope)} className="mt-1 h-10 w-full rounded-lg border border-stroke bg-bg px-2 text-sm"><option value="full_universe">Full Universe</option><option value="watchlist">Watchlist</option></select></label>
          <label>Top N Per Category<input type="number" min={1} max={20} value={topNPerCategory} onChange={(e) => setTopNPerCategory(Number(e.target.value))} className="mt-1 h-10 w-full rounded-lg border border-stroke bg-bg px-2 text-sm" /></label>
          <label>Final Shortlist Limit (auto)<input type="text" readOnly value={`${selectedCategoryCount} x ${topNPerCategory} = ${autoFinalShortlistLimit}`} className="mt-1 h-10 w-full rounded-lg border border-stroke bg-bg px-2 text-sm text-slate-300" /></label>
        </div>

        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          {(["trend_mode", "build_up", "momentum_mode", "value_rebuild", "overextended"] as ScannerCategory[]).map((cat) => (
            <button key={cat} type="button" onClick={() => toggleCategory(cat)} className={`rounded-md border px-2 py-1 ${categories.includes(cat) ? "border-cyan/60 text-cyan" : "border-stroke text-slate-300"}`}>{cat}</button>
          ))}
        </div>
        <div className="mt-3 grid gap-3 md:grid-cols-2 text-xs text-slate-300">
          <label>Cohort Name<input value={cohortName} onChange={(e) => setCohortName(e.target.value)} className="mt-1 h-10 w-full rounded-lg border border-stroke bg-bg px-2 text-sm" /></label>
          <label>Cohort Notes<input value={cohortNotes} onChange={(e) => setCohortNotes(e.target.value)} className="mt-1 h-10 w-full rounded-lg border border-stroke bg-bg px-2 text-sm" /></label>
          <label>Duplicate Cohort Behavior
            <select value={duplicateStrategy} onChange={(e) => setDuplicateStrategy(e.target.value as "use_existing" | "archive_existing_create_new" | "create_duplicate_anyway")} className="mt-1 h-10 w-full rounded-lg border border-stroke bg-bg px-2 text-sm">
              <option value="use_existing">Use Existing Cohort (Recommended)</option>
              <option value="archive_existing_create_new">Archive Existing and Create New</option>
              <option value="create_duplicate_anyway">Create Duplicate Anyway</option>
            </select>
          </label>
        </div>
        <p className="mt-2 text-xs text-slate-400">
          Discovery Run selects new symbols. Follow-up Run tracks the same cohort symbols only.
        </p>
        <p className="mt-1 text-xs text-slate-400">
          Debug mode uses sequential short JSON prompts for reliable provider/fallback tracing.
        </p>
        <button type="button" onClick={() => setShowAdvanced((prev) => !prev)} className="mt-3 rounded-md border border-stroke px-2 py-1 text-xs hover:text-cyan">
          {showAdvanced ? "Hide Advanced Settings" : "Show Advanced Settings"}
        </button>
        {showAdvanced ? (
        <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3 text-xs text-slate-300 rounded-lg border border-stroke/70 p-3">
            <label>LLM Concurrency<input type="number" min={1} max={8} value={llmConcurrency} onChange={(e) => setLlmConcurrency(Number(e.target.value))} className="mt-1 h-10 w-full rounded-lg border border-stroke bg-bg px-2 text-sm" /></label>
            <label>LLM Timeout (sec)<input type="number" min={5} max={300} value={contextTimeout} onChange={(e) => setContextTimeout(Number(e.target.value))} className="mt-1 h-10 w-full rounded-lg border border-stroke bg-bg px-2 text-sm" /></label>
            <label>Review Period Days<input type="number" min={7} max={365} value={reviewDays} onChange={(e) => setReviewDays(Number(e.target.value))} className="mt-1 h-10 w-full rounded-lg border border-stroke bg-bg px-2 text-sm" /></label>
            <div className="md:col-span-2 xl:col-span-3">
              <button type="button" onClick={cleanupDuplicateCohortsDryRun} disabled={loading} className="h-9 rounded border border-stroke px-3 text-xs hover:text-cyan disabled:opacity-60">Cleanup Duplicate Cohorts (Dry Run)</button>
              {cleanupResult ? (
                <div className="mt-2 text-xs text-slate-400 space-y-1">
                  <p>duplicate_groups={cleanupResult.duplicate_groups.length} archived_on_apply={cleanupResult.archived_cohort_ids.length}</p>
                  {cleanupResult.duplicate_groups.map((g) => (
                    <p key={g.group_id}>
                      {g.group_id}: keep `{g.keep_cohort_id}` archive `{g.archive_cohort_ids.join(", ") || "-"}`
                    </p>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
        ) : null}

        <div className="mt-3 grid gap-2 md:grid-cols-2">
          <button type="button" onClick={createDiscoveryCohort} disabled={loading || !backendConnected || !canCreateCohort} className="h-10 rounded-lg bg-cyan px-3 text-sm font-semibold text-bg disabled:opacity-60">{loading ? "Running..." : "Create New Candidate Cohort"}</button>
          <p className="text-xs text-slate-400">Runs scanner category-by-category, merges candidates, and stores immutable cohort candidate snapshots.</p>
        </div>

      </Panel>
      </section>

      

      {showAdvanced ? (
        <Panel>
          <SectionTitle title="Legacy Daily Runs (Debug)" subtitle="Legacy daily scanner runs for debugging only; cohort workflow is primary." />
          <div className="max-h-[240px] overflow-auto rounded-lg border border-stroke/70">
            <table className="w-full text-xs">
              <thead className="sticky top-0 z-20 bg-bg"><tr className="border-b border-stroke text-left text-slate-400"><th className="px-2 py-2">Date</th><th className="px-2 py-2">Symbols</th><th className="px-2 py-2">Categories</th><th className="px-2 py-2">Top N / Cat</th><th className="px-2 py-2">Raw Before Merge</th><th className="px-2 py-2">Final After Merge</th><th className="px-2 py-2">Status</th></tr></thead>
              <tbody>
                {(dashboard?.runs ?? []).map((row) => (
                  <tr key={row.id} className="border-b border-stroke/50"><td className="px-2 py-2">{new Date(row.timestamp).toLocaleString()}</td><td className="px-2 py-2">{row.symbols_count}</td><td className="px-2 py-2">{row.scanner_categories.join(", ")}</td><td className="px-2 py-2">{row.top_n_per_category}</td><td className="px-2 py-2">{row.raw_candidates_before_merge}</td><td className="px-2 py-2">{row.final_candidates_after_merge}</td><td className="px-2 py-2">{row.status}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      ) : null}

      <section id="active-cohorts">
      <Panel>
        <SectionTitle title="Active Cohorts" subtitle="Follow-up Run tracks existing cohort symbols and forward performance" />
        <div className="grid gap-3 text-xs">
          <div className="grid gap-2 md:grid-cols-2">
            <label>Cohort Filter
              <select value={cohortFilter} onChange={(e) => setCohortFilter(e.target.value as "active" | "archived" | "all")} className="mt-1 h-10 w-full rounded-lg border border-stroke bg-bg px-2 text-sm">
                <option value="active">Active</option>
                <option value="archived">Archived</option>
                <option value="all">All</option>
              </select>
            </label>
          </div>
          <label>Selected Cohort
            <select value={selectedCohortId} onChange={(e) => setSelectedCohortId(e.target.value)} className="mt-1 h-10 w-full rounded-lg border border-stroke bg-bg px-2 text-sm">
              <option value="">Select cohort</option>
              {filteredCohorts.map((row) => (
                <option key={row.id} value={row.id}>
                  {`${row.name} | created ${new Date(row.created_at).toLocaleString()} | start ${row.start_date} | ${row.status} | ${row.symbols_count ?? 0} symbols | latest ${row.latest_followup_date ?? "-"} | ${row.short_id ?? row.id.slice(0, 8)}`}
                </option>
              ))}
            </select>
          </label>
          {selectedCohortMeta ? (
            <div className="rounded-lg border border-stroke/70 p-3 text-xs text-slate-300">
              <p className="font-semibold text-slate-100">Selected Cohort Status</p>
              <p>Name: {selectedCohortMeta.name}</p>
              <p>Cohort ID: {selectedCohortMeta.id}</p>
              <p>Created at: {new Date(selectedCohortMeta.created_at).toLocaleString()}</p>
              <p>Start date: {selectedCohortMeta.start_date}</p>
              <p>Candidate count: {selectedCohortCandidateCount}</p>
              <p>Follow-up snapshots: {latestCohortSnapshotCount}</p>
              <p>Latest follow-up date: {selectedCohortMeta.latest_followup_date ?? "-"}</p>
              <p>Contexts generated: {generatedCohortContextCount}</p>
              <p>Briefing status: {generatedCohortContextCount > 0 ? "ready/generated contexts available" : "waiting contexts"}</p>
              <p>Review readiness: {canRunCohortReview ? "ready" : "follow-up required"}</p>
              <p>Status: {selectedCohortMeta.status}</p>
            </div>
          ) : null}
          <div className="rounded-lg border border-stroke/70 p-3">
            <p className="mb-2 text-xs text-slate-400">Cohort Actions</p>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={runCohortFollowup} disabled={loading || !canRunFollowup} className={actionButtonClass(followupDone)}>Run Follow-up for Selected Cohort</button>
              <button type="button" onClick={() => runCohortContexts(false)} disabled={loading || !canRunCohortContexts} className={actionButtonClass(contextsDone)}>Generate Cohort Symbol Contexts</button>
              <button type="button" onClick={runCohortBriefing} disabled={loading || !canRunCohortBriefing} className={actionButtonClass(briefingDone)}>Generate Cohort Briefing</button>
              <button type="button" onClick={runCohortReview} disabled={loading || !canRunCohortReview} className={actionButtonClass(reviewDone)}>Review Selected Cohort</button>
              <select value={exportMode} onChange={(e) => setExportMode(e.target.value as "initial" | "followup" | "lifecycle" | "review_28d")} className="h-10 rounded-lg border border-stroke bg-bg px-2 text-xs">
                <option value="initial">Export: Initial</option>
                <option value="followup">Export: Latest Follow-up</option>
                <option value="lifecycle">Export: Full Lifecycle</option>
                <option value="review_28d">Export: 28-Day Review</option>
              </select>
              <button type="button" onClick={exportCohortReport} disabled={loading || !canExportCohortReport} className={actionButtonClass(exportDone)}>Export Cohort Report</button>
              <button type="button" onClick={activateSelectedCohort} disabled={loading || !selectedCohortId || !selectedIsArchived} className="h-10 rounded-lg border border-stroke px-3 text-sm hover:text-cyan disabled:opacity-60">Reactivate Cohort</button>
              <button type="button" onClick={archiveSelectedCohort} disabled={loading || !selectedCohortId || !selectedIsActive} className="h-10 rounded-lg border border-stroke px-3 text-sm hover:text-cyan disabled:opacity-60">Archive Cohort</button>
              <button type="button" onClick={deleteSelectedCohort} disabled={loading || !selectedCohortId} className="h-10 rounded-lg border border-red/60 px-3 text-sm text-red hover:bg-red/10 disabled:opacity-60">Delete Cohort</button>
              <button type="button" onClick={() => { setLlmConsoleExpanded(true); jumpTo("cohort-console"); }} className="rounded border border-stroke px-2 py-1 text-xs hover:text-cyan">Jump to Console</button>
            </div>
          </div>
          <div className="mt-3 max-h-[340px] overflow-auto rounded-lg border border-stroke/70 xl:mt-0">
              <table className="w-full text-xs">
                <thead className="sticky top-0 z-20 bg-bg">
                  <tr className="border-b border-stroke text-left text-slate-400">
                    <th className="sticky left-0 z-10 bg-bg px-2 py-2">Symbol</th>
                    <th className="px-2 py-2">Original Snapshot</th>
                    <th className="px-2 py-2">Latest Follow-up</th>
                    <th className="px-2 py-2">Return Since Selection</th>
                    <th className="px-2 py-2">Current Status</th>
                    <th className="px-2 py-2">Blocked By</th>
                    <th className="px-2 py-2">Data Quality</th>
                    <th className="px-2 py-2">Forward Performance</th>
                  </tr>
                </thead>
                <tbody>
                  {!selectedCohortId ? (
                    <tr><td className="px-2 py-3 text-slate-400" colSpan={8}>No cohort selected.</td></tr>
                  ) : (selectedCohortMeta?.status === "archived" ? (
                    <tr><td className="px-2 py-3 text-slate-400" colSpan={8}>Selected cohort is archived. Follow-up actions are disabled.</td></tr>
                  ) : null)}
                  {selectedCohortId && !selectedCohortDetail ? (
                    <tr><td className="px-2 py-3 text-slate-400" colSpan={8}>Selected cohort could not be loaded (API error or missing cohort_id).</td></tr>
                  ) : null}
                  {selectedCohortId && (selectedCohortDetail?.candidates?.length ?? 0) === 0 ? (
                    <tr><td className="px-2 py-3 text-slate-400" colSpan={8}>No candidates found for selected cohort.</td></tr>
                  ) : null}
                  {selectedCohortId && (selectedCohortDetail?.candidates?.length ?? 0) > 0 && (selectedCohortDetail?.latest_states?.length ?? 0) === 0 ? (
                    <tr><td className="px-2 py-3 text-slate-400" colSpan={8}>Follow-up not run yet for this cohort.</td></tr>
                  ) : null}
                  {(selectedCohortDetail?.latest_states ?? []).map((row) => {
                    const original = (selectedCohortDetail?.candidates ?? []).find((x) => x.symbol === row.symbol);
                    const validity = row.validity_state ?? "pending_validation";
                    return (
                      <tr key={`${row.cohort_id}-${row.symbol}`} className="border-b border-stroke/50">
                        <td className="sticky left-0 z-10 bg-bg px-2 py-2">{row.symbol}</td>
                        <td className="px-2 py-2 min-w-[320px]">
                          <p>selected_score={row.selected_score.toFixed(2)} | selected_setup={row.selected_setup_type}</p>
                          <details className="mt-1">
                            <summary className="cursor-pointer text-slate-300">Original why selected</summary>
                            <p className="mt-1 text-slate-300">{original?.selected_reason ?? row.selected_reason ?? "-"}</p>
                          </details>
                        </td>
                        <td className="px-2 py-2">{row.latest_followup_date ?? "pending"}</td>
                        <td className="px-2 py-2">{row.return_since_selection ?? "pending"}</td>
                        <td className="px-2 py-2">
                          {!row.latest_followup_date
                            ? "pending follow-up"
                            : validity === "needs_data_check"
                              ? "needs_data_check"
                            : validity === "pending_validation"
                              ? "pending validation"
                              : validity === "valid"
                                ? "valid"
                                : `invalid (${row.invalidation_reason ?? "n/a"})`}
                        </td>
                        <td className="px-2 py-2">{row.blocked_by ?? "none"}</td>
                        <td className="px-2 py-2">{row.data_quality_flags?.length ? row.data_quality_flags.join(", ") : "-"}</td>
                        <td className="px-2 py-2">1D:{row.return_1d ?? "pending"} 3D:{row.return_3d ?? "pending"} 7D:{row.return_7d ?? "pending"} 14D:{row.return_14d ?? "pending"} 28D:{row.return_28d ?? "pending"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
          </div>
        </div>
        {cohortContextFailedSymbols.length > 0 ? (
          <div className="mt-2 flex items-center gap-2 text-xs">
            <span className="text-red">Failed symbols: {cohortContextFailedSymbols.join(", ")}</span>
            <button type="button" onClick={() => runCohortContexts(true)} disabled={loading || !canRunCohortContexts} className="rounded border border-stroke px-2 py-1 hover:text-cyan disabled:opacity-60">Retry Failed Symbols</button>
          </div>
        ) : null}
        {cohortReview ? <p className="mt-2 text-xs text-slate-300">{cohortReview.readiness_message}</p> : null}
      </Panel>
      </section>

      <section id="cohort-console">
      <Panel>
          <SectionTitle title="Pipeline / LLM Console" subtitle="Placed near Active Cohorts for follow-up/context runs" />
          {llmStatus ? (
            <p className="text-xs text-slate-400">
              Endpoint: {llmStatus.base_url} | Checked: {new Date(llmStatus.checked_at).toLocaleString()} | Status: {llmStatus.connected ? "connected" : `error: ${llmStatus.error ?? "unknown"}`}
            </p>
          ) : null}
          <div className="mt-2">
            <button type="button" onClick={() => setLlmConsoleExpanded((prev) => !prev)} className="rounded border border-stroke px-2 py-1 text-xs hover:text-cyan">
              {llmConsoleExpanded ? "Minimize Console" : "Expand Console"}
            </button>
          </div>
          {llmConsoleExpanded ? (
          <>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
            <button type="button" onClick={() => setConsoleTab("pipeline")} className={`rounded border px-2 py-1 ${consoleTab === "pipeline" ? "border-cyan/60 text-cyan" : "border-stroke text-slate-300"}`}>Pipeline Steps</button>
            <button type="button" onClick={() => setConsoleTab("llm")} className={`rounded border px-2 py-1 ${consoleTab === "llm" ? "border-cyan/60 text-cyan" : "border-stroke text-slate-300"}`}>LLM Calls</button>
            {consoleTab === "llm" ? (
              <>
                <select value={llmStatusFilter} onChange={(e) => setLlmStatusFilter(e.target.value as "all" | "success" | "fail")} className="h-8 rounded border border-stroke bg-bg px-2 text-xs">
                  <option value="all">All Status</option>
                  <option value="success">Success</option>
                  <option value="fail">Fail</option>
                </select>
                <select value={llmProviderFilter} onChange={(e) => setLlmProviderFilter(e.target.value as "all" | "openai" | "ollama")} className="h-8 rounded border border-stroke bg-bg px-2 text-xs">
                  <option value="all">All Providers</option>
                  <option value="openai">OpenAI</option>
                  <option value="ollama">Ollama</option>
                </select>
                <span className="text-slate-400">showing {filteredLlmLogs.length}/{llmLogs.length}</span>
              </>
            ) : null}
          </div>

          {consoleTab === "pipeline" ? (
            <div className="mt-3 max-h-[460px] overflow-auto rounded-lg border border-stroke/70">
              <table className="w-full text-xs">
                <thead className="sticky top-0 z-20 bg-bg">
                  <tr className="border-b border-stroke text-left text-slate-400">
                    <th className="px-2 py-2">Time</th>
                    <th className="px-2 py-2">Action</th>
                    <th className="px-2 py-2">Cohort</th>
                    <th className="px-2 py-2">Cohort ID</th>
                    <th className="px-2 py-2">Status</th>
                    <th className="px-2 py-2">Category</th>
                    <th className="px-2 py-2">Symbol</th>
                    <th className="px-2 py-2">Provider</th>
                    <th className="px-2 py-2">Duration ms</th>
                    <th className="px-2 py-2">Message</th>
                    <th className="px-2 py-2">Details</th>
                  </tr>
                </thead>
                <tbody>
                  {pipelineEvents.map((row) => {
                    const relatedLog = expandedPipelineIds[row.id] ? getRelatedLogForEvent(row) : null;
                    return (
                      <Fragment key={row.id}>
                        <tr
                          className={`border-b border-stroke/50 cursor-pointer ${row.status === "failed" ? "bg-red/10" : ""} ${expandedPipelineIds[row.id] ? "bg-cyan/5" : ""}`}
                          onClick={() => setExpandedPipelineIds((prev) => ({ ...prev, [row.id]: !prev[row.id] }))}
                        >
                          <td className="px-2 py-2">{new Date(row.timestamp).toLocaleTimeString()}</td>
                          <td className="px-2 py-2">{row.step_name}</td>
                          <td className="px-2 py-2">{row.cohort_name ?? "-"}</td>
                          <td className="px-2 py-2">{row.cohort_id ?? "-"}</td>
                          <td className={`px-2 py-2 ${row.status === "failed" ? "text-red" : row.status === "success" ? "text-green" : "text-yellow-300"}`}>{row.status}</td>
                          <td className="px-2 py-2">{row.category ?? "-"}</td>
                          <td className="px-2 py-2">{row.symbol ?? "-"}</td>
                          <td className="px-2 py-2">{row.provider ?? "-"}</td>
                          <td className="px-2 py-2">{row.duration_ms}</td>
                          <td className="px-2 py-2">{row.error_message ?? row.message ?? "-"}</td>
                          <td className="px-2 py-2">
                            <button
                              type="button"
                              onClick={(event) => {
                                event.stopPropagation();
                                setExpandedPipelineIds((prev) => ({ ...prev, [row.id]: !prev[row.id] }));
                              }}
                              className="rounded border border-stroke px-2 py-1 hover:text-cyan"
                            >
                              {expandedPipelineIds[row.id] ? "Collapse" : "Expand"}
                            </button>
                          </td>
                        </tr>
                        {expandedPipelineIds[row.id] ? (
                          <tr className="border-b border-stroke/40 bg-panelSoft/60">
                            <td className="px-2 py-2 text-slate-300" colSpan={11}>
                              <p className="mb-1 text-slate-300">Full message</p>
                              <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded border border-stroke/60 bg-bg/50 p-2">{row.error_message ?? row.message ?? "-"}</pre>
                              {(row.error_message ?? "").includes("JSON") || (row.error_message ?? "").includes("Unterminated string") ? (
                                <p className="mt-2 text-xs text-yellow-300">
                                  Meaning: model output was not valid JSON text (usually an unclosed quote or malformed text fragment).
                                </p>
                              ) : null}
                              {relatedLog ? (
                                <div className="mt-3">
                                  <p className="text-slate-200">Related LLM call: {relatedLog.provider ?? "-"} / {relatedLog.model ?? "-"}</p>
                                  <p className="mt-1 text-slate-300">Prompt</p>
                                  <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded border border-stroke/60 bg-bg/50 p-2">{relatedLog.prompt_preview ?? relatedLog.prompt}</pre>
                                  <p className="mt-2 text-slate-300">Response</p>
                                  <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded border border-stroke/60 bg-bg/50 p-2">{relatedLog.response_preview ?? relatedLog.raw_response ?? "-"}</pre>
                                </div>
                              ) : (
                                <p className="mt-2 text-xs text-slate-400">No matching LLM log found for this pipeline event.</p>
                              )}
                            </td>
                          </tr>
                        ) : null}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="mt-3 max-h-[460px] overflow-auto rounded-lg border border-stroke/70">
              <table className="w-full text-xs">
                <thead className="sticky top-0 z-20 bg-bg">
                  <tr className="border-b border-stroke text-left text-slate-400">
                    <th className="px-2 py-2">Time</th>
                    <th className="px-2 py-2">Symbol</th>
                    <th className="px-2 py-2">Type</th>
                    <th className="px-2 py-2">Provider</th>
                    <th className="px-2 py-2">Model</th>
                    <th className="px-2 py-2">Status</th>
                    <th className="px-2 py-2">Fallback</th>
                    <th className="px-2 py-2">Duration ms</th>
                    <th className="px-2 py-2">Tokens Est.</th>
                    <th className="px-2 py-2">Details</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredLlmLogs.map((row) => (
                    <Fragment key={row.id}>
                      <tr className={`border-b border-stroke/50 ${row.status === "fail" ? "bg-red/10" : ""}`}>
                        <td className="px-2 py-2">{new Date(row.timestamp).toLocaleTimeString()}</td>
                        <td className="px-2 py-2">{row.symbol ?? "-"}</td>
                        <td className="px-2 py-2">{row.call_type}</td>
                        <td className="px-2 py-2">{row.provider ?? "-"}</td>
                        <td className="px-2 py-2">{row.model ?? "-"}</td>
                        <td className={`px-2 py-2 ${row.status === "fail" ? "text-red" : "text-green"}`}>{row.status}</td>
                        <td className="px-2 py-2">{row.fallback_used ? `yes (${row.fallback_provider ?? "-"})` : "no"}</td>
                        <td className="px-2 py-2">{row.duration_ms}</td>
                        <td className="px-2 py-2">{row.token_estimate ?? 0}</td>
                        <td className="px-2 py-2"><button type="button" onClick={() => setExpandedLogIds((prev) => ({ ...prev, [row.id]: !prev[row.id] }))} className="rounded border border-stroke px-2 py-1 hover:text-cyan">{expandedLogIds[row.id] ? "Collapse" : "Expand"}</button></td>
                      </tr>
                      {expandedLogIds[row.id] ? (
                        <tr className="border-b border-stroke/40 bg-panelSoft/60">
                          <td className="px-2 py-2 text-slate-300" colSpan={10}>
                            {row.error_message ? <p className="mb-2 text-red">Error: {row.error_message}</p> : null}
                            <p className="mb-2 text-slate-300">Endpoint: {row.endpoint}</p>
                            <p className="font-semibold text-slate-200">Prompt Preview</p>
                            <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded border border-stroke/60 bg-bg/50 p-2">{row.prompt_preview ?? row.prompt.slice(0, 300)}</pre>
                            <p className="mt-2 font-semibold text-slate-200">Response Preview</p>
                            <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded border border-stroke/60 bg-bg/50 p-2">{row.response_preview ?? (row.raw_response ? row.raw_response.slice(0, 300) : "-")}</pre>
                            <p className="mt-2 font-semibold text-slate-200">Parsed/Used Output</p>
                            <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded border border-stroke/60 bg-bg/50 p-2">{JSON.stringify(row.parsed_output, null, 2)}</pre>
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          </>
          ) : (
            <p className="mt-3 text-xs text-slate-400">Console minimized. Expand anytime to inspect pipeline and LLM call details.</p>
          )}
      </Panel>
      </section>

      <section id="candidates">
      <Panel>
        <SectionTitle title="Latest Merged Candidates" subtitle="Category-balanced merge, deduplication, and multi-category priority boost" />
        <div className="max-h-[360px] overflow-auto rounded-lg border border-stroke/70">
          <table className="w-full text-xs">
            <thead className="sticky top-0 z-20 bg-bg">
              <tr className="border-b border-stroke text-left text-slate-400">
                <th className="px-2 py-2">Merged Rank</th>
                <th className="px-2 py-2">Symbol</th>
                <th className="px-2 py-2">Category Source</th>
                <th className="px-2 py-2">Score / Category</th>
                <th className="px-2 py-2">Score Breakdown</th>
                <th className="px-2 py-2 whitespace-nowrap">Multi-Category</th>
                <th className="px-2 py-2">Why Selected</th>
                <th className="px-2 py-2">Daily Change</th>
                <th className="px-2 py-2">Forward Perf</th>
              </tr>
            </thead>
            <tbody>
              {(dashboard?.latest_run_results ?? []).map((row) => (
                <tr key={`${row.symbol}-${row.merged_rank}`} className="border-b border-stroke/50">
                  <td className="px-2 py-2">{row.merged_rank}</td>
                  <td className="px-2 py-2 font-semibold text-slate-100">{row.symbol}</td>
                  <td className="px-2 py-2">{row.category_tags.join(", ")}</td>
                  <td className="px-2 py-2">{Object.entries(row.score_by_category).map(([k, v]) => `${k}:${v.toFixed(1)}`).join(" | ")}</td>
                  <td className="px-2 py-2">
                    base:{row.base_score.toFixed(1)} + boost:{row.category_boost.toFixed(1)} + dq:{row.data_quality_penalty.toFixed(1)} = displayed:{row.score.toFixed(1)}
                  </td>
                  <td className="px-2 py-2 whitespace-nowrap">{row.multi_category ? <span className="inline-flex shrink-0 whitespace-nowrap rounded border border-cyan/60 px-2 py-1 text-cyan">multi-category</span> : "-"}</td>
                  <td className="px-2 py-2 min-w-[320px]">{row.why_selected || "-"}</td>
                  <td className="px-2 py-2 min-w-[260px]">{String(row.daily_change?.message ?? "No previous run comparison")}</td>
                  <td className="px-2 py-2">
                    1D:{row.return_1d ?? "pending"} | 3D:{row.return_3d ?? "pending"} | 7D:{row.return_7d ?? "pending"} | 14D:{row.return_14d ?? "pending"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      </section>

      <section id="review-readiness">
      <Panel>
        <SectionTitle title="Review Readiness" subtitle="Deterministic review input health before 28-day review" />
        <div className="text-xs text-slate-300 space-y-1">
          <p>Runs collected: {dashboard?.review_readiness?.runs_collected ?? 0}</p>
          <p>Unique days: {dashboard?.review_readiness?.unique_days ?? 0}</p>
          <p>Symbols tracked: {dashboard?.review_readiness?.symbols_tracked ?? 0}</p>
          <p>Days until 28-day review: {dashboard?.review_readiness?.days_until_28_day_review ?? 28}</p>
          <p>Status: {dashboard?.review_readiness?.message ?? "-"}</p>
          <p>Best category by 7D: {dashboard?.deterministic_review_stats?.best_category_by_7d ?? "-"}</p>
          <p>Worst category by 7D: {dashboard?.deterministic_review_stats?.worst_category_by_7d ?? "-"}</p>
        </div>
      </Panel>
      </section>

      </div>
    </main>
  );
}
