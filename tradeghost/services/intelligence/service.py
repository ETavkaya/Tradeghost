from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from tradeghost.services.analysis_engine import AnalysisEngine
from tradeghost.services.backtest.engine import BacktestEngine
from tradeghost.services.intelligence.providers import GroqProvider, LLMProvider, OllamaProvider
from tradeghost.services.scanner.engine import ScannerEngine
from tradeghost.shared.config.settings import get_settings
from tradeghost.shared.models.schemas import (
    DailyBriefing,
    DailyBriefingRequest,
    DailyPipelineRequest,
    DailyRun,
    DailyRunDetail,
    IntelligenceDashboardResponse,
    IntelligenceRunResponse,
    LLMResponseTestRequest,
    LLMResponseTestResult,
    LLMConnectionStatus,
    LLMDebugLog,
    PipelineDebugEvent,
    ScannerRequest,
    SymbolBacktestSummary,
    SymbolContext,
    SymbolContextBatchRequest,
    SymbolContextBatchResponse,
    SymbolResult,
    SystemReview,
    SystemReviewRequest,
)


class IntelligenceService:
    def __init__(
        self,
        analysis_engine: AnalysisEngine | None = None,
        scanner_engine: ScannerEngine | None = None,
        backtest_engine: BacktestEngine | None = None,
    ) -> None:
        self.settings = get_settings()
        self.base_dir = self.settings.logs_dir / "intelligence"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.runs_path = self.base_dir / "daily_runs.json"
        self.results_path = self.base_dir / "symbol_results.json"
        self.contexts_path = self.base_dir / "symbol_contexts.json"
        self.briefings_path = self.base_dir / "daily_briefings.json"
        self.reviews_path = self.base_dir / "system_reviews.json"
        self.llm_logs_path = self.base_dir / "llm_calls.json"
        self.pipeline_logs_path = self.base_dir / "pipeline_events.json"
        self.analysis_engine = analysis_engine or AnalysisEngine()
        self.scanner_engine = scanner_engine or ScannerEngine(analysis_engine=self.analysis_engine)
        self.backtest_engine = backtest_engine or BacktestEngine(analysis_engine=self.analysis_engine)
        self._logger = logging.getLogger(__name__)
        self._llm_logs_lock = Lock()
        self._pipeline_logs_lock = Lock()
        self._providers: dict[str, LLMProvider] = {
            "groq": GroqProvider(self.settings),
            "ollama": OllamaProvider(self.settings),
        }

    def _normalize_provider(self, provider: str | None) -> str:
        value = (provider or "ollama").strip().lower()
        return value if value in {"ollama", "groq"} else "ollama"

    def _ollama_generate_direct(
        self,
        *,
        prompt: str,
        model: str,
        timeout_seconds: float,
        symbol: str | None = None,
        run_id: str | None = None,
        debug_stream: bool = False,
    ) -> tuple[str, str]:
        endpoint = self.settings.ollama_base_url.rstrip("/") + "/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": bool(debug_stream),
            "keep_alive": self.settings.ollama_keep_alive,
            "options": {
                "temperature": self.settings.ollama_temperature,
                "top_p": self.settings.ollama_top_p,
                "repeat_penalty": self.settings.ollama_repeat_penalty,
                "num_predict": self.settings.ollama_num_predict,
                "num_ctx": self.settings.ollama_num_ctx,
                "num_thread": self.settings.ollama_num_thread,
            },
        }
        req = Request(
            url=endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=timeout_seconds) as response:  # noqa: S310
            if debug_stream:
                chunks: list[str] = []
                chunk_idx = 0
                while True:
                    line = response.readline()
                    if not line:
                        break
                    line_str = line.decode("utf-8").strip()
                    if not line_str:
                        continue
                    evt = json.loads(line_str)
                    token = str(evt.get("response", ""))
                    if token:
                        chunks.append(token)
                        if symbol and run_id and (chunk_idx % 20 == 0):
                            self._append_pipeline_event(
                                step_name="ollama_stream_chunk",
                                status="running",
                                run_id=run_id,
                                symbol=symbol,
                                message=f"chunks={chunk_idx+1} preview={''.join(chunks)[-60:]}",
                            )
                        chunk_idx += 1
                text = "".join(chunks).strip()
            else:
                body = json.loads(response.read().decode("utf-8"))
                text = str(body.get("response", "")).strip()
        if not text:
            raise RuntimeError("Empty Ollama response")
        return text, endpoint

    def _read_rows(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError as exc:
            backup = path.with_suffix(f"{path.suffix}.bad")
            try:
                path.rename(backup)
            except OSError:
                backup = path
            self._logger.warning("Recovered malformed JSON file at %s (%s)", path, exc)
            self._write_rows(path, [])
            return []

    def _write_rows(self, path: Path, rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")

    def _read_runs(self) -> list[DailyRun]:
        return [DailyRun.model_validate(row) for row in self._read_rows(self.runs_path)]

    def _save_runs(self, rows: list[DailyRun]) -> None:
        self._write_rows(self.runs_path, [row.model_dump(mode="json") for row in rows])

    def _read_symbol_results(self) -> list[dict[str, Any]]:
        return self._read_rows(self.results_path)

    def _save_symbol_results(self, rows: list[dict[str, Any]]) -> None:
        self._write_rows(self.results_path, rows)

    def _read_contexts(self) -> list[SymbolContext]:
        return [SymbolContext.model_validate(row) for row in self._read_rows(self.contexts_path)]

    def _save_contexts(self, rows: list[SymbolContext]) -> None:
        self._write_rows(self.contexts_path, [row.model_dump(mode="json") for row in rows])

    def _read_briefings(self) -> list[DailyBriefing]:
        return [DailyBriefing.model_validate(row) for row in self._read_rows(self.briefings_path)]

    def _save_briefings(self, rows: list[DailyBriefing]) -> None:
        self._write_rows(self.briefings_path, [row.model_dump(mode="json") for row in rows])

    def _read_reviews(self) -> list[SystemReview]:
        return [SystemReview.model_validate(row) for row in self._read_rows(self.reviews_path)]

    def _save_reviews(self, rows: list[SystemReview]) -> None:
        self._write_rows(self.reviews_path, [row.model_dump(mode="json") for row in rows])

    def _read_llm_logs(self) -> list[LLMDebugLog]:
        return [LLMDebugLog.model_validate(row) for row in self._read_rows(self.llm_logs_path)]

    def _save_llm_logs(self, rows: list[LLMDebugLog]) -> None:
        self._write_rows(self.llm_logs_path, [row.model_dump(mode="json") for row in rows])

    def _append_llm_log(self, row: LLMDebugLog) -> None:
        with self._llm_logs_lock:
            try:
                rows = self._read_llm_logs()
                rows.append(row)
                self._save_llm_logs(rows[-500:])
            except Exception as exc:  # pragma: no cover - best effort logging path
                self._logger.warning("Failed to persist LLM debug log: %s", exc)

    def _read_pipeline_events(self) -> list[PipelineDebugEvent]:
        return [PipelineDebugEvent.model_validate(row) for row in self._read_rows(self.pipeline_logs_path)]

    def _save_pipeline_events(self, rows: list[PipelineDebugEvent]) -> None:
        self._write_rows(self.pipeline_logs_path, [row.model_dump(mode="json") for row in rows])

    def _append_pipeline_event(
        self,
        *,
        step_name: str,
        status: str,
        duration_ms: int = 0,
        run_id: str | None = None,
        symbol: str | None = None,
        category: str | None = None,
        message: str | None = None,
        error_message: str | None = None,
    ) -> None:
        event = PipelineDebugEvent(
            id=str(uuid4()),
            timestamp=datetime.now(UTC),
            step_name=step_name,
            status=status,
            duration_ms=duration_ms,
            run_id=run_id,
            symbol=symbol,
            category=category,
            message=message,
            error_message=error_message,
        )
        with self._pipeline_logs_lock:
            rows = self._read_pipeline_events()
            rows.append(event)
            self._save_pipeline_events(rows[-1500:])

    def _finalize_stale_running_events(self, stale_after_seconds: int = 300) -> None:
        now = datetime.now(UTC)
        with self._pipeline_logs_lock:
            rows = self._read_pipeline_events()
            changed = False
            updated: list[PipelineDebugEvent] = []
            for row in rows:
                if row.status == "running":
                    age = (now - row.timestamp).total_seconds()
                    if age > stale_after_seconds:
                        row = row.model_copy(update={"status": "failed", "error_message": "stale_running_timeout"})
                        changed = True
                updated.append(row)
            if changed:
                self._save_pipeline_events(updated[-1500:])

    @staticmethod
    def _slice_latest(rows: list[Any], limit: int = 1) -> list[Any]:
        return rows[-limit:] if rows else []

    def run_daily_pipeline(self, req: DailyPipelineRequest) -> IntelligenceRunResponse:
        started_at = datetime.now(UTC)
        self._append_pipeline_event(
            step_name="daily_pipeline_started",
            status="running",
            message=f"market={req.market.value} duration={req.duration.value} categories={','.join([c.value for c in req.categories])}",
        )
        category_rows: dict[str, SymbolResult] = {}
        raw_candidates = 0

        for category in req.categories:
            cat_started = datetime.now(UTC)
            self._append_pipeline_event(
                step_name="scanner_category_started",
                status="running",
                category=category.value,
                message=f"top_n={req.top_n_per_category}",
            )
            universe_symbols, _ = self.scanner_engine.get_universe_symbols(req.market.value, req.scanner_universe_scope)
            symbol_overrides = universe_symbols[: req.max_universe_symbols]
            scan = self.scanner_engine.scan(
                ScannerRequest(
                    market=req.market,
                    duration=req.duration,
                    category=category,
                    max_results=req.scanner_max_results,
                    universe_scope=req.scanner_universe_scope,
                    max_runtime_seconds=req.scanner_max_runtime_seconds,
                    use_custom_rules=False,
                    symbol_overrides=symbol_overrides,
                )
            )
            per_category_rows = scan.results[: req.top_n_per_category]
            raw_candidates += len(per_category_rows)
            self._append_pipeline_event(
                step_name="scanner_category_completed",
                status="success",
                category=category.value,
                duration_ms=int((datetime.now(UTC) - cat_started).total_seconds() * 1000),
                message=f"selected={len(per_category_rows)} processed={scan.scope.processed_count}",
            )
            for row in per_category_rows:
                if row.symbol not in category_rows:
                    built = self._build_symbol_result(row.symbol, req.market.value, [category.value], row.scanner_score)
                    built = built.model_copy(update={"score_by_category": {category.value: float(row.scanner_score)}})
                    category_rows[row.symbol] = built
                else:
                    existing = category_rows[row.symbol]
                    merged = sorted(
                        {
                            *(str(tag.value) if hasattr(tag, "value") else str(tag) for tag in existing.category_tags),
                            category.value,
                        }
                    )
                    existing_scores = dict(existing.score_by_category)
                    existing_scores[category.value] = float(row.scanner_score)
                    category_rows[row.symbol] = existing.model_copy(
                        update={
                            "category_tags": merged,
                            "score": max(existing.score, row.scanner_score),
                            "score_by_category": existing_scores,
                        }
                    )

        boosted_rows: list[SymbolResult] = []
        for row in category_rows.values():
            category_count = len(row.category_tags)
            boost = max(0.0, (category_count - 1) * 2.0)
            boosted_rows.append(
                row.model_copy(
                    update={
                        "score": row.score + boost,
                        "priority_boost": boost,
                        "multi_category": category_count > 1,
                    }
                )
            )
        ranked = sorted(boosted_rows, key=lambda r: (r.score, len(r.category_tags)), reverse=True)[: req.max_candidates]
        ranked = [
            row.model_copy(update={"merged_rank": idx + 1})
            for idx, row in enumerate(ranked)
        ]

        run = DailyRun(
            id=str(uuid4()),
            date=date.today(),
            timestamp=started_at,
            symbols_count=len(ranked),
            scanner_categories=req.categories,
            top_n_per_category=req.top_n_per_category,
            raw_candidates_before_merge=raw_candidates,
            final_candidates_after_merge=len(category_rows),
            status="completed",
            note="Deterministic category-balanced pipeline complete; no LLM calls were used.",
        )

        runs = self._read_runs()
        runs.append(run)
        self._save_runs(runs)

        result_rows = self._read_symbol_results()
        result_rows.append(
            DailyRunDetail(run=run, symbol_results=ranked).model_dump(mode="json")
        )
        self._save_symbol_results(result_rows)
        self._append_pipeline_event(
            step_name="daily_pipeline_completed",
            status="success",
            run_id=run.id,
            duration_ms=int((datetime.now(UTC) - started_at).total_seconds() * 1000),
            message=f"raw={raw_candidates} merged={len(category_rows)} final={len(ranked)}",
        )
        return IntelligenceRunResponse(run=run, symbol_results=ranked)

    def _build_symbol_result(self, symbol: str, market: str, category_tags: list[str], scanner_score: float) -> SymbolResult:
        analysis = self.analysis_engine.analyze_combined(
            ticker=symbol,
            market=market,
            window="1y",
            strategy_mode="balanced",
        )
        location = analysis.location
        setup = analysis.setup_interpretation
        backtest = self.backtest_engine.run(
            symbol,
            market=market,
            window="1y",
            strategy_mode="balanced",
            score_threshold=analysis.analysis_config.score_threshold,
            warmup_bars=analysis.analysis_config.warmup_bars,
        )
        return SymbolResult(
            symbol=symbol,
            market=analysis.market,
            category_tags=category_tags,
            score=float(scanner_score),
            trend=setup.trend_state,
            ema_distances={
                "ema20": round(location.distance_to_ema20_pct, 3),
                "ema50": round(location.distance_to_ema50_pct, 3),
                "ema100": round(location.distance_to_ema100_pct, 3),
                "ema200": round(location.distance_to_ema200_pct, 3),
            },
            setup_type=setup.setup_type,
            analysis_snapshot={
                "ticker": analysis.ticker,
                "window": analysis.window,
                "score": analysis.quantedge.final_score,
                "opportunity_type": analysis.chartmap.opportunity_type,
                "entry_gate": analysis.entry_gate.model_dump(mode="json"),
                "fib_mode": "visual_only",
            },
            backtest_summary=SymbolBacktestSummary(
                trades=backtest.trades,
                win_rate=backtest.win_rate,
                expectancy=backtest.expectancy,
                average_return=backtest.average_return,
                max_drawdown=backtest.max_drawdown,
            ),
        )

    def _ollama_generate(
        self,
        *,
        prompt: str,
        model: str,
        timeout_seconds: float,
        call_type: str,
        symbol: str | None = None,
        parsed_output: dict[str, Any] | None = None,
        run_id: str | None = None,
        debug_stream: bool = False,
    ) -> str:
        started = datetime.now(UTC)
        primary_provider = self._normalize_provider(self.settings.llm_provider)
        fallback_provider = self._normalize_provider(self.settings.llm_fallback_provider)
        primary_model = model or (self.settings.groq_model if primary_provider == "groq" else self.settings.ollama_model)
        fallback_model = self.settings.ollama_model if fallback_provider == "ollama" else self.settings.groq_model
        if not self.settings.intelligence_llm_enabled:
            err = "LLM layer is disabled by configuration."
            self._append_llm_log(
                LLMDebugLog(
                    id=str(uuid4()),
                    timestamp=started,
                    symbol=symbol,
                    endpoint="-",
                    call_type=call_type,
                    prompt=prompt,
                    status="fail",
                    error_message=err,
                    duration_ms=0,
                    parsed_output=parsed_output or {},
                    provider=primary_provider,
                    model=primary_model,
                )
            )
            raise RuntimeError(err)
        last_exc: Exception | None = None
        providers_to_try: list[tuple[str, str, bool]] = [(primary_provider, primary_model, False)]
        if fallback_provider != primary_provider:
            providers_to_try.append((fallback_provider, fallback_model, True))
        try:
            for provider_name, provider_model, is_fallback in providers_to_try:
                attempt_started = datetime.now(UTC)
                try:
                    if provider_name == "groq":
                        result = self._providers["groq"].generate(
                            prompt=prompt,
                            model=provider_model,
                            timeout_seconds=timeout_seconds,
                            options={
                                "temperature": self.settings.ollama_temperature,
                                "num_predict": self.settings.ollama_num_predict,
                            },
                        )
                        text, endpoint = result.raw_response, result.endpoint
                        duration_ms = result.duration_ms
                    else:
                        if debug_stream:
                            text, endpoint = self._ollama_generate_direct(
                                prompt=prompt,
                                model=provider_model,
                                timeout_seconds=timeout_seconds,
                                symbol=symbol,
                                run_id=run_id,
                                debug_stream=debug_stream,
                            )
                            duration_ms = int((datetime.now(UTC) - attempt_started).total_seconds() * 1000)
                        else:
                            result = self._providers["ollama"].generate(
                                prompt=prompt,
                                model=provider_model,
                                timeout_seconds=timeout_seconds,
                                options={
                                    "temperature": self.settings.ollama_temperature,
                                    "top_p": self.settings.ollama_top_p,
                                    "repeat_penalty": self.settings.ollama_repeat_penalty,
                                    "num_predict": self.settings.ollama_num_predict,
                                    "num_ctx": self.settings.ollama_num_ctx,
                                    "num_thread": self.settings.ollama_num_thread,
                                },
                            )
                            text, endpoint = result.raw_response, result.endpoint
                            duration_ms = result.duration_ms
                    self._append_llm_log(
                        LLMDebugLog(
                            id=str(uuid4()),
                            timestamp=started,
                            symbol=symbol,
                            endpoint=endpoint,
                            call_type=call_type,
                            prompt=prompt,
                            raw_response=text,
                            parsed_output=parsed_output or {},
                            status="success",
                            duration_ms=duration_ms,
                            provider=provider_name,
                            model=provider_model,
                            fallback_used=is_fallback,
                            fallback_provider=fallback_provider if is_fallback else None,
                        )
                    )
                    if is_fallback and symbol:
                        self._append_pipeline_event(
                            step_name="llm_fallback_used",
                            status="success",
                            run_id=run_id,
                            symbol=symbol,
                            message=f"primary={primary_provider} fallback={fallback_provider}",
                        )
                    return text
                except Exception as exc:
                    last_exc = exc
                    duration_ms = int((datetime.now(UTC) - attempt_started).total_seconds() * 1000)
                    endpoint = self.settings.groq_base_url if provider_name == "groq" else self.settings.ollama_base_url
                    self._append_llm_log(
                        LLMDebugLog(
                            id=str(uuid4()),
                            timestamp=started,
                            symbol=symbol,
                            endpoint=endpoint,
                            call_type=call_type,
                            prompt=prompt,
                            status="fail",
                            error_message=str(exc),
                            duration_ms=duration_ms,
                            parsed_output=parsed_output or {},
                            provider=provider_name,
                            model=provider_model,
                            fallback_used=is_fallback,
                            fallback_provider=fallback_provider if is_fallback else None,
                        )
                    )
            raise RuntimeError(str(last_exc) if last_exc else "LLM generation failed")
        except Exception as exc:
            raise exc

    def _context_prompt(self, row: SymbolResult, short_context_mode: bool) -> str:
        if short_context_mode:
            return (
                "Return ONLY valid JSON. No markdown. No investment advice. Keep each field under 25 words.\n"
                "Fields:\n"
                "{\n"
                '  "bull_case": "...",\n'
                '  "bear_case": "...",\n'
                '  "risks": "...",\n'
                '  "summary": "..."\n'
                "}\n\n"
                "Input:\n"
                f"symbol={row.symbol}\n"
                f"category={','.join([tag.value if hasattr(tag, 'value') else str(tag) for tag in row.category_tags])}\n"
                f"score={row.score:.2f}\n"
                f"trend={row.trend}\n"
                f"setup_type={row.setup_type}\n"
                f"ema20={row.ema_distances.get('ema20', 0.0):.2f}\n"
                f"ema50={row.ema_distances.get('ema50', 0.0):.2f}\n"
                f"ema100={row.ema_distances.get('ema100', 0.0):.2f}\n"
                f"ema200={row.ema_distances.get('ema200', 0.0):.2f}\n"
            )
        return (
            "You are a financial analyst.\n"
            "Do NOT give buy/sell advice.\n"
            "Do NOT provide price targets.\n"
            "Do NOT alter system configuration.\n\n"
            f"Analyze the following stock context:\n\n"
            f"Symbol: {row.symbol}\n"
            f"Category: {', '.join([tag.value if hasattr(tag, 'value') else str(tag) for tag in row.category_tags])}\n"
            f"Score: {row.score:.2f}\n"
            f"Trend: {row.trend}\n"
            f"Distance to EMA20: {row.ema_distances.get('ema20', 0.0):.2f}\n"
            f"Distance to EMA50: {row.ema_distances.get('ema50', 0.0):.2f}\n"
            f"Setup type: {row.setup_type}\n\n"
            "Output with strict sections:\n"
            "Bull case:\n"
            "Bear case:\n"
            "Risks:\n"
            "Summary:\n"
        )

    @staticmethod
    def _extract_section(text: str, section: str) -> str:
        lower = text.lower()
        key = f"{section.lower()}:"
        idx = lower.find(key)
        if idx < 0:
            return ""
        start = idx + len(key)
        candidates = []
        for marker in ["bull case:", "bear case:", "risks:", "summary:"]:
            pos = lower.find(marker, start)
            if pos >= 0:
                candidates.append(pos)
        end = min(candidates) if candidates else len(text)
        return text[start:end].strip()

    def _generate_single_symbol_context(self, row: SymbolResult, *, model: str, timeout_seconds: float, short_context_mode: bool, run_id: str, debug_stream: bool) -> SymbolContext:
        symbol_started = datetime.now(UTC)
        self._append_pipeline_event(
            step_name="symbol_context_started",
            status="running",
            run_id=run_id,
            symbol=row.symbol,
            message=f"model={model} short_mode={short_context_mode}",
        )
        try:
            raw = self._ollama_generate(
                prompt=self._context_prompt(row, short_context_mode),
                model=model,
                timeout_seconds=timeout_seconds,
                call_type="symbol_context",
                symbol=row.symbol,
                run_id=run_id,
                debug_stream=debug_stream,
            )
            bull = ""
            bear = ""
            risks = ""
            summary = ""
            if short_context_mode:
                parsed_json: dict[str, Any]
                try:
                    parsed_json = json.loads(raw)
                except json.JSONDecodeError:
                    left = raw.find("{")
                    right = raw.rfind("}")
                    if left >= 0 and right > left:
                        parsed_json = json.loads(raw[left : right + 1])
                    else:
                        raise
                bull = str(parsed_json.get("bull_case", "")).strip()
                bear = str(parsed_json.get("bear_case", "")).strip()
                risks = str(parsed_json.get("risks", "")).strip()
                summary = str(parsed_json.get("summary", "")).strip()
            else:
                bull = self._extract_section(raw, "Bull case") or "No clear bull-case context returned."
                bear = self._extract_section(raw, "Bear case") or "No clear bear-case context returned."
                risks = self._extract_section(raw, "Risks") or "No explicit risks returned."
                summary = self._extract_section(raw, "Summary") or raw[:400]
            self._append_llm_log(
                LLMDebugLog(
                    id=str(uuid4()),
                    timestamp=datetime.now(UTC),
                    symbol=row.symbol,
                    endpoint=self.settings.ollama_base_url.rstrip("/") + "/api/generate",
                    call_type="symbol_context_parsed",
                    prompt="(parsed output)",
                    raw_response=raw,
                    parsed_output={
                        "bull_case": bull,
                        "bear_case": bear,
                        "risks": risks,
                        "summary": summary,
                    },
                    status="success",
                    duration_ms=0,
                )
            )
            self._append_pipeline_event(
                step_name="symbol_context_completed",
                status="success",
                run_id=run_id,
                symbol=row.symbol,
                duration_ms=int((datetime.now(UTC) - symbol_started).total_seconds() * 1000),
                message="parsed successfully",
            )
            return SymbolContext(
                symbol=row.symbol,
                date=date.today(),
                bull_case=bull,
                bear_case=bear,
                risks=risks,
                summary=summary,
                model=model,
                status="generated",
            )
        except (TimeoutError, URLError, RuntimeError, OSError, ValueError, json.JSONDecodeError) as exc:
            self._append_pipeline_event(
                step_name="symbol_context_completed",
                status="failed",
                run_id=run_id,
                symbol=row.symbol,
                duration_ms=int((datetime.now(UTC) - symbol_started).total_seconds() * 1000),
                error_message=str(exc),
            )
            return SymbolContext(
                symbol=row.symbol,
                date=date.today(),
                bull_case="",
                bear_case="",
                risks="",
                summary="",
                model=model,
                status="failed",
                error=str(exc),
            )

    def _get_run_detail(self, run_id: str) -> DailyRunDetail:
        rows = self._read_symbol_results()
        for row in rows:
            parsed = DailyRunDetail.model_validate(row)
            if parsed.run.id == run_id:
                return parsed
        raise FileNotFoundError(run_id)

    def generate_symbol_contexts(self, req: SymbolContextBatchRequest) -> SymbolContextBatchResponse:
        started = datetime.now(UTC)
        self._append_pipeline_event(
            step_name="symbol_context_batch_started",
            status="running",
            run_id=req.run_id,
            message=f"limit={req.context_symbol_limit} concurrency={req.max_concurrency} timeout={req.timeout_seconds}s sequential={req.sequential_mode}",
        )
        detail = self._get_run_detail(req.run_id)
        target_rows = detail.symbol_results[: req.context_symbol_limit]
        self._append_pipeline_event(
            step_name="symbol_context_candidates_selected",
            status="success",
            run_id=req.run_id,
            message="symbols=" + ",".join([row.symbol for row in target_rows]),
        )
        contexts: list[SymbolContext] = []
        workers = 1 if req.sequential_mode else req.max_concurrency
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(
                    self._generate_single_symbol_context,
                    row,
                    model=req.model,
                    timeout_seconds=req.timeout_seconds,
                    short_context_mode=req.short_context_mode,
                    run_id=req.run_id,
                    debug_stream=req.debug_stream,
                )
                for row in target_rows
            ]
            for future in as_completed(futures):
                contexts.append(future.result())

        stored = self._read_contexts()
        stored.extend(contexts)
        self._save_contexts(stored)
        failed = sum(1 for row in contexts if row.status != "generated")
        self._append_pipeline_event(
            step_name="symbol_context_batch_completed",
            status="success" if failed < len(contexts) else "failed",
            run_id=req.run_id,
            duration_ms=int((datetime.now(UTC) - started).total_seconds() * 1000),
            message=f"generated={len(contexts)-failed} failed={failed}",
            error_message=None if failed < len(contexts) else "all symbol contexts failed",
        )
        return SymbolContextBatchResponse(
            run_id=req.run_id,
            generated=len(contexts) - failed,
            failed=failed,
            contexts=sorted(contexts, key=lambda row: row.symbol),
        )

    def generate_daily_briefing(self, req: DailyBriefingRequest) -> DailyBriefing:
        detail = self._get_run_detail(req.run_id)
        by_symbol = {row.symbol: row for row in self._read_contexts() if row.date == detail.run.date}
        top_rows = sorted(detail.symbol_results, key=lambda row: row.score, reverse=True)[:10]
        prompt_parts = [
            "You are preparing a deterministic market briefing.",
            "Do NOT give buy/sell advice.",
            "Do NOT provide price targets.",
        ]
        if req.short_briefing_mode:
            prompt_parts.extend(
                [
                    "Keep output compact.",
                    "Return exactly 3 sections with 2-3 bullets each:",
                    "Top opportunities",
                    "Key risks",
                    "Market tone summary",
                ]
            )
        else:
            prompt_parts.append("Return three sections: Top opportunities, Key risks, Market tone summary.")
        for row in top_rows:
            ctx = by_symbol.get(row.symbol)
            summary = ctx.summary if ctx and ctx.status == "generated" else "No LLM context available."
            prompt_parts.append(
                f"- {row.symbol} | category={','.join([str(tag) for tag in row.category_tags])} | "
                f"score={row.score:.2f} | trend={row.trend} | summary={summary}"
            )
        prompt = "\n".join(prompt_parts)
        try:
            text = self._ollama_generate(
                prompt=prompt,
                model=req.model,
                timeout_seconds=req.timeout_seconds,
                call_type="daily_briefing",
            )
            briefing = DailyBriefing(date=detail.run.date, summary_text=text, model=req.model, status="generated")
        except (TimeoutError, URLError, RuntimeError, OSError, ValueError) as exc:
            briefing = DailyBriefing(
                date=detail.run.date,
                summary_text="Daily briefing generation failed.",
                model=req.model,
                status="failed",
                error=str(exc),
            )
        rows = self._read_briefings()
        rows.append(briefing)
        self._save_briefings(rows)
        return briefing

    def run_system_review(self, req: SystemReviewRequest) -> SystemReview:
        min_date = date.today() - timedelta(days=req.days)
        result_rows: list[DailyRunDetail] = []
        for row in self._read_symbol_results():
            parsed = DailyRunDetail.model_validate(row)
            if parsed.run.date >= min_date:
                result_rows.append(parsed)
        if not result_rows:
            review = SystemReview(
                id=str(uuid4()),
                period=f"last_{req.days}d",
                findings="No runs in selected period.",
                mistakes="No data.",
                missed_patterns="No data.",
                recommendations="Run daily pipeline first.",
                model=req.model,
                status="generated",
            )
            rows = self._read_reviews()
            rows.append(review)
            self._save_reviews(rows)
            return review

        perf_rows: list[dict[str, Any]] = []
        for detail in result_rows:
            for row in detail.symbol_results:
                forward = self._forward_returns(row.symbol, row.market.value)
                perf_rows.append(
                    {
                        "symbol": row.symbol,
                        "categories": [str(tag) for tag in row.category_tags],
                        "score": row.score,
                        "trend": row.trend,
                        "setup_type": row.setup_type,
                        "backtest": row.backtest_summary.model_dump(),
                        "fwd_1d": forward.get("1d"),
                        "fwd_3d": forward.get("3d"),
                        "fwd_7d": forward.get("7d"),
                    }
                )

        prompt = (
            "Return ONLY valid JSON. No markdown. No trade instructions.\n"
            "Do not modify configs directly; recommendations only.\n"
            "Schema:\n"
            '{"findings":[],"mistakes":[],"missed_patterns":[],"recommendations":[]}\n'
            f"Data window days: {req.days}\n"
            f"Data: {json.dumps(perf_rows[:300])}\n"
        )
        try:
            text = self._ollama_generate(prompt=prompt, model=req.model, timeout_seconds=req.timeout_seconds, call_type="system_review")
            parsed: dict[str, Any] = {}
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                left = text.find("{")
                right = text.rfind("}")
                if left >= 0 and right > left:
                    parsed = json.loads(text[left : right + 1])
            findings = "\n".join([str(x) for x in parsed.get("findings", [])]) if parsed else self._extract_section(text, "Findings") or text[:600]
            mistakes = "\n".join([str(x) for x in parsed.get("mistakes", [])]) if parsed else self._extract_section(text, "Mistakes") or ""
            missed = "\n".join([str(x) for x in parsed.get("missed_patterns", [])]) if parsed else self._extract_section(text, "Missed patterns") or ""
            recommendations = "\n".join([str(x) for x in parsed.get("recommendations", [])]) if parsed else self._extract_section(text, "Recommendations") or ""
            review = SystemReview(
                id=str(uuid4()),
                period=f"last_{req.days}d",
                findings=findings,
                mistakes=mistakes,
                missed_patterns=missed,
                recommendations=recommendations,
                model=req.model,
                status="generated",
            )
        except (TimeoutError, URLError, RuntimeError, OSError, ValueError) as exc:
            review = SystemReview(
                id=str(uuid4()),
                period=f"last_{req.days}d",
                findings="Review generation failed.",
                mistakes="",
                missed_patterns="",
                recommendations="",
                model=req.model,
                status="failed",
                error=str(exc),
            )
        rows = self._read_reviews()
        rows.append(review)
        self._save_reviews(rows)
        return review

    def _forward_returns(self, symbol: str, market: str) -> dict[str, float | None]:
        try:
            bundle = self.analysis_engine.data_service.get_market_data(symbol, market=market, period="1y")
            close = bundle.daily["close"].dropna().astype(float)
            if len(close) < 8:
                return {"1d": None, "3d": None, "7d": None}
            return {
                "1d": float((close.iloc[-1] / close.iloc[-2] - 1.0) * 100),
                "3d": float((close.iloc[-1] / close.iloc[-4] - 1.0) * 100),
                "7d": float((close.iloc[-1] / close.iloc[-8] - 1.0) * 100),
            }
        except Exception:
            return {"1d": None, "3d": None, "7d": None}

    def get_dashboard(self) -> IntelligenceDashboardResponse:
        self._finalize_stale_running_events()
        runs = self._read_runs()
        latest_results: list[SymbolResult] = []
        if runs:
            latest_id = runs[-1].id
            try:
                latest_results = self._get_run_detail(latest_id).symbol_results
            except FileNotFoundError:
                latest_results = []
        contexts = self._read_contexts()
        briefings = self._read_briefings()
        reviews = self._read_reviews()
        return IntelligenceDashboardResponse(
            runs=sorted(runs, key=lambda row: row.timestamp, reverse=True),
            latest_run_results=latest_results,
            latest_contexts=sorted(self._slice_latest(contexts, limit=50), key=lambda row: (row.date, row.symbol), reverse=True),
            latest_briefing=briefings[-1] if briefings else None,
            latest_review=reviews[-1] if reviews else None,
            pipeline_events=sorted(self._slice_latest(self._read_pipeline_events(), limit=250), key=lambda row: row.timestamp, reverse=True),
        )

    def get_llm_logs(self, limit: int = 200) -> list[LLMDebugLog]:
        rows = self._read_llm_logs()
        return sorted(rows, key=lambda row: row.timestamp, reverse=True)[: max(1, min(limit, 500))]

    def get_llm_status(self, timeout_seconds: float = 2.0) -> LLMConnectionStatus:
        checked_at = datetime.now(UTC)
        primary_provider = self._normalize_provider(self.settings.llm_provider)
        fallback_provider = self._normalize_provider(self.settings.llm_fallback_provider)
        base_url = self.settings.groq_base_url.rstrip("/") if primary_provider == "groq" else self.settings.ollama_base_url.rstrip("/")
        installed: list[str] = []
        primary_connected = False
        fallback_connected = False
        model_available: bool | None = None
        model_used = self.settings.groq_model if primary_provider == "groq" else self.settings.ollama_model
        primary_model = self.settings.groq_model if primary_provider == "groq" else self.settings.ollama_model
        fallback_model = self.settings.groq_model if fallback_provider == "groq" else self.settings.ollama_model
        primary_health = self._providers[primary_provider].health_check(model=primary_model, timeout_seconds=timeout_seconds)
        fallback_health = self._providers[fallback_provider].health_check(model=fallback_model, timeout_seconds=timeout_seconds)
        primary_connected = primary_health.connected
        fallback_connected = fallback_health.connected
        installed = primary_health.installed_models
        model_available = primary_health.model_available
        err = primary_health.error
        base_url = primary_health.endpoint

        last_logs = self.get_llm_logs(limit=1)
        last_duration = last_logs[0].duration_ms if last_logs else None
        last_fallback = last_logs[0].fallback_used if last_logs else None
        return LLMConnectionStatus(
            connected=primary_connected or fallback_connected,
            base_url=base_url,
            checked_at=checked_at,
            error=err,
            model_used=model_used,
            model_available=model_available,
            installed_models=installed[:100],
            primary_provider=primary_provider,
            fallback_provider=fallback_provider,
            primary_connected=primary_connected,
            fallback_connected=fallback_connected,
            last_response_duration_ms=last_duration,
            last_fallback_used=last_fallback,
        )

    def test_llm_response(self, req: LLMResponseTestRequest) -> LLMResponseTestResult:
        checked_at = datetime.now(UTC)
        endpoint = self.settings.ollama_base_url.rstrip("/") + "/api/generate"
        started = datetime.now(UTC)
        try:
            text = self._ollama_generate(
                prompt="Reply with exactly: OK",
                model=req.model,
                timeout_seconds=req.timeout_seconds,
                call_type="health_probe",
            )
            elapsed_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
            threshold_ms = int(req.threshold_seconds * 1000)
            return LLMResponseTestResult(
                ok=True,
                model=req.model,
                endpoint=endpoint,
                response_time_ms=elapsed_ms,
                threshold_ms=threshold_ms,
                within_threshold=elapsed_ms <= threshold_ms,
                status="success",
                response_preview=text[:120],
                checked_at=checked_at,
            )
        except Exception as exc:
            elapsed_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
            threshold_ms = int(req.threshold_seconds * 1000)
            return LLMResponseTestResult(
                ok=False,
                model=req.model,
                endpoint=endpoint,
                response_time_ms=elapsed_ms,
                threshold_ms=threshold_ms,
                within_threshold=False,
                status="fail",
                error=str(exc),
                checked_at=checked_at,
            )
