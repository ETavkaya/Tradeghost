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
from tradeghost.services.intelligence.providers import LLMProvider, OllamaProvider, OpenAIProvider
from tradeghost.services.scanner.engine import ScannerEngine
from tradeghost.shared.config.settings import get_settings
from tradeghost.shared.models.schemas import (
    CandidateCohort,
    CandidateCohortStatus,
    CohortCandidate,
    CohortCleanupDuplicateRequest,
    CohortCleanupDuplicateResponse,
    CohortDailySnapshot,
    CohortDetail,
    CohortDeleteResponse,
    CohortDuplicateGroup,
    CohortDuplicateStrategy,
    CohortReportMode,
    CohortFollowupRequest,
    CohortFollowupResponse,
    CohortSymbolContextRequest,
    CohortBriefingRequest,
    CohortReviewRequest,
    CohortReviewResponse,
    CohortReviewStats,
    CohortStatusUpdateResponse,
    DailyBriefing,
    DailyBriefingRequest,
    DiscoveryCreateCohortRequest,
    DailyPipelineRequest,
    DailyRun,
    DailyRunDetail,
    IntelligenceDashboardResponse,
    IntelligenceReviewApproval,
    IntelligenceReviewApprovalRequest,
    IntelligenceRunReport,
    IntelligenceRunReportExport,
    IntelligenceRunResponse,
    LLMResponseTestRequest,
    LLMResponseTestResult,
    LatestCohortState,
    LLMConnectionStatus,
    LLMDebugLog,
    PipelineDebugEvent,
    ReviewReadiness,
    ScannerRequest,
    SymbolBacktestSummary,
    SymbolContext,
    SymbolContextBatchRequest,
    SymbolContextBatchResponse,
    SymbolResult,
    DeterministicReviewStats,
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
        self.approvals_path = self.base_dir / "review_approvals.json"
        self.cohorts_path = self.base_dir / "candidate_cohorts.json"
        self.cohort_candidates_path = self.base_dir / "cohort_candidates.json"
        self.cohort_snapshots_path = self.base_dir / "cohort_daily_snapshots.json"
        self.llm_logs_path = self.base_dir / "llm_calls.json"
        self.pipeline_logs_path = self.base_dir / "pipeline_events.json"
        self.analysis_engine = analysis_engine or AnalysisEngine()
        self.scanner_engine = scanner_engine or ScannerEngine(analysis_engine=self.analysis_engine)
        self.backtest_engine = backtest_engine or BacktestEngine(analysis_engine=self.analysis_engine)
        self._logger = logging.getLogger(__name__)
        self._llm_logs_lock = Lock()
        self._pipeline_logs_lock = Lock()
        self._providers: dict[str, LLMProvider] = {
            "openai": OpenAIProvider(self.settings),
            "ollama": OllamaProvider(self.settings),
        }

    def _normalize_provider(self, provider: str | None) -> str:
        value = (provider or "openai").strip().lower()
        return value if value in {"ollama", "openai"} else "openai"

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

    def _read_approvals(self) -> list[IntelligenceReviewApproval]:
        return [IntelligenceReviewApproval.model_validate(row) for row in self._read_rows(self.approvals_path)]

    def _save_approvals(self, rows: list[IntelligenceReviewApproval]) -> None:
        self._write_rows(self.approvals_path, [row.model_dump(mode="json") for row in rows])

    def _read_cohorts(self) -> list[CandidateCohort]:
        return [CandidateCohort.model_validate(row) for row in self._read_rows(self.cohorts_path)]

    def _save_cohorts(self, rows: list[CandidateCohort]) -> None:
        self._write_rows(self.cohorts_path, [row.model_dump(mode="json") for row in rows])

    def _read_cohort_candidates(self) -> list[CohortCandidate]:
        return [CohortCandidate.model_validate(row) for row in self._read_rows(self.cohort_candidates_path)]

    def _save_cohort_candidates(self, rows: list[CohortCandidate]) -> None:
        self._write_rows(self.cohort_candidates_path, [row.model_dump(mode="json") for row in rows])

    def _read_cohort_snapshots(self) -> list[CohortDailySnapshot]:
        return [CohortDailySnapshot.model_validate(row) for row in self._read_rows(self.cohort_snapshots_path)]

    def _save_cohort_snapshots(self, rows: list[CohortDailySnapshot]) -> None:
        self._write_rows(self.cohort_snapshots_path, [row.model_dump(mode="json") for row in rows])

    @staticmethod
    def _normalize_cohort_name(name: str) -> str:
        return "".join(ch.lower() for ch in (name or "").strip() if ch.isalnum())

    def _enrich_cohort_metadata(self, rows: list[CandidateCohort]) -> list[CandidateCohort]:
        candidates = self._read_cohort_candidates()
        snapshots = self._read_cohort_snapshots()
        symbol_count_by_id: dict[str, int] = {}
        latest_followup_by_id: dict[str, date] = {}
        for row in candidates:
            symbol_count_by_id[row.cohort_id] = symbol_count_by_id.get(row.cohort_id, 0) + 1
        for row in snapshots:
            prev = latest_followup_by_id.get(row.cohort_id)
            if prev is None or row.snapshot_date > prev:
                latest_followup_by_id[row.cohort_id] = row.snapshot_date
        return [
            row.model_copy(
                update={
                    "symbols_count": symbol_count_by_id.get(row.id, 0),
                    "latest_followup_date": latest_followup_by_id.get(row.id),
                    "short_id": row.id[:8],
                }
            )
            for row in rows
        ]

    def _sort_cohorts(self, rows: list[CandidateCohort]) -> list[CandidateCohort]:
        status_order = {
            CandidateCohortStatus.ACTIVE: 0,
            CandidateCohortStatus.COMPLETED: 1,
            CandidateCohortStatus.ARCHIVED: 2,
        }
        return sorted(
            rows,
            key=lambda row: (
                status_order.get(row.status, 9),
                -int(row.created_at.timestamp()),
            ),
        )

    def list_cohorts(self) -> list[CandidateCohort]:
        return self._sort_cohorts(self._enrich_cohort_metadata(self._read_cohorts()))

    def get_cohort_detail(self, cohort_id: str) -> CohortDetail:
        cohorts = self._read_cohorts()
        cohort = next((row for row in cohorts if row.id == cohort_id), None)
        if cohort is None:
            raise FileNotFoundError(f"Cohort not found: {cohort_id}")
        candidates = [row for row in self._read_cohort_candidates() if row.cohort_id == cohort_id]
        snapshots = [row for row in self._read_cohort_snapshots() if row.cohort_id == cohort_id]
        ordered_candidates = sorted(candidates, key=lambda row: row.selected_rank)
        ordered_snapshots = sorted(snapshots, key=lambda row: (row.snapshot_date, row.symbol))
        latest_states = self._derive_latest_cohort_states(ordered_candidates, ordered_snapshots)
        return CohortDetail(
            cohort=cohort,
            candidates=ordered_candidates,
            snapshots=ordered_snapshots,
            latest_states=latest_states,
        )

    def _derive_latest_cohort_states(
        self,
        candidates: list[CohortCandidate],
        snapshots: list[CohortDailySnapshot],
    ) -> list[LatestCohortState]:
        latest_by_symbol: dict[str, CohortDailySnapshot] = {}
        for snap in snapshots:
            latest_by_symbol[snap.symbol] = snap
        rows: list[LatestCohortState] = []
        for cand in candidates:
            latest = latest_by_symbol.get(cand.symbol)
            rows.append(
                LatestCohortState(
                    cohort_id=cand.cohort_id,
                    symbol=cand.symbol,
                    latest_followup_date=latest.snapshot_date if latest else None,
                    selected_rank=cand.selected_rank,
                    selected_score=cand.selected_score,
                    selected_setup_type=cand.selected_setup_type,
                    selected_reason=cand.selected_reason,
                    selected_categories=cand.selected_categories,
                    current_price=latest.current_price if latest else None,
                    current_score=latest.current_score if latest else None,
                    current_setup_type=latest.current_setup_type if latest else None,
                    current_trend_state=latest.current_trend_state if latest else None,
                    current_score_dynamics=latest.current_score_dynamics if latest else None,
                    current_trigger_state=latest.current_trigger_state if latest else None,
                    current_trigger_score=latest.current_trigger_score if latest else None,
                    return_since_selection=latest.return_since_selection if latest else None,
                    return_1d=latest.return_1d if latest else None,
                    return_3d=latest.return_3d if latest else None,
                    return_7d=latest.return_7d if latest else None,
                    return_14d=latest.return_14d if latest else None,
                    return_28d=latest.return_28d if latest else None,
                    validity_state=latest.validity_state if latest else "pending_validation",
                    invalidation_reason=latest.invalidation_reason if latest else None,
                    entry_readiness=latest.entry_readiness if latest else "pending_validation",
                    blocked_by=latest.blocked_by if latest else "none",
                    readiness_explanation=latest.readiness_explanation if latest else "Awaiting first follow-up snapshot.",
                    data_quality_flags=latest.data_quality_flags if latest else [],
                )
            )
        return rows

    def archive_cohort(self, cohort_id: str) -> CohortStatusUpdateResponse:
        cohorts = self._read_cohorts()
        found = False
        updated: list[CandidateCohort] = []
        cohort_name = None
        for row in cohorts:
            if row.id == cohort_id:
                found = True
                cohort_name = row.name
                updated.append(row.model_copy(update={"status": CandidateCohortStatus.ARCHIVED}))
            else:
                updated.append(row)
        if not found:
            raise FileNotFoundError(f"Cohort not found: {cohort_id}")
        self._save_cohorts(updated)
        self._append_pipeline_event(
            step_name="cohort_archived",
            status="success",
            cohort_id=cohort_id,
            cohort_name=cohort_name,
            message="action=archive",
        )
        return CohortStatusUpdateResponse(cohort_id=cohort_id, status=CandidateCohortStatus.ARCHIVED)

    def activate_cohort(self, cohort_id: str) -> CohortStatusUpdateResponse:
        cohorts = self._read_cohorts()
        found = False
        updated: list[CandidateCohort] = []
        cohort_name = None
        for row in cohorts:
            if row.id == cohort_id:
                found = True
                cohort_name = row.name
                updated.append(row.model_copy(update={"status": CandidateCohortStatus.ACTIVE}))
            else:
                updated.append(row)
        if not found:
            raise FileNotFoundError(f"Cohort not found: {cohort_id}")
        self._save_cohorts(updated)
        self._append_pipeline_event(
            step_name="cohort_activated",
            status="success",
            cohort_id=cohort_id,
            cohort_name=cohort_name,
            message="action=activate",
        )
        return CohortStatusUpdateResponse(cohort_id=cohort_id, status=CandidateCohortStatus.ACTIVE)

    def delete_cohort(self, cohort_id: str) -> CohortDeleteResponse:
        cohorts = self._read_cohorts()
        cohort = next((row for row in cohorts if row.id == cohort_id), None)
        if cohort is None:
            raise FileNotFoundError(f"Cohort not found: {cohort_id}")
        cohorts = [row for row in cohorts if row.id != cohort_id]
        self._save_cohorts(cohorts)

        candidates = self._read_cohort_candidates()
        snapshots = self._read_cohort_snapshots()
        contexts = self._read_contexts()
        briefings = self._read_briefings()
        reviews = self._read_reviews()

        removed_candidates = sum(1 for row in candidates if row.cohort_id == cohort_id)
        removed_snapshots = sum(1 for row in snapshots if row.cohort_id == cohort_id)
        removed_contexts = sum(1 for row in contexts if row.cohort_id == cohort_id)
        removed_briefings = sum(1 for row in briefings if row.cohort_id == cohort_id)
        removed_reviews = sum(1 for row in reviews if getattr(row, "id", "").startswith(cohort_id))

        self._save_cohort_candidates([row for row in candidates if row.cohort_id != cohort_id])
        self._save_cohort_snapshots([row for row in snapshots if row.cohort_id != cohort_id])
        self._save_contexts([row for row in contexts if row.cohort_id != cohort_id])
        self._save_briefings([row for row in briefings if row.cohort_id != cohort_id])
        # Cohort reviews are deterministic ad-hoc currently; no persistent cohort review rows to delete by id.
        self._save_reviews([row for row in reviews if not getattr(row, "id", "").startswith(cohort_id)])

        self._append_pipeline_event(
            step_name="cohort_deleted",
            status="success",
            cohort_id=cohort_id,
            cohort_name=cohort.name,
            message=f"action=delete candidates={removed_candidates} snapshots={removed_snapshots} contexts={removed_contexts}",
        )
        return CohortDeleteResponse(
            cohort_id=cohort_id,
            deleted=True,
            removed_candidates=removed_candidates,
            removed_snapshots=removed_snapshots,
            removed_contexts=removed_contexts,
            removed_briefings=removed_briefings,
            removed_reviews=removed_reviews,
        )

    def cleanup_duplicate_cohorts(self, req: CohortCleanupDuplicateRequest) -> CohortCleanupDuplicateResponse:
        cohorts = [row for row in self._read_cohorts() if row.status == CandidateCohortStatus.ACTIVE]
        details = {row.id: self.get_cohort_detail(row.id) for row in cohorts}
        adjacency: dict[str, set[str]] = {row.id: set() for row in cohorts}

        def jaccard(a: set[str], b: set[str]) -> float:
            if not a and not b:
                return 1.0
            denom = len(a.union(b))
            return 0.0 if denom == 0 else len(a.intersection(b)) / denom

        for i, left in enumerate(cohorts):
            left_symbols = {row.symbol for row in details[left.id].candidates}
            left_name = self._normalize_cohort_name(left.name)
            for right in cohorts[i + 1:]:
                if left.market != right.market or left.start_date != right.start_date:
                    continue
                right_symbols = {row.symbol for row in details[right.id].candidates}
                right_name = self._normalize_cohort_name(right.name)
                overlap = jaccard(left_symbols, right_symbols)
                same_name = left_name == right_name
                if same_name or overlap >= 0.8:
                    adjacency[left.id].add(right.id)
                    adjacency[right.id].add(left.id)

        seen: set[str] = set()
        groups: list[list[str]] = []
        for row in cohorts:
            if row.id in seen:
                continue
            stack = [row.id]
            comp: list[str] = []
            while stack:
                node = stack.pop()
                if node in seen:
                    continue
                seen.add(node)
                comp.append(node)
                stack.extend(adjacency.get(node, set()) - seen)
            if len(comp) > 1:
                groups.append(comp)

        duplicate_groups: list[CohortDuplicateGroup] = []
        to_archive_ids: list[str] = []
        for idx, group_ids in enumerate(groups, start=1):
            ranked = sorted(
                group_ids,
                key=lambda cid: (
                    len(details[cid].snapshots),
                    len(details[cid].candidates),
                    details[cid].cohort.created_at.timestamp(),
                ),
                reverse=True,
            )
            keep_id = ranked[0]
            archive_ids = ranked[1:]
            to_archive_ids.extend(archive_ids)
            duplicate_groups.append(
                CohortDuplicateGroup(
                    group_id=f"group-{idx}",
                    cohort_ids=ranked,
                    keep_cohort_id=keep_id,
                    archive_cohort_ids=archive_ids,
                    reasons=[
                        "same market/start_date",
                        "same normalized name or high symbol overlap",
                    ],
                    details=[
                        {
                            "cohort_id": cid,
                            "name": details[cid].cohort.name,
                            "created_at": details[cid].cohort.created_at.isoformat(),
                            "candidates": len(details[cid].candidates),
                            "snapshots": len(details[cid].snapshots),
                            "latest_followup_date": max((s.snapshot_date for s in details[cid].snapshots), default=None),
                        }
                        for cid in ranked
                    ],
                )
            )

        archived_ids: list[str] = []
        if req.apply_archive and not req.dry_run and to_archive_ids:
            cohort_rows = self._read_cohorts()
            updated_rows: list[CandidateCohort] = []
            for row in cohort_rows:
                if row.id in set(to_archive_ids):
                    updated_rows.append(row.model_copy(update={"status": CandidateCohortStatus.ARCHIVED}))
                    archived_ids.append(row.id)
                else:
                    updated_rows.append(row)
            self._save_cohorts(updated_rows)
            self._append_pipeline_event(
                step_name="cohort_cleanup_duplicates_applied",
                status="success",
                message=f"action=cleanup_duplicates archived={len(archived_ids)}",
            )

        return CohortCleanupDuplicateResponse(
            dry_run=req.dry_run,
            duplicate_groups=duplicate_groups,
            archived_cohort_ids=sorted(set(archived_ids)),
        )

    def run_discovery_create_cohort(self, req: DiscoveryCreateCohortRequest) -> CohortDetail:
        if not req.name.strip():
            raise ValueError("Cohort name is required.")
        if not req.categories:
            raise ValueError("At least one scanner category is required.")
        cohorts_existing = self._read_cohorts()
        active_same_name = [
            row for row in cohorts_existing
            if row.status == CandidateCohortStatus.ACTIVE
            and row.market == req.market
            and row.start_date == date.today()
            and self._normalize_cohort_name(row.name) == self._normalize_cohort_name(req.name)
        ]
        if active_same_name:
            existing = sorted(active_same_name, key=lambda row: row.created_at, reverse=True)[0]
            if req.duplicate_strategy == CohortDuplicateStrategy.USE_EXISTING:
                self._append_pipeline_event(
                    step_name="cohort_create_dedup_use_existing",
                    status="success",
                    cohort_id=existing.id,
                    cohort_name=existing.name,
                    message=f"duplicate detected for name={req.name}",
                )
                return self.get_cohort_detail(existing.id)
            if req.duplicate_strategy == CohortDuplicateStrategy.ARCHIVE_EXISTING_CREATE_NEW:
                cohorts_existing = [
                    row.model_copy(update={"status": CandidateCohortStatus.ARCHIVED})
                    if row.id in {x.id for x in active_same_name}
                    else row
                    for row in cohorts_existing
                ]
                self._save_cohorts(cohorts_existing)
                self._append_pipeline_event(
                    step_name="cohort_create_archive_existing",
                    status="success",
                    cohort_id=existing.id,
                    cohort_name=existing.name,
                    message=f"archived existing duplicate cohort(s) for name={req.name}",
                )
        discovery = self.run_daily_pipeline(
            DailyPipelineRequest(
                market=req.market,
                duration=req.duration,
                categories=req.categories,
                max_candidates=req.max_candidates,
                top_n_per_category=req.top_n_per_category,
                max_universe_symbols=req.max_universe_symbols,
                scanner_max_results=req.scanner_max_results,
                scanner_universe_scope=req.scanner_universe_scope,
                scanner_max_runtime_seconds=req.scanner_max_runtime_seconds,
            )
        )
        cohort = CandidateCohort(
            id=str(uuid4()),
            name=req.name.strip() or f"cohort-{date.today().isoformat()}",
            start_date=discovery.run.date,
            market=req.market,
            analysis_window=req.duration,
            selected_categories=req.categories,
            top_n_per_category=req.top_n_per_category,
            status=CandidateCohortStatus.ACTIVE,
            notes=req.notes.strip(),
        )
        cohorts = self._read_cohorts()
        cohorts.append(cohort)
        self._save_cohorts(cohorts)
        self._append_pipeline_event(
            step_name="cohort_created",
            status="success",
            cohort_id=cohort.id,
            cohort_name=cohort.name,
            message=f"action=create symbols={len(discovery.symbol_results)}",
        )

        cohort_candidates = self._read_cohort_candidates()
        for row in discovery.symbol_results:
            cohort_candidates.append(
                CohortCandidate(
                    cohort_id=cohort.id,
                    symbol=row.symbol,
                    market=row.market,
                    selected_at=datetime.now(UTC),
                    selected_price=row.price_at_selection,
                    selected_rank=row.merged_rank,
                    selected_score=row.score,
                    selected_base_score=row.base_score,
                    selected_category_boost=row.category_boost,
                    selected_final_score_raw=row.final_score_raw,
                    selected_final_score_capped=row.final_score_capped,
                    selected_categories=[x.value if hasattr(x, "value") else x for x in row.category_tags],
                    selected_setup_type=row.setup_type,
                    selected_candidate_type=row.candidate_type,
                    selected_entry_readiness=row.entry_readiness,
                    selected_blocked_by=row.blocked_by,
                    selected_readiness_explanation=row.readiness_explanation,
                    selected_trend_state=row.trend,
                    selected_score_dynamics=str(row.structure_snapshot.get("score_dynamics_state")) if row.structure_snapshot.get("score_dynamics_state") is not None else None,
                    selected_reason=row.why_selected,
                    selected_main_opportunity_reason=row.main_opportunity_reason,
                    selected_main_risk_reason=row.main_risk_reason,
                    selected_confirm_entry_condition=row.confirm_entry_condition,
                    selected_invalidation_condition=row.invalidation_condition,
                    selected_structure_snapshot=row.structure_snapshot,
                    selected_risk_flags=row.risk_flags,
                    selected_data_quality_flags=row.data_quality_flags,
                    selected_data_quality_penalty=row.data_quality_penalty,
                    selected_displayed_score=row.score,
                )
            )
        self._save_cohort_candidates(cohort_candidates)
        return self.get_cohort_detail(cohort.id)

    def run_cohort_followup(self, req: CohortFollowupRequest) -> CohortFollowupResponse:
        detail = self.get_cohort_detail(req.cohort_id)
        self._append_pipeline_event(
            step_name="cohort_followup_started",
            status="running",
            cohort_id=detail.cohort.id,
            cohort_name=detail.cohort.name,
            message=f"action=followup cohort_id={detail.cohort.id} cohort_name={detail.cohort.name}",
        )
        snapshots = self._read_cohort_snapshots()
        today = date.today()
        new_snapshots: list[CohortDailySnapshot] = []
        for cand in detail.candidates:
            analysis = self.analysis_engine.analyze_combined(
                ticker=cand.symbol,
                market=cand.market.value,
                window="1y",
                strategy_mode="balanced",
            )
            close = float(analysis.chart.current_price)
            selected_price = cand.selected_price
            perf = self._forward_returns_from_selection(cand.symbol, cand.market.value, cand.selected_at.date(), selected_price)
            data_quality_flags = self._build_data_quality_flags(analysis)
            normalized_setup = self._normalize_setup_type(
                analysis,
                [x.value if hasattr(x, "value") else str(x) for x in cand.selected_categories],
                data_quality_flags,
            )
            risk_flags = self._build_risk_flags(analysis)
            classification = self._classify_candidate_type(
                analysis,
                [x.value if hasattr(x, "value") else str(x) for x in cand.selected_categories],
                risk_flags,
                data_quality_flags,
                normalized_setup,
            )
            has_min_horizon = perf.get("7d") is not None
            severe_structure_break = str(analysis.setup_interpretation.trend_state or "") in {"damaged_trend", "weakening_trend"}
            severe_gate_failure = str(analysis.entry_gate.skip_reason or "") in {"regime_filter", "location_filter"} and has_min_horizon
            if self._is_serious_data_quality(data_quality_flags):
                validity_state = "needs_data_check"
                still_valid_candidate = None
                invalidation_reason = "data_quality_flags_detected"
            elif severe_structure_break and severe_gate_failure:
                validity_state = "invalid"
                still_valid_candidate = False
                invalidation_reason = str(analysis.entry_gate.skip_reason or "severe_structure_break")
            elif analysis.entry_gate.final_entry_decision and has_min_horizon:
                validity_state = "valid"
                still_valid_candidate = True
                invalidation_reason = None
            else:
                validity_state = "pending_validation"
                still_valid_candidate = None
                invalidation_reason = None
            snap = CohortDailySnapshot(
                cohort_id=req.cohort_id,
                symbol=cand.symbol,
                snapshot_date=today,
                current_price=close,
                current_score=float(analysis.quantedge.final_score),
                current_categories=cand.selected_categories,
                current_setup_type=normalized_setup,
                current_trend_state=analysis.setup_interpretation.trend_state,
                current_score_dynamics=analysis.entry_gate.score_dynamics_state,
                current_trigger_state=analysis.trigger.trigger_state,
                current_trigger_score=float(analysis.trigger.trigger_score),
                price_change_since_selection=((close / selected_price - 1.0) * 100.0) if selected_price and selected_price > 0 else None,
                return_since_selection=((close / selected_price - 1.0) * 100.0) if selected_price and selected_price > 0 else None,
                return_1d=perf.get("1d"),
                return_3d=perf.get("3d"),
                return_7d=perf.get("7d"),
                return_14d=perf.get("14d"),
                return_28d=perf.get("28d"),
                max_runup_since_selection=perf.get("max_runup"),
                max_drawdown_since_selection=perf.get("max_drawdown"),
                still_valid_candidate=still_valid_candidate,
                validity_state=validity_state,
                invalidation_reason=invalidation_reason,
                entry_readiness=classification["entry_readiness"] if validity_state != "needs_data_check" else "needs_data_check",
                blocked_by=classification["blocked_by"] if validity_state != "needs_data_check" else "data_quality",
                readiness_explanation=classification["readiness_explanation"] if validity_state != "needs_data_check" else "Metrics may be distorted by adjusted price / split / EMA inconsistency. Review data before interpreting.",
                data_quality_flags=data_quality_flags,
            )
            snapshots = [row for row in snapshots if not (row.cohort_id == req.cohort_id and row.symbol == cand.symbol and row.snapshot_date == today)]
            snapshots.append(snap)
            new_snapshots.append(snap)
        self._save_cohort_snapshots(snapshots)
        self._append_pipeline_event(
            step_name="cohort_followup_completed",
            status="success",
            cohort_id=detail.cohort.id,
            cohort_name=detail.cohort.name,
            message=f"action=followup snapshots={len(new_snapshots)}",
        )
        return CohortFollowupResponse(cohort_id=req.cohort_id, snapshot_date=today, snapshots=sorted(new_snapshots, key=lambda row: row.symbol))

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
        cohort_id: str | None = None,
        cohort_name: str | None = None,
        symbol: str | None = None,
        provider: str | None = None,
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
            cohort_id=cohort_id,
            cohort_name=cohort_name,
            symbol=symbol,
            provider=provider,
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
            base_score = float(row.base_score if row.base_score > 0 else row.score)
            final_score_raw = base_score + boost
            final_score_capped = min(100.0, final_score_raw)
            displayed_score = max(0.0, min(100.0, final_score_capped + float(getattr(row, "data_quality_penalty", 0.0))))
            boosted_rows.append(
                row.model_copy(
                    update={
                        "score": displayed_score,
                        "priority_boost": boost,
                        "category_boost": boost,
                        "final_score_raw": final_score_raw,
                        "final_score_capped": final_score_capped,
                        "multi_category": category_count > 1,
                    }
                )
            )
        ranked = sorted(boosted_rows, key=lambda r: (r.score, r.final_score_raw, len(r.category_tags), r.base_score), reverse=True)[: req.max_candidates]
        ranked = [
            row.model_copy(update={"merged_rank": idx + 1})
            for idx, row in enumerate(ranked)
        ]

        runs = self._read_runs()
        previous_detail: DailyRunDetail | None = None
        if runs:
            try:
                previous_detail = self._get_run_detail(runs[-1].id)
            except FileNotFoundError:
                previous_detail = None

        ranked = self._apply_daily_change_tracking(ranked, previous_detail)

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

    def _build_data_quality_flags(self, analysis: Any) -> list[str]:
        flags: list[str] = []
        location = analysis.location
        summary = analysis.indicator_summary if isinstance(analysis.indicator_summary, dict) else {}
        close = float(summary.get("close", analysis.chart.current_price) or 0.0)
        ema20 = float(summary.get("ema_20", 0.0) or 0.0)
        ema50 = float(summary.get("ema_50", 0.0) or 0.0)
        ema100 = float(summary.get("ema_100", 0.0) or 0.0)
        ema200 = float(summary.get("ema_200", 0.0) or 0.0)
        if abs(float(location.distance_to_ema200_pct)) >= 80:
            flags.append("price_vs_ema200_unusually_high")
        if close <= 0 or min(ema20, ema50, ema100, ema200) <= 0:
            flags.append("non_positive_price_or_ema")
        if ema200 > 0 and abs((ema20 - ema200) / ema200) * 100.0 >= 90:
            flags.append("ema_spread_unusually_wide")
        if close > 0 and ema200 > 0 and abs((close - ema200) / ema200) * 100.0 >= 120:
            flags.append("possible_split_or_unadjusted_price_jump")
        if analysis.setup_interpretation.trend_state == "bullish_trend" and not (ema20 >= ema50 >= ema100 >= ema200):
            flags.append("ema_stack_inconsistent_with_bullish_trend")
        return sorted(set(flags))

    @staticmethod
    def _data_quality_penalty(flags: list[str]) -> float:
        severe = {"possible_split_or_unadjusted_price_jump", "non_positive_price_or_ema"}
        medium = {"price_vs_ema200_unusually_high", "ema_spread_unusually_wide", "ema_stack_inconsistent_with_bullish_trend"}
        penalty = 0.0
        for flag in flags:
            if flag in severe:
                penalty -= 12.0
            elif flag in medium:
                penalty -= 6.0
        return penalty

    @staticmethod
    def _is_serious_data_quality(flags: list[str]) -> bool:
        serious = {"possible_split_or_unadjusted_price_jump", "non_positive_price_or_ema"}
        return any(flag in serious for flag in flags)

    @staticmethod
    def _map_blocked_by(skip_reason: str, risk_flags: list[str], data_quality_flags: list[str], analysis: Any) -> str:
        if data_quality_flags:
            return "data_quality"
        mapping = {
            "trigger_filter": "trigger_missing",
            "resistance_room_filter": "resistance_room",
            "location_filter": "location_filter",
            "regime_filter": "regime_filter",
            "score_threshold": "score_threshold",
            "weak_volume_confirmation": "weak_volume",
            "overextended": "overextended",
        }
        if skip_reason in mapping:
            return mapping[skip_reason]
        if analysis.location.overextended_flag:
            return "overextended"
        lowered_risks = {x.lower() for x in risk_flags}
        if "weak_volume_confirmation" in lowered_risks:
            return "weak_volume"
        if "resistance_room_filter" in lowered_risks:
            return "resistance_room"
        return "none"

    @staticmethod
    def _normalize_setup_type(analysis: Any, category_tags: list[str], data_quality_flags: list[str]) -> str:
        setup = str(analysis.setup_interpretation.setup_type or "").strip() or "trend_watch"
        trend_state = str(analysis.setup_interpretation.trend_state or "")
        extension_state = str(analysis.setup_interpretation.extension_state or "")
        dist_ema200 = abs(float(analysis.location.distance_to_ema200_pct))
        support_distance = float(analysis.location.support_distance_pct)
        trigger_score = float(analysis.trigger.trigger_score)
        trigger_threshold = float(analysis.analysis_config.trigger_filter.min_trigger_score)
        trigger_state = str(analysis.trigger.trigger_state or "").lower()
        lower_cats = {str(x).lower() for x in category_tags}
        if data_quality_flags:
            return "data_quality_watch"
        if extension_state == "overextended" or dist_ema200 >= 18:
            if trigger_state == "confirmed" and trigger_score >= trigger_threshold:
                return "overextended_momentum_watch"
            return "momentum_watch"
        if trend_state == "bullish_trend" and support_distance > 6.0:
            return "momentum_watch"
        if "value_rebuild" in lower_cats and float(analysis.location.distance_to_ema200_pct) <= 3.0:
            return "value_rebuild_watch"
        if setup == "second_attempt_breakout":
            has_evidence = (
                bool(getattr(analysis.setup_interpretation, "prior_breakout_failed", False))
                and int(getattr(analysis.setup_interpretation, "reclaim_attempt_count", 0)) >= 1
                and int(getattr(analysis.setup_interpretation, "evidence_score", 0)) >= 2
                and getattr(analysis.setup_interpretation, "breakout_level", None) is not None
            )
            if not has_evidence:
                return "momentum_watch" if trend_state == "bullish_trend" else "trend_watch"
        return setup

    def _classify_candidate_type(
        self,
        analysis: Any,
        category_tags: list[str],
        risk_flags: list[str],
        data_quality_flags: list[str],
        setup_type: str,
    ) -> dict[str, str]:
        trigger_state = str(analysis.trigger.trigger_state or "unknown").lower()
        trigger_score = float(analysis.trigger.trigger_score)
        min_trigger = float(analysis.analysis_config.trigger_filter.min_trigger_score)
        skip_reason = str(analysis.entry_gate.skip_reason or "")
        blocked_by = self._map_blocked_by(skip_reason, risk_flags, data_quality_flags, analysis)
        opportunity_reason = str(
            analysis.chartmap.opportunity_interest_reason
            or f"{setup_type} structure with {analysis.entry_gate.score_dynamics_state or 'unknown'} dynamics"
        )
        risk_reason = str(analysis.chartmap.opportunity_risk_reason or (risk_flags[0] if risk_flags else "normal_risk_profile"))
        trigger_confirmed = trigger_state == "confirmed" and trigger_score >= min_trigger
        if not trigger_confirmed:
            confirm_entry = (
                f"Needs trigger confirmation and trigger score >= {min_trigger:.1f} "
                f"(current_state={analysis.trigger.trigger_state}, current_score={trigger_score:.1f})."
            )
        elif blocked_by != "none":
            confirm_entry = f"Trigger is already confirmed. Entry still needs `{blocked_by}` to improve."
        else:
            confirm_entry = "Entry conditions are currently met."
        invalidate = skip_reason or "Invalidate if trend weakens and price loses key EMA support with no trigger confirmation."
        if data_quality_flags:
            return {
                "candidate_type": "watch_candidate",
                "entry_readiness": "needs_data_check",
                "blocked_by": "data_quality",
                "readiness_explanation": "Metrics may be distorted by adjusted price / split / EMA inconsistency. Review data before interpreting.",
                "main_opportunity_reason": opportunity_reason,
                "main_risk_reason": "Data quality flags detected; treat this candidate as needs_data_check.",
                "confirm_entry_condition": "Verify data integrity first, then reassess trigger/location conditions.",
                "invalidation_condition": "Invalidate if data remains unusable after validation.",
            }
        if analysis.entry_gate.final_entry_decision:
            return {
                "candidate_type": "entry_candidate",
                "entry_readiness": "ready",
                "blocked_by": "none",
                "readiness_explanation": "Entry conditions are currently met.",
                "main_opportunity_reason": opportunity_reason,
                "main_risk_reason": risk_reason,
                "confirm_entry_condition": (
                    "Entry conditions are currently met."
                ),
                "invalidation_condition": invalidate,
            }
        if trigger_state in {"absent", "none"} or trigger_score < min_trigger:
            return {
                "candidate_type": "watch_candidate",
                "entry_readiness": "watch",
                "blocked_by": "trigger_missing",
                "readiness_explanation": "Bullish structure is present, but there is no trigger confirmation yet.",
                "main_opportunity_reason": opportunity_reason,
                "main_risk_reason": risk_reason,
                "confirm_entry_condition": confirm_entry,
                "invalidation_condition": invalidate,
            }
        lower_risks = {r.lower() for r in risk_flags}
        lower_cats = {c.lower() for c in category_tags}
        if (
            analysis.location.overextended_flag
            or "overextended" in lower_risks
            or "overextended" in lower_cats
            or skip_reason in {"overextended", "resistance_room_filter"}
        ):
            return {
                "candidate_type": "risk_monitor",
                "entry_readiness": "risk_monitor",
                "blocked_by": "overextended" if analysis.location.overextended_flag else (blocked_by if blocked_by != "none" else "resistance_room"),
                "readiness_explanation": "Trend is strong but price is stretched or blocked by location risk. Monitor rather than treat as an entry.",
                "main_opportunity_reason": opportunity_reason,
                "main_risk_reason": risk_reason,
                "confirm_entry_condition": confirm_entry,
                "invalidation_condition": "Invalidate if overextension persists or resistance rejection continues.",
            }
        if skip_reason in {"score_threshold", "regime_filter", "location_filter", "trigger_filter"}:
            return {
                "candidate_type": "invalid_candidate",
                "entry_readiness": "blocked",
                "blocked_by": blocked_by,
                "readiness_explanation": f"Entry is blocked by `{blocked_by}` under current deterministic gates.",
                "main_opportunity_reason": opportunity_reason,
                "main_risk_reason": risk_reason,
                "confirm_entry_condition": confirm_entry,
                "invalidation_condition": invalidate,
            }
        return {
            "candidate_type": "watch_candidate",
            "entry_readiness": "watch",
            "blocked_by": blocked_by if blocked_by != "none" else "none",
            "readiness_explanation": "Selected for monitoring, not yet a confirmed entry setup.",
            "main_opportunity_reason": opportunity_reason,
            "main_risk_reason": risk_reason,
            "confirm_entry_condition": confirm_entry,
            "invalidation_condition": invalidate,
        }

    def _build_symbol_result(self, symbol: str, market: str, category_tags: list[str], scanner_score: float) -> SymbolResult:
        analysis = self.analysis_engine.analyze_combined(
            ticker=symbol,
            market=market,
            window="1y",
            strategy_mode="balanced",
        )
        location = analysis.location
        setup = analysis.setup_interpretation
        data_quality_flags = self._build_data_quality_flags(analysis)
        setup_type = self._normalize_setup_type(analysis, category_tags, data_quality_flags)
        base_score = max(0.0, min(100.0, float(scanner_score)))
        backtest = self.backtest_engine.run(
            symbol,
            market=market,
            window="1y",
            strategy_mode="balanced",
            score_threshold=analysis.analysis_config.score_threshold,
            warmup_bars=analysis.analysis_config.warmup_bars,
        )
        structure_snapshot = {
            "trend_state": setup.trend_state,
            "setup_type": setup_type,
            "extension_state": setup.extension_state,
            "score_dynamics_state": analysis.entry_gate.score_dynamics_state,
            "price_vs_ema20": round(location.distance_to_ema20_pct, 3),
            "price_vs_ema50": round(location.distance_to_ema50_pct, 3),
            "price_vs_ema100": round(location.distance_to_ema100_pct, 3),
            "price_vs_ema200": round(location.distance_to_ema200_pct, 3),
            "support_distance": round(location.support_distance_pct, 3),
            "resistance_room": round(location.resistance_room_pct, 3),
            "volume_ratio_20": analysis.entry_gate.volume_ratio_20,
            "trigger_state": analysis.trigger.trigger_state,
            "trigger_score": round(float(analysis.trigger.trigger_score), 2),
            "trigger_threshold": round(float(analysis.analysis_config.trigger_filter.min_trigger_score), 2),
            "prior_breakout_failed": setup.prior_breakout_failed,
            "reclaim_attempt_count": setup.reclaim_attempt_count,
            "breakout_level": setup.breakout_level,
            "evidence_score": setup.evidence_score,
        }
        risk_flags = self._build_risk_flags(analysis)
        classification = self._classify_candidate_type(analysis, category_tags, risk_flags, data_quality_flags, setup_type)
        structure_snapshot["candidate_type"] = classification["candidate_type"]
        structure_snapshot["entry_readiness"] = classification["entry_readiness"]
        structure_snapshot["blocked_by"] = classification["blocked_by"]
        structure_snapshot["readiness_explanation"] = classification["readiness_explanation"]
        why_selected = self._build_why_selected_text(
            symbol=symbol,
            category_tags=category_tags,
            setup_type=setup_type,
            candidate_type=classification["candidate_type"],
            trend_state=setup.trend_state,
            score=base_score,
            score_dynamics=analysis.entry_gate.score_dynamics_state,
            location=location,
            trigger_state=analysis.trigger.trigger_state,
            trigger_score=float(analysis.trigger.trigger_score),
            trigger_threshold=float(analysis.analysis_config.trigger_filter.min_trigger_score),
            trigger_reason=analysis.trigger.trigger_reason,
            main_risk=(risk_flags[0] if risk_flags else "normal monitoring risk"),
        )
        data_quality_penalty = self._data_quality_penalty(data_quality_flags)
        displayed_score = max(0.0, min(100.0, base_score + data_quality_penalty))

        return SymbolResult(
            symbol=symbol,
            market=analysis.market,
            category_tags=category_tags,
            base_score=base_score,
            category_boost=0.0,
            data_quality_penalty=data_quality_penalty,
            final_score_raw=base_score,
            final_score_capped=min(100.0, base_score),
            score=displayed_score,
            trend=setup.trend_state,
            ema_distances={
                "ema20": round(location.distance_to_ema20_pct, 3),
                "ema50": round(location.distance_to_ema50_pct, 3),
                "ema100": round(location.distance_to_ema100_pct, 3),
                "ema200": round(location.distance_to_ema200_pct, 3),
            },
            setup_type=setup_type,
            candidate_type=classification["candidate_type"],
            entry_readiness=classification["entry_readiness"],
            blocked_by=classification["blocked_by"],
            readiness_explanation=classification["readiness_explanation"],
            main_opportunity_reason=classification["main_opportunity_reason"],
            main_risk_reason=classification["main_risk_reason"],
            confirm_entry_condition=classification["confirm_entry_condition"],
            invalidation_condition=classification["invalidation_condition"],
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
            why_selected=why_selected,
            structure_snapshot=structure_snapshot,
            daily_change={"status": "new_candidate", "message": "New candidate"},
            risk_flags=risk_flags,
            data_quality_flags=data_quality_flags,
            price_at_selection=float(analysis.chart.current_price),
            selection_date=date.today(),
            benchmark_symbol="SPY" if market == "us" else "XU100.IS",
            return_1d=None,
            return_3d=None,
            return_7d=None,
            return_14d=None,
            max_drawdown_after_selection=None,
            max_runup_after_selection=None,
        )

    def _build_risk_flags(self, analysis: Any) -> list[str]:
        flags: list[str] = []
        if analysis.location.overextended_flag:
            flags.append("overextended")
        if analysis.entry_gate.skip_reason:
            flags.append(str(analysis.entry_gate.skip_reason))
        if analysis.setup_interpretation.trend_state in {"damaged_trend", "weakening_trend"}:
            flags.append("trend_weakening")
        if analysis.entry_gate.volume_ratio_20 is not None and analysis.entry_gate.volume_ratio_20 < 1.0:
            flags.append("weak_volume_confirmation")
        return flags or ["normal_risk_profile"]

    def _build_why_selected_text(
        self,
        *,
        symbol: str,
        category_tags: list[str],
        setup_type: str,
        candidate_type: str,
        trend_state: str,
        score: float,
        score_dynamics: str | None,
        location: Any,
        trigger_state: str,
        trigger_score: float,
        trigger_threshold: float,
        trigger_reason: str,
        main_risk: str,
    ) -> str:
        categories = " + ".join(category_tags)
        ema_structure = "above" if location.distance_to_ema200_pct >= 0 else "below"
        dynamics = score_dynamics or "unknown"
        trigger_confirmed = trigger_score >= trigger_threshold and str(trigger_state).lower() == "confirmed"
        if candidate_type == "entry_candidate":
            monitoring_note = "Entry conditions are currently met."
        elif candidate_type == "risk_monitor":
            monitoring_note = "This is not an entry candidate. Monitor risk/extension or wait for better location."
        elif trigger_confirmed:
            monitoring_note = "Trigger is confirmed, but entry is still blocked by deterministic risk filters."
        else:
            monitoring_note = "Bullish structure is present, but trigger confirmation is still missing."
        return (
            f"{symbol} selected because it appears in {categories}; setup={setup_type}; trend={trend_state}; "
            f"candidate_type={candidate_type}; score={score:.2f}; score_dynamics={dynamics}; "
            f"price is {ema_structure} EMA200 ({location.distance_to_ema200_pct:.2f}%); "
            f"trigger_state={trigger_state}; trigger_score={trigger_score:.1f}/{trigger_threshold:.1f}; "
            f"trigger={trigger_reason}; risk={main_risk}; note={monitoring_note}"
        )

    def _apply_daily_change_tracking(self, ranked: list[SymbolResult], previous_detail: DailyRunDetail | None) -> list[SymbolResult]:
        if previous_detail is None:
            return ranked
        previous_map = {row.symbol: row for row in previous_detail.symbol_results}
        updated: list[SymbolResult] = []
        for row in ranked:
            prev = previous_map.get(row.symbol)
            if prev is None:
                updated.append(
                    row.model_copy(
                        update={
                            "daily_change": {
                                "status": "new_candidate",
                                "message": "New candidate",
                            }
                        }
                    )
                )
                continue
            prev_cats = sorted([str(x) for x in prev.category_tags])
            curr_cats = sorted([str(x) for x in row.category_tags])
            added = [x for x in curr_cats if x not in prev_cats]
            removed = [x for x in prev_cats if x not in curr_cats]
            rank_change = prev.merged_rank - row.merged_rank
            prev_raw_score = prev.final_score_raw if hasattr(prev, "final_score_raw") else prev.score
            curr_raw_score = row.final_score_raw
            score_delta = curr_raw_score - prev_raw_score
            message_parts = [
                f"Rank {'improved' if rank_change > 0 else 'dropped' if rank_change < 0 else 'unchanged'} from {prev.merged_rank} to {row.merged_rank}",
                f"Score changed capped {prev.score:.2f} -> {row.score:.2f}; raw {prev_raw_score:.2f} -> {curr_raw_score:.2f} ({score_delta:+.2f})",
            ]
            if added:
                message_parts.append(f"Added tags: {', '.join(added)}")
            if removed:
                message_parts.append(f"Removed tags: {', '.join(removed)}")
            updated.append(
                row.model_copy(
                    update={
                        "daily_change": {
                            "status": "repeated_candidate",
                            "previous_rank": prev.merged_rank,
                            "current_rank": row.merged_rank,
                            "rank_change": rank_change,
                            "previous_score": prev_raw_score,
                            "current_score": curr_raw_score,
                            "score_delta": score_delta,
                            "previous_categories": prev_cats,
                            "current_categories": curr_cats,
                            "added_categories": added,
                            "removed_categories": removed,
                            "message": "; ".join(message_parts),
                        }
                    }
                )
            )
        return updated

    def _estimate_tokens(self, prompt: str, response_text: str) -> int:
        return max(1, int((len(prompt) + len(response_text)) / 4))

    @staticmethod
    def _symbol_context_response_format() -> dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "symbol_context_output",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "bull_case": {"type": "string"},
                        "bear_case": {"type": "string"},
                        "risk": {"type": "string"},
                        "context": {"type": "string"},
                        "confidence": {"type": "string"},
                    },
                    "required": ["bull_case", "bear_case", "risk", "context", "confidence"],
                },
            },
        }

    @staticmethod
    def _explain_json_error(exc: json.JSONDecodeError) -> str:
        return (
            "Model returned broken JSON text (usually an unclosed quote or malformed comma). "
            f"Raw parser error: {exc.msg} at line {exc.lineno}, column {exc.colno}."
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
        response_format: dict[str, Any] | None = None,
        max_tokens_hint: int | None = None,
    ) -> str:
        started = datetime.now(UTC)
        primary_provider = self._normalize_provider(self.settings.llm_provider)
        fallback_provider = self._normalize_provider(self.settings.llm_fallback_provider)
        primary_model = model or (self.settings.openai_model if primary_provider == "openai" else self.settings.ollama_model)
        fallback_model = self.settings.ollama_model if fallback_provider == "ollama" else self.settings.openai_model
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
                for attempt_idx in range(2):
                    try:
                        if provider_name == "openai":
                            result = self._providers["openai"].generate(
                                prompt=prompt,
                                model=provider_model,
                                timeout_seconds=timeout_seconds,
                                options={
                                    "temperature": self.settings.ollama_temperature,
                                    "num_predict": int(max_tokens_hint or self.settings.ollama_num_predict),
                                    "response_format": response_format if response_format is not None else None,
                                },
                            )
                            text, endpoint = result.raw_response, result.endpoint
                            duration_ms = result.duration_ms
                            token_estimate = result.token_estimate or self._estimate_tokens(prompt, text)
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
                                token_estimate = self._estimate_tokens(prompt, text)
                            else:
                                result = self._providers["ollama"].generate(
                                    prompt=prompt,
                                    model=provider_model,
                                    timeout_seconds=timeout_seconds,
                                    options={
                                        "temperature": self.settings.ollama_temperature,
                                        "top_p": self.settings.ollama_top_p,
                                        "repeat_penalty": self.settings.ollama_repeat_penalty,
                                        "num_predict": int(max_tokens_hint or self.settings.ollama_num_predict),
                                        "num_ctx": self.settings.ollama_num_ctx,
                                        "num_thread": self.settings.ollama_num_thread,
                                    },
                                )
                                text, endpoint = result.raw_response, result.endpoint
                                duration_ms = result.duration_ms
                                token_estimate = result.token_estimate or self._estimate_tokens(prompt, text)
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
                                token_estimate=token_estimate,
                                prompt_preview=prompt[:1200],
                                response_preview=text[:1200],
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
                        endpoint = self.settings.openai_base_url if provider_name == "openai" else self.settings.ollama_base_url
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
                                token_estimate=0,
                                prompt_preview=prompt[:1200],
                            )
                        )
                        if attempt_idx == 0:
                            continue
                        break
            raise RuntimeError(str(last_exc) if last_exc else "LLM generation failed")
        except Exception as exc:
            raise exc

    def _context_prompt(self, row: SymbolResult, short_context_mode: bool) -> str:
        if short_context_mode:
            return (
                "Return ONLY valid JSON. No markdown. No investment advice. Keep each field <=20 words.\n"
                "Fields:\n"
                "{\n"
                '  "bull_case": "...",\n'
                '  "bear_case": "...",\n'
                '  "risk": "...",\n'
                '  "context": "...",\n'
                '  "confidence": "..."\n'
                "}\n\n"
                "Input:\n"
                f"symbol={row.symbol}\n"
                f"category={','.join([tag.value if hasattr(tag, 'value') else str(tag) for tag in row.category_tags])}\n"
                f"score={row.score:.2f}\n"
                f"score_breakdown=base:{row.base_score:.2f},boost:{row.category_boost:.2f},dq:{row.data_quality_penalty:.2f},raw:{row.final_score_raw:.2f},capped:{row.final_score_capped:.2f},displayed:{row.score:.2f}\n"
                f"trend={row.trend}\n"
                f"setup_type={row.setup_type}\n"
                f"candidate_type={row.candidate_type}\n"
                f"entry_readiness={row.entry_readiness}\n"
                f"blocked_by={row.blocked_by}\n"
                f"readiness_explanation={row.readiness_explanation}\n"
                f"risk_flags={','.join(row.risk_flags)}\n"
                f"data_quality_flags={','.join(row.data_quality_flags)}\n"
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
                response_format=self._symbol_context_response_format() if short_context_mode else None,
                max_tokens_hint=220 if short_context_mode else None,
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
                        try:
                            parsed_json = json.loads(raw[left : right + 1])
                        except json.JSONDecodeError as exc:
                            raise RuntimeError(self._explain_json_error(exc)) from exc
                    else:
                        exc = json.JSONDecodeError("No JSON object found in model output", raw, 0)
                        raise RuntimeError(self._explain_json_error(exc)) from exc
                bull = str(parsed_json.get("bull_case", "")).strip()
                bear = str(parsed_json.get("bear_case", "")).strip()
                risks = str(parsed_json.get("risk", parsed_json.get("risks", ""))).strip()
                summary = str(parsed_json.get("context", parsed_json.get("summary", ""))).strip()
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
                    endpoint="-",
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
                run_id=run_id,
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
                run_id=run_id,
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
            failed_symbols=sorted([row.symbol for row in contexts if row.status != "generated"]),
        )

    def generate_cohort_symbol_contexts(self, req: CohortSymbolContextRequest) -> SymbolContextBatchResponse:
        detail = self.get_cohort_detail(req.cohort_id)
        self._append_pipeline_event(
            step_name="cohort_symbol_context_batch_started",
            status="running",
            cohort_id=detail.cohort.id,
            cohort_name=detail.cohort.name,
            provider=self._normalize_provider(self.settings.llm_provider),
            message=f"action=contexts cohort_id={detail.cohort.id} symbols_limit={req.context_symbol_limit}",
        )
        candidates = detail.candidates
        if req.symbols:
            selected = {s.upper() for s in req.symbols}
            candidates = [row for row in candidates if row.symbol.upper() in selected]
        candidates = candidates[: req.context_symbol_limit]
        contexts: list[SymbolContext] = []
        workers = 1 if req.sequential_mode else req.max_concurrency
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = []
            for cand in candidates:
                symbol_result = SymbolResult(
                    symbol=cand.symbol,
                    market=cand.market,
                    category_tags=cand.selected_categories,
                    score_by_category={},
                    merged_rank=cand.selected_rank,
                    multi_category=len(cand.selected_categories) > 1,
                    priority_boost=0.0,
                    base_score=cand.selected_base_score,
                    category_boost=cand.selected_category_boost,
                    data_quality_penalty=cand.selected_data_quality_penalty,
                    final_score_raw=cand.selected_final_score_raw,
                    final_score_capped=cand.selected_final_score_capped,
                    score=cand.selected_displayed_score if cand.selected_displayed_score else cand.selected_score,
                    trend=cand.selected_trend_state,
                    ema_distances={},
                    setup_type=cand.selected_setup_type,
                    candidate_type=cand.selected_candidate_type,
                    entry_readiness=cand.selected_entry_readiness,
                    blocked_by=cand.selected_blocked_by,
                    readiness_explanation=cand.selected_readiness_explanation,
                    main_opportunity_reason=cand.selected_main_opportunity_reason,
                    main_risk_reason=cand.selected_main_risk_reason,
                    confirm_entry_condition=cand.selected_confirm_entry_condition,
                    invalidation_condition=cand.selected_invalidation_condition,
                    why_selected=cand.selected_reason,
                    structure_snapshot=cand.selected_structure_snapshot,
                    risk_flags=cand.selected_risk_flags,
                    data_quality_flags=cand.selected_data_quality_flags,
                )
                futures.append(
                    executor.submit(
                        self._generate_single_symbol_context,
                        symbol_result,
                        model=req.model,
                        timeout_seconds=req.timeout_seconds,
                        short_context_mode=req.short_context_mode,
                        run_id=req.cohort_id,
                        debug_stream=req.debug_stream,
                    )
                )
            for future, cand in zip(futures, candidates):
                try:
                    row = future.result()
                except Exception as exc:  # pragma: no cover
                    row = SymbolContext(
                        symbol=cand.symbol,
                        run_id=None,
                        cohort_id=req.cohort_id,
                        selected_at=cand.selected_at,
                        date=date.today(),
                        bull_case="",
                        bear_case="",
                        risks="",
                        summary="",
                        model=req.model,
                        status="failed",
                        error=str(exc),
                    )
                row = row.model_copy(update={"cohort_id": req.cohort_id, "selected_at": cand.selected_at, "run_id": None})
                contexts.append(row)
                stored = self._read_contexts()
                stored.append(row)
                self._save_contexts(stored)
        failed = sum(1 for row in contexts if row.status != "generated")
        self._append_pipeline_event(
            step_name="cohort_symbol_context_batch_completed",
            status="success" if failed < len(contexts) else "failed",
            cohort_id=detail.cohort.id,
            cohort_name=detail.cohort.name,
            provider=self._normalize_provider(self.settings.llm_provider),
            message=f"action=contexts generated={len(contexts)-failed} failed={failed}",
            error_message=None if failed < len(contexts) else "all cohort symbol contexts failed",
        )
        return SymbolContextBatchResponse(
            run_id=req.cohort_id,
            generated=len(contexts) - failed,
            failed=failed,
            contexts=sorted(contexts, key=lambda row: row.symbol),
            failed_symbols=sorted([row.symbol for row in contexts if row.status != "generated"]),
        )

    def generate_cohort_briefing(self, req: CohortBriefingRequest) -> DailyBriefing:
        detail = self.get_cohort_detail(req.cohort_id)
        self._append_pipeline_event(
            step_name="cohort_briefing_started",
            status="running",
            cohort_id=detail.cohort.id,
            cohort_name=detail.cohort.name,
            provider=self._normalize_provider(self.settings.llm_provider),
            message=f"action=briefing cohort_id={detail.cohort.id}",
        )
        by_symbol = {row.symbol: row for row in self._read_contexts() if row.cohort_id == req.cohort_id and row.status == "generated"}
        if not by_symbol:
            self._append_pipeline_event(
                step_name="cohort_briefing_completed",
                status="failed",
                cohort_id=detail.cohort.id,
                cohort_name=detail.cohort.name,
                provider=self._normalize_provider(self.settings.llm_provider),
                error_message="no generated cohort symbol contexts",
            )
            return DailyBriefing(
                date=date.today(),
                cohort_id=req.cohort_id,
                summary_text="Cohort briefing skipped: no generated cohort symbol contexts.",
                model=req.model,
                status="failed",
                error="no generated symbol contexts for cohort_id",
            )
        prompt_parts = [
            "Use deterministic facts only. No buy/sell advice. Keep concise.",
            "Sections: Top opportunities, Key risks, Notable cohort changes.",
        ]
        for cand in detail.candidates:
            ctx = by_symbol.get(cand.symbol)
            if not ctx:
                continue
            latest = [s for s in detail.snapshots if s.symbol == cand.symbol]
            snap = latest[-1] if latest else None
            validity = (
                snap.validity_state
                if snap and snap.validity_state
                else ("valid" if snap and snap.still_valid_candidate is True else "invalid" if snap and snap.still_valid_candidate is False else "pending_validation")
            )
            prompt_parts.append(
                f"- {cand.symbol} | why_selected={cand.selected_reason} | setup={cand.selected_setup_type} | "
                f"score={cand.selected_score:.2f} | followup_7d={snap.return_7d if snap else 'pending'} | "
                f"candidate_type={cand.selected_candidate_type} | entry_readiness={cand.selected_entry_readiness} | "
                f"validity={validity} | risks={','.join(cand.selected_risk_flags)} | "
                f"llm_summary={ctx.summary}"
            )
        text = self._ollama_generate(prompt="\n".join(prompt_parts), model=req.model, timeout_seconds=req.timeout_seconds, call_type="cohort_briefing")
        briefing = DailyBriefing(date=date.today(), cohort_id=req.cohort_id, summary_text=text, model=req.model, status="generated")
        rows = self._read_briefings()
        rows.append(briefing)
        self._save_briefings(rows)
        self._append_pipeline_event(
            step_name="cohort_briefing_completed",
            status="success",
            cohort_id=detail.cohort.id,
            cohort_name=detail.cohort.name,
            provider=self._normalize_provider(self.settings.llm_provider),
            message="action=briefing generated",
        )
        return briefing

    def generate_daily_briefing(self, req: DailyBriefingRequest) -> DailyBriefing:
        briefing_started = datetime.now(UTC)
        self._append_pipeline_event(
            step_name="daily_briefing_started",
            status="running",
            run_id=req.run_id,
            message=f"model={req.model} timeout={req.timeout_seconds}s",
        )
        detail = self._get_run_detail(req.run_id)
        by_symbol = {row.symbol: row for row in self._read_contexts() if row.run_id == req.run_id and row.status == "generated"}
        top_rows = sorted(detail.symbol_results, key=lambda row: row.score, reverse=True)[:10]
        rows_with_context = [row for row in top_rows if row.symbol in by_symbol]
        if not rows_with_context:
            self._append_pipeline_event(
                step_name="daily_briefing_completed",
                status="failed",
                run_id=req.run_id,
                duration_ms=int((datetime.now(UTC) - briefing_started).total_seconds() * 1000),
                error_message="no generated symbol contexts for this run_id",
            )
            briefing = DailyBriefing(
                date=detail.run.date,
                summary_text="Daily briefing skipped: no generated symbol contexts for this run.",
                model=req.model,
                status="failed",
                error="no generated symbol contexts for run_id",
            )
            rows = self._read_briefings()
            rows.append(briefing)
            self._save_briefings(rows)
            return briefing
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
        for row in rows_with_context:
            ctx = by_symbol.get(row.symbol)
            summary = ctx.summary if ctx else "No LLM context available."
            daily_change = row.daily_change.get("message", "No previous run comparison")
            structure = row.structure_snapshot
            prompt_parts.append(
                f"- {row.symbol} | category={','.join([str(tag) for tag in row.category_tags])} | "
                f"score={row.score:.2f} | score_breakdown=base:{row.base_score:.2f},boost:{row.category_boost:.2f},dq:{row.data_quality_penalty:.2f},raw:{row.final_score_raw:.2f},capped:{row.final_score_capped:.2f} | "
                f"setup={row.setup_type} | candidate_type={row.candidate_type} | entry_readiness={row.entry_readiness} | why_selected={row.why_selected} | "
                f"structure_snapshot={json.dumps(structure)} | daily_change={daily_change} | "
                f"risk_flags={','.join(row.risk_flags)} | data_quality_flags={','.join(row.data_quality_flags)} | llm_summary={summary}"
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
            self._append_pipeline_event(
                step_name="daily_briefing_completed",
                status="success",
                run_id=req.run_id,
                duration_ms=int((datetime.now(UTC) - briefing_started).total_seconds() * 1000),
                message=f"symbols_used={len(rows_with_context)}",
            )
        except (TimeoutError, URLError, RuntimeError, OSError, ValueError) as exc:
            briefing = DailyBriefing(
                date=detail.run.date,
                summary_text="Daily briefing generation failed.",
                model=req.model,
                status="failed",
                error=str(exc),
            )
            self._append_pipeline_event(
                step_name="daily_briefing_completed",
                status="failed",
                run_id=req.run_id,
                duration_ms=int((datetime.now(UTC) - briefing_started).total_seconds() * 1000),
                error_message=str(exc),
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
        readiness = self._compute_review_readiness()
        deterministic_stats = self._compute_deterministic_review_stats(result_rows)
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

        if not readiness.ready_for_28_day_review:
            review = SystemReview(
                id=str(uuid4()),
                period=f"last_{req.days}d",
                findings=(
                    f"Review needs more historical runs. Current history: {readiness.unique_days} days. "
                    "Target: 28 days."
                ),
                mistakes="Insufficient history for full confidence review.",
                missed_patterns="Pending until more runs are collected.",
                recommendations=(
                    f"Continue daily runs. Days until 28-day review: {readiness.days_until_28_day_review}. "
                    f"Deterministic stats so far: best_7d={deterministic_stats.best_category_by_7d}, "
                    f"worst_7d={deterministic_stats.worst_category_by_7d}."
                ),
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
            f"Deterministic stats: {json.dumps(deterministic_stats.model_dump(mode='json'))}\n"
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
            if len(close) < 15:
                return {"1d": None, "3d": None, "7d": None, "14d": None}
            return {
                "1d": float((close.iloc[-1] / close.iloc[-2] - 1.0) * 100),
                "3d": float((close.iloc[-1] / close.iloc[-4] - 1.0) * 100),
                "7d": float((close.iloc[-1] / close.iloc[-8] - 1.0) * 100),
                "14d": float((close.iloc[-1] / close.iloc[-15] - 1.0) * 100),
            }
        except Exception:
            return {"1d": None, "3d": None, "7d": None, "14d": None}

    def _forward_returns_from_selection(
        self,
        symbol: str,
        market: str,
        selection_date: date,
        selected_price: float | None,
    ) -> dict[str, float | None]:
        try:
            bundle = self.analysis_engine.data_service.get_market_data(symbol, market=market, period="1y")
            close = bundle.daily["close"].dropna().astype(float)
            if close.empty:
                return {"1d": None, "3d": None, "7d": None, "14d": None, "28d": None, "max_runup": None, "max_drawdown": None}
            if selected_price is None or selected_price <= 0:
                selected_price = float(close.iloc[0])
            from_idx = 0
            for idx, ts in enumerate(close.index):
                if ts.date() >= selection_date:
                    from_idx = idx
                    break
            series = close.iloc[from_idx:]
            if series.empty:
                return {"1d": None, "3d": None, "7d": None, "14d": None, "28d": None, "max_runup": None, "max_drawdown": None}
            def ret_at(days: int) -> float | None:
                if len(series) <= days:
                    return None
                return float((series.iloc[days] / selected_price - 1.0) * 100.0)
            runup = float((series.max() / selected_price - 1.0) * 100.0)
            drawdown = float((series.min() / selected_price - 1.0) * 100.0)
            return {
                "1d": ret_at(1),
                "3d": ret_at(3),
                "7d": ret_at(7),
                "14d": ret_at(14),
                "28d": ret_at(28),
                "max_runup": runup,
                "max_drawdown": drawdown,
            }
        except Exception:
            return {"1d": None, "3d": None, "7d": None, "14d": None, "28d": None, "max_runup": None, "max_drawdown": None}

    def run_cohort_review(self, req: CohortReviewRequest) -> CohortReviewResponse:
        cohorts = self._read_cohorts()
        cohort_by_id = {row.id: row for row in cohorts}
        if req.cohort_id not in cohort_by_id:
            raise FileNotFoundError(f"Cohort not found: {req.cohort_id}")
        target_ids = [req.cohort_id]
        candidate_rows = [row for row in self._read_cohort_candidates() if row.cohort_id in target_ids]
        snapshot_rows = [row for row in self._read_cohort_snapshots() if row.cohort_id in target_ids]
        unique_days = len({row.snapshot_date for row in snapshot_rows})
        days_remaining = max(0, req.days_required - unique_days)
        sufficient_window = days_remaining == 0
        readiness = (
            f"Review ready. History: {unique_days}/{req.days_required} days."
            if sufficient_window
            else f"Review needs more history: {unique_days}/{req.days_required} days."
        )
        by_symbol_snapshots: dict[str, list[CohortDailySnapshot]] = {}
        for row in sorted(snapshot_rows, key=lambda x: (x.snapshot_date, x.symbol)):
            by_symbol_snapshots.setdefault(f"{row.cohort_id}|{row.symbol}", []).append(row)
        returns_by_cat: dict[str, list[float]] = {}
        score_ret_pairs: list[tuple[float, float]] = []
        false_positives = 0
        missed_follow = 0
        stayed_valid = 0
        invalidated_quickly = 0
        pending_validation_count = 0
        needs_data_check_count = 0
        pending_horizon_count = 0
        ret1d_vals: list[float] = []
        best_symbol = None
        worst_symbol = None
        best_ret = -9999.0
        worst_ret = 9999.0
        multi_cat_returns: list[float] = []
        for cand in candidate_rows:
            symbol_snaps = by_symbol_snapshots.get(f"{cand.cohort_id}|{cand.symbol}", [])
            latest = symbol_snaps[-1] if symbol_snaps else None
            ret7 = latest.return_7d if latest else None
            if latest and latest.return_1d is not None:
                ret1d_vals.append(float(latest.return_1d))
            validity_state = "pending_validation"
            if latest:
                if getattr(latest, "validity_state", None):
                    validity_state = str(latest.validity_state)
                elif latest.still_valid_candidate is True:
                    validity_state = "valid"
                elif latest.still_valid_candidate is False:
                    validity_state = "invalid"
            has_required_horizon = latest is not None and latest.return_7d is not None
            if not has_required_horizon:
                pending_horizon_count += 1
            if ret7 is not None:
                for cat in cand.selected_categories:
                    key = cat.value if hasattr(cat, "value") else str(cat)
                    returns_by_cat.setdefault(key, []).append(float(ret7))
                score_ret_pairs.append((cand.selected_score, float(ret7)))
                if len(cand.selected_categories) > 1:
                    multi_cat_returns.append(float(ret7))
                if ret7 > best_ret:
                    best_ret, best_symbol = ret7, cand.symbol
                if ret7 < worst_ret:
                    worst_ret, worst_symbol = ret7, cand.symbol
            if validity_state == "pending_validation":
                pending_validation_count += 1
            if validity_state == "needs_data_check":
                needs_data_check_count += 1
            if sufficient_window and validity_state == "invalid" and latest and latest.return_7d is not None and latest.return_7d < 0:
                false_positives += 1
            if validity_state == "valid":
                stayed_valid += 1
            if sufficient_window and validity_state == "invalid" and symbol_snaps:
                invalid_snap = next((snap for snap in symbol_snaps if (getattr(snap, "validity_state", None) == "invalid" or snap.still_valid_candidate is False)), None)
                cohort_start = cohort_by_id.get(cand.cohort_id).start_date if cand.cohort_id in cohort_by_id else cand.selected_at.date()
                if invalid_snap is not None and (invalid_snap.snapshot_date - cohort_start).days <= 3:
                    invalidated_quickly += 1
            if latest and latest.return_7d is not None and latest.return_7d < -3:
                missed_follow += 1
        avg_by_cat = {k: round(sum(v) / len(v), 3) for k, v in returns_by_cat.items() if v}
        best_cat = max(avg_by_cat, key=avg_by_cat.get) if avg_by_cat else None
        worst_cat = min(avg_by_cat, key=avg_by_cat.get) if avg_by_cat else None
        note = "insufficient data"
        if score_ret_pairs:
            up = sum(1 for score, ret in score_ret_pairs if score >= 75 and ret > 0)
            down = len(score_ret_pairs) - up
            note = f"high-score positive-follow-through={up}, otherwise={down}"
        if not sufficient_window:
            note = (
                f"insufficient data: {unique_days}/{req.days_required} days collected. "
                "False-positive and quick-invalidation stats are deferred."
            )
            false_positives = 0
            invalidated_quickly = 0
            missed_follow = 0
        stats = CohortReviewStats(
            average_return_by_category=avg_by_cat,
            best_candidate=best_symbol,
            worst_candidate=worst_symbol,
            best_category=best_cat,
            worst_category=worst_cat,
            multi_category_avg_return_7d=(round(sum(multi_cat_returns) / len(multi_cat_returns), 3) if multi_cat_returns else None),
            false_positives=false_positives,
            missed_follow_through=missed_follow,
            stayed_valid=stayed_valid,
            invalidated_quickly=invalidated_quickly,
            pending_validation_count=pending_validation_count,
            needs_data_check_count=needs_data_check_count,
            snapshots_collected=len(snapshot_rows),
            pending_horizon_count=pending_horizon_count,
            early_return_1d_avg=(round(sum(ret1d_vals) / len(ret1d_vals), 3) if ret1d_vals else None),
            insufficient_data=not sufficient_window,
            score_delta_vs_return_note=note,
        )
        selected_name = cohort_by_id[req.cohort_id].name
        self._append_pipeline_event(
            step_name="cohort_review_completed",
            status="success",
            cohort_id=req.cohort_id,
            cohort_name=selected_name,
            message=f"action=review cohort_id={req.cohort_id} days={unique_days}/{req.days_required}",
        )
        return CohortReviewResponse(
            cohort_id=req.cohort_id,
            readiness_message=readiness,
            days_collected=unique_days,
            days_required=req.days_required,
            days_remaining=days_remaining,
            deterministic_stats=stats,
            llm_summary=None,
        )

    def _compute_review_readiness(self) -> ReviewReadiness:
        runs = self._read_runs()
        details = [DailyRunDetail.model_validate(row) for row in self._read_symbol_results()]
        unique_days = len({run.date for run in runs})
        symbols = {item.symbol for detail in details for item in detail.symbol_results}
        days_until = max(0, 28 - unique_days)
        ready = unique_days >= 28
        msg = (
            "Ready for 28-day review."
            if ready
            else f"Review needs more history. Current unique days: {unique_days}, target: 28."
        )
        return ReviewReadiness(
            runs_collected=len(runs),
            unique_days=unique_days,
            symbols_tracked=len(symbols),
            days_until_28_day_review=days_until,
            ready_for_28_day_review=ready,
            message=msg,
        )

    def _compute_deterministic_review_stats(self, details: list[DailyRunDetail]) -> DeterministicReviewStats:
        if not details:
            return DeterministicReviewStats()
        rows: list[dict[str, Any]] = []
        for detail in details:
            for row in detail.symbol_results:
                fwd = self._forward_returns(row.symbol, row.market.value)
                rows.append(
                    {
                        "categories": [str(x) for x in row.category_tags],
                        "setup_type": row.setup_type,
                        "score": row.score,
                        "ret7": fwd.get("7d"),
                    }
                )
        cat_vals: dict[str, list[float]] = {}
        setup_vals: dict[str, list[float]] = {}
        repeated = 0
        seen: set[str] = set()
        strong_poor = 0
        low_strong = 0
        for row in rows:
            ret7 = row["ret7"]
            if ret7 is None:
                continue
            if row["score"] >= 80 and ret7 < 0:
                strong_poor += 1
            if row["score"] < 60 and ret7 > 0:
                low_strong += 1
            setup_vals.setdefault(str(row["setup_type"]), []).append(float(ret7))
            for cat in row["categories"]:
                cat_vals.setdefault(cat, []).append(float(ret7))
            key = f"{row['setup_type']}|{','.join(sorted(row['categories']))}"
            if key in seen:
                repeated += 1
            seen.add(key)
        avg_cat = {k: (sum(v) / len(v)) for k, v in cat_vals.items() if v}
        avg_setup = {k: round(sum(v) / len(v), 3) for k, v in setup_vals.items() if v}
        best = max(avg_cat, key=avg_cat.get) if avg_cat else None
        worst = min(avg_cat, key=avg_cat.get) if avg_cat else None
        highest_false = worst
        return DeterministicReviewStats(
            best_category_by_7d=best,
            worst_category_by_7d=worst,
            highest_false_positive_group=highest_false,
            repeated_candidates=repeated,
            strong_score_poor_return=strong_poor,
            low_score_strong_return=low_strong,
            average_return_by_setup_type=avg_setup,
        )

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
        details = [DailyRunDetail.model_validate(row) for row in self._read_symbol_results()]
        cohorts = self.list_cohorts()
        cohort_details = [self.get_cohort_detail(row.id) for row in cohorts[:20]]
        return IntelligenceDashboardResponse(
            runs=sorted(runs, key=lambda row: row.timestamp, reverse=True),
            latest_run_results=latest_results,
            latest_contexts=sorted(self._slice_latest(contexts, limit=50), key=lambda row: (row.date, row.symbol), reverse=True),
            latest_briefing=briefings[-1] if briefings else None,
            latest_review=reviews[-1] if reviews else None,
            pipeline_events=sorted(self._slice_latest(self._read_pipeline_events(), limit=250), key=lambda row: row.timestamp, reverse=True),
            cohorts=cohorts,
            cohort_details=cohort_details,
            review_readiness=self._compute_review_readiness(),
            deterministic_review_stats=self._compute_deterministic_review_stats(details),
        )

    def get_run_report(self, run_id: str) -> IntelligenceRunReport:
        detail = self._get_run_detail(run_id)
        contexts = [row for row in self._read_contexts() if row.run_id == run_id]
        briefings = [row for row in self._read_briefings() if row.date == detail.run.date]
        reviews = self._read_reviews()
        approvals = [row for row in self._read_approvals() if row.run_id == run_id]
        llm_logs = [row for row in self._read_llm_logs() if (row.symbol in {x.symbol for x in detail.symbol_results} or row.call_type in {"daily_briefing", "system_review"})]
        pipeline_events = [row for row in self._read_pipeline_events() if row.run_id == run_id]
        return IntelligenceRunReport(
            run=detail.run,
            symbol_results=detail.symbol_results,
            contexts=sorted(contexts, key=lambda row: row.symbol),
            briefing=briefings[-1] if briefings else None,
            review=reviews[-1] if reviews else None,
            approval=approvals[-1] if approvals else None,
            llm_logs=sorted(llm_logs, key=lambda row: row.timestamp, reverse=True)[:300],
            pipeline_events=sorted(pipeline_events, key=lambda row: row.timestamp, reverse=True),
        )

    def approve_run_report(self, req: IntelligenceReviewApprovalRequest) -> IntelligenceReviewApproval:
        _ = self._get_run_detail(req.run_id)
        approval = IntelligenceReviewApproval(
            id=str(uuid4()),
            run_id=req.run_id,
            reviewer=req.reviewer.strip() or "operator",
            status=req.status.strip() or "approved",
            notes=req.notes.strip(),
        )
        rows = self._read_approvals()
        rows.append(approval)
        self._save_approvals(rows)
        self._append_pipeline_event(
            step_name="run_report_approval",
            status="success",
            run_id=req.run_id,
            message=f"reviewer={approval.reviewer} status={approval.status}",
        )
        return approval

    def export_run_report_markdown(self, run_id: str) -> IntelligenceRunReportExport:
        report = self.get_run_report(run_id)
        readiness = self._compute_review_readiness()
        lines: list[str] = []
        lines.append(f"# TradeGhost Intelligence Journal - {report.run.date}")
        lines.append("")
        lines.append("## 1. Run Summary")
        lines.append(f"- Run ID: `{report.run.id}`")
        lines.append(f"- Date: `{report.run.date}`")
        lines.append(f"- Categories: `{', '.join([c.value if hasattr(c, 'value') else str(c) for c in report.run.scanner_categories])}`")
        lines.append(f"- Top N per category: `{report.run.top_n_per_category}`")
        lines.append(f"- Raw candidates before merge: `{report.run.raw_candidates_before_merge}`")
        lines.append(f"- Final candidates after merge: `{report.run.final_candidates_after_merge}`")
        lines.append("")
        lines.append("## 2. Top Candidates")
        for row in report.symbol_results:
            score_formula = (
                f"{row.base_score:.2f} base + {row.category_boost:.2f} boost + {row.data_quality_penalty:.2f} data_quality_penalty = {row.score:.2f} displayed"
            )
            if row.final_score_raw > 100:
                score_formula += f" (capped {row.final_score_capped:.2f})"
            lines.append(f"### {row.merged_rank}. {row.symbol}")
            lines.append(f"- Score: `{row.score:.2f}`")
            lines.append(f"- Score Breakdown: `{score_formula}`")
            lines.append(f"- Categories: `{', '.join([str(x) for x in row.category_tags])}`")
            lines.append(f"- Setup Type: `{row.setup_type}`")
            lines.append(f"- Candidate Type: `{row.candidate_type}`")
            lines.append(f"- Entry Readiness: `{row.entry_readiness}`")
            lines.append(f"- Blocked By: `{row.blocked_by}`")
            lines.append(f"- Readiness Explanation: {row.readiness_explanation or '-'}")
            lines.append(f"- Main Opportunity Reason: {row.main_opportunity_reason or '-'}")
            lines.append(f"- Main Risk: {row.main_risk_reason or '-'}")
            lines.append(f"- What Confirms Entry: {row.confirm_entry_condition or '-'}")
            lines.append(f"- What Invalidates Candidate: {row.invalidation_condition or '-'}")
            lines.append(f"- Data Quality Flags: `{', '.join(row.data_quality_flags) if row.data_quality_flags else '-'}`")
            lines.append(f"- Why Selected: {row.why_selected}")
            lines.append(f"- Structure Snapshot: `{json.dumps(row.structure_snapshot, default=str)}`")
            lines.append(f"- Daily Change: `{json.dumps(row.daily_change, default=str)}`")
            lines.append(f"- Risk Flags: `{', '.join(row.risk_flags)}`")
            lines.append(f"- Forward Performance: 1D={row.return_1d if row.return_1d is not None else 'pending'}, 3D={row.return_3d if row.return_3d is not None else 'pending'}, 7D={row.return_7d if row.return_7d is not None else 'pending'}, 14D={row.return_14d if row.return_14d is not None else 'pending'}")
            lines.append("")
        lines.append("")
        lines.append("## 3. LLM Context")
        if not report.contexts:
            lines.append("- No symbol contexts.")
        for ctx in report.contexts:
            lines.append(f"### {ctx.symbol} ({ctx.status})")
            lines.append(f"- Bull case: {ctx.bull_case or '-'}")
            lines.append(f"- Bear case: {ctx.bear_case or '-'}")
            lines.append(f"- Risks: {ctx.risks or '-'}")
            lines.append(f"- Summary: {ctx.summary or ctx.error or '-'}")
        lines.append("")
        lines.append("## 4. Daily Briefing")
        lines.append(report.briefing.summary_text if report.briefing else "No briefing.")
        lines.append("")
        lines.append("## 5. Forward Performance")
        lines.append("- Captured fields: `price_at_selection`, `selection_date`, `return_1d`, `return_3d`, `return_7d`, `return_14d`, `max_drawdown_after_selection`, `max_runup_after_selection`.")
        lines.append("- Pending values remain `pending` until enough post-selection bars are available.")
        lines.append("")
        lines.append("## 6. Review Readiness")
        lines.append(f"- Runs collected: `{readiness.runs_collected}`")
        lines.append(f"- Unique days: `{readiness.unique_days}`")
        lines.append(f"- Symbols tracked: `{readiness.symbols_tracked}`")
        lines.append(f"- Days until 28-day review: `{readiness.days_until_28_day_review}`")
        lines.append(f"- Status: `{readiness.message}`")
        lines.append("")
        lines.append("## System Review")
        if report.review:
            lines.append(f"- Findings: {report.review.findings}")
            lines.append(f"- Mistakes: {report.review.mistakes}")
            lines.append(f"- Missed Patterns: {report.review.missed_patterns}")
            lines.append(f"- Recommendations: {report.review.recommendations}")
        else:
            lines.append("No review.")
        lines.append("")
        lines.append("## Approval")
        if report.approval:
            lines.append(f"- Status: `{report.approval.status}`")
            lines.append(f"- Reviewer: `{report.approval.reviewer}`")
            lines.append(f"- Notes: {report.approval.notes or '-'}")
            lines.append(f"- Time: `{report.approval.created_at.isoformat()}`")
        else:
            lines.append("- Not approved yet.")
        markdown = "\n".join(lines).strip() + "\n"
        return IntelligenceRunReportExport(
            run_id=run_id,
            filename=f"tradeghost-intelligence-report-{report.run.date}-{run_id[:8]}.md",
            report_mode="daily_run",
            markdown=markdown,
        )

    def _build_versioned_cohort_export_filename(
        self,
        *,
        cohort_name: str,
        cohort_id: str,
        report_mode: CohortReportMode,
        export_dt: datetime,
    ) -> str:
        slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in cohort_name.strip()).strip("-")
        slug = slug or cohort_id[:8].lower()
        short_id = cohort_id[:8].lower()
        mode = report_mode.value
        ts = export_dt.strftime("%Y-%m-%d-%H%M")
        base = f"tradeghost-cohort-{slug}-{short_id}-{mode}-{ts}"
        export_dir = self.base_dir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        existing = sorted(export_dir.glob(f"{base}*.md"))
        if not existing:
            return f"{base}.md"
        return f"{base}-v{len(existing) + 1}.md"

    def export_cohort_report_markdown(
        self,
        cohort_id: str,
        report_mode: CohortReportMode = CohortReportMode.LIFECYCLE,
    ) -> IntelligenceRunReportExport:
        detail = self.get_cohort_detail(cohort_id)
        self._append_pipeline_event(
            step_name="cohort_export_started",
            status="running",
            cohort_id=detail.cohort.id,
            cohort_name=detail.cohort.name,
            message=f"action=export mode={report_mode.value}",
        )
        review = self.run_cohort_review(CohortReviewRequest(cohort_id=cohort_id))
        latest_followup_date = max((x.snapshot_date for x in detail.snapshots), default=None)
        exported_at = datetime.now(UTC)
        filename = self._build_versioned_cohort_export_filename(
            cohort_name=detail.cohort.name,
            cohort_id=detail.cohort.id,
            report_mode=report_mode,
            export_dt=exported_at,
        )
        lines: list[str] = []
        lines.append(f"# TradeGhost Candidate Cohort Report - {detail.cohort.name}")
        lines.append("")
        lines.append(f"- report_mode: `{report_mode.value}`")
        lines.append(f"- exported_at: `{exported_at.isoformat()}`")
        lines.append(f"- cohort_id: `{detail.cohort.id}`")
        lines.append(f"- cohort_name: `{detail.cohort.name}`")
        lines.append(f"- latest_followup_date: `{latest_followup_date}`")
        lines.append(f"- candidate_count: `{len(detail.candidates)}`")
        lines.append(f"- followup_snapshot_count: `{len(detail.snapshots)}`")
        lines.append("")
        lines.append("## Initial Selection Snapshot")
        lines.append(f"- Cohort ID: `{detail.cohort.id}`")
        lines.append(f"- Start date: `{detail.cohort.start_date}`")
        lines.append(f"- Market: `{detail.cohort.market.value}`")
        lines.append(f"- Analysis window: `{detail.cohort.analysis_window.value}`")
        lines.append(f"- Categories: `{', '.join([c.value if hasattr(c, 'value') else str(c) for c in detail.cohort.selected_categories])}`")
        grouped_candidates: dict[str, list[CohortCandidate]] = {
            "ready": [],
            "watch": [],
            "risk_monitor": [],
            "needs_data_check": [],
            "pending_validation": [],
            "blocked": [],
        }
        for row in detail.candidates:
            key = row.selected_entry_readiness if row.selected_entry_readiness in grouped_candidates else "watch"
            grouped_candidates[key].append(row)
        for group_name in ["ready", "watch", "risk_monitor", "blocked", "needs_data_check", "pending_validation"]:
            if not grouped_candidates[group_name]:
                continue
            lines.append(f"### Group: {group_name}")
            for row in grouped_candidates[group_name]:
                lines.append(f"#### {row.selected_rank}. {row.symbol}")
                lines.append(f"- Original why selected: {row.selected_reason}")
                score_formula = (
                    f"{row.selected_base_score:.2f} base + {row.selected_category_boost:.2f} boost + "
                    f"{row.selected_data_quality_penalty:.2f} data_quality_penalty => {row.selected_displayed_score:.2f} displayed"
                )
                lines.append(f"- Score Breakdown: `{score_formula}`")
                lines.append(f"- Candidate Type: `{row.selected_candidate_type}`")
                lines.append(f"- Entry Readiness: `{row.selected_entry_readiness}`")
                lines.append(f"- Blocked By: `{row.selected_blocked_by}`")
                lines.append(f"- Readiness Explanation: {row.selected_readiness_explanation or '-'}")
                lines.append(f"- Main Opportunity Reason: {row.selected_main_opportunity_reason or '-'}")
                lines.append(f"- Main Risk: {row.selected_main_risk_reason or '-'}")
                lines.append(f"- What would confirm entry: {row.selected_confirm_entry_condition or '-'}")
                lines.append(f"- What would invalidate candidate: {row.selected_invalidation_condition or '-'}")
                lines.append(f"- Structure snapshot: `{json.dumps(row.selected_structure_snapshot, default=str)}`")
                lines.append(f"- Risk flags: `{', '.join(row.selected_risk_flags) if row.selected_risk_flags else '-'}`")
                lines.append(f"- Data quality flags: `{', '.join(row.selected_data_quality_flags) if row.selected_data_quality_flags else '-'}`")
            lines.append("")
        if report_mode == CohortReportMode.INITIAL:
            lines.append("## Follow-up")
            lines.append("- Not included in initial report mode.")
        else:
            lines.append("## Latest Follow-up State")
            if not detail.latest_states:
                lines.append("- No follow-up snapshots yet.")
            for state in detail.latest_states:
                lines.append(
                    f"- {state.symbol}: latest_date={state.latest_followup_date} "
                    f"return_since_selection={state.return_since_selection if state.return_since_selection is not None else 'pending'} "
                    f"1D={state.return_1d if state.return_1d is not None else 'pending'} "
                    f"3D={state.return_3d if state.return_3d is not None else 'pending'} "
                    f"7D={state.return_7d if state.return_7d is not None else 'pending'} "
                    f"14D={state.return_14d if state.return_14d is not None else 'pending'} "
                    f"28D={state.return_28d if state.return_28d is not None else 'pending'} "
                    f"validity={state.validity_state} blocked_by={state.blocked_by}"
                )
                if state.data_quality_flags:
                    lines.append(f"  - data_quality_flags={','.join(state.data_quality_flags)}")
                lines.append(f"  - readiness={state.entry_readiness}; explanation={state.readiness_explanation}")
        if report_mode == CohortReportMode.LIFECYCLE:
            lines.append("")
            lines.append("## Full Follow-up Timeline")
            if not detail.snapshots:
                lines.append("- No follow-up snapshots yet.")
            for snap in detail.snapshots:
                lines.append(
                    f"- {snap.snapshot_date} | {snap.symbol} | score={snap.current_score if snap.current_score is not None else '-'} "
                    f"| return_since_selection={snap.return_since_selection if snap.return_since_selection is not None else 'pending'} "
                    f"| validity={snap.validity_state} | blocked_by={snap.blocked_by}"
                )
        if report_mode == CohortReportMode.REVIEW_28D:
            lines.append("")
            lines.append("## 28-Day Review")
            lines.append(f"- Readiness: {review.readiness_message}")
            lines.append(f"- Deterministic stats: `{json.dumps(review.deterministic_stats.model_dump(mode='json'), default=str)}`")
            lines.append(f"- LLM summary: {review.llm_summary or 'not generated'}")
        else:
            lines.append("")
            lines.append("## Review Snapshot")
            lines.append(f"- Readiness: {review.readiness_message}")
            lines.append(f"- Deterministic stats: `{json.dumps(review.deterministic_stats.model_dump(mode='json'), default=str)}`")
        markdown = "\n".join(lines).strip() + "\n"
        export_path = self.base_dir / "exports" / filename
        export_path.write_text(markdown, encoding="utf-8")
        self._append_pipeline_event(
            step_name="cohort_export_completed",
            status="success",
            cohort_id=detail.cohort.id,
            cohort_name=detail.cohort.name,
            message=f"action=export mode={report_mode.value} file={filename}",
        )
        return IntelligenceRunReportExport(
            run_id=cohort_id,
            filename=filename,
            report_mode=report_mode.value,
            cohort_id=cohort_id,
            exported_at=exported_at,
            latest_followup_date=latest_followup_date,
            markdown=markdown,
        )

    def get_llm_logs(self, limit: int = 200) -> list[LLMDebugLog]:
        rows = self._read_llm_logs()
        return sorted(rows, key=lambda row: row.timestamp, reverse=True)[: max(1, min(limit, 500))]

    def get_llm_status(self, timeout_seconds: float = 2.0) -> LLMConnectionStatus:
        checked_at = datetime.now(UTC)
        primary_provider = self._normalize_provider(self.settings.llm_provider)
        fallback_provider = self._normalize_provider(self.settings.llm_fallback_provider)
        base_url = self.settings.openai_base_url.rstrip("/") if primary_provider == "openai" else self.settings.ollama_base_url.rstrip("/")
        installed: list[str] = []
        primary_connected = False
        fallback_connected = False
        model_available: bool | None = None
        model_used = self.settings.openai_model if primary_provider == "openai" else self.settings.ollama_model
        primary_model = self.settings.openai_model if primary_provider == "openai" else self.settings.ollama_model
        fallback_model = self.settings.openai_model if fallback_provider == "openai" else self.settings.ollama_model
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
            primary_model=primary_model,
            fallback_model=fallback_model,
            primary_connected=primary_connected,
            fallback_connected=fallback_connected,
            last_response_duration_ms=last_duration,
            last_fallback_used=last_fallback,
        )

    def test_llm_response(self, req: LLMResponseTestRequest) -> LLMResponseTestResult:
        checked_at = datetime.now(UTC)
        primary_provider = self._normalize_provider(self.settings.llm_provider)
        endpoint = self.settings.openai_base_url.rstrip("/") if primary_provider == "openai" else self.settings.ollama_base_url.rstrip("/")
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
