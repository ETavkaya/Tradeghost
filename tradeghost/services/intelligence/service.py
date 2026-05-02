from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from tradeghost.services.analysis_engine import AnalysisEngine
from tradeghost.services.backtest.engine import BacktestEngine
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
        self.analysis_engine = analysis_engine or AnalysisEngine()
        self.scanner_engine = scanner_engine or ScannerEngine(analysis_engine=self.analysis_engine)
        self.backtest_engine = backtest_engine or BacktestEngine(analysis_engine=self.analysis_engine)
        self._logger = logging.getLogger(__name__)

    def _read_rows(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

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

    @staticmethod
    def _slice_latest(rows: list[Any], limit: int = 1) -> list[Any]:
        return rows[-limit:] if rows else []

    def run_daily_pipeline(self, req: DailyPipelineRequest) -> IntelligenceRunResponse:
        started_at = datetime.now(UTC)
        category_rows: dict[str, SymbolResult] = {}
        raw_candidates = 0

        for category in req.categories:
            scan = self.scanner_engine.scan(
                ScannerRequest(
                    market=req.market,
                    duration=req.duration,
                    category=category,
                    max_results=req.scanner_max_results,
                    universe_scope=req.scanner_universe_scope,
                    max_runtime_seconds=req.scanner_max_runtime_seconds,
                    use_custom_rules=False,
                )
            )
            per_category_rows = scan.results[: req.top_n_per_category]
            raw_candidates += len(per_category_rows)
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

    def _ollama_generate(self, *, prompt: str, model: str, timeout_seconds: float) -> str:
        if not self.settings.intelligence_llm_enabled:
            raise RuntimeError("LLM layer is disabled by configuration.")
        url = self.settings.ollama_base_url.rstrip("/") + "/api/generate"
        payload = {"model": model, "prompt": prompt, "stream": False}
        req = Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=timeout_seconds) as response:  # noqa: S310
            body = json.loads(response.read().decode("utf-8"))
        text = str(body.get("response", "")).strip()
        if not text:
            raise RuntimeError("Empty LLM response.")
        return text

    def _context_prompt(self, row: SymbolResult) -> str:
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

    def _generate_single_symbol_context(self, row: SymbolResult, *, model: str, timeout_seconds: float) -> SymbolContext:
        try:
            raw = self._ollama_generate(prompt=self._context_prompt(row), model=model, timeout_seconds=timeout_seconds)
            bull = self._extract_section(raw, "Bull case") or "No clear bull-case context returned."
            bear = self._extract_section(raw, "Bear case") or "No clear bear-case context returned."
            risks = self._extract_section(raw, "Risks") or "No explicit risks returned."
            summary = self._extract_section(raw, "Summary") or raw[:400]
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
        except (TimeoutError, URLError, RuntimeError, OSError, ValueError) as exc:
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
        detail = self._get_run_detail(req.run_id)
        contexts: list[SymbolContext] = []
        with ThreadPoolExecutor(max_workers=req.max_concurrency) as executor:
            futures = [
                executor.submit(
                    self._generate_single_symbol_context,
                    row,
                    model=req.model,
                    timeout_seconds=req.timeout_seconds,
                )
                for row in detail.symbol_results
            ]
            for future in as_completed(futures):
                contexts.append(future.result())

        stored = self._read_contexts()
        stored.extend(contexts)
        self._save_contexts(stored)
        failed = sum(1 for row in contexts if row.status != "generated")
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
            "Return three sections: Top opportunities, Key risks, Market tone summary.",
        ]
        for row in top_rows:
            ctx = by_symbol.get(row.symbol)
            summary = ctx.summary if ctx and ctx.status == "generated" else "No LLM context available."
            prompt_parts.append(
                f"- {row.symbol} | category={','.join([str(tag) for tag in row.category_tags])} | "
                f"score={row.score:.2f} | trend={row.trend} | summary={summary}"
            )
        prompt = "\n".join(prompt_parts)
        try:
            text = self._ollama_generate(prompt=prompt, model=req.model, timeout_seconds=25.0)
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
            "You are reviewing a trading system.\n"
            "Do NOT suggest trades.\n"
            "Suggest only system improvements.\n"
            "Analyze: which signals worked, which failed, missed opportunities, over-filtering vs under-filtering.\n"
            f"Data window: last {req.days} days.\n"
            f"Data: {json.dumps(perf_rows[:300])}\n\n"
            "Return strict sections:\nFindings:\nMistakes:\nMissed patterns:\nRecommendations:\n"
        )
        try:
            text = self._ollama_generate(prompt=prompt, model=req.model, timeout_seconds=req.timeout_seconds)
            review = SystemReview(
                id=str(uuid4()),
                period=f"last_{req.days}d",
                findings=self._extract_section(text, "Findings") or text[:600],
                mistakes=self._extract_section(text, "Mistakes") or "",
                missed_patterns=self._extract_section(text, "Missed patterns") or "",
                recommendations=self._extract_section(text, "Recommendations") or "",
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
        )
