"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Panel, Pill, SectionTitle, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import type {
  IntelligenceDashboardResponse,
  MarketCode,
  ScannerCategory,
  StrategyLabExperiment,
  StrategyLabExperimentDetail,
  StrategyLabNumeric,
} from "@/lib/types";

const categories: ScannerCategory[] = ["trend_mode", "build_up", "momentum_mode", "value_rebuild", "overextended"];

function errorMessage(error: unknown): string {
  if (!(error instanceof Error)) return "The request failed.";
  try {
    const payload = JSON.parse(error.message) as { detail?: unknown };
    if (typeof payload.detail === "string") return payload.detail;
    return JSON.stringify(payload.detail ?? payload);
  } catch {
    return error.message;
  }
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function categoryLabel(category: string): string {
  return category.replace(/_/g, " ");
}

function money(value: StrategyLabNumeric | null | undefined): string {
  if (value === null || value === undefined) return "-";
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `$${numeric.toFixed(2)}` : String(value);
}

function valueText(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

function localDateTimeValue(date: Date): string {
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function todayValue(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function PortfolioPage() {
  const [experiments, setExperiments] = useState<StrategyLabExperiment[]>([]);
  const [detail, setDetail] = useState<StrategyLabExperimentDetail | null>(null);
  const [dashboard, setDashboard] = useState<IntelligenceDashboardResponse | null>(null);
  const [selectedExperimentId, setSelectedExperimentId] = useState("");
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [featureError, setFeatureError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [experimentName, setExperimentName] = useState("");
  const [experimentMarket, setExperimentMarket] = useState<MarketCode>("us");
  const [activationAt, setActivationAt] = useState(() => localDateTimeValue(new Date(Date.now() + 60 * 60 * 1000)));
  const [confirmVirtual, setConfirmVirtual] = useState(false);
  const [sourceRunId, setSourceRunId] = useState("");
  const [symbol, setSymbol] = useState("");
  const [category, setCategory] = useState<ScannerCategory>("trend_mode");
  const [processDate, setProcessDate] = useState(todayValue);
  const [confirmProcess, setConfirmProcess] = useState(false);

  const loadExperiment = useCallback(async (experimentId: string) => {
    if (!experimentId) {
      setDetail(null);
      return;
    }
    const response = await api.getStrategyLabExperiment(experimentId);
    setDetail(response);
  }, []);

  const load = useCallback(async (preferredExperimentId?: string) => {
    setLoading(true);
    setActionError(null);
    setFeatureError(null);
    const [experimentsResult, dashboardResult] = await Promise.allSettled([
      api.listStrategyLabExperiments(),
      api.getIntelligenceDashboard(),
    ]);

    if (dashboardResult.status === "fulfilled") {
      setDashboard(dashboardResult.value);
      const latest = dashboardResult.value.runs[0];
      if (latest) setSourceRunId((current) => current || latest.id);
    }

    if (experimentsResult.status === "rejected") {
      setFeatureError(errorMessage(experimentsResult.reason));
      setExperiments([]);
      setDetail(null);
      setLoading(false);
      return;
    }

    const nextExperiments = experimentsResult.value;
    setExperiments(nextExperiments);
    const nextId = preferredExperimentId ?? selectedExperimentId ?? nextExperiments[0]?.id ?? "";
    setSelectedExperimentId(nextId);
    try {
      await loadExperiment(nextId);
    } catch (requestError) {
      setActionError(errorMessage(requestError));
    } finally {
      setLoading(false);
    }
  }, [loadExperiment, selectedExperimentId]);

  useEffect(() => {
    void load();
  }, [load]);

  const selectExperiment = async (experimentId: string) => {
    setSelectedExperimentId(experimentId);
    setActionError(null);
    try {
      await loadExperiment(experimentId);
    } catch (requestError) {
      setActionError(errorMessage(requestError));
    }
  };

  const createExperiment = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!confirmVirtual) {
      setActionError("Confirm that this creates a virtual experiment only before continuing.");
      return;
    }
    setWorking(true);
    setActionError(null);
    setNotice(null);
    try {
      const created = await api.createStrategyLabExperiment({
        name: experimentName.trim(),
        activation_at: new Date(activationAt).toISOString(),
        market: experimentMarket,
      });
      setExperimentName("");
      setConfirmVirtual(false);
      setNotice(`Virtual experiment ${created.experiment.name} created. It remains ${created.experiment.status} until explicitly activated.`);
      await load(created.experiment.id);
    } catch (requestError) {
      setActionError(errorMessage(requestError));
    } finally {
      setWorking(false);
    }
  };

  const activateExperiment = async () => {
    if (!detail) return;
    setWorking(true);
    setActionError(null);
    setNotice(null);
    try {
      const activated = await api.activateStrategyLabExperiment(detail.experiment.id);
      setDetail(activated);
      setNotice("Experiment activated manually. It can accept only fresh deterministic daily-run evidence after its activation time.");
      await load(detail.experiment.id);
    } catch (requestError) {
      setActionError(errorMessage(requestError));
    } finally {
      setWorking(false);
    }
  };

  const addDecision = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!detail) return;
    setWorking(true);
    setActionError(null);
    setNotice(null);
    try {
      const decision = await api.createStrategyLabDecision(detail.experiment.id, {
        source_run_id: sourceRunId.trim(),
        symbol: symbol.trim().toUpperCase(),
        category,
      });
      setNotice(`Deterministic decision recorded as ${decision.decision_status}. The frozen source evidence was retained by the ledger.`);
      setSymbol("");
      await load(detail.experiment.id);
    } catch (requestError) {
      setActionError(errorMessage(requestError));
    } finally {
      setWorking(false);
    }
  };

  const processExperiment = async () => {
    if (!detail) return;
    if (!confirmProcess) {
      setActionError("Confirm the selected as-of date before manually processing canonical bars.");
      return;
    }
    setWorking(true);
    setActionError(null);
    setNotice(null);
    try {
      const result = await api.processStrategyLabExperiment(detail.experiment.id, processDate);
      setConfirmProcess(false);
      setNotice(`Processed ${result.as_of_date}: ${result.entry_fills_created} fills, ${result.valuations_created} valuations, ${result.exits_created} exits, ${result.data_quality_holds} data-quality holds.`);
      await load(detail.experiment.id);
    } catch (requestError) {
      setActionError(errorMessage(requestError));
    } finally {
      setWorking(false);
    }
  };

  const sleeveMetrics = useMemo(() => asRecord(detail?.metrics.sleeves), [detail]);
  const avoidedMetrics = useMemo(() => asRecord(detail?.metrics.avoided_basket), [detail]);
  const latestRun = dashboard?.runs[0] ?? null;

  return (
    <main className="space-y-4">
      <Panel className="border-violet/40 bg-gradient-to-r from-panel to-panelSoft">
        <p className="text-xs font-medium uppercase tracking-wide text-violet">Manual Strategy Lab</p>
        <h2 className="mt-1 text-2xl font-semibold">Portfolio</h2>
        <p className="mt-2 max-w-4xl text-sm text-slate-300">
          Strategy Lab is a future-only virtual experiment ledger. It does not submit broker orders, convert cohorts into trades, or allow an LLM to create a decision.
        </p>
      </Panel>

      <Panel>
        <SectionTitle title="How Portfolio works" subtitle="Virtual experiment workflow; this is not a broker portfolio." />
        <ol className="grid gap-3 text-sm text-slate-300 md:grid-cols-4">
          <li><span className="font-semibold text-cyan">1. Discover</span><br />Run the unchanged deterministic US or BIST scanner.</li>
          <li><span className="font-semibold text-cyan">2. Create</span><br />Create and manually activate a future-only virtual experiment.</li>
          <li><span className="font-semibold text-cyan">3. Record</span><br />Submit an eligible candidate from a fresh run; the backend freezes its evidence.</li>
          <li><span className="font-semibold text-cyan">4. Process</span><br />Manually process canonical bars for virtual fills, valuations, and the fixed 56-session exit.</li>
        </ol>
        <p className="mt-3 text-xs text-slate-400">No broker order, automatic scheduler, historical cohort conversion, scanner-rule change, or LLM trade decision is possible here.</p>
      </Panel>

      {featureError ? (
        <Panel className="border-amber/50 bg-amber/5">
          <SectionTitle title="Strategy Lab is unavailable in this runtime" />
          <p className="text-sm text-amber">{featureError}</p>
          <p className="mt-2 text-xs text-slate-400">When the backend reports feature gating, an operator must intentionally enable both Product V2 and Strategy Lab. This UI does not change environment flags, start a scheduler, or activate an experiment.</p>
        </Panel>
      ) : null}
      {actionError ? <Panel className="border-red/50 text-sm text-red">{actionError}</Panel> : null}
      {notice ? <Panel className="border-green/50 text-sm text-green">{notice}</Panel> : null}

      <div className="grid gap-3 md:grid-cols-3">
        <StatCard label="Virtual experiments" value={String(experiments.length)} />
        <StatCard label="Latest discovery run" value={latestRun?.date ?? "No run"} />
        <StatCard label="Experiment status" value={detail?.experiment.status ?? "Unavailable"} />
      </div>

      {!featureError ? (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
          <Panel>
            <SectionTitle title="Experiments" subtitle="Manual, future-only and virtual." />
            {loading ? <p className="text-sm text-slate-400">Loading Strategy Lab ledger…</p> : null}
            {!loading && experiments.length === 0 ? <p className="text-sm text-slate-400">No virtual experiments have been created.</p> : null}
            <div className="space-y-2">
              {experiments.map((experiment) => (
                <button
                  key={experiment.id}
                  type="button"
                  onClick={() => void selectExperiment(experiment.id)}
                  className={`w-full rounded-lg border p-3 text-left text-sm transition ${selectedExperimentId === experiment.id ? "border-cyan/50 bg-cyan/10" : "border-stroke bg-panelSoft hover:border-cyan/30"}`}
                >
                  <div className="flex items-center justify-between gap-2"><span className="font-semibold">{experiment.name}</span><Pill>{experiment.status}</Pill></div>
                  <p className="mt-1 text-xs text-slate-400">Activation: {new Date(experiment.activation_at).toLocaleString()}</p>
                </button>
              ))}
            </div>

            <form onSubmit={createExperiment} className="mt-5 space-y-3 border-t border-stroke pt-4">
              <h3 className="text-sm font-semibold">Create virtual experiment</h3>
              <input required value={experimentName} onChange={(event) => setExperimentName(event.target.value)} placeholder="Experiment name" className="w-full rounded-lg border border-stroke bg-bg px-3 py-2 text-sm" />
              <label className="block text-xs text-slate-400">Market
                <select value={experimentMarket} onChange={(event) => setExperimentMarket(event.target.value as MarketCode)} className="mt-1 w-full rounded-lg border border-stroke bg-bg px-3 py-2 text-sm text-slate-100">
                  <option value="us">US stocks</option>
                  <option value="bist">BIST stocks</option>
                </select>
              </label>
              <label className="block text-xs text-slate-400">Activation time (local time, stored as UTC)
                <input required type="datetime-local" value={activationAt} onChange={(event) => setActivationAt(event.target.value)} className="mt-1 w-full rounded-lg border border-stroke bg-bg px-3 py-2 text-sm text-slate-100" />
              </label>
              <label className="flex gap-2 text-xs text-slate-300"><input type="checkbox" checked={confirmVirtual} onChange={(event) => setConfirmVirtual(event.target.checked)} className="accent-cyan" /> I understand this creates a virtual experiment only; it cannot trade a broker account.</label>
              <button disabled={working} className="rounded-lg border border-cyan/50 bg-cyan/15 px-3 py-2 text-sm font-semibold text-cyan disabled:opacity-50">Create experiment</button>
            </form>
          </Panel>

          <section className="space-y-4">
            {!detail && !loading ? <Panel><p className="text-sm text-slate-400">Select an experiment to inspect its ledger.</p></Panel> : null}
            {detail ? <ExperimentDetail detail={detail} sleeveMetrics={sleeveMetrics} avoidedMetrics={avoidedMetrics} working={working} sourceRunId={sourceRunId} symbol={symbol} category={category} processDate={processDate} confirmProcess={confirmProcess} onActivate={() => void activateExperiment()} onDecision={addDecision} onSourceRunId={setSourceRunId} onSymbol={setSymbol} onCategory={setCategory} onProcessDate={setProcessDate} onConfirmProcess={setConfirmProcess} onProcess={() => void processExperiment()} /> : null}
          </section>
        </div>
      ) : null}
    </main>
  );
}

function ExperimentDetail({
  detail,
  sleeveMetrics,
  avoidedMetrics,
  working,
  sourceRunId,
  symbol,
  category,
  processDate,
  confirmProcess,
  onActivate,
  onDecision,
  onSourceRunId,
  onSymbol,
  onCategory,
  onProcessDate,
  onConfirmProcess,
  onProcess,
}: {
  detail: StrategyLabExperimentDetail;
  sleeveMetrics: Record<string, unknown>;
  avoidedMetrics: Record<string, unknown>;
  working: boolean;
  sourceRunId: string;
  symbol: string;
  category: ScannerCategory;
  processDate: string;
  confirmProcess: boolean;
  onActivate: () => void;
  onDecision: (event: FormEvent<HTMLFormElement>) => void;
  onSourceRunId: (value: string) => void;
  onSymbol: (value: string) => void;
  onCategory: (value: ScannerCategory) => void;
  onProcessDate: (value: string) => void;
  onConfirmProcess: (value: boolean) => void;
  onProcess: () => void;
}) {
  const metrics = detail.metrics;
  const scheduled = detail.experiment.status === "scheduled";
  const active = detail.experiment.status === "active";

  return <>
    <Panel>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <SectionTitle title={detail.experiment.name} subtitle={`Policy ${detail.experiment.policy_version} · rule ${detail.experiment.rule_version} · data ${detail.experiment.data_version}`} />
          <p className="text-xs text-slate-400">Activated at {new Date(detail.experiment.activation_at).toLocaleString()} · {detail.experiment.market.toUpperCase()} virtual ledger</p>
        </div>
        <Pill className={active ? "border-green/40 text-green" : "border-amber/40 text-amber"}>{detail.experiment.status}</Pill>
      </div>
      {scheduled ? <button type="button" disabled={working} onClick={onActivate} className="mt-4 rounded-lg border border-amber/50 bg-amber/10 px-3 py-2 text-sm font-semibold text-amber disabled:opacity-50">Activate manually</button> : null}
      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <StatCard label="Realised P&L" value={money(metrics.realised_pnl as StrategyLabNumeric | null)} />
        <StatCard label="Hit rate" value={metrics.hit_rate_pct === null || metrics.hit_rate_pct === undefined ? "-" : `${valueText(metrics.hit_rate_pct)}%`} />
        <StatCard label="Data-quality holds" value={valueText(metrics.data_quality_hold_count)} />
      </div>
    </Panel>

    <Panel>
      <SectionTitle title="Sleeves" subtitle="Avoided overextended observations stay outside realised P&L." />
      <div className="grid gap-3 md:grid-cols-2">
        {detail.sleeves.map((sleeve) => {
          const metric = asRecord(sleeveMetrics[sleeve.sleeve_key]);
          return <div key={sleeve.id} className="rounded-xl border border-stroke bg-panelSoft p-3">
            <div className="flex justify-between gap-2"><span className="font-semibold capitalize">{categoryLabel(sleeve.sleeve_key)}</span><span className="text-xs text-slate-400">{valueText(metric.active_positions)}/{sleeve.max_positions} active</span></div>
            <p className="mt-2 text-sm text-slate-300">Cash {money(metric.cash as StrategyLabNumeric | null)} · open value {money(metric.open_value as StrategyLabNumeric | null)}</p>
            <p className="mt-1 text-xs text-slate-400">Slot allocation {money(sleeve.allocation_per_slot)} · capacity used {valueText(metric.capacity_used_pct)}%</p>
          </div>;
        })}
      </div>
      <div className="mt-4 rounded-xl border border-violet/30 bg-violet/5 p-3 text-sm">
        <span className="font-semibold text-violet">Avoided basket: </span>{valueText(avoidedMetrics.count)} observations, {valueText(avoidedMetrics.complete_count)} complete, average hypothetical return {valueText(avoidedMetrics.average_return_pct)}%. It is explicitly excluded from realised P&L.
      </div>
    </Panel>

    {active ? <Panel>
      <SectionTitle title="Manual ledger actions" subtitle="The backend deterministically accepts or rejects the frozen daily-run candidate; this form cannot override it." />
      <form onSubmit={onDecision} className="grid gap-3 md:grid-cols-3">
        <input required value={sourceRunId} onChange={(event) => onSourceRunId(event.target.value)} placeholder="Fresh daily run ID" className="rounded-lg border border-stroke bg-bg px-3 py-2 text-sm" />
        <input required value={symbol} onChange={(event) => onSymbol(event.target.value)} placeholder="Symbol" className="rounded-lg border border-stroke bg-bg px-3 py-2 text-sm" />
        <select value={category} onChange={(event) => onCategory(event.target.value as ScannerCategory)} className="rounded-lg border border-stroke bg-bg px-3 py-2 text-sm">
          {categories.map((option) => <option key={option} value={option}>{categoryLabel(option)}</option>)}
        </select>
        <button disabled={working} className="w-fit rounded-lg border border-cyan/50 bg-cyan/15 px-3 py-2 text-sm font-semibold text-cyan disabled:opacity-50">Record deterministic decision</button>
      </form>
      <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-stroke pt-4">
        <label className="text-xs text-slate-400">Process as of date <input type="date" value={processDate} onChange={(event) => onProcessDate(event.target.value)} className="ml-2 rounded border border-stroke bg-bg px-2 py-1 text-slate-100" /></label>
        <label className="flex gap-2 text-xs text-slate-300"><input type="checkbox" checked={confirmProcess} onChange={(event) => onConfirmProcess(event.target.checked)} className="accent-cyan" /> I confirm manual canonical-bar processing.</label>
        <button type="button" disabled={working} onClick={onProcess} className="rounded-lg border border-stroke bg-panelSoft px-3 py-2 text-sm font-semibold text-slate-200 disabled:opacity-50">Process experiment</button>
      </div>
    </Panel> : null}

    <Panel>
      <SectionTitle title="Positions and decisions" subtitle="Append-only decision evidence and projected position state." />
      <div className="grid gap-4 xl:grid-cols-2">
        <div className="overflow-x-auto">
          <h3 className="mb-2 text-sm font-semibold">Positions ({detail.positions.length})</h3>
          {detail.positions.length === 0 ? <p className="text-sm text-slate-400">No virtual positions.</p> : <table className="min-w-full text-left text-xs"><thead className="border-b border-stroke uppercase text-slate-400"><tr><th className="px-2 py-2">Symbol</th><th className="px-2 py-2">Status</th><th className="px-2 py-2">Entry</th><th className="px-2 py-2">P&L</th></tr></thead><tbody>{detail.positions.map((position) => <tr key={position.id} className="border-b border-stroke/70"><td className="px-2 py-2 font-semibold">{position.symbol}</td><td className="px-2 py-2">{position.status}</td><td className="px-2 py-2">{position.entry_date ?? "Pending"}</td><td className="px-2 py-2">{money(position.realised_pnl)}</td></tr>)}</tbody></table>}
        </div>
        <div className="overflow-x-auto">
          <h3 className="mb-2 text-sm font-semibold">Decisions ({detail.decisions.length})</h3>
          {detail.decisions.length === 0 ? <p className="text-sm text-slate-400">No decisions recorded.</p> : <table className="min-w-full text-left text-xs"><thead className="border-b border-stroke uppercase text-slate-400"><tr><th className="px-2 py-2">Symbol</th><th className="px-2 py-2">Status</th><th className="px-2 py-2">Reasons</th></tr></thead><tbody>{detail.decisions.map((decision) => <tr key={decision.id} className="border-b border-stroke/70"><td className="px-2 py-2 font-semibold">{decision.symbol}</td><td className="px-2 py-2">{decision.decision_status}</td><td className="px-2 py-2 text-slate-400">{decision.reason_codes.join(", ") || "-"}</td></tr>)}</tbody></table>}
        </div>
      </div>
    </Panel>
  </>;
}
