"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { UnifiedAnalysisChart } from "@/components/unified-analysis-chart";
import { Panel, SectionTitle, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import {
  AlertProfileSuggestionRule,
  MarketCode,
  ScannerCustomRule,
  ScannerCategory,
  ScannerDuration,
  ScannerRequest,
  ScannerResponse,
  ScannerResult,
  LLMQChatMessage,
  ScannerLLMQChatResponse,
  ScannerRuleField,
  ScannerRuleOperator,
  ScannerUniverseScope,
  Watchlist,
  CombinedAnalysisResponse,
} from "@/lib/types";

const SCANNER_STATE_STORAGE_KEY = "tradeghost_scanner_state_v1";
const LLMQ_INITIAL_QUERY = "Give me a context-only explanation of why this symbol appeared in the scanner and what matters next.";
const BASE_LLMQ_CHIPS = [
  "Why is this interesting despite weak trend?",
  "What macro conditions matter here?",
  "What could invalidate this setup?",
  "What news would strengthen this candidate?",
  "Does valuation support this structure?",
  "Recovery story or dead-cat bounce risk?",
  "What would institutional buyers care about?",
  "What would improve confirmation?",
  "Compare with stronger names in this sector.",
];

const recommendedDurationByCategory: Record<ScannerCategory, ScannerDuration> = {
  trend_mode: "2y",
  build_up: "2y",
  momentum_mode: "1y",
  value_rebuild: "2y",
  overextended: "1y",
};

const rationaleByCategory: Record<ScannerCategory, string> = {
  trend_mode: "2Y is recommended to evaluate continuation quality with enough context.",
  build_up: "2Y is recommended to evaluate EMA200 reclaim/rebuild behavior before breakout.",
  momentum_mode: "1Y is recommended to prioritize recent expansion dynamics while preserving enough trend context.",
  value_rebuild: "2Y is recommended so rebuild and valuation-recovery structure can be observed with enough context.",
  overextended: "1Y is recommended to focus on recent stretched moves and caution zones.",
};

const categoryDefinition: Record<ScannerCategory, { title: string; desc: string; bias: string }> = {
  trend_mode: {
    title: "Trend Mode",
    desc: "Stocks already in constructive uptrend with favorable EMA alignment and continuation potential.",
    bias: "continuation bias",
  },
  build_up: {
    title: "Build-up",
    desc: "Stocks preparing for larger moves: EMA200 reclaim attempts, repeated tests, compression, and structure rebuilding.",
    bias: "pre-breakout bias",
  },
  momentum_mode: {
    title: "Momentum Mode",
    desc: "Stocks already breaking out or expanding with strong structure and improving score dynamics.",
    bias: "expansion / continuation bias",
  },
  value_rebuild: {
    title: "Value Rebuild / Cheap Reversal",
    desc: "Potentially cheap, washed-out names rebuilding above EMA100/EMA200 with improving structure and confluence.",
    bias: "rebuild / reversal bias",
  },
  overextended: {
    title: "Overextended",
    desc: "Stocks already stretched after strong moves; useful for caution, monitoring, and pullback planning.",
    bias: "caution / monitor bias",
  },
};

const sortOptions: Array<{ key: keyof ScannerResult; label: string }> = [
  { key: "scanner_score", label: "Score" },
  { key: "current_score", label: "Current" },
  { key: "score_delta_short", label: "D(5)" },
  { key: "score_delta_medium", label: "D(20)" },
  { key: "price_vs_ema200_pct", label: "Price vs EMA200" },
  { key: "support_distance_pct", label: "Support%" },
  { key: "resistance_room_pct", label: "Room%" },
  { key: "volume_ratio_20", label: "VolRatio20" },
  { key: "resistance_test_count", label: "Res Tests" },
  { key: "ema200_test_count", label: "EMA200 Tests" },
];

const ruleFieldOptions: Array<{ value: ScannerRuleField; label: string; numeric: boolean }> = [
  { value: "price_vs_ema200_pct", label: "Price vs EMA200 %", numeric: true },
  { value: "distance_to_ema20_pct", label: "Distance to EMA20 % (signed)", numeric: true },
  { value: "distance_to_ema50_pct", label: "Distance to EMA50 % (signed)", numeric: true },
  { value: "distance_to_ema100_pct", label: "Distance to EMA100 % (signed)", numeric: true },
  { value: "distance_to_ema200_pct", label: "Distance to EMA200 % (signed)", numeric: true },
  { value: "abs_distance_to_ema20_pct", label: "Abs Distance to EMA20 %", numeric: true },
  { value: "abs_distance_to_ema50_pct", label: "Abs Distance to EMA50 %", numeric: true },
  { value: "abs_distance_to_ema100_pct", label: "Abs Distance to EMA100 %", numeric: true },
  { value: "abs_distance_to_ema200_pct", label: "Abs Distance to EMA200 %", numeric: true },
  { value: "rsi_14", label: "RSI 14", numeric: true },
  { value: "volume_ratio_20", label: "Volume Ratio 20", numeric: true },
  { value: "support_distance_pct", label: "Support Distance %", numeric: true },
  { value: "resistance_room_pct", label: "Resistance Room %", numeric: true },
  { value: "ema200_slope_state", label: "EMA200 Slope State", numeric: false },
  { value: "trend_state", label: "Trend State", numeric: false },
];

const operatorOptions: Array<{ value: ScannerRuleOperator; label: string }> = [
  { value: "gt", label: ">" },
  { value: "gte", label: ">=" },
  { value: "lt", label: "<" },
  { value: "lte", label: "<=" },
  { value: "eq", label: "=" },
  { value: "in", label: "in (csv)" },
];

const ruleDefaultByField: Record<ScannerRuleField, ScannerCustomRule> = {
  price_vs_ema200_pct: { field: "price_vs_ema200_pct", operator: "gt", value_number: 0 },
  distance_to_ema20_pct: { field: "distance_to_ema20_pct", operator: "lt", value_number: 5 },
  distance_to_ema50_pct: { field: "distance_to_ema50_pct", operator: "lt", value_number: 8 },
  distance_to_ema100_pct: { field: "distance_to_ema100_pct", operator: "lt", value_number: 10 },
  distance_to_ema200_pct: { field: "distance_to_ema200_pct", operator: "lt", value_number: 12 },
  abs_distance_to_ema20_pct: { field: "abs_distance_to_ema20_pct", operator: "lt", value_number: 3 },
  abs_distance_to_ema50_pct: { field: "abs_distance_to_ema50_pct", operator: "lt", value_number: 5 },
  abs_distance_to_ema100_pct: { field: "abs_distance_to_ema100_pct", operator: "lt", value_number: 7 },
  abs_distance_to_ema200_pct: { field: "abs_distance_to_ema200_pct", operator: "lt", value_number: 9 },
  rsi_14: { field: "rsi_14", operator: "lt", value_number: 35 },
  volume_ratio_20: { field: "volume_ratio_20", operator: "gt", value_number: 1.5 },
  support_distance_pct: { field: "support_distance_pct", operator: "lt", value_number: 6 },
  resistance_room_pct: { field: "resistance_room_pct", operator: "gt", value_number: 2 },
  ema200_slope_state: { field: "ema200_slope_state", operator: "eq", value_text: "rising" },
  trend_state: { field: "trend_state", operator: "eq", value_text: "bullish_trend" },
};

export default function ScannerPage() {
  const router = useRouter();
  const [market, setMarket] = useState<MarketCode>("us");
  const [category, setCategory] = useState<ScannerCategory>("trend_mode");
  const [duration, setDuration] = useState<ScannerDuration>("2y");
  const [keepManualDuration, setKeepManualDuration] = useState(false);
  const [maxResults, setMaxResults] = useState(20);
  const [universeScope, setUniverseScope] = useState<ScannerUniverseScope>("capped_universe");
  const [selectedWatchlistId, setSelectedWatchlistId] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [result, setResult] = useState<ScannerResponse | null>(null);
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);

  const [sortKey, setSortKey] = useState<keyof ScannerResult>("scanner_score");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const [useCustomRules, setUseCustomRules] = useState(false);
  const [customRules, setCustomRules] = useState<ScannerCustomRule[]>([]);
  const [rangeStart, setRangeStart] = useState("");
  const [rangeEnd, setRangeEnd] = useState("");
  const [selectedSectors, setSelectedSectors] = useState<string[]>([]);
  const [selectedIndustries, setSelectedIndustries] = useState<string[]>([]);
  const [alertPlanRow, setAlertPlanRow] = useState<ScannerResult | null>(null);
  const [alertPlanRules, setAlertPlanRules] = useState<AlertProfileSuggestionRule[]>([]);
  const [alertPlanLoading, setAlertPlanLoading] = useState(false);
  const [alertPlanNotificationEnabled, setAlertPlanNotificationEnabled] = useState(false);
  const [alertPlanNotifyEmail, setAlertPlanNotifyEmail] = useState("");
  const [userLabel, setUserLabel] = useState("local-user");
  const [presetName, setPresetName] = useState("");
  const [savedPresets, setSavedPresets] = useState<Array<{ name: string; rules: ScannerCustomRule[] }>>([]);
  const [selectedPreview, setSelectedPreview] = useState<ScannerResult | null>(null);
  const [previewAnalysis, setPreviewAnalysis] = useState<CombinedAnalysisResponse | null>(null);
  const [llmqRow, setLlmqRow] = useState<ScannerResult | null>(null);
  const [llmqLoading, setLlmqLoading] = useState(false);
  const [llmqResult, setLlmqResult] = useState<ScannerLLMQChatResponse | null>(null);
  const [llmqStatus, setLlmqStatus] = useState<"idle" | "loading" | "success" | "fallback" | "error">("idle");
  const [llmqCopied, setLlmqCopied] = useState(false);
  const [llmqMessages, setLlmqMessages] = useState<LLMQChatMessage[]>([]);
  const [llmqBySymbol, setLlmqBySymbol] = useState<Record<string, LLMQChatMessage[]>>({});
  const [llmqInput, setLlmqInput] = useState("");
  const [llmqCollapsed, setLlmqCollapsed] = useState(true);
  const [llmqAutoQueryLabel, setLlmqAutoQueryLabel] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem(SCANNER_STATE_STORAGE_KEY);
      if (!raw) return;
      const saved = JSON.parse(raw) as {
        market?: MarketCode;
        category?: ScannerCategory;
        duration?: ScannerDuration;
        maxResults?: number;
        universeScope?: ScannerUniverseScope;
        selectedWatchlistId?: string;
        sortKey?: keyof ScannerResult;
        sortDirection?: "asc" | "desc";
        useCustomRules?: boolean;
        customRules?: ScannerCustomRule[];
        rangeStart?: string;
        rangeEnd?: string;
        result?: ScannerResponse | null;
      };
      if (saved.market) setMarket(saved.market);
      if (saved.category) setCategory(saved.category);
      if (saved.duration) setDuration(saved.duration);
      if (saved.maxResults) setMaxResults(saved.maxResults);
      if (saved.universeScope) setUniverseScope(saved.universeScope);
      if (saved.selectedWatchlistId !== undefined) setSelectedWatchlistId(saved.selectedWatchlistId);
      if (saved.sortKey) setSortKey(saved.sortKey);
      if (saved.sortDirection) setSortDirection(saved.sortDirection);
      if (saved.useCustomRules !== undefined) setUseCustomRules(saved.useCustomRules);
      if (saved.customRules) setCustomRules(saved.customRules);
      if (saved.rangeStart !== undefined) setRangeStart(saved.rangeStart);
      if (saved.rangeEnd !== undefined) setRangeEnd(saved.rangeEnd);
      if (saved.result) setResult(saved.result);
    } catch {
      // ignore broken local state and continue with defaults
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(
        SCANNER_STATE_STORAGE_KEY,
        JSON.stringify({
          market,
          category,
          duration,
          maxResults,
          universeScope,
          selectedWatchlistId,
          sortKey,
          sortDirection,
          useCustomRules,
          customRules,
          rangeStart,
          rangeEnd,
          result,
        })
      );
    } catch {
      // ignore storage write errors
    }
  }, [
    market,
    category,
    duration,
    maxResults,
    universeScope,
    selectedWatchlistId,
    sortKey,
    sortDirection,
    useCustomRules,
    customRules,
    rangeStart,
    rangeEnd,
    result,
  ]);

  const recommended = recommendedDurationByCategory[category];

  useEffect(() => {
    const loadWatchlists = async () => {
      try {
        const rows = await api.listWatchlists();
        setWatchlists(rows);
        if (rows.length > 0) {
          setSelectedWatchlistId((prev) => prev || rows[0].id);
        }
      } catch {
        setWatchlists([]);
      }
    };
    loadWatchlists();
  }, []);

  useEffect(() => {
    if (!notice) return;
    const id = setTimeout(() => setNotice(null), 2500);
    return () => clearTimeout(id);
  }, [notice]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem("tradeghost_scanner_rule_presets_v1");
      if (!raw) return;
      setSavedPresets(JSON.parse(raw));
    } catch {
      setSavedPresets([]);
    }
  }, []);

  const persistPresets = (next: Array<{ name: string; rules: ScannerCustomRule[] }>) => {
    setSavedPresets(next);
    if (typeof window !== "undefined") {
      window.localStorage.setItem("tradeghost_scanner_rule_presets_v1", JSON.stringify(next));
    }
  };

  const onCategoryChange = (next: ScannerCategory) => {
    setCategory(next);
    if (!keepManualDuration) {
      setDuration(recommendedDurationByCategory[next]);
    }
  };

  const runScan = async () => {
    setLoading(true);
    setError(null);
    try {
      const payload: ScannerRequest = {
        market,
        duration,
        category,
        max_results: maxResults,
        universe_scope: universeScope,
        use_custom_rules: useCustomRules && customRules.length > 0,
        ...(useCustomRules && customRules.length > 0 ? { custom_rules: customRules } : {}),
        ...(rangeStart && rangeEnd ? { range_start: rangeStart, range_end: rangeEnd } : {}),
        ...(selectedWatchlistId && universeScope === "watchlist"
          ? {
              symbol_overrides: (watchlists.find((wl) => wl.id === selectedWatchlistId)?.items ?? [])
                .filter((it) => it.market === market)
                .map((it) => it.symbol),
            }
          : {}),
      };
      const response = await api.scanner(payload);
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scanner request failed.");
    } finally {
      setLoading(false);
    }
  };

  const sortedResults = useMemo(() => {
    if (!result) return [];
    const next = [...result.results];
    next.sort((a, b) => {
      const av = a[sortKey] as number | string | null;
      const bv = b[sortKey] as number | string | null;
      if (av === null && bv === null) return 0;
      if (av === null) return 1;
      if (bv === null) return -1;
      if (typeof av === "number" && typeof bv === "number") {
        return sortDirection === "asc" ? av - bv : bv - av;
      }
      const cmp = String(av).localeCompare(String(bv));
      return sortDirection === "asc" ? cmp : -cmp;
    });
    return next;
  }, [result, sortKey, sortDirection]);

  const sectorOptions = useMemo(() => {
    const s = new Set<string>();
    for (const row of result?.results ?? []) s.add(row.sector ?? "unknown");
    return [...s].sort((a, b) => a.localeCompare(b));
  }, [result]);

  const industryOptions = useMemo(() => {
    const s = new Set<string>();
    for (const row of result?.results ?? []) s.add(row.industry ?? "unknown");
    return [...s].sort((a, b) => a.localeCompare(b));
  }, [result]);

  const filteredResults = useMemo(() => {
    return sortedResults.filter((row) => {
      const sectorPass = selectedSectors.length === 0 || selectedSectors.includes(row.sector ?? "unknown");
      const industryPass = selectedIndustries.length === 0 || selectedIndustries.includes(row.industry ?? "unknown");
      return sectorPass && industryPass;
    });
  }, [sortedResults, selectedSectors, selectedIndustries]);
  const llmqQuickChips = useMemo(() => {
    const sector = (llmqRow?.sector ?? "").toLowerCase();
    if (sector.includes("financial")) {
      return [...BASE_LLMQ_CHIPS, "How sensitive is this to rates and yield curve?", "What does credit quality risk mean here?"];
    }
    if (sector.includes("health")) {
      return [...BASE_LLMQ_CHIPS, "How does pipeline dependency affect this setup?", "How exposed is this to patent cliff or regulatory risk?"];
    }
    return BASE_LLMQ_CHIPS;
  }, [llmqRow]);

  const toggleSort = (key: keyof ScannerResult) => {
    if (sortKey === key) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setSortDirection("desc");
  };

  const addRule = () => {
    setUseCustomRules(true);
    setCustomRules((prev) => [...prev, { ...ruleDefaultByField.price_vs_ema200_pct }]);
  };

  const updateRule = (index: number, patch: Partial<ScannerCustomRule>) => {
    setCustomRules((prev) => prev.map((rule, i) => (i === index ? { ...rule, ...patch } : rule)));
  };

  const setRuleFieldWithDefault = (index: number, field: ScannerRuleField) => {
    const template = ruleDefaultByField[field];
    updateRule(index, {
      field,
      operator: template.operator,
      value_number: template.value_number ?? null,
      value_text: template.value_text ?? null,
      value_list: template.value_list ?? [],
    });
  };

  const addPresetRule = (field: ScannerRuleField) => {
    setUseCustomRules(true);
    setCustomRules((prev) => [...prev, { ...ruleDefaultByField[field] }]);
  };

  const addBuildUpPreset = () => {
    setUseCustomRules(true);
    setCustomRules((prev) => [
      ...prev,
      { ...ruleDefaultByField.price_vs_ema200_pct },
      { ...ruleDefaultByField.distance_to_ema20_pct },
      { ...ruleDefaultByField.volume_ratio_20 },
    ]);
  };

  const removeRule = (index: number) => {
    setCustomRules((prev) => prev.filter((_, i) => i !== index));
  };

  const addToWatchlist = async (symbol: string) => {
    if (!selectedWatchlistId) {
      setNotice("Select a target watchlist first.");
      return;
    }
    try {
      await api.addWatchlistItem(selectedWatchlistId, symbol, market);
      setNotice(`${symbol} added to watchlist.`);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Failed to add symbol to watchlist.");
    }
  };

  const openAlertPlan = async (row: ScannerResult) => {
    try {
      setAlertPlanLoading(true);
      const response = await api.suggestAlertProfile({
        symbol: row.symbol,
        market,
        scanner_category: result?.scope.category ?? category,
        watchlist_id: selectedWatchlistId || null,
        shortlisted_by: userLabel || "local-user",
        created_by: userLabel || "local-user",
        notification_enabled: alertPlanNotificationEnabled,
        notify_email: alertPlanNotifyEmail || null,
      });
      setAlertPlanRow(row);
      setAlertPlanRules(response.rules);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Failed to load alert profile suggestions.");
    } finally {
      setAlertPlanLoading(false);
    }
  };

  const openPreview = async (row: ScannerResult) => {
    setSelectedPreview(row);
    try {
      const analysis = await api.analyzeCombined(row.symbol, market, duration, {});
      setPreviewAnalysis(analysis);
    } catch {
      setPreviewAnalysis(null);
    }
  };

  const sendMessage = async (
    row: ScannerResult,
    messageText: string,
    options?: { hiddenUserPrompt?: boolean; clearConversation?: boolean }
  ) => {
    const text = messageText.trim();
    if (!text) return;
    const hiddenUserPrompt = options?.hiddenUserPrompt ?? false;
    const clearConversation = options?.clearConversation ?? false;
    const baseVisible = clearConversation ? [] : llmqMessages;
    const userMessage = { role: "user", content: text } as LLMQChatMessage;
    const nextVisible = hiddenUserPrompt ? baseVisible : [...baseVisible, userMessage];
    const backendMessages = [...nextVisible, userMessage];
    console.log("[LLMQ] sendMessage called", { symbol: row.symbol, message: text, hiddenUserPrompt, clearConversation });
    setLlmqLoading(true);
    setLlmqStatus("loading");
    setLlmqAutoQueryLabel(hiddenUserPrompt ? "Auto context query" : null);
    setLlmqMessages(nextVisible);
    setLlmqBySymbol((prev) => ({ ...prev, [row.symbol]: nextVisible }));
    if (!hiddenUserPrompt) setLlmqInput("");
    try {
      const payload = {
        symbol: row.symbol,
        scanner_snapshot: row as unknown as Record<string, unknown>,
        messages: backendMessages,
      };
      console.log("[LLMQ] payload", payload);
      const response = (await api.llmqChat(payload)) as ScannerLLMQChatResponse & Record<string, unknown>;
      const responseMap = response as Record<string, unknown>;
      console.log("[LLMQ] response", response);
      const answer =
        (typeof response.answer === "string" && response.answer.trim()) ||
        (typeof responseMap["content"] === "string" && (responseMap["content"] as string).trim()) ||
        (typeof responseMap["text"] === "string" && (responseMap["text"] as string).trim()) ||
        (typeof responseMap["message"] === "string" && (responseMap["message"] as string).trim()) ||
        "LLMQ returned empty content. Showing deterministic fallback summary is recommended.";
      const normalized: ScannerLLMQChatResponse = {
        provider: String(response.provider ?? "unknown"),
        model: String(response.model ?? "unknown"),
        status: String(response.status ?? "success"),
        fallback_used: Boolean(response.fallback_used),
        answer,
        error_message: (response.error_message as string | null) ?? null,
        warning_message: (response.warning_message as string | null) ?? null,
      };
      setLlmqResult(normalized);
      const withAssistant = [...nextVisible, { role: "assistant", content: answer } as LLMQChatMessage];
      setLlmqMessages(withAssistant);
      setLlmqBySymbol((prev) => ({ ...prev, [row.symbol]: withAssistant }));
      setLlmqStatus(normalized.fallback_used || normalized.status === "fallback_only" ? "fallback" : "success");
    } catch (error) {
      console.error("[LLMQ] error", error);
      const detail = error instanceof Error ? error.message : "Failed to load LLMQ context.";
      const errorReply = `LLMQ request failed. ${detail}`;
      const withError = [...nextVisible, { role: "assistant", content: errorReply } as LLMQChatMessage];
      setLlmqMessages(withError);
      setLlmqBySymbol((prev) => ({ ...prev, [row.symbol]: withError }));
      setLlmqStatus("error");
      setLlmqResult({
        provider: "none",
        model: "none",
        status: "error",
        fallback_used: false,
        answer: errorReply,
        error_message: detail,
        warning_message: "LLMQ request failed. Showing error response in chat.",
      });
      setNotice(detail);
    } finally {
      setLlmqLoading(false);
      setLlmqAutoQueryLabel(null);
    }
  };

  const openLLMQ = async (row: ScannerResult) => {
    setLlmqRow(row);
    setLlmqResult(null);
    setLlmqStatus("idle");
    setLlmqCopied(false);
    setLlmqCollapsed(false);
    const existing = llmqBySymbol[row.symbol];
    if (existing && existing.length > 0) {
      setLlmqMessages(existing);
      setLlmqAutoQueryLabel(null);
      return;
    }
    setLlmqMessages([]);
    await sendMessage(row, LLMQ_INITIAL_QUERY, { hiddenUserPrompt: true, clearConversation: true });
  };

  const regenerateLLMQ = async () => {
    if (!llmqRow) return;
    setLlmqMessages([]);
    setLlmqBySymbol((prev) => ({ ...prev, [llmqRow.symbol]: [] }));
    setLlmqResult(null);
    setLlmqStatus("idle");
    await sendMessage(llmqRow, LLMQ_INITIAL_QUERY, { hiddenUserPrompt: true, clearConversation: true });
  };

  const copyLLMQ = async () => {
    const text = llmqMessages.map((m) => `${m.role.toUpperCase()}: ${m.content}`).join("\n\n");
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      setLlmqCopied(true);
      setTimeout(() => setLlmqCopied(false), 1500);
      return;
    } catch {
      // fallback below
    }
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      setLlmqCopied(true);
      setTimeout(() => setLlmqCopied(false), 1500);
    } catch {
      setNotice("Copy failed. Select text and copy manually.");
    }
  };

  const sendLLMQ = async () => {
    if (!llmqRow) return;
    const text = llmqInput.trim();
    if (!text) return;
    await sendMessage(llmqRow, text);
  };
  const sendChipLLMQ = async (chipText: string) => {
    if (!llmqRow || llmqLoading) return;
    await sendMessage(llmqRow, chipText);
  };

  const ruleMeaning = (rule: ScannerCustomRule): string => {
    if (rule.field === "rsi_14") return `RSI ${rule.operator} ${rule.value_number ?? "?"}: lower values are stricter for oversold screens.`;
    if (rule.field.startsWith("distance_to_ema")) return `${rule.field} uses signed distance: + above EMA, - below EMA.`;
    if (rule.field.startsWith("abs_distance_to_ema")) return `${rule.field} uses absolute distance (ignores above/below sign).`;
    if (rule.field === "volume_ratio_20") return "Higher value requires stronger volume expansion.";
    if (rule.field === "support_distance_pct") return "Lower value keeps symbols closer to support.";
    if (rule.field === "resistance_room_pct") return "Higher value requires more upside room to resistance.";
    return "Deterministic AND filter.";
  };

  const updateAlertPlanRule = (index: number, patch: Partial<AlertProfileSuggestionRule>) => {
    setAlertPlanRules((prev) => prev.map((rule, i) => (i === index ? { ...rule, ...patch } : rule)));
  };

  const applyAlertPlan = async () => {
    if (!alertPlanRow) return;
    try {
      const created = await api.applyAlertProfile({
        scope_type: "symbol",
        scope_ref: alertPlanRow.symbol,
        symbol: alertPlanRow.symbol,
        market,
        scanner_category: result?.scope.category ?? category,
        watchlist_id: selectedWatchlistId || null,
        shortlisted_by: userLabel || "local-user",
        created_by: userLabel || "local-user",
        notification_enabled: alertPlanNotificationEnabled,
        notify_email: alertPlanNotifyEmail || null,
        rules: alertPlanRules,
      });
      setNotice(`Created ${created.length} alert rules for ${alertPlanRow.symbol}.`);
      setAlertPlanRow(null);
      setAlertPlanRules([]);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Failed to apply alert profile.");
    }
  };

  return (
    <main className="space-y-4">
      <Panel>
        <SectionTitle title="Stock Scanner" subtitle="Bounded deterministic discovery layer" />
        <p className="text-sm text-slate-300">Scanner = discovery shortlist. Use Monitor tab for persistent watchlists and alert tracking.</p>
      </Panel>

      {notice ? (
        <Panel className="border-cyan/30 bg-cyan/10">
          <p className="text-sm text-cyan">{notice}</p>
        </Panel>
      ) : null}

      {alertPlanRow ? (
        <Panel>
          <SectionTitle title={`Alert Plan: ${alertPlanRow.symbol}`} subtitle="Category-aware suggested rules. Select, edit, and apply." />
          <div className="grid gap-2 md:grid-cols-3">
            <label className="space-y-1 text-xs text-slate-300">
              <span>User Label</span>
              <input value={userLabel} onChange={(event) => setUserLabel(event.target.value)} className="h-9 w-full rounded-lg border border-stroke bg-bg px-2" />
            </label>
            <label className="space-y-1 text-xs text-slate-300">
              <span>Notify Email (optional)</span>
              <input value={alertPlanNotifyEmail} onChange={(event) => setAlertPlanNotifyEmail(event.target.value)} placeholder="name@example.com" className="h-9 w-full rounded-lg border border-stroke bg-bg px-2" />
            </label>
            <label className="mt-6 inline-flex items-center gap-2 text-xs text-slate-300">
              <input type="checkbox" checked={alertPlanNotificationEnabled} onChange={(event) => setAlertPlanNotificationEnabled(event.target.checked)} />
              Enable notification-ready status
            </label>
          </div>
          <div className="mt-3 space-y-2">
            {alertPlanRules.map((rule, index) => (
              <div key={rule.temp_id} className="grid gap-2 rounded-lg border border-stroke/70 bg-panelSoft p-2 md:grid-cols-[auto_1fr_220px_120px_120px]">
                <label className="inline-flex items-center gap-2 text-xs">
                  <input type="checkbox" checked={rule.selected} onChange={(event) => updateAlertPlanRule(index, { selected: event.target.checked })} />
                  use
                </label>
                <div>
                  <p className="text-sm text-slate-100">{rule.name}</p>
                  <p className="text-xs text-slate-400">{rule.rationale}</p>
                </div>
                <input value={rule.parameters ? JSON.stringify(rule.parameters) : "{}"} onChange={(event) => {
                  try {
                    const parsed = JSON.parse(event.target.value);
                    updateAlertPlanRule(index, { parameters: parsed });
                  } catch {
                    // keep existing value until valid json
                  }
                }} className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs" />
                <select value={rule.severity} onChange={(event) => updateAlertPlanRule(index, { severity: event.target.value as AlertProfileSuggestionRule["severity"] })} className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs">
                  <option value="info">info</option>
                  <option value="watch">watch</option>
                  <option value="important">important</option>
                  <option value="critical">critical</option>
                </select>
                <input type="number" min={0} max={1440} value={rule.cooldown_minutes} onChange={(event) => updateAlertPlanRule(index, { cooldown_minutes: Number(event.target.value) })} className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs" />
              </div>
            ))}
          </div>
          <div className="mt-3 flex gap-2">
            <button type="button" onClick={() => setAlertPlanRules((prev) => prev.map((row) => ({ ...row, selected: true })))} className="rounded-lg border border-stroke px-3 py-2 text-xs hover:text-cyan">Select All</button>
            <button type="button" onClick={applyAlertPlan} className="rounded-lg border border-stroke px-3 py-2 text-xs hover:text-cyan">Apply Selected</button>
            <button type="button" onClick={() => { setAlertPlanRow(null); setAlertPlanRules([]); }} className="rounded-lg border border-stroke px-3 py-2 text-xs">Close</button>
          </div>
        </Panel>
      ) : null}

      <Panel>
        <SectionTitle title="Scanner Inputs" subtitle="Single-pass bounded scan across selected scope" />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
          <label className="space-y-1 text-sm">
            <span className="text-xs text-slate-400">Stock Type</span>
            <select value={market} onChange={(event) => setMarket(event.target.value as MarketCode)} className="h-10 w-full rounded-lg border border-stroke bg-bg px-3">
              <option value="us">US</option>
              <option value="bist">BIST</option>
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-xs text-slate-400">Scan Category</span>
            <select value={category} onChange={(event) => onCategoryChange(event.target.value as ScannerCategory)} className="h-10 w-full rounded-lg border border-stroke bg-bg px-3">
              <option value="trend_mode">Trend Mode</option>
              <option value="build_up">Build-up</option>
              <option value="momentum_mode">Momentum Mode</option>
              <option value="value_rebuild">Value Rebuild</option>
              <option value="overextended">Overextended</option>
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-xs text-slate-400">Duration</span>
            <select value={duration} onChange={(event) => { setDuration(event.target.value as ScannerDuration); setKeepManualDuration(true); }} className="h-10 w-full rounded-lg border border-stroke bg-bg px-3">
              <option value="1y">1Y</option>
              <option value="2y">2Y</option>
              <option value="3y">3Y</option>
              <option value="5y">5Y</option>
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-xs text-slate-400">Max Results</span>
            <select value={maxResults} onChange={(event) => setMaxResults(Number(event.target.value))} className="h-10 w-full rounded-lg border border-stroke bg-bg px-3">
              <option value={20}>20</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-xs text-slate-400">Universe Scope</span>
            <select value={universeScope} onChange={(event) => setUniverseScope(event.target.value as ScannerUniverseScope)} className="h-10 w-full rounded-lg border border-stroke bg-bg px-3">
              <option value="full_universe">Full Universe</option>
              <option value="watchlist">Watchlist / Favorites</option>
              <option value="capped_universe">Capped Universe</option>
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-xs text-slate-400">Target Watchlist</span>
            <select value={selectedWatchlistId} onChange={(event) => setSelectedWatchlistId(event.target.value)} className="h-10 w-full rounded-lg border border-stroke bg-bg px-3">
              <option value="">Select watchlist</option>
              {watchlists.map((wl) => (
                <option key={wl.id} value={wl.id}>{wl.name}</option>
              ))}
            </select>
          </label>
        </div>

        <div className="mt-3 rounded-xl border border-stroke/70 bg-panelSoft p-3 text-xs text-slate-300">
          Selected duration: {duration.toUpperCase()} | Recommended duration for {categoryDefinition[category].title}: {recommended.toUpperCase()}. Reason: {rationaleByCategory[category]}
        </div>
        <label className="mt-3 inline-flex items-center gap-2 text-xs text-slate-300">
          <input type="checkbox" checked={keepManualDuration} onChange={(event) => setKeepManualDuration(event.target.checked)} />
          Keep manual duration when category changes
        </label>

        <div className="mt-4 rounded-xl border border-stroke/70 bg-panelSoft p-3">
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-semibold text-slate-200">Optional Custom Filters (AND conditions)</p>
            <label className="inline-flex items-center gap-2 text-xs text-slate-300">
              <input type="checkbox" checked={useCustomRules} onChange={(event) => setUseCustomRules(event.target.checked)} />
              Enable custom filters
            </label>
          </div>
          <p className="mt-2 text-xs text-slate-400">
            Custom filters refine selected category results. They do not replace category logic. Slider controls appear for numeric rules.
          </p>
          {useCustomRules ? (
            <div className="mt-3 space-y-2">
              <p className="text-xs text-slate-400">
                Numeric rules include slider tuning. Signed EMA distance means: positive above EMA, negative below EMA.
              </p>
              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={() => addPresetRule("price_vs_ema200_pct")} className="rounded-lg border border-stroke px-2 py-1 text-xs hover:text-cyan">Above EMA200</button>
                <button type="button" onClick={() => addPresetRule("distance_to_ema20_pct")} className="rounded-lg border border-stroke px-2 py-1 text-xs hover:text-cyan">Near EMA20</button>
                <button type="button" onClick={() => addPresetRule("volume_ratio_20")} className="rounded-lg border border-stroke px-2 py-1 text-xs hover:text-cyan">Volume Expansion</button>
                <button type="button" onClick={() => addPresetRule("rsi_14")} className="rounded-lg border border-stroke px-2 py-1 text-xs hover:text-cyan">Oversold RSI</button>
                <button type="button" onClick={addBuildUpPreset} className="rounded-lg border border-stroke px-2 py-1 text-xs hover:text-cyan">Build-up Basic</button>
              </div>
              {customRules.length === 0 ? (
                <p className="text-xs text-slate-400">No custom rule yet. Click a quick preset or "Add Rule" to show slider controls.</p>
              ) : null}
              {customRules.map((rule, index) => {
                const fieldMeta = ruleFieldOptions.find((f) => f.value === rule.field) ?? ruleFieldOptions[0];
                return (
                  <div key={`${rule.field}-${index}`} className="grid gap-2 rounded-lg border border-stroke/60 p-2 md:grid-cols-4">
                    <select value={rule.field} onChange={(event) => setRuleFieldWithDefault(index, event.target.value as ScannerRuleField)} className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs">
                      {ruleFieldOptions.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                    </select>
                    <select value={rule.operator} onChange={(event) => updateRule(index, { operator: event.target.value as ScannerRuleOperator })} className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs">
                      {operatorOptions.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                    </select>
                    {fieldMeta.numeric && rule.operator !== "in" ? (
                      <div className="space-y-1">
                        <input type="number" value={rule.value_number ?? 0} onChange={(event) => updateRule(index, { value_number: Number(event.target.value), value_text: null, value_list: [] })} className="h-9 w-full rounded-lg border border-stroke bg-bg px-2 text-xs" />
                        <input
                          type="range"
                          min={rule.field === "rsi_14" ? 0 : rule.field.startsWith("abs_distance_to_ema") ? 0 : -25}
                          max={rule.field === "rsi_14" ? 100 : 25}
                          step={0.5}
                          value={rule.value_number ?? 0}
                          onChange={(event) => updateRule(index, { value_number: Number(event.target.value), value_text: null, value_list: [] })}
                          className="w-full"
                        />
                      </div>
                    ) : (
                      <input
                        type="text"
                        value={rule.operator === "in" ? (rule.value_list ?? []).join(",") : (rule.value_text ?? "")}
                        onChange={(event) => {
                          const raw = event.target.value;
                          if (rule.operator === "in") {
                            updateRule(index, {
                              value_list: raw.split(",").map((v) => v.trim()).filter(Boolean),
                              value_text: null,
                              value_number: null,
                            });
                            return;
                          }
                          updateRule(index, { value_text: raw, value_number: null, value_list: [] });
                        }}
                        placeholder={rule.operator === "in" ? "rising,flat" : "value"}
                        className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs"
                      />
                    )}
                    <button type="button" onClick={() => removeRule(index)} className="h-9 rounded-lg border border-stroke px-2 text-xs text-red">Remove</button>
                    <p className="md:col-span-4 text-[11px] text-slate-400">{ruleMeaning(rule)}</p>
                  </div>
                );
              })}
              <button type="button" onClick={addRule} className="rounded-lg border border-stroke px-3 py-2 text-xs text-slate-200 hover:text-cyan">Add Rule</button>
              <div className="mt-2 grid gap-2 md:grid-cols-[1fr_auto_auto]">
                <input value={presetName} onChange={(e) => setPresetName(e.target.value)} placeholder="Preset name (e.g. RSI Pullback)" className="h-9 rounded-lg border border-stroke bg-bg px-2 text-xs" />
                <button type="button" onClick={() => { if (!presetName.trim()) return; persistPresets([...savedPresets, { name: presetName.trim(), rules: customRules }]); setPresetName(""); }} className="rounded-lg border border-stroke px-3 py-2 text-xs">Save Preset</button>
                <button type="button" onClick={() => { setCustomRules([]); }} className="rounded-lg border border-stroke px-3 py-2 text-xs">Clear Rules</button>
              </div>
              {savedPresets.length > 0 ? (
                <div className="grid gap-2 md:grid-cols-2">
                  {savedPresets.map((p) => (
                    <div key={p.name} className="flex items-center justify-between rounded-md border border-stroke/70 px-2 py-1 text-xs">
                      <span>{p.name}</span>
                      <div className="flex gap-1">
                        <button type="button" onClick={() => { setUseCustomRules(true); setCustomRules(p.rules); }} className="rounded border border-stroke px-2 py-1">Load</button>
                        <button type="button" onClick={() => persistPresets(savedPresets.filter((x) => x.name !== p.name))} className="rounded border border-red/40 px-2 py-1 text-red">Delete</button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
          {!useCustomRules ? (
            <div className="mt-3 rounded-lg border border-stroke/50 bg-bg/40 px-3 py-2 text-xs text-slate-400">
              Enable custom filters, then add a numeric rule (like RSI or EMA distance) to use sliders.
            </div>
          ) : null}
        </div>

        <button type="button" onClick={runScan} disabled={loading} className="mt-4 h-11 rounded-lg bg-cyan px-6 text-sm font-semibold text-bg transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50">
          {loading ? "Scanning..." : "Run Scanner"}
        </button>
        <button type="button" onClick={() => router.push("/monitor")} className="ml-2 mt-4 h-11 rounded-lg border border-stroke px-4 text-sm text-slate-300 hover:text-cyan">
          Open Monitor Workspace
        </button>
      </Panel>

      <Panel>
        <SectionTitle title="Category Definitions" subtitle="Scanner is candidate discovery, not direct execution" />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {(Object.keys(categoryDefinition) as ScannerCategory[]).map((key) => (
            <div key={key} className="rounded-xl border border-stroke/70 bg-panelSoft p-3">
              <p className="text-sm font-semibold text-slate-100">{categoryDefinition[key].title}</p>
              <p className="mt-1 text-xs text-slate-300">{categoryDefinition[key].desc}</p>
              <p className="mt-2 text-xs text-cyan">Bias: {categoryDefinition[key].bias}</p>
            </div>
          ))}
        </div>
      </Panel>

      {error ? (
        <Panel className="border-red/40 bg-red/10">
          <p className="text-sm text-red">{error}</p>
        </Panel>
      ) : null}

      {result ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
            <StatCard label="Stock Type" value={result.scope.market.toUpperCase()} />
            <StatCard label="Category" value={result.scope.category.replaceAll("_", " ")} />
            <StatCard label="Duration" value={result.scope.duration.toUpperCase()} />
            <StatCard label="Universe Size" value={`${result.scope.symbol_count}`} />
            <StatCard label="Processed" value={`${result.scope.processed_count}`} />
            <StatCard label="Runtime" value={`${result.scope.runtime_seconds.toFixed(2)}s`} />
          </div>

          <Panel className="bg-panelSoft">
            <p className="text-xs text-slate-300">Diagnostics: eligible {result.scope.category_eligible_count}, relaxed eligible {result.scope.relaxed_eligible_count}, custom-filtered {result.scope.custom_filtered_count}, ranked {result.scope.ranked_count}, returned {result.scope.final_returned_count}. Universe source: {result.scope.universe_source ?? "n/a"}.</p>
            {result.rule_impact.length > 0 ? (
              <div className="mt-2 space-y-1">
                {result.rule_impact.map((r) => (
                  <p key={r.rule_name} className="text-xs text-slate-300">{r.rule_name}: {r.before_count} {"->"} {r.after_count} (removed {r.removed_count})</p>
                ))}
              </div>
            ) : null}
          </Panel>

          {selectedPreview && previewAnalysis ? (
            <Panel>
              <SectionTitle title={`Scanner Chart Preview: ${selectedPreview.symbol}`} subtitle="Quick visual check without leaving Scanner" />
              <UnifiedAnalysisChart chart={previewAnalysis.chart} title={`${selectedPreview.symbol} Preview`} />
            </Panel>
          ) : null}

          <Panel>
            <SectionTitle title="Scanner Results" subtitle="Ranked shortlist for next analysis step" />
            <div className="mb-2 grid gap-2 md:grid-cols-2">
              <label className="text-xs text-slate-300">Sector filter
                <select
                  multiple
                  value={selectedSectors}
                  onChange={(e) => setSelectedSectors(Array.from(e.target.selectedOptions).map((o) => o.value))}
                  className="mt-1 h-24 w-full rounded border border-stroke bg-bg px-2 text-xs"
                >
                  {sectorOptions.map((x) => <option key={x} value={x}>{x}</option>)}
                </select>
                <p className="mt-1 text-[11px] text-slate-400">All sectors (default) when none selected.</p>
              </label>
              <label className="text-xs text-slate-300">Industry filter
                <select
                  multiple
                  value={selectedIndustries}
                  onChange={(e) => setSelectedIndustries(Array.from(e.target.selectedOptions).map((o) => o.value))}
                  className="mt-1 h-24 w-full rounded border border-stroke bg-bg px-2 text-xs"
                >
                  {industryOptions.map((x) => <option key={x} value={x}>{x}</option>)}
                </select>
                <p className="mt-1 text-[11px] text-slate-400">All industries (default) when none selected.</p>
              </label>
            </div>
            <div className="mb-2 flex flex-wrap gap-2 text-xs">
              <span className="rounded border border-stroke px-2 py-1">{selectedSectors.length ? `Sectors: ${selectedSectors.join(", ")}` : "All sectors"}</span>
              <span className="rounded border border-stroke px-2 py-1">{selectedIndustries.length ? `Industries: ${selectedIndustries.join(", ")}` : "All industries"}</span>
              <button type="button" onClick={() => setSelectedSectors([])} className="rounded border border-stroke px-2 py-1 hover:text-cyan">All sectors</button>
              <button type="button" onClick={() => setSelectedIndustries([])} className="rounded border border-stroke px-2 py-1 hover:text-cyan">All industries</button>
              <button type="button" onClick={() => { setSelectedSectors([]); setSelectedIndustries([]); }} className="rounded border border-stroke px-2 py-1 hover:text-cyan">Clear filters</button>
            </div>
            {result?.sector_summary?.length ? (
              <div className="mb-2 text-xs text-slate-300">
                <p>Top sector: {result.top_sector_by_candidate_count ?? "-"}</p>
                {result.sector_summary.map((s) => (
                  <p key={s.sector}>{s.sector}: {s.candidate_count} candidates | avg score {s.average_score.toFixed(1)} | categories {Object.entries(s.category_distribution).map(([k, v]) => `${k}:${v}`).join(", ")}</p>
                ))}
              </div>
            ) : null}
            <div className="max-h-[72vh] overflow-auto rounded-xl border border-stroke/70">
              <table className="min-w-[2650px] table-auto text-sm">
                <thead>
                  <tr className="border-b border-stroke text-left text-slate-400">
                    <th className="sticky left-0 top-0 z-30 w-[120px] bg-panel px-2 py-2 shadow-[8px_0_12px_-12px_rgba(0,0,0,0.6)]">Symbol</th>
                    <th className="sticky top-0 z-20 w-[180px] bg-panel px-2 py-2">Company</th>
                    <th className="sticky top-0 z-20 w-[140px] bg-panel px-2 py-2">Sector</th>
                    <th className="sticky top-0 z-20 w-[160px] bg-panel px-2 py-2">Industry</th>
                    {sortOptions.map((option) => (
                      <th key={option.key} className="sticky top-0 z-20 w-[88px] bg-panel px-2 py-2">
                        <button type="button" onClick={() => toggleSort(option.key)} className="inline-flex items-center gap-1 hover:text-slate-200">
                          {option.label}
                          {sortKey === option.key ? (sortDirection === "asc" ? "up" : "down") : ""}
                        </button>
                      </th>
                    ))}
                    <th className="sticky top-0 z-20 w-[112px] bg-panel px-2 py-2">Dynamics</th>
                    <th className="sticky top-0 z-20 w-[108px] bg-panel px-2 py-2">Momentum Fit</th>
                    <th className="sticky top-0 z-20 w-[120px] bg-panel px-2 py-2">Ext State</th>
                    <th className="sticky top-0 z-20 w-[120px] bg-panel px-2 py-2">Mom Candidate</th>
                    <th className="sticky top-0 z-20 w-[140px] bg-panel px-2 py-2">Opportunity</th>
                    <th className="sticky top-0 z-20 w-[110px] bg-panel px-2 py-2">Fib Confluence</th>
                    <th className="sticky top-0 z-20 w-[90px] bg-panel px-2 py-2">Fib Room%</th>
                    <th className="sticky top-0 z-20 w-[80px] bg-panel px-2 py-2">P/B</th>
                    <th className="sticky top-0 z-20 w-[80px] bg-panel px-2 py-2">P/E</th>
                    <th className="sticky top-0 z-20 w-[90px] bg-panel px-2 py-2">Priority</th>
                    <th className="sticky top-0 z-20 w-[130px] bg-panel px-2 py-2">Category</th>
                    <th className="sticky top-0 z-20 w-[420px] bg-panel px-2 py-2">Reason</th>
                    <th className="sticky top-0 z-20 w-[130px] bg-panel px-2 py-2">Trend State</th>
                    <th className="sticky top-0 z-20 w-[110px] bg-panel px-2 py-2">EMA200 Slope</th>
                    <th className="sticky top-0 z-20 w-[90px] bg-panel px-2 py-2">Rep Tests</th>
                    <th className="sticky top-0 z-20 bg-panel px-2 py-2 whitespace-nowrap">TV</th>
                    <th className="sticky top-0 z-20 bg-panel px-2 py-2 whitespace-nowrap">Open</th>
                    <th className="sticky top-0 z-20 bg-panel px-2 py-2 whitespace-nowrap">Track</th>
                    <th className="sticky top-0 z-20 bg-panel px-2 py-2 whitespace-nowrap">LLMQ</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredResults.length === 0 ? (
                    <tr>
                      <td className="sticky left-0 z-10 bg-panel px-2 py-3 text-slate-400 shadow-[8px_0_12px_-12px_rgba(0,0,0,0.6)]">No candidates found for selected scope.</td>
                      <td className="px-2 py-3 text-slate-400" colSpan={30}></td>
                    </tr>
                  ) : (
                    filteredResults.map((row) => (
                      <Fragment key={`${row.normalized_symbol}-wrap`}>
                      <tr className="border-b border-stroke/50 align-top">
                        <td className="sticky left-0 z-10 bg-panel px-2 py-2 shadow-[8px_0_12px_-12px_rgba(0,0,0,0.6)]">
                          <div className="font-medium text-slate-100">{row.symbol}</div>
                          <div className="text-[11px] text-slate-400">Score {row.scanner_score.toFixed(1)} | {row.priority}</div>
                          <button type="button" onClick={() => openPreview(row)} className="mt-1 rounded border border-stroke px-1 py-0.5 text-[10px] hover:text-cyan">Preview</button>
                        </td>
                        <td className="px-2 py-2">{row.company_name ?? "unknown"}</td>
                        <td className="px-2 py-2">{row.sector ?? "unknown"}</td>
                        <td className="px-2 py-2">{row.industry ?? "unknown"}</td>
                        <td className="px-2 py-2">{row.scanner_score.toFixed(2)}</td>
                        <td className="px-2 py-2">{row.current_score.toFixed(2)}</td>
                        <td className={`px-2 py-2 ${row.score_delta_short >= 0 ? "text-green" : "text-red"}`}>{row.score_delta_short.toFixed(2)}</td>
                        <td className={`px-2 py-2 ${row.score_delta_medium >= 0 ? "text-green" : "text-red"}`}>{row.score_delta_medium.toFixed(2)}</td>
                        <td className="px-2 py-2">{row.price_vs_ema200_pct.toFixed(2)}%</td>
                        <td className="px-2 py-2">{row.support_distance_pct.toFixed(2)}%</td>
                        <td className="px-2 py-2">{row.resistance_room_pct.toFixed(2)}%</td>
                        <td className="px-2 py-2">{row.volume_ratio_20.toFixed(2)}</td>
                        <td className="px-2 py-2">{row.resistance_test_count}</td>
                        <td className="px-2 py-2">{row.ema200_test_count}</td>
                        <td className="px-2 py-2">{row.score_dynamics_state}</td>
                        <td className="px-2 py-2">{row.momentum_fit_score.toFixed(2)}</td>
                        <td className="px-2 py-2">{row.extension_state.replaceAll("_", " ")}</td>
                        <td className="px-2 py-2">{row.momentum_continuation_candidate ? "yes" : "no"}</td>
                        <td className="px-2 py-2">{row.opportunity_type.replaceAll("_", " ")}</td>
                        <td className="px-2 py-2">{row.fib_ema_confluence_score?.toFixed(1) ?? "n/a"}</td>
                        <td className="px-2 py-2">{row.fib_target_room_pct?.toFixed(2) ?? "n/a"}</td>
                        <td className="px-2 py-2">{row.price_to_book?.toFixed(2) ?? "n/a"}</td>
                        <td className="px-2 py-2">{row.price_to_earnings?.toFixed(2) ?? "n/a"}</td>
                        <td className="px-2 py-2 capitalize">{row.priority}</td>
                        <td className="px-2 py-2">{row.category_tag.replaceAll("_", " ")}</td>
                        <td className="px-2 py-2 text-xs text-slate-300">
                          <div className="max-w-[420px] whitespace-normal break-words leading-5" title={row.short_reason}>{row.short_reason}</div>
                        </td>
                        <td className="px-2 py-2">{row.trend_state}</td>
                        <td className="px-2 py-2">{row.ema200_slope_state}</td>
                        <td className="px-2 py-2">{row.repeated_test_count}</td>
                        <td className="px-2 py-2 whitespace-nowrap">
                          <a href={row.tradingview_url} target="_blank" rel="noreferrer" className="rounded-md border border-stroke px-2 py-1 text-xs text-slate-300 hover:text-cyan">TradingView</a>
                        </td>
                        <td className="px-2 py-2 whitespace-nowrap">
                          <button
                            type="button"
                            onClick={() =>
                              router.push(
                                `/analysis?ticker=${encodeURIComponent(row.symbol)}&market=${encodeURIComponent(result.scope.market)}&window=${encodeURIComponent(result.scope.duration)}&scanner_category=${encodeURIComponent(result.scope.category)}&scanner_score=${encodeURIComponent(row.scanner_score.toFixed(2))}&scanner_current_score=${encodeURIComponent(row.current_score.toFixed(2))}&scanner_delta_short=${encodeURIComponent(row.score_delta_short.toFixed(2))}&scanner_delta_medium=${encodeURIComponent(row.score_delta_medium.toFixed(2))}&scanner_dynamics_state=${encodeURIComponent(row.score_dynamics_state)}&scanner_reason=${encodeURIComponent(row.short_reason)}&scanner_momentum_fit=${encodeURIComponent(row.momentum_fit_score.toFixed(2))}&scanner_extension_state=${encodeURIComponent(row.extension_state)}&scanner_momentum_candidate=${encodeURIComponent(String(row.momentum_continuation_candidate))}`
                              )
                            }
                            className="rounded-md border border-stroke px-2 py-1 text-xs text-slate-300 hover:text-cyan"
                          >
                            Open Analysis
                          </button>
                        </td>
                        <td className="px-2 py-2 whitespace-nowrap">
                          <div className="flex gap-1">
                            <button type="button" onClick={() => addToWatchlist(row.symbol)} className="rounded-md border border-stroke px-2 py-1 text-xs text-slate-300 hover:text-cyan">Add WL</button>
                            <button type="button" onClick={() => openAlertPlan(row)} disabled={alertPlanLoading} className="rounded-md border border-stroke px-2 py-1 text-xs text-slate-300 hover:text-cyan disabled:opacity-60">{alertPlanLoading ? "Loading..." : "Alert Plan"}</button>
                          </div>
                        </td>
                        <td className="px-2 py-2 whitespace-nowrap">
                          <button type="button" onClick={() => openLLMQ(row)} disabled={llmqLoading} className="rounded-md border border-stroke px-2 py-1 text-xs text-slate-300 hover:text-cyan disabled:opacity-60">LLMQ</button>
                        </td>
                      </tr>
                      </Fragment>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </Panel>
          <div className={`fixed inset-y-0 right-0 z-50 w-full max-w-[540px] border-l border-stroke bg-panel shadow-2xl transition-transform duration-300 ${llmqCollapsed ? "translate-x-[calc(100%-42px)]" : "translate-x-0"}`}>
              <div className="sticky top-0 z-10 flex items-center justify-between border-b border-stroke bg-panel px-4 py-3">
                <div>
                  <p className="text-sm font-semibold text-slate-100">LLMQ: {llmqRow?.symbol ?? "-"}</p>
                  <p className="text-xs text-slate-400">
                    {llmqRow ? `${llmqRow.company_name ?? llmqRow.symbol} · ${llmqRow.sector ?? "unknown"} · ${llmqRow.category_tag.replaceAll("_", " ")} · Score ${llmqRow.scanner_score.toFixed(1)}` : "Click LLMQ on any row for contextual interpretation."}
                  </p>
                  <p className="text-xs text-slate-400">
                    {llmqStatus === "loading"
                      ? "Provider status: loading..."
                      : llmqStatus === "fallback"
                        ? "Provider status: fallback"
                        : llmqStatus === "error"
                          ? "Provider status: error"
                          : llmqStatus === "success" && llmqResult
                            ? `Provider: ${llmqResult.provider.toUpperCase()} / ${llmqResult.model}`
                            : "Provider status: idle"}
                  </p>
                </div>
                <div className="flex gap-2">
                  <button type="button" onClick={copyLLMQ} disabled={llmqMessages.length === 0} className="rounded border border-stroke px-2 py-1 text-xs hover:text-cyan disabled:opacity-60">{llmqCopied ? "Copied" : "Copy Conversation"}</button>
                  <button type="button" onClick={regenerateLLMQ} disabled={llmqLoading || !llmqRow} className="rounded border border-stroke px-2 py-1 text-xs hover:text-cyan disabled:opacity-60">Regenerate</button>
                  <button type="button" onClick={() => setLlmqCollapsed((v) => !v)} className="rounded border border-stroke px-2 py-1 text-xs">{llmqCollapsed ? "Restore" : "Collapse"}</button>
                  <button type="button" onClick={() => { setLlmqCollapsed(true); setLlmqCopied(false); setLlmqInput(""); setLlmqAutoQueryLabel(null); setLlmqStatus("idle"); }} className="rounded border border-stroke px-2 py-1 text-xs">Close</button>
                </div>
              </div>
              <div className="h-[calc(100vh-64px)] overflow-auto p-4">
                {llmqLoading ? <p className="text-xs text-slate-300">Generating context...</p> : null}
                {llmqAutoQueryLabel ? <p className="mb-2 text-[11px] text-slate-400">{llmqAutoQueryLabel}</p> : null}
                {llmqResult?.warning_message ? (
                  <p className="mb-2 rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-xs text-amber-200">{llmqResult.warning_message}</p>
                ) : null}
                <div className="space-y-3 pb-6">
                  {llmqMessages.length === 0 && !llmqLoading ? (
                    <p className="rounded border border-stroke bg-bg px-3 py-2 text-xs text-slate-300">Sidebar is ready. Click LLMQ on a scanner row to auto-generate context.</p>
                  ) : null}
                  {llmqMessages.map((m, i) => (
                    <div key={`m-${i}`} className={`rounded border px-3 py-2 text-xs whitespace-pre-wrap ${m.role === "user" ? "border-cyan/40 bg-cyan/10 text-cyan-100" : "border-stroke bg-bg text-slate-200"}`}>
                      {m.content}
                    </div>
                  ))}
                </div>
                {llmqRow ? (
                  <div className="mb-2 flex flex-wrap gap-2">
                    {llmqQuickChips.map((chip) => (
                      <button key={chip} type="button" disabled={llmqLoading} onClick={() => sendChipLLMQ(chip)} className="rounded-full border border-stroke px-2 py-1 text-[11px] text-slate-300 hover:text-cyan disabled:opacity-60">
                        {chip}
                      </button>
                    ))}
                  </div>
                ) : null}
                <div className="sticky bottom-0 mt-2 border-t border-stroke bg-panel pt-2">
                  <div className="flex gap-2">
                    <textarea
                      value={llmqInput}
                      onChange={(e) => setLlmqInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          void sendLLMQ();
                        }
                      }}
                      placeholder="Ask a follow-up question..."
                      className="h-16 flex-1 rounded border border-stroke bg-bg p-2 text-xs text-slate-200"
                    />
                    <button type="button" onClick={sendLLMQ} disabled={llmqLoading || !llmqInput.trim() || !llmqRow} className="h-16 rounded border border-stroke px-3 text-xs hover:text-cyan disabled:opacity-60">Send</button>
                  </div>
                </div>
              </div>
            </div>
          <button
            type="button"
            onClick={() => setLlmqCollapsed(false)}
            className={`fixed right-0 top-1/2 z-[60] -translate-y-1/2 rounded-l border border-r-0 border-stroke bg-panel px-2 py-3 text-xs text-slate-200 transition-opacity duration-200 ${llmqCollapsed ? "opacity-100" : "pointer-events-none opacity-0"}`}
          >
            {llmqRow ? `LLMQ: ${llmqRow.symbol} >` : "LLMQ >"}
          </button>
        </>
      ) : null}
    </main>
  );
}
