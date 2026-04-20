"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { UnifiedAnalysisChart } from "@/components/unified-analysis-chart";
import { ChartMapSectionCard, QuantEdgeSectionCard, SwingPulseSectionCard } from "@/components/unified-sections";
import { useAnalysisContext } from "@/components/analysis-context";
import { TickerControls } from "@/components/ticker-controls";
import { Panel, SectionTitle, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import { AnalysisConfig, AnalysisWindow, MarketCode, StrategyMode } from "@/lib/types";

type RegimeMode = "strict" | "medium" | "relaxed";

type ModePreset = {
  score_threshold: number;
  warmup_bars: number;
  regime_mode: RegimeMode;
  max_support_distance_pct: number;
  min_resistance_room_pct: number;
  min_trigger_score: number;
  max_overextension_ema20_pct: number;
  max_overextension_ema50_pct: number;
  max_overextension_ema100_pct: number;
  max_overextension_ema200_pct: number;
};

const MODE_PRESETS: Record<Exclude<StrategyMode, "custom">, ModePreset> = {
  aggressive: {
    score_threshold: 50,
    warmup_bars: 80,
    regime_mode: "relaxed",
    max_support_distance_pct: 7.5,
    min_resistance_room_pct: 1.5,
    min_trigger_score: 55,
    max_overextension_ema20_pct: 7,
    max_overextension_ema50_pct: 10,
    max_overextension_ema100_pct: 14,
    max_overextension_ema200_pct: 18,
  },
  balanced: {
    score_threshold: 60,
    warmup_bars: 80,
    regime_mode: "medium",
    max_support_distance_pct: 5,
    min_resistance_room_pct: 2.5,
    min_trigger_score: 65,
    max_overextension_ema20_pct: 5,
    max_overextension_ema50_pct: 8,
    max_overextension_ema100_pct: 11,
    max_overextension_ema200_pct: 15,
  },
  conservative: {
    score_threshold: 72,
    warmup_bars: 80,
    regime_mode: "strict",
    max_support_distance_pct: 3.5,
    min_resistance_room_pct: 3.5,
    min_trigger_score: 75,
    max_overextension_ema20_pct: 3,
    max_overextension_ema50_pct: 5,
    max_overextension_ema100_pct: 8,
    max_overextension_ema200_pct: 12,
  },
};

function InfoHint({ label, text }: { label: string; text: string }) {
  return (
    <div className="group relative">
      <span className="text-xs text-slate-400">{label}</span>
      <span className="ml-1 inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-stroke text-[10px] text-slate-300">?</span>
      <div className="pointer-events-none absolute left-0 top-5 z-10 hidden w-64 rounded-lg border border-stroke bg-bg p-2 text-xs text-slate-300 shadow-2xl group-hover:block">
        {text}
      </div>
    </div>
  );
}

export default function AnalysisPage() {
  return (
    <Suspense fallback={<main className="space-y-4"><Panel><SectionTitle title="Loading Analysis..." /></Panel></main>}>
      <AnalysisPageInner />
    </Suspense>
  );
}

function toPanelValues(config: AnalysisConfig | null): ModePreset {
  if (!config) {
    return MODE_PRESETS.balanced;
  }
  return {
    score_threshold: config.score_threshold,
    warmup_bars: config.warmup_bars,
    regime_mode: (config.regime_filter.regime_mode as RegimeMode) ?? "medium",
    max_support_distance_pct: config.location_filter.max_support_distance_pct,
    min_resistance_room_pct: config.location_filter.min_resistance_room_pct,
    min_trigger_score: config.trigger_filter.min_trigger_score,
    max_overextension_ema20_pct: config.location_filter.max_overextension_ema20_pct,
    max_overextension_ema50_pct: config.location_filter.max_overextension_ema50_pct,
    max_overextension_ema100_pct: config.location_filter.max_overextension_ema100_pct,
    max_overextension_ema200_pct: config.location_filter.max_overextension_ema200_pct,
  };
}

function AnalysisPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { analysis, setAnalysis } = useAnalysisContext();
  const [ticker, setTicker] = useState(analysis?.ticker ?? "TSLA");
  const [market, setMarket] = useState<MarketCode>(analysis?.market ?? "us");
  const [window, setWindow] = useState<AnalysisWindow>(analysis?.window ?? "6m");
  const [strategyMode, setStrategyMode] = useState<StrategyMode>(analysis?.strategy_mode_used ?? "balanced");

  const seed = toPanelValues(analysis?.analysis_config ?? null);
  const [scoreThreshold, setScoreThreshold] = useState(seed.score_threshold);
  const [warmupBars, setWarmupBars] = useState(seed.warmup_bars);
  const [regimeMode, setRegimeMode] = useState<RegimeMode>(seed.regime_mode);
  const [maxSupportDistancePct, setMaxSupportDistancePct] = useState(seed.max_support_distance_pct);
  const [minResistanceRoomPct, setMinResistanceRoomPct] = useState(seed.min_resistance_room_pct);
  const [minTriggerScore, setMinTriggerScore] = useState(seed.min_trigger_score);
  const [maxOver20, setMaxOver20] = useState(seed.max_overextension_ema20_pct);
  const [maxOver50, setMaxOver50] = useState(seed.max_overextension_ema50_pct);
  const [maxOver100, setMaxOver100] = useState(seed.max_overextension_ema100_pct);
  const [maxOver200, setMaxOver200] = useState(seed.max_overextension_ema200_pct);
  const [customSeeded, setCustomSeeded] = useState(strategyMode === "custom");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const nextTicker = searchParams.get("ticker");
    const nextMarket = searchParams.get("market");
    const nextWindow = searchParams.get("window");
    if (nextTicker) setTicker(nextTicker.toUpperCase());
    if (nextMarket === "us" || nextMarket === "bist") {
      setMarket(nextMarket);
    }
    if (nextWindow && ["5d", "1m", "3m", "6m", "1y", "2y", "3y", "4y", "5y", "10y"].includes(nextWindow)) {
      setWindow(nextWindow as AnalysisWindow);
    }
  }, [searchParams]);

  const applyPreset = (preset: ModePreset) => {
    setScoreThreshold(preset.score_threshold);
    setWarmupBars(preset.warmup_bars);
    setRegimeMode(preset.regime_mode);
    setMaxSupportDistancePct(preset.max_support_distance_pct);
    setMinResistanceRoomPct(preset.min_resistance_room_pct);
    setMinTriggerScore(preset.min_trigger_score);
    setMaxOver20(preset.max_overextension_ema20_pct);
    setMaxOver50(preset.max_overextension_ema50_pct);
    setMaxOver100(preset.max_overextension_ema100_pct);
    setMaxOver200(preset.max_overextension_ema200_pct);
  };

  const onModeChange = (next: StrategyMode) => {
    setStrategyMode(next);
    if (next === "custom") {
      if (!customSeeded) {
        applyPreset(MODE_PRESETS.balanced);
        setCustomSeeded(true);
      }
      return;
    }
    applyPreset(MODE_PRESETS[next]);
  };

  const onAnalyze = async () => {
    setLoading(true);
    setError(null);
    const config = {
      strategy_mode: strategyMode,
      score_threshold: scoreThreshold,
      warmup_bars: warmupBars,
      regime_filter: { regime_mode: regimeMode },
      location_filter: {
        max_support_distance_pct: maxSupportDistancePct,
        min_resistance_room_pct: minResistanceRoomPct,
        max_overextension_ema20_pct: maxOver20,
        max_overextension_ema50_pct: maxOver50,
        max_overextension_ema100_pct: maxOver100,
        max_overextension_ema200_pct: maxOver200,
      },
      trigger_filter: { min_trigger_score: minTriggerScore },
    };

    try {
      const result = await api.analyzeCombined(ticker, market, window, config);
      setAnalysis(result);
      if (result.analysis_config.strategy_mode === "custom") {
        setCustomSeeded(true);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run analysis.");
    } finally {
      setLoading(false);
    }
  };

  const readOnly = strategyMode !== "custom";

  return (
    <main className="space-y-4">
      <Panel>
        <SectionTitle title="Mode & Thresholds" subtitle="Preset modes are read-only. Switch to custom to edit filters." />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          <label className="space-y-1 text-sm">
            <InfoHint label="Strategy Mode" text="Aggressive, balanced, and conservative use fixed preset logic. Custom unlocks editable deterministic thresholds." />
            <select value={strategyMode} onChange={(event) => onModeChange(event.target.value as StrategyMode)} className="h-10 w-full rounded-lg border border-stroke bg-bg px-3 text-sm">
              <option value="aggressive">Aggressive</option>
              <option value="balanced">Balanced</option>
              <option value="conservative">Conservative</option>
              <option value="custom">Custom</option>
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <InfoHint label="Score Threshold" text="Minimum final score required before other gates can produce an actionable entry." />
            <input type="number" value={scoreThreshold} onChange={(event) => setScoreThreshold(Number(event.target.value))} className="h-10 w-full rounded-lg border border-stroke bg-bg px-3" disabled={readOnly} />
          </label>
          <label className="space-y-1 text-sm">
            <InfoHint label="Warmup Bars" text="Extra historical bars used for indicator stabilization before visible evaluation starts." />
            <input type="number" value={warmupBars} onChange={(event) => setWarmupBars(Number(event.target.value))} className="h-10 w-full rounded-lg border border-stroke bg-bg px-3" disabled={readOnly} />
          </label>
          <label className="space-y-1 text-sm">
            <InfoHint label="Regime Strictness" text="Controls EMA trend gate toughness: relaxed, medium, strict." />
            <select value={regimeMode} onChange={(event) => setRegimeMode(event.target.value as RegimeMode)} className="h-10 w-full rounded-lg border border-stroke bg-bg px-3 text-sm" disabled={readOnly}>
              <option value="relaxed">Relaxed</option>
              <option value="medium">Medium</option>
              <option value="strict">Strict</option>
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <InfoHint label="Support Max Distance %" text="Rejects entries too far above nearest support zone." />
            <input type="number" step="0.1" value={maxSupportDistancePct} onChange={(event) => setMaxSupportDistancePct(Number(event.target.value))} className="h-10 w-full rounded-lg border border-stroke bg-bg px-3" disabled={readOnly} />
          </label>
          <label className="space-y-1 text-sm">
            <InfoHint label="Min Resistance Room %" text="Minimum upside room required to nearest resistance for long entries." />
            <input type="number" step="0.1" value={minResistanceRoomPct} onChange={(event) => setMinResistanceRoomPct(Number(event.target.value))} className="h-10 w-full rounded-lg border border-stroke bg-bg px-3" disabled={readOnly} />
          </label>
          <label className="space-y-1 text-sm">
            <InfoHint label="Trigger Minimum Score" text="Timing confirmation threshold. Entries fail if trigger score stays below this value." />
            <input type="number" step="0.1" value={minTriggerScore} onChange={(event) => setMinTriggerScore(Number(event.target.value))} className="h-10 w-full rounded-lg border border-stroke bg-bg px-3" disabled={readOnly} />
          </label>
          <label className="space-y-1 text-sm">
            <InfoHint label="Overextension Cap EMA20 %" text="Max allowable distance above EMA20 before setup is treated as stretched/overextended." />
            <input type="number" step="0.1" value={maxOver20} onChange={(event) => setMaxOver20(Number(event.target.value))} className="h-10 w-full rounded-lg border border-stroke bg-bg px-3" disabled={readOnly} />
          </label>
          <label className="space-y-1 text-sm">
            <InfoHint label="Overextension Cap EMA50 %" text="Max allowable distance above EMA50 before location filter flags overextension." />
            <input type="number" step="0.1" value={maxOver50} onChange={(event) => setMaxOver50(Number(event.target.value))} className="h-10 w-full rounded-lg border border-stroke bg-bg px-3" disabled={readOnly} />
          </label>
          <label className="space-y-1 text-sm">
            <InfoHint label="Overextension Cap EMA100 %" text="Medium-term overextension cap used by the location gate." />
            <input type="number" step="0.1" value={maxOver100} onChange={(event) => setMaxOver100(Number(event.target.value))} className="h-10 w-full rounded-lg border border-stroke bg-bg px-3" disabled={readOnly} />
          </label>
          <label className="space-y-1 text-sm md:col-span-2 xl:col-span-1">
            <InfoHint label="Overextension Cap EMA200 %" text="Long-regime overextension cap to avoid chasing price far above EMA200." />
            <input type="number" step="0.1" value={maxOver200} onChange={(event) => setMaxOver200(Number(event.target.value))} className="h-10 w-full rounded-lg border border-stroke bg-bg px-3" disabled={readOnly} />
          </label>
        </div>
      </Panel>

      <TickerControls
        ticker={ticker}
        onTickerChange={setTicker}
        market={market}
        onMarketChange={(nextMarket) => {
          setMarket(nextMarket);
          if (nextMarket === "bist" && ticker.endsWith(".IS")) {
            setTicker(ticker.replace(".IS", ""));
          }
        }}
        window={window}
        onWindowChange={setWindow}
        onSubmit={onAnalyze}
        loading={loading}
        buttonLabel="Analyze"
      />

      {error ? (
        <Panel className="border-red/40 bg-red/10">
          <SectionTitle title="Request Error" />
          <p className="text-sm text-red">{error}</p>
        </Panel>
      ) : null}

      {!analysis && !loading ? (
        <Panel>
          <SectionTitle title="Unified Analysis" subtitle="Run one analysis flow to generate QuantEdge, SwingPulse, and ChartMap together." />
          <p className="text-sm text-slate-300">Backtest is unlocked after a successful analysis run.</p>
        </Panel>
      ) : null}

      {analysis ? (
        <>
          <UnifiedAnalysisChart
            chart={analysis.chart}
            title={`${analysis.ticker} Unified Analysis (${analysis.market.toUpperCase()} - ${analysis.window.toUpperCase()})`}
          />

          <Panel className="flex flex-col gap-3 bg-gradient-to-r from-panelSoft to-panel md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-sm text-slate-400">Context</p>
              <p className="text-sm text-slate-200">
                Combined analysis generated for {analysis.ticker} ({analysis.market.toUpperCase()} - {analysis.window.toUpperCase()}) as of {analysis.as_of}. Strategy mode: {analysis.strategy_mode_used}.
              </p>
            </div>
            <button
              type="button"
              onClick={() => router.push("/backtest")}
              className="h-10 rounded-lg bg-cyan px-5 text-sm font-semibold text-bg transition hover:brightness-110"
            >
              Open Backtest From This Analysis
            </button>
          </Panel>

          <Panel>
            <SectionTitle title="Analysis Config" subtitle="Official shared config and entry gate result" />
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
              <StatCard label="Market" value={analysis.analysis_config.market.toUpperCase()} />
              <StatCard label="Window" value={analysis.analysis_config.lookback_window.toUpperCase()} />
              <StatCard label="Mode" value={analysis.analysis_config.strategy_mode} />
              <StatCard label="Threshold" value={`${analysis.analysis_config.score_threshold.toFixed(1)}`} />
              <StatCard label="Warmup Bars" value={`${analysis.analysis_config.warmup_bars}`} />
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
              <StatCard label="Threshold Passed" value={analysis.analysis_pipeline.threshold_passed ? "Yes" : "No"} />
              <StatCard label="Regime Valid" value={analysis.analysis_pipeline.regime_valid ? "Yes" : "No"} />
              <StatCard label="Location Valid" value={analysis.analysis_pipeline.location_valid ? "Yes" : "No"} />
              <StatCard label="Trigger Valid" value={analysis.analysis_pipeline.trigger_valid ? "Yes" : "No"} />
              <StatCard label="Final Entry" value={analysis.analysis_pipeline.final_entry_decision ? "Yes" : "No"} />
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard label="Trend State" value={analysis.setup_interpretation.trend_state} />
              <StatCard label="Pullback State" value={analysis.setup_interpretation.pullback_state} />
              <StatCard label="Trigger State" value={analysis.setup_interpretation.trigger_state} />
              <StatCard label="Setup Status" value={analysis.setup_interpretation.setup_status} />
            </div>
            <div className="mt-3 rounded-xl border border-stroke/70 bg-panelSoft p-3 text-xs text-slate-300">
              Regime mode: {analysis.analysis_config.regime_filter.regime_mode}. Support max: {analysis.analysis_config.location_filter.max_support_distance_pct.toFixed(2)}%.
              Resistance min room: {analysis.analysis_config.location_filter.min_resistance_room_pct.toFixed(2)}%. Overextension caps (EMA20/50/100/200):
              {" "}{analysis.analysis_config.location_filter.max_overextension_ema20_pct.toFixed(2)}% /
              {" "}{analysis.analysis_config.location_filter.max_overextension_ema50_pct.toFixed(2)}% /
              {" "}{analysis.analysis_config.location_filter.max_overextension_ema100_pct.toFixed(2)}% /
              {" "}{analysis.analysis_config.location_filter.max_overextension_ema200_pct.toFixed(2)}%.
              Trigger minimum score: {analysis.analysis_config.trigger_filter.min_trigger_score.toFixed(1)}.
            </div>
          </Panel>

          <QuantEdgeSectionCard analysis={analysis} />
          <SwingPulseSectionCard analysis={analysis} />
          <ChartMapSectionCard analysis={analysis} />
        </>
      ) : null}
    </main>
  );
}
