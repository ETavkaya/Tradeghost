from __future__ import annotations

import json
import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, timedelta
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import uuid4
from zoneinfo import ZoneInfo

from tradeghost.services.analysis_engine import AnalysisEngine
from tradeghost.services.backtest.engine import BacktestEngine
from tradeghost.services.intelligence.daily_report_store import CohortDailyReportStore
from tradeghost.services.intelligence.providers import LLMProvider, OllamaProvider, OpenAIProvider
from tradeghost.services.scanner.engine import ScannerEngine
from tradeghost.shared.config.settings import get_settings
from tradeghost.shared.market import normalize_symbol
from tradeghost.shared.models.schemas import (
    CandidateCohort,
    CandidateCohortStatus,
    CohortCandidate,
    CohortCleanupDuplicateRequest,
    CohortCleanupDuplicateResponse,
    CohortDailySnapshot,
    CohortDailyReportDetail,
    CohortDailyReportRunResponse,
    CohortDailyReportSummary,
    CohortDetail,
    CohortDeleteResponse,
    CohortDuplicateGroup,
    CohortDuplicateStrategy,
    CohortReportMode,
    CohortFollowupRequest,
    CohortFollowupSettingsRequest,
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


DAILY_REPORT_PROMPT_VERSION = "daily_cohort_followup_v1"
MARKET_CONTEXT_PROMPT_VERSION = "market_context_note_v1"
FINAL_28D_REVIEW_PROMPT_VERSION = "final_28d_cohort_review_v1"
SYMBOL_CONTEXT_PROMPT_VERSION = "symbol_context_v1"
DAILY_FOLLOWUP_JOB_NAME = "daily_cohort_followup_job"


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
        self.scheduler_logs_dir = self.settings.logs_dir / "scheduler"
        self.scheduler_logs_path = self.scheduler_logs_dir / "daily_followup.log"
        self.daily_report_store = CohortDailyReportStore(self.settings.database_url)
        self.analysis_engine = analysis_engine or AnalysisEngine()
        self.scanner_engine = scanner_engine or ScannerEngine(analysis_engine=self.analysis_engine)
        self.backtest_engine = backtest_engine or BacktestEngine(analysis_engine=self.analysis_engine)
        self._logger = logging.getLogger(__name__)
        self._llm_logs_lock = Lock()
        self._pipeline_logs_lock = Lock()
        self._daily_followup_db_warning_logged = False
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

    @staticmethod
    def _log_value(value: Any) -> str:
        text = str(value)
        return text.replace("\n", " ").replace("\r", " ")

    def _log_llm_context_event(self, event: str, **fields: Any) -> None:
        parts = [f"[LLM_CONTEXT] {event}"]
        for key, value in fields.items():
            if value is None:
                continue
            parts.append(f"{key}={self._log_value(value)}")
        self._logger.info(" ".join(parts))

    def log_daily_followup_scheduler_event(self, event: str, **fields: Any) -> None:
        status = str(fields.pop("status", "info"))
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event,
            "job_name": DAILY_FOLLOWUP_JOB_NAME,
            "status": status,
            **{key: value for key, value in fields.items() if value is not None},
        }
        try:
            self.scheduler_logs_dir.mkdir(parents=True, exist_ok=True)
            with self.scheduler_logs_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, default=str) + "\n")
        except Exception as exc:  # pragma: no cover - best effort logging path
            self._logger.warning("Failed to write scheduler log: %s", exc)

    def _read_scheduler_log_entries(self, limit: int = 500) -> list[dict[str, Any]]:
        if not self.scheduler_logs_path.exists():
            return []
        try:
            lines = self.scheduler_logs_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []
        entries: list[dict[str, Any]] = []
        for line in lines[-max(1, limit):]:
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                entries.append(parsed)
        return entries

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
        return [self._normalize_cohort_followup_defaults(CandidateCohort.model_validate(row)) for row in self._read_rows(self.cohorts_path)]

    def _save_cohorts(self, rows: list[CandidateCohort]) -> None:
        self._write_rows(self.cohorts_path, [self._normalize_cohort_followup_defaults(row).model_dump(mode="json") for row in rows])

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

    def _normalize_cohort_followup_defaults(self, cohort: CandidateCohort) -> CandidateCohort:
        updates: dict[str, Any] = {}
        if not cohort.followup_start_date:
            updates["followup_start_date"] = cohort.start_date
        if not cohort.followup_target_days or cohort.followup_target_days <= 0:
            updates["followup_target_days"] = 28
        if self._normalize_cohort_name(cohort.name) == "milestoneemre":
            updates["followup_enabled"] = True
            updates["followup_target_days"] = 28
        return cohort.model_copy(update=updates) if updates else cohort

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
                    selected_company_name=cand.selected_company_name,
                    selected_sector=cand.selected_sector,
                    selected_industry=cand.selected_industry,
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

    def update_cohort_followup_settings(self, cohort_id: str, req: CohortFollowupSettingsRequest) -> CandidateCohort:
        cohorts = self._read_cohorts()
        updated_rows: list[CandidateCohort] = []
        updated_cohort: CandidateCohort | None = None
        for row in cohorts:
            if row.id != cohort_id:
                updated_rows.append(row)
                continue
            payload = row.model_dump()
            if req.followup_enabled is not None:
                payload["followup_enabled"] = req.followup_enabled
            if req.followup_start_date is not None:
                payload["followup_start_date"] = req.followup_start_date
            if req.followup_target_days is not None:
                payload["followup_target_days"] = req.followup_target_days
            if req.followup_schedule is not None:
                payload["followup_schedule"] = req.followup_schedule.strip() or None
            if req.followup_completed is not None:
                payload["followup_completed"] = req.followup_completed
            if payload.get("followup_enabled") and payload.get("followup_completed"):
                payload["followup_completed"] = False
            updated_cohort = CandidateCohort.model_validate(payload)
            updated_rows.append(updated_cohort)
        if updated_cohort is None:
            raise FileNotFoundError(f"Cohort not found: {cohort_id}")
        self._save_cohorts(updated_rows)
        self._append_pipeline_event(
            step_name="cohort_followup_settings_updated",
            status="success",
            cohort_id=updated_cohort.id,
            cohort_name=updated_cohort.name,
            message=(
                f"enabled={str(updated_cohort.followup_enabled).lower()} "
                f"target_days={updated_cohort.followup_target_days} schedule={updated_cohort.followup_schedule or 'default'}"
            ),
        )
        return updated_cohort

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
            selected_blocked_by = row.blocked_by
            if selected_blocked_by == "none":
                selected_blocked_by = self._blocked_by_from_risk_flags(row.risk_flags, fallback="none")
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
                    selected_blocked_by=selected_blocked_by,
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
                    selected_displayed_score=(row.score if row.score is not None else row.base_score),
                    selected_company_name=row.company_name,
                    selected_sector=row.sector,
                    selected_industry=row.industry,
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
            message=f"action=followup selected_cohort_id={detail.cohort.id} cohort_name={detail.cohort.name}",
        )
        snapshots = self._read_cohort_snapshots()
        target_date = req.report_date or date.today()
        trading_day = self._is_us_trading_day(target_date)
        new_snapshots: list[CohortDailySnapshot] = []
        if not trading_day:
            self.log_daily_followup_scheduler_event(
                "job_skipped_market_closed",
                status="success",
                cohort_id=detail.cohort.id,
                cohort_name=detail.cohort.name,
                report_date=target_date.isoformat(),
                error_message="Market closed; follow-up snapshot generation skipped.",
            )
            self._append_pipeline_event(
                step_name="cohort_followup_skipped_market_closed",
                status="success",
                cohort_id=detail.cohort.id,
                cohort_name=detail.cohort.name,
                message=f"report_date={target_date.isoformat()} trading_day=false",
            )
            return CohortFollowupResponse(cohort_id=req.cohort_id, snapshot_date=target_date, snapshots=[])
        for cand in detail.candidates:
            analysis = self.analysis_engine.analyze_combined(
                ticker=cand.symbol,
                market=cand.market.value,
                window="1y",
                strategy_mode="balanced",
                as_of_date=target_date,
            )
            close = self._latest_close_for_symbol(cand.symbol, cand.market.value, target_date)
            selected_price = cand.selected_price
            perf = self._forward_returns_from_selection(
                cand.symbol,
                cand.market.value,
                detail.cohort.start_date,
                selected_price,
                latest_price_for_since=close,
                as_of_date=target_date,
            )
            data_quality_flags = self._build_data_quality_flags(analysis)
            data_quality_flags.extend([str(x) for x in perf.get("data_quality_flags", []) if x])
            if close is None:
                data_quality_flags.append("missing_exact_symbol_latest_price")
            data_quality_flags = sorted(set(data_quality_flags))
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
            hard_invalidation = bool(severe_structure_break and severe_gate_failure)
            hard_invalidation_reason = str(analysis.entry_gate.skip_reason or "severe_structure_break") if hard_invalidation else None
            has_any_data_quality = bool(data_quality_flags)
            if has_any_data_quality:
                validity_state = "needs_data_check"
                still_valid_candidate = None
                invalidation_reason = hard_invalidation_reason if hard_invalidation else None
                entry_readiness = "needs_data_check"
                blocked_by = "data_quality"
                readiness_explanation = "Metrics may be distorted by adjusted price / split / EMA inconsistency. Review data before interpreting."
            elif hard_invalidation:
                validity_state = "invalid"
                still_valid_candidate = False
                invalidation_reason = hard_invalidation_reason
                entry_readiness = "invalid"
                blocked_by = str(hard_invalidation_reason or "deterministic_invalidation")
                readiness_explanation = f"Deterministic invalidation: {hard_invalidation_reason or 'structure and gate failure'}."
            elif analysis.entry_gate.final_entry_decision and has_min_horizon:
                validity_state = "valid"
                still_valid_candidate = True
                invalidation_reason = None
                entry_readiness = classification["entry_readiness"]
                blocked_by = self._blocked_by_from_risk_flags(
                    risk_flags,
                    fallback=(classification["blocked_by"] if classification["blocked_by"] != "none" else "none"),
                )
                readiness_explanation = classification["readiness_explanation"]
            else:
                validity_state = "pending_validation"
                still_valid_candidate = None
                invalidation_reason = None
                entry_readiness = "pending_validation"
                blocked_by = self._blocked_by_from_risk_flags(
                    risk_flags,
                    fallback=(classification["blocked_by"] if classification["blocked_by"] != "none" else "none"),
                )
                readiness_explanation = "Awaiting full follow-up horizon with usable data."
            snap = CohortDailySnapshot(
                cohort_id=req.cohort_id,
                symbol=cand.symbol,
                snapshot_date=target_date,
                current_price=close,
                current_score=float(analysis.quantedge.final_score),
                current_categories=cand.selected_categories,
                current_setup_type=normalized_setup,
                current_trend_state=analysis.setup_interpretation.trend_state,
                current_score_dynamics=analysis.entry_gate.score_dynamics_state,
                current_trigger_state=analysis.trigger.trigger_state,
                current_trigger_score=float(analysis.trigger.trigger_score),
                price_change_since_selection=perf.get("since_selection"),
                return_since_selection=perf.get("since_selection"),
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
                entry_readiness=entry_readiness,
                blocked_by=blocked_by,
                readiness_explanation=readiness_explanation,
                data_quality_flags=data_quality_flags,
            )
            snapshots = [row for row in snapshots if not (row.cohort_id == req.cohort_id and row.symbol == cand.symbol and row.snapshot_date == target_date)]
            snapshots.append(snap)
            new_snapshots.append(snap)
            self._logger.info(
                "action=followup_validity selected_cohort_id=%s cohort_name=%s symbol=%s validity_state=%s hard_invalidation=%s invalidation_reason=%s",
                detail.cohort.id,
                detail.cohort.name,
                cand.symbol,
                validity_state,
                str(hard_invalidation).lower(),
                hard_invalidation_reason or "null",
            )
            self._logger.info(
                "[return_since_selection] symbol=%s selected_price=%.4f latest_price=%.4f return=%s",
                cand.symbol,
                float(selected_price or 0.0),
                close,
                f"{perf.get('since_selection'):.4f}" if perf.get("since_selection") is not None else "pending_or_flagged",
            )
        self._save_cohort_snapshots(snapshots)
        self._append_pipeline_event(
            step_name="cohort_followup_completed",
            status="success",
            cohort_id=detail.cohort.id,
            cohort_name=detail.cohort.name,
            message=f"action=followup selected_cohort_id={detail.cohort.id} cohort_name={detail.cohort.name} snapshots={len(new_snapshots)}",
        )
        return CohortFollowupResponse(cohort_id=req.cohort_id, snapshot_date=target_date, snapshots=sorted(new_snapshots, key=lambda row: row.symbol))

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
                        row = row.model_copy(update={"error_message": "stale_warning: stale_running_timeout"})
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
                    built = built.model_copy(
                        update={
                            "score_by_category": {category.value: float(row.scanner_score)},
                            "company_name": row.company_name,
                            "sector": row.sector,
                            "industry": row.industry,
                            "sector_key": row.sector_key,
                            "industry_key": row.industry_key,
                            "metadata_source": row.metadata_source,
                            "metadata_data_quality_status": row.metadata_data_quality_status,
                        }
                    )
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
        serious = {
            "possible_split_or_unadjusted_price_jump",
            "non_positive_price_or_ema",
            "return_outlier_1d",
            "return_outlier_3d",
            "non_positive_reference_price",
            "missing_selected_price",
            "missing_latest_price",
            "suspicious_return_since_selection",
            "possible_adjusted_unadjusted_mismatch",
            "possible_symbol_price_mismatch",
        }
        return any(flag in serious for flag in flags)

    @staticmethod
    def _blocked_by_from_risk_flags(risk_flags: list[str], fallback: str = "none") -> str:
        lowered = {str(x).lower() for x in (risk_flags or [])}
        if "resistance_room_filter" in lowered:
            return "resistance_room_filter"
        if "overextended_filter" in lowered:
            return "overextended_filter"
        if "overextended" in lowered:
            return "overextended"
        if "location_filter" in lowered:
            return "location_filter"
        if "score_threshold" in lowered:
            return "score_threshold"
        if "weak_volume_confirmation" in lowered:
            return "weak_volume_confirmation"
        return fallback

    @staticmethod
    def _build_confirm_entry_text(trigger_state: str | None, trigger_score: float | None, trigger_threshold: float | None, blocked_by: str | None) -> str:
        thr = float(trigger_threshold) if trigger_threshold is not None else 65.0
        score = float(trigger_score) if trigger_score is not None else 0.0
        state = str(trigger_state or "").lower()
        confirmed = state == "confirmed" or score >= thr
        blocked = str(blocked_by or "none")
        if not confirmed:
            return f"Need trigger confirmation and trigger score >= {thr:.1f}."
        if blocked in {"resistance_room_filter", "resistance_room"}:
            return "Trigger is confirmed, but entry is blocked by resistance room."
        if blocked in {"overextended_filter", "overextended"}:
            return "Trigger is confirmed, but entry is blocked by overextension."
        if blocked == "location_filter":
            return "Trigger is confirmed, but entry is blocked by location filter."
        if blocked and blocked != "none":
            return f"Trigger is confirmed, but entry is blocked by {blocked}."
        return "Entry trigger is confirmed."

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
        trigger_confirmed = trigger_state == "confirmed" or trigger_score >= min_trigger
        confirm_entry = self._build_confirm_entry_text(
            trigger_state=str(analysis.trigger.trigger_state),
            trigger_score=trigger_score,
            trigger_threshold=min_trigger,
            blocked_by=blocked_by,
        )
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
            company_name=analysis.indicator_summary.get("name") if isinstance(analysis.indicator_summary, dict) else None,
            sector=analysis.indicator_summary.get("sector") if isinstance(analysis.indicator_summary, dict) else None,
            industry=analysis.indicator_summary.get("industry") if isinstance(analysis.indicator_summary, dict) else None,
            metadata_source="analysis_market_data",
            metadata_data_quality_status="ok",
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

    @staticmethod
    def _clip_context_words(text: str, max_words: int = 20) -> str:
        words = str(text or "").replace("\n", " ").strip().split()
        if not words:
            return ""
        if len(words) <= max_words:
            return " ".join(words)
        return " ".join(words[:max_words]).rstrip(".,;:") + "."

    def _deterministic_symbol_context(
        self,
        row: SymbolResult,
        *,
        model: str,
        run_id: str,
        error_message: str,
    ) -> SymbolContext:
        categories = ", ".join([tag.value if hasattr(tag, "value") else str(tag) for tag in row.category_tags]) or "uncategorized"
        risk_flags = [str(flag) for flag in (row.risk_flags or []) if str(flag)]
        data_quality_flags = [str(flag) for flag in (row.data_quality_flags or []) if str(flag)]
        blocked_by = str(row.blocked_by or "none")
        readiness = str(row.entry_readiness or "unknown")

        if row.main_opportunity_reason:
            bull = row.main_opportunity_reason
        else:
            bull = f"{row.symbol} has {row.trend} structure, setup {row.setup_type}, category {categories}."

        if data_quality_flags:
            bear = f"Data quality needs review: {', '.join(data_quality_flags)}."
        elif row.main_risk_reason:
            bear = row.main_risk_reason
        elif risk_flags:
            bear = f"Risk flags present: {', '.join(risk_flags)}."
        else:
            bear = f"Readiness is {readiness}; blocked_by is {blocked_by}."

        if data_quality_flags:
            risks = f"Data quality flags: {', '.join(data_quality_flags)}."
        elif risk_flags:
            risks = f"Risk flags: {', '.join(risk_flags)}."
        else:
            risks = "No explicit deterministic risk flags in the cohort snapshot."

        summary = (
            "Deterministic fallback context only; LLM output was unavailable or invalid. "
            "Scanner score, category, and readiness are unchanged."
        )

        self._append_llm_log(
            LLMDebugLog(
                id=str(uuid4()),
                timestamp=datetime.now(UTC),
                symbol=row.symbol,
                endpoint="-",
                call_type="symbol_context_deterministic_fallback",
                prompt="(deterministic fallback)",
                raw_response=summary,
                parsed_output={
                    "bull_case": self._clip_context_words(bull),
                    "bear_case": self._clip_context_words(bear),
                    "risks": self._clip_context_words(risks),
                    "summary": self._clip_context_words(summary),
                },
                status="success",
                duration_ms=0,
                provider="deterministic",
                model="deterministic-fallback",
                fallback_used=True,
                error_message=error_message,
            )
        )
        return SymbolContext(
            symbol=row.symbol,
            run_id=run_id,
            date=date.today(),
            bull_case=self._clip_context_words(bull),
            bear_case=self._clip_context_words(bear),
            risks=self._clip_context_words(risks),
            summary=self._clip_context_words(summary),
            model=f"{model} (deterministic fallback)",
            status="generated",
            error=error_message,
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
        prompt_version: str | None = None,
        request_id: str | None = None,
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
                    prompt_version=prompt_version,
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
                            if call_type == "symbol_context":
                                self._log_llm_context_event(
                                    "request_payload_built",
                                    request_id=request_id,
                                    provider=provider_name.upper(),
                                    model=provider_model,
                                    endpoint=call_type,
                                    prompt_version=prompt_version,
                                    request_payload_built=True,
                                )
                                self._log_llm_context_event(
                                    "openai_call_started",
                                    request_id=request_id,
                                    provider=provider_name.upper(),
                                    model=provider_model,
                                    endpoint=call_type,
                                )
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
                            if call_type == "symbol_context":
                                self._log_llm_context_event(
                                    "openai_call_success",
                                    request_id=request_id,
                                    provider=provider_name.upper(),
                                    model=provider_model,
                                    endpoint=call_type,
                                    duration_ms=duration_ms,
                                    fallback_used=is_fallback,
                                )
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
                                prompt_version=prompt_version,
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
                        endpoint = (
                            self.settings.openai_base_url.rstrip("/") + "/responses"
                            if provider_name == "openai"
                            else self.settings.ollama_base_url
                        )
                        if call_type == "symbol_context" and provider_name == "openai":
                            self._log_llm_context_event(
                                "openai_call_failed",
                                request_id=request_id,
                                provider=provider_name.upper(),
                                model=provider_model,
                                endpoint=call_type,
                                duration_ms=duration_ms,
                                error_type=type(exc).__name__,
                                error_message=str(exc),
                                fallback_used=is_fallback,
                            )
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
                                prompt_version=prompt_version,
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
                "Return ONLY valid JSON. No markdown. Context only. Do not create trade instructions. Keep each field <=20 words.\n"
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
                f"company_name={row.company_name or 'unknown'}\n"
                f"sector={row.sector or 'unknown'}\n"
                f"industry={row.industry or 'unknown'}\n"
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
            "Do NOT give trade instructions.\n"
            "Do NOT provide price targets.\n"
            "Do NOT alter system configuration.\n\n"
            f"Analyze the following stock context:\n\n"
            f"Symbol: {row.symbol}\n"
            f"Category: {', '.join([tag.value if hasattr(tag, 'value') else str(tag) for tag in row.category_tags])}\n"
            f"Score: {row.score:.2f}\n"
            f"Company: {row.company_name or 'unknown'}\n"
            f"Sector: {row.sector or 'unknown'}\n"
            f"Industry: {row.industry or 'unknown'}\n"
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

    def _generate_single_symbol_context(
        self,
        row: SymbolResult,
        *,
        model: str,
        timeout_seconds: float,
        short_context_mode: bool,
        run_id: str,
        debug_stream: bool,
        request_id: str | None = None,
    ) -> SymbolContext:
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
                prompt_version=SYMBOL_CONTEXT_PROMPT_VERSION,
                request_id=request_id,
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
            self._log_llm_context_event(
                "response_parse_success",
                request_id=request_id,
                symbol=row.symbol,
                model=model,
                endpoint="symbol-contexts",
                response_parse_success=True,
                fallback_used=False,
            )
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
        except Exception as exc:
            error_message = str(exc)
            self._log_llm_context_event(
                "response_parse_success",
                request_id=request_id,
                symbol=row.symbol,
                model=model,
                endpoint="symbol-contexts",
                response_parse_success=False,
                fallback_used=True,
                error_type=type(exc).__name__,
                error_message=error_message,
            )
            fallback = self._deterministic_symbol_context(row, model=model, run_id=run_id, error_message=error_message)
            self._append_pipeline_event(
                step_name="symbol_context_fallback_used",
                status="success",
                run_id=run_id,
                symbol=row.symbol,
                duration_ms=int((datetime.now(UTC) - symbol_started).total_seconds() * 1000),
                message="deterministic fallback used for symbol context",
                error_message=error_message,
            )
            self._append_pipeline_event(
                step_name="symbol_context_completed",
                status="success",
                run_id=run_id,
                symbol=row.symbol,
                duration_ms=int((datetime.now(UTC) - symbol_started).total_seconds() * 1000),
                message="generated deterministic fallback context",
                error_message=error_message,
            )
            return fallback

    def _get_run_detail(self, run_id: str) -> DailyRunDetail:
        rows = self._read_symbol_results()
        for row in rows:
            parsed = DailyRunDetail.model_validate(row)
            if parsed.run.id == run_id:
                return parsed
        raise FileNotFoundError(run_id)

    def generate_symbol_contexts(self, req: SymbolContextBatchRequest) -> SymbolContextBatchResponse:
        started = datetime.now(UTC)
        model = self.settings.llmq_chat_model
        request_id = str(uuid4())
        provider = self._normalize_provider(self.settings.llm_provider)
        self._log_llm_context_event(
            "request_started",
            request_id=request_id,
            run_id=req.run_id,
            provider=provider.upper(),
            model=model,
            endpoint="symbol-contexts",
            prompt_version=SYMBOL_CONTEXT_PROMPT_VERSION,
        )
        self._append_pipeline_event(
            step_name="symbol_context_batch_started",
            status="running",
            run_id=req.run_id,
            provider=provider,
            message=f"request_id={request_id} limit={req.context_symbol_limit} concurrency={req.max_concurrency} timeout={req.timeout_seconds}s sequential={req.sequential_mode}",
        )
        detail = self._get_run_detail(req.run_id)
        target_rows = detail.symbol_results[: req.context_symbol_limit]
        self._log_llm_context_event(
            "symbols_selected",
            request_id=request_id,
            run_id=req.run_id,
            symbols_count=len(target_rows),
            provider=provider.upper(),
            model=model,
            endpoint="symbol-contexts",
            prompt_version=SYMBOL_CONTEXT_PROMPT_VERSION,
        )
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
                    model=model,
                    timeout_seconds=req.timeout_seconds,
                    short_context_mode=req.short_context_mode,
                    run_id=req.run_id,
                    debug_stream=req.debug_stream,
                    request_id=request_id,
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
        fallback_used = any(bool(row.error) or "fallback" in (row.model or "").lower() for row in contexts)
        error_message = "; ".join([str(row.error) for row in contexts if row.error]) or None
        return SymbolContextBatchResponse(
            run_id=req.run_id,
            generated=len(contexts) - failed,
            failed=failed,
            contexts=sorted(contexts, key=lambda row: row.symbol),
            failed_symbols=sorted([row.symbol for row in contexts if row.status != "generated"]),
            request_id=request_id,
            provider=provider.upper(),
            model=model,
            endpoint="/intelligence/symbol-contexts",
            fallback_used=fallback_used,
            error_message=error_message,
        )

    def generate_cohort_symbol_contexts(self, req: CohortSymbolContextRequest) -> SymbolContextBatchResponse:
        detail = self.get_cohort_detail(req.cohort_id)
        model = self.settings.llmq_chat_model
        provider = self._normalize_provider(self.settings.llm_provider)
        request_id = str(uuid4())
        self._log_llm_context_event(
            "request_started",
            request_id=request_id,
            cohort_id=detail.cohort.id,
            provider=provider.upper(),
            model=model,
            endpoint="symbol-contexts",
            prompt_version=SYMBOL_CONTEXT_PROMPT_VERSION,
        )
        self._append_pipeline_event(
            step_name="cohort_symbol_context_batch_started",
            status="running",
            cohort_id=detail.cohort.id,
            cohort_name=detail.cohort.name,
            provider=provider,
            message=f"request_id={request_id} action=contexts selected_cohort_id={detail.cohort.id} cohort_name={detail.cohort.name} symbols_limit={req.context_symbol_limit}",
        )
        candidates = detail.candidates
        if req.symbols:
            selected = {s.upper() for s in req.symbols}
            candidates = [row for row in candidates if row.symbol.upper() in selected]
        candidates = candidates[: req.context_symbol_limit]
        self._log_llm_context_event(
            "symbols_selected",
            request_id=request_id,
            cohort_id=detail.cohort.id,
            symbols_count=len(candidates),
            provider=provider.upper(),
            model=model,
            endpoint="symbol-contexts",
            prompt_version=SYMBOL_CONTEXT_PROMPT_VERSION,
        )
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
                    company_name=cand.selected_company_name,
                    sector=cand.selected_sector,
                    industry=cand.selected_industry,
                    metadata_source="cohort_snapshot",
                    metadata_data_quality_status="ok" if (cand.selected_sector or cand.selected_industry) else "metadata_missing",
                )
                futures.append(
                    executor.submit(
                        self._generate_single_symbol_context,
                        symbol_result,
                        model=model,
                        timeout_seconds=req.timeout_seconds,
                        short_context_mode=req.short_context_mode,
                        run_id=req.cohort_id,
                        debug_stream=req.debug_stream,
                        request_id=request_id,
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
                        model=model,
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
            message=f"action=contexts selected_cohort_id={detail.cohort.id} cohort_name={detail.cohort.name} generated={len(contexts)-failed} failed={failed}",
            error_message=None if failed < len(contexts) else "all cohort symbol contexts failed",
        )
        fallback_used = any(bool(row.error) or "fallback" in (row.model or "").lower() for row in contexts)
        error_message = "; ".join([str(row.error) for row in contexts if row.error]) or None
        self._log_llm_context_event(
            "request_completed",
            request_id=request_id,
            cohort_id=detail.cohort.id,
            symbols_count=len(candidates),
            provider=provider.upper(),
            model=model,
            endpoint="symbol-contexts",
            fallback_used=fallback_used,
            response_parse_success=failed == 0,
        )
        return SymbolContextBatchResponse(
            run_id=req.cohort_id,
            generated=len(contexts) - failed,
            failed=failed,
            contexts=sorted(contexts, key=lambda row: row.symbol),
            failed_symbols=sorted([row.symbol for row in contexts if row.status != "generated"]),
            request_id=request_id,
            provider=provider.upper(),
            model=model,
            endpoint="/intelligence/cohorts/symbol-contexts",
            fallback_used=fallback_used,
            error_message=error_message,
        )

    def generate_cohort_briefing(self, req: CohortBriefingRequest) -> DailyBriefing:
        detail = self.get_cohort_detail(req.cohort_id)
        model = self.settings.daily_report_llm_model
        self._append_pipeline_event(
            step_name="cohort_briefing_started",
            status="running",
            cohort_id=detail.cohort.id,
            cohort_name=detail.cohort.name,
            provider=self._normalize_provider(self.settings.llm_provider),
            message=f"action=briefing selected_cohort_id={detail.cohort.id} cohort_name={detail.cohort.name}",
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
                model=model,
                status="failed",
                error="no generated symbol contexts for cohort_id",
            )
        prompt_parts = [
            "Use deterministic facts only. No trade instructions. Keep concise.",
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
        text = self._ollama_generate(prompt="\n".join(prompt_parts), model=model, timeout_seconds=req.timeout_seconds, call_type="cohort_briefing", prompt_version=DAILY_REPORT_PROMPT_VERSION)
        briefing = DailyBriefing(date=date.today(), cohort_id=req.cohort_id, summary_text=text, model=model, status="generated")
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
        model = self.settings.daily_report_llm_model
        self._append_pipeline_event(
            step_name="daily_briefing_started",
            status="running",
            run_id=req.run_id,
            message=f"model={model} timeout={req.timeout_seconds}s",
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
                model=model,
                status="failed",
                error="no generated symbol contexts for run_id",
            )
            rows = self._read_briefings()
            rows.append(briefing)
            self._save_briefings(rows)
            return briefing
        prompt_parts = [
            "You are preparing a deterministic market briefing.",
            "Do NOT give trade instructions.",
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
                model=model,
                timeout_seconds=req.timeout_seconds,
                call_type="daily_briefing",
                prompt_version=DAILY_REPORT_PROMPT_VERSION,
            )
            briefing = DailyBriefing(date=detail.run.date, summary_text=text, model=model, status="generated")
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
                model=model,
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
        model = self.settings.final_28d_review_llm_model
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
                model=model,
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
                model=model,
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
            text = self._ollama_generate(
                prompt=prompt,
                model=model,
                timeout_seconds=req.timeout_seconds,
                call_type="system_review",
                prompt_version=FINAL_28D_REVIEW_PROMPT_VERSION,
            )
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
                model=model,
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
                model=model,
                status="failed",
                error=str(exc),
            )
        rows = self._read_reviews()
        rows.append(review)
        self._save_reviews(rows)
        return review

    def _latest_close_for_symbol(self, symbol: str, market: str, as_of_date: date) -> float | None:
        try:
            requested_symbol = normalize_symbol(symbol, market).strip().upper()
            bundle = self.analysis_engine.data_service.get_market_data(symbol, market=market, period="1y", use_cache=False)
            bundle_symbol = str(getattr(bundle, "normalized_ticker", "") or "").strip().upper()
            if requested_symbol and bundle_symbol and requested_symbol != bundle_symbol:
                self._logger.warning(
                    "[latest_price] symbol=%s source_symbol=%s status=mismatch",
                    requested_symbol,
                    bundle_symbol,
                )
                return None
            close = bundle.daily["close"].dropna().astype(float)
            close = close[close.index.map(lambda ts: ts.date() <= as_of_date)]
            if close.empty:
                return None
            return float(close.iloc[-1])
        except Exception:
            return None

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
        latest_price_for_since: float | None = None,
        as_of_date: date | None = None,
    ) -> dict[str, float | None]:
        try:
            bundle = self.analysis_engine.data_service.get_market_data(symbol, market=market, period="1y", use_cache=False)
            close = bundle.daily["close"].dropna().astype(float)
            if as_of_date is not None:
                close = close[close.index.map(lambda ts: ts.date() <= as_of_date)]
            dq_flags: list[str] = []
            requested_symbol = normalize_symbol(symbol, market).strip().upper()
            bundle_symbol = str(getattr(bundle, "normalized_ticker", "") or "").strip().upper()
            if requested_symbol and bundle_symbol and requested_symbol != bundle_symbol:
                self._logger.warning(
                    "[horizon_return] symbol=%s source_symbol=%s status=mismatch",
                    requested_symbol,
                    bundle_symbol,
                )
                return {
                    "1d": None,
                    "3d": None,
                    "7d": None,
                    "14d": None,
                    "28d": None,
                    "max_runup": None,
                    "max_drawdown": None,
                    "since_selection": None,
                    "data_quality_flags": ["possible_symbol_price_mismatch"],
                }
            if close.empty:
                return {"1d": None, "3d": None, "7d": None, "14d": None, "28d": None, "max_runup": None, "max_drawdown": None, "since_selection": None, "data_quality_flags": ["missing_price_series"]}
            from_idx = 0
            for idx, ts in enumerate(close.index):
                if ts.date() >= selection_date:
                    from_idx = idx
                    break
            series = close.iloc[from_idx:]
            if series.empty:
                return {"1d": None, "3d": None, "7d": None, "14d": None, "28d": None, "max_runup": None, "max_drawdown": None, "since_selection": None, "data_quality_flags": ["missing_selection_window"]}
            if selected_price is None or selected_price <= 0:
                selected_price = float(series.iloc[0])
            latest_price = float(series.iloc[-1])
            def ret_from_selection_horizon(days: int, label: str) -> float | None:
                if len(series) <= days:
                    self._logger.info(
                        "[horizon_return] symbol=%s selected_price=%.6f price_at_%s=pending return_%s=pending",
                        symbol,
                        float(selected_price or 0.0),
                        label,
                        label,
                    )
                    return None
                horizon_price = float(series.iloc[days])
                if selected_price is None or selected_price <= 0 or horizon_price <= 0:
                    dq_flags.append("non_positive_horizon_price")
                    self._logger.info(
                        "[horizon_return] symbol=%s selected_price=%.6f price_at_%s=pending return_%s=pending",
                        symbol,
                        float(selected_price or 0.0),
                        label,
                        label,
                    )
                    return None
                ret = float((horizon_price - float(selected_price)) / float(selected_price) * 100.0)
                if market == "us" and abs(ret) > 40.0:
                    dq_flags.append(f"return_outlier_{label}")
                    self._logger.info(
                        "[horizon_return] symbol=%s selected_price=%.6f price_at_%s=%.6f return_%s=pending",
                        symbol,
                        float(selected_price or 0.0),
                        label,
                        horizon_price,
                        label,
                    )
                    return None
                self._logger.info(
                    "[horizon_return] symbol=%s selected_price=%.6f price_at_%s=%.6f return_%s=%.12f",
                    symbol,
                    float(selected_price),
                    label,
                    horizon_price,
                    label,
                    ret,
                )
                return ret
            since_selection = None
            effective_latest_for_since = float(latest_price_for_since) if latest_price_for_since is not None else latest_price
            if latest_price_for_since is None:
                dq_flags.append("missing_latest_price")
            if selected_price is None or selected_price <= 0:
                dq_flags.append("missing_selected_price")
            elif effective_latest_for_since <= 0:
                dq_flags.append("missing_latest_price")
            else:
                since_selection = float((effective_latest_for_since - float(selected_price)) / float(selected_price) * 100.0)
                if market == "us" and abs(since_selection) > 40.0:
                    dq_flags.append("suspicious_return_since_selection")
                    dq_flags.append("possible_adjusted_unadjusted_mismatch")
                    dq_flags.append("possible_symbol_price_mismatch")
                    since_selection = None
            runup = float((series.max() / selected_price - 1.0) * 100.0) if selected_price and selected_price > 0 else None
            drawdown = float((series.min() / selected_price - 1.0) * 100.0) if selected_price and selected_price > 0 else None
            return {
                "1d": ret_from_selection_horizon(1, "1d"),
                "3d": ret_from_selection_horizon(3, "3d"),
                "7d": ret_from_selection_horizon(7, "7d"),
                "14d": ret_from_selection_horizon(14, "14d"),
                "28d": ret_from_selection_horizon(28, "28d"),
                "since_selection": since_selection,
                "max_runup": runup,
                "max_drawdown": drawdown,
                "data_quality_flags": sorted(set(dq_flags)),
            }
        except Exception:
            return {"1d": None, "3d": None, "7d": None, "14d": None, "28d": None, "max_runup": None, "max_drawdown": None, "since_selection": None, "data_quality_flags": ["forward_return_calc_error"]}

    @staticmethod
    def _return_from_price_pair(selected_price: float | None, horizon_price: float | None) -> float | None:
        if selected_price is None or horizon_price is None or selected_price <= 0:
            return None
        return round(float((horizon_price - selected_price) / selected_price * 100.0), 4)

    def _selection_price_horizons(
        self,
        cand: CohortCandidate,
        *,
        selection_date: date,
        as_of_date: date,
    ) -> dict[str, Any]:
        empty = {
            "selected_price": cand.selected_price,
            "price_7d": None,
            "price_14d": None,
            "price_28d": None,
            "latest_price": None,
            "latest_price_date": None,
            "return_7d": None,
            "return_14d": None,
            "return_28d": None,
            "return_since_selection": None,
            "data_quality_flags": [],
        }
        try:
            requested_symbol = normalize_symbol(cand.symbol, cand.market.value).strip().upper()
            bundle = self.analysis_engine.data_service.get_market_data(
                cand.symbol,
                market=cand.market.value,
                period="2y",
                use_cache=False,
            )
            bundle_symbol = str(getattr(bundle, "normalized_ticker", "") or "").strip().upper()
            if requested_symbol and bundle_symbol and requested_symbol != bundle_symbol:
                return {**empty, "data_quality_flags": ["possible_symbol_price_mismatch"]}
            close = bundle.daily["close"].dropna().astype(float)
            close = close[close.index.map(lambda timestamp: timestamp.date() <= as_of_date)]
            if close.empty:
                return {**empty, "data_quality_flags": ["missing_price_series"]}
            start_positions = [
                position
                for position, timestamp in enumerate(close.index)
                if timestamp.date() >= selection_date
            ]
            if not start_positions:
                return {**empty, "data_quality_flags": ["missing_selection_window"]}
            start_position = start_positions[0]
            selected_price = cand.selected_price
            if selected_price is None or selected_price <= 0:
                selected_price = float(close.iloc[start_position])
            series = close.iloc[start_position:]
            if series.empty:
                return {**empty, "selected_price": selected_price, "data_quality_flags": ["missing_selection_window"]}

            def price_after_trading_days(days_after_selection: int) -> float | None:
                if len(series) <= days_after_selection:
                    return None
                return float(series.iloc[days_after_selection])

            price_7d = price_after_trading_days(7)
            price_14d = price_after_trading_days(14)
            price_28d = price_after_trading_days(28)
            latest_price = float(series.iloc[-1])
            latest_price_date = series.index[-1].date()
            return {
                "selected_price": selected_price,
                "price_7d": price_7d,
                "price_14d": price_14d,
                "price_28d": price_28d,
                "latest_price": latest_price,
                "latest_price_date": latest_price_date,
                "return_7d": self._return_from_price_pair(selected_price, price_7d),
                "return_14d": self._return_from_price_pair(selected_price, price_14d),
                "return_28d": self._return_from_price_pair(selected_price, price_28d),
                "return_since_selection": self._return_from_price_pair(selected_price, latest_price),
                "data_quality_flags": [],
            }
        except Exception:
            return {**empty, "data_quality_flags": ["selection_horizon_calc_error"]}

    def _latest_followup_date_for_cohort(
        self,
        cohort_id: str,
        snapshots: list[CohortDailySnapshot] | None = None,
        *,
        through_date: date | None = None,
    ) -> date | None:
        dates = {
            row.snapshot_date
            for row in (snapshots if snapshots is not None else self._read_cohort_snapshots())
            if row.cohort_id == cohort_id and (through_date is None or row.snapshot_date <= through_date)
        }
        try:
            dates.update(
                row.report_date
                for row in self.daily_report_store.list_reports(cohort_id)
                if row.followup_snapshot_count > 0 and (through_date is None or row.report_date <= through_date)
            )
        except Exception:
            pass
        return max(dates) if dates else None

    def _cohort_followup_coverage(
        self,
        cohort: CandidateCohort,
        snapshots: list[CohortDailySnapshot],
        *,
        days_required: int,
        through_date: date | None = None,
    ) -> dict[str, Any]:
        start_date = cohort.followup_start_date or cohort.start_date
        latest_followup_date = through_date or self._latest_followup_date_for_cohort(cohort.id, snapshots)
        as_of_date = latest_followup_date or date.today()
        elapsed_trading_days = self._trading_days_between(start_date, as_of_date)
        valid_dates = {
            row.snapshot_date
            for row in snapshots
            if row.cohort_id == cohort.id
            and row.snapshot_date >= start_date
            and row.snapshot_date <= as_of_date
            and self._is_us_trading_day(row.snapshot_date)
        }
        try:
            valid_dates.update(
                row.report_date
                for row in self.daily_report_store.list_reports(cohort.id)
                if row.followup_snapshot_count > 0
                and row.report_date >= start_date
                and row.report_date <= as_of_date
                and self._is_us_trading_day(row.report_date)
            )
        except Exception:
            pass
        expected_days = min(max(1, int(days_required)), len(elapsed_trading_days))
        valid_snapshot_days = min(len(valid_dates), expected_days)
        missing_days_count = max(0, expected_days - valid_snapshot_days)
        missing_dates = [day for day in elapsed_trading_days if day not in valid_dates][:missing_days_count]
        coverage_pct = round((valid_snapshot_days / expected_days * 100.0), 1) if expected_days else 0.0
        return {
            "start_date": start_date,
            "latest_followup_date": latest_followup_date,
            "calendar_days_elapsed": max(0, (as_of_date - start_date).days),
            "trading_days_elapsed": len(elapsed_trading_days),
            "valid_followup_snapshot_days": valid_snapshot_days,
            "expected_followup_days": expected_days,
            "snapshot_coverage_pct": coverage_pct,
            "missing_followup_days_count": missing_days_count,
            "missing_followup_dates": missing_dates,
            "daily_path_review_complete": expected_days > 0 and valid_snapshot_days >= expected_days,
        }

    def run_cohort_review(self, req: CohortReviewRequest) -> CohortReviewResponse:
        model = self.settings.final_28d_review_llm_model
        cohorts = self._read_cohorts()
        cohort_by_id = {row.id: row for row in cohorts}
        if req.cohort_id not in cohort_by_id:
            raise FileNotFoundError(f"Cohort not found: {req.cohort_id}")
        cohort = cohort_by_id[req.cohort_id]
        selected_name = cohort.name
        self._append_pipeline_event(
            step_name="cohort_review_started",
            status="running",
            cohort_id=req.cohort_id,
            cohort_name=selected_name,
            message=f"action=review selected_cohort_id={req.cohort_id} cohort_name={selected_name}",
        )
        target_ids = [req.cohort_id]
        candidate_rows = [row for row in self._read_cohort_candidates() if row.cohort_id in target_ids]
        snapshot_rows = [row for row in self._read_cohort_snapshots() if row.cohort_id in target_ids]
        coverage = self._cohort_followup_coverage(cohort, snapshot_rows, days_required=req.days_required)
        review_as_of = coverage["latest_followup_date"] or date.today()
        unique_days = int(coverage["valid_followup_snapshot_days"])
        expected_days = int(coverage["expected_followup_days"])
        days_remaining = int(coverage["missing_followup_days_count"])
        daily_path_review_complete = bool(coverage["daily_path_review_complete"])
        sufficient_window = daily_path_review_complete
        horizon_review_available = False
        horizon_28d_available = False
        horizon_28d_candidate_count = 0
        horizon_28d_missing_count = len(candidate_rows)
        horizon_28d_positive_count = 0
        horizon_28d_negative_count = 0
        warning = None
        by_symbol_snapshots: dict[str, list[CohortDailySnapshot]] = {}
        for row in sorted(snapshot_rows, key=lambda snapshot: (snapshot.snapshot_date, snapshot.symbol)):
            by_symbol_snapshots.setdefault(f"{row.cohort_id}|{row.symbol}", []).append(row)
        return_since_by_cat: dict[str, list[float]] = {}
        return_7d_by_cat: dict[str, list[float]] = {}
        return_14d_by_cat: dict[str, list[float]] = {}
        return_28d_by_cat: dict[str, list[float]] = {}
        score_ret_pairs: list[tuple[float, float]] = []
        false_positives = 0
        missed_follow = 0
        stayed_valid = 0
        invalidated_quickly = 0
        pending_validation_count = 0
        needs_data_check_count = 0
        pending_horizon_count = 0
        ret1d_vals: list[float] = []
        by_sector_1d: dict[str, list[float]] = {}
        by_sector_3d: dict[str, list[float]] = {}
        by_sector_7d: dict[str, list[float]] = {}
        sector_counts: dict[str, int] = {}
        best_symbol = None
        worst_symbol = None
        best_ret = -9999.0
        worst_ret = 9999.0
        best_symbol_28d = None
        worst_symbol_28d = None
        best_ret_28d = -9999.0
        worst_ret_28d = 9999.0
        multi_cat_returns: list[float] = []
        for cand in candidate_rows:
            symbol_snaps = by_symbol_snapshots.get(f"{cand.cohort_id}|{cand.symbol}", [])
            latest = symbol_snaps[-1] if symbol_snaps else None
            sector_name = (cand.selected_sector or "unknown").strip() or "unknown"
            sector_counts[sector_name] = sector_counts.get(sector_name, 0) + 1
            horizons = self._selection_price_horizons(
                cand,
                selection_date=cohort.start_date,
                as_of_date=review_as_of,
            )
            latest_return = horizons.get("return_since_selection")
            ret7 = horizons.get("return_7d")
            ret14 = horizons.get("return_14d")
            ret28 = horizons.get("return_28d")
            horizon_is_data_quality = bool(horizons.get("data_quality_flags"))
            if any(isinstance(value, (int, float)) for value in [latest_return, ret7, ret14, ret28]):
                horizon_review_available = True
            latest_is_data_quality = bool(
                latest
                and (
                    str(getattr(latest, "entry_readiness", "")) == "needs_data_check"
                    or str(getattr(latest, "blocked_by", "")) == "data_quality"
                    or bool(getattr(latest, "data_quality_flags", []))
                )
            )
            if latest and latest.return_1d is not None and not latest_is_data_quality:
                ret1d_vals.append(float(latest.return_1d))
                by_sector_1d.setdefault(sector_name, []).append(float(latest.return_1d))
            if latest and latest.return_3d is not None and not latest_is_data_quality:
                by_sector_3d.setdefault(sector_name, []).append(float(latest.return_3d))
            if isinstance(ret7, (int, float)) and not horizon_is_data_quality:
                by_sector_7d.setdefault(sector_name, []).append(float(ret7))
            validity_state = "pending_validation"
            if latest:
                if getattr(latest, "validity_state", None):
                    validity_state = str(latest.validity_state)
                elif latest.still_valid_candidate is True:
                    validity_state = "valid"
                elif latest.still_valid_candidate is False:
                    validity_state = "invalid"
            if latest_is_data_quality:
                validity_state = "needs_data_check"
            has_required_horizon = ret7 is not None and ret14 is not None and ret28 is not None
            if not has_required_horizon:
                pending_horizon_count += 1
            if not horizon_is_data_quality:
                for cat in cand.selected_categories:
                    key = cat.value if hasattr(cat, "value") else str(cat)
                    if isinstance(latest_return, (int, float)):
                        return_since_by_cat.setdefault(key, []).append(float(latest_return))
                    if isinstance(ret7, (int, float)):
                        return_7d_by_cat.setdefault(key, []).append(float(ret7))
                    if isinstance(ret14, (int, float)):
                        return_14d_by_cat.setdefault(key, []).append(float(ret14))
                    if isinstance(ret28, (int, float)):
                        return_28d_by_cat.setdefault(key, []).append(float(ret28))
            if ret7 is not None and not horizon_is_data_quality:
                score_ret_pairs.append((cand.selected_score, float(ret7)))
                if len(cand.selected_categories) > 1:
                    multi_cat_returns.append(float(ret7))
                if ret7 > best_ret:
                    best_ret, best_symbol = ret7, cand.symbol
                if ret7 < worst_ret:
                    worst_ret, worst_symbol = ret7, cand.symbol
            if ret28 is not None and not horizon_is_data_quality:
                horizon_28d_candidate_count += 1
                if ret28 > 0:
                    horizon_28d_positive_count += 1
                elif ret28 < 0:
                    horizon_28d_negative_count += 1
                if ret28 > best_ret_28d:
                    best_ret_28d, best_symbol_28d = ret28, cand.symbol
                if ret28 < worst_ret_28d:
                    worst_ret_28d, worst_symbol_28d = ret28, cand.symbol
            if validity_state == "pending_validation":
                pending_validation_count += 1
            elif validity_state == "needs_data_check":
                needs_data_check_count += 1
            if sufficient_window and validity_state == "invalid" and ret7 is not None and ret7 < 0:
                false_positives += 1
            if sufficient_window and validity_state == "valid":
                stayed_valid += 1
            if sufficient_window and validity_state == "invalid" and symbol_snaps:
                invalid_snap = next((snap for snap in symbol_snaps if (getattr(snap, "validity_state", None) == "invalid" or snap.still_valid_candidate is False)), None)
                cohort_start = cohort_by_id.get(cand.cohort_id).start_date if cand.cohort_id in cohort_by_id else cand.selected_at.date()
                if invalid_snap is not None and (invalid_snap.snapshot_date - cohort_start).days <= 3:
                    invalidated_quickly += 1
            if sufficient_window and ret7 is not None and ret7 < -3:
                missed_follow += 1
        avg_since_by_cat = {key: round(sum(values) / len(values), 3) for key, values in return_since_by_cat.items() if values}
        avg_7d_by_cat = {key: round(sum(values) / len(values), 3) for key, values in return_7d_by_cat.items() if values}
        avg_14d_by_cat = {key: round(sum(values) / len(values), 3) for key, values in return_14d_by_cat.items() if values}
        avg_28d_by_cat = {key: round(sum(values) / len(values), 3) for key, values in return_28d_by_cat.items() if values}
        avg_by_sector_7d = {
            sector: round(sum(values) / len(values), 3)
            for sector, values in by_sector_7d.items()
            if values
        }
        best_cat_28d = max(avg_28d_by_cat, key=avg_28d_by_cat.get) if avg_28d_by_cat else None
        worst_cat_28d = min(avg_28d_by_cat, key=avg_28d_by_cat.get) if avg_28d_by_cat else None
        best_cat = best_cat_28d
        worst_cat = worst_cat_28d
        best_sector_by_1d = max(by_sector_1d, key=lambda sector: (sum(by_sector_1d[sector]) / len(by_sector_1d[sector]))) if by_sector_1d else None
        worst_sector_by_1d = min(by_sector_1d, key=lambda sector: (sum(by_sector_1d[sector]) / len(by_sector_1d[sector]))) if by_sector_1d else None
        best_sector_by_3d = max(by_sector_3d, key=lambda sector: (sum(by_sector_3d[sector]) / len(by_sector_3d[sector]))) if by_sector_3d else None
        worst_sector_by_3d = min(by_sector_3d, key=lambda sector: (sum(by_sector_3d[sector]) / len(by_sector_3d[sector]))) if by_sector_3d else None
        best_sector_by_7d = max(by_sector_7d, key=lambda sector: (sum(by_sector_7d[sector]) / len(by_sector_7d[sector]))) if by_sector_7d else None
        worst_sector_by_7d = min(by_sector_7d, key=lambda sector: (sum(by_sector_7d[sector]) / len(by_sector_7d[sector]))) if by_sector_7d else None
        sector_concentration_warning = None
        if sector_counts:
            top_sector = max(sector_counts, key=sector_counts.get)
            top_count = sector_counts[top_sector]
            total_count = max(1, len(candidate_rows))
            top_ratio = (top_count / total_count) * 100.0
            if top_ratio >= 60.0:
                sector_concentration_warning = (
                    f"{top_ratio:.0f}% of this cohort is {top_sector}. Review may be sector-biased."
                )
        horizon_28d_missing_count = max(0, len(candidate_rows) - horizon_28d_candidate_count)
        horizon_28d_available = bool(
            int(coverage["trading_days_elapsed"]) >= req.days_required
            and horizon_28d_candidate_count > 0
        )
        note = "insufficient data"
        if score_ret_pairs:
            up = sum(1 for score, ret in score_ret_pairs if score >= 75 and ret > 0)
            down = len(score_ret_pairs) - up
            note = f"high-score positive-follow-through={up}, otherwise={down}"
        if not sufficient_window:
            note = (
                f"daily snapshot coverage incomplete: {unique_days}/{expected_days} days "
                f"({coverage['snapshot_coverage_pct']}%). "
                "Invalidation/recovery path metrics are deferred until backfill. "
                f"Horizon outcome review is {'available' if horizon_review_available else 'pending price data'}."
            )
            false_positives = 0
            invalidated_quickly = 0
            missed_follow = 0
            best_sector_by_1d = None
            worst_sector_by_1d = None
            best_sector_by_3d = None
            worst_sector_by_3d = None
            best_sector_by_7d = None
            worst_sector_by_7d = None
        if horizon_28d_available and not daily_path_review_complete:
            warning = "Historical price horizon is available, but daily follow-up snapshots are incomplete. Run backfill."
        horizon_status = (
            f"available for {horizon_28d_candidate_count}/{len(candidate_rows)} candidates"
            if horizon_28d_available and horizon_28d_missing_count == 0
            else f"partially available for {horizon_28d_candidate_count}/{len(candidate_rows)} candidates"
            if horizon_28d_available
            else "pending price data"
            if int(coverage["trading_days_elapsed"]) >= req.days_required
            else f"pending elapsed trading days ({coverage['trading_days_elapsed']}/{req.days_required})"
        )
        path_status = "complete" if daily_path_review_complete else "incomplete until backfill"
        readiness_parts = [
            f"28D price horizon: {horizon_status}.",
            f"Daily snapshot coverage: {unique_days}/{expected_days} days ({coverage['snapshot_coverage_pct']}%).",
            f"Daily path review: {path_status}.",
            f"Horizon outcome review: {'available' if horizon_review_available else 'pending'}.",
        ]
        if warning:
            readiness_parts.append(warning)
        readiness = " ".join(readiness_parts)
        stats = CohortReviewStats(
            average_return_by_category=avg_7d_by_cat,
            return_since_selection_by_category=avg_since_by_cat,
            return_7d_by_category=avg_7d_by_cat,
            return_14d_by_category=avg_14d_by_cat,
            return_28d_by_category=avg_28d_by_cat,
            best_candidate=best_symbol_28d if horizon_28d_available else best_symbol,
            worst_candidate=worst_symbol_28d if horizon_28d_available else worst_symbol,
            best_category=best_cat,
            worst_category=worst_cat,
            horizon_28d_available=horizon_28d_available,
            horizon_28d_candidate_count=horizon_28d_candidate_count,
            horizon_28d_missing_count=horizon_28d_missing_count,
            horizon_28d_positive_count=horizon_28d_positive_count,
            horizon_28d_negative_count=horizon_28d_negative_count,
            best_candidate_by_28d=best_symbol_28d,
            worst_candidate_by_28d=worst_symbol_28d,
            best_category_by_28d=best_cat_28d,
            worst_category_by_28d=worst_cat_28d,
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
            average_return_by_sector_7d=avg_by_sector_7d,
            best_sector_by_1d=best_sector_by_1d,
            worst_sector_by_1d=worst_sector_by_1d,
            best_sector_by_3d=best_sector_by_3d,
            worst_sector_by_3d=worst_sector_by_3d,
            best_sector_by_7d=best_sector_by_7d,
            worst_sector_by_7d=worst_sector_by_7d,
            sector_concentration_warning=sector_concentration_warning,
            sector_candidate_distribution=sector_counts,
        )
        self._append_pipeline_event(
            step_name="cohort_review_completed",
            status="success",
            cohort_id=req.cohort_id,
            cohort_name=selected_name,
            message=(
                f"action=review selected_cohort_id={req.cohort_id} cohort_name={selected_name} "
                f"snapshot_coverage={unique_days}/{expected_days} horizon_28d_available={str(horizon_28d_available).lower()}"
            ),
        )
        llm_summary = None
        if sufficient_window and horizon_28d_available:
            prompt = (
                "You are a context-only final cohort reviewer.\n"
                "Do not change deterministic scores, categories, ranking, validity, or readiness.\n"
                "Do not give trade instructions. Suggest deterministic metric review ideas only.\n"
                "Summarize category performance, false positives, missed follow-through, and market-relative caveats in <=180 words.\n"
                f"cohort_id={req.cohort_id}\n"
                f"deterministic_stats={json.dumps(stats.model_dump(mode='json'), default=str)}\n"
            )
            try:
                llm_summary = self._ollama_generate(
                    prompt=prompt,
                    model=model,
                    timeout_seconds=req.timeout_seconds,
                    call_type="cohort_28d_review",
                    max_tokens_hint=320,
                    prompt_version=FINAL_28D_REVIEW_PROMPT_VERSION,
                )
            except Exception as exc:
                llm_summary = f"Final review LLM unavailable; deterministic stats remain authoritative. error={exc}"
        return CohortReviewResponse(
            cohort_id=req.cohort_id,
            readiness_message=readiness,
            days_collected=unique_days,
            days_required=expected_days,
            days_remaining=days_remaining,
            start_date=coverage["start_date"],
            latest_followup_date=coverage["latest_followup_date"],
            calendar_days_elapsed=coverage["calendar_days_elapsed"],
            trading_days_elapsed=coverage["trading_days_elapsed"],
            valid_followup_snapshot_days=coverage["valid_followup_snapshot_days"],
            expected_followup_days=expected_days,
            snapshot_coverage_pct=coverage["snapshot_coverage_pct"],
            missing_followup_days_count=coverage["missing_followup_days_count"],
            missing_followup_dates=coverage["missing_followup_dates"],
            horizon_28d_available=horizon_28d_available,
            horizon_outcome_review_available=horizon_review_available,
            daily_path_review_complete=daily_path_review_complete,
            snapshot_coverage_warning=warning,
            deterministic_stats=stats,
            llm_summary=llm_summary,
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
        report_mode: CohortReportMode = CohortReportMode.FOLLOWUP,
    ) -> IntelligenceRunReportExport:
        detail = self.get_cohort_detail(cohort_id)
        selected_cohort_id_used = detail.cohort.id
        mode_label = "latest_followup" if report_mode == CohortReportMode.FOLLOWUP else report_mode.value
        self._append_pipeline_event(
            step_name="cohort_export_started",
            status="running",
            cohort_id=detail.cohort.id,
            cohort_name=detail.cohort.name,
            message=f"action=export selected_cohort_id={selected_cohort_id_used} cohort_name={detail.cohort.name} report_mode={mode_label}",
        )
        review = self.run_cohort_review(CohortReviewRequest(cohort_id=cohort_id))
        latest_followup_date = max((x.snapshot_date for x in detail.snapshots), default=None)
        followup_snapshot_count = len(detail.snapshots)
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
        lines.append(f"- report_mode: `{mode_label}`")
        lines.append(f"- exported_at: `{exported_at.isoformat()}`")
        lines.append(f"- cohort_id: `{detail.cohort.id}`")
        lines.append(f"- cohort_name: `{detail.cohort.name}`")
        lines.append(f"- selected_cohort_id_used: `{selected_cohort_id_used}`")
        lines.append(f"- start_date: `{review.start_date or detail.cohort.start_date}`")
        lines.append(f"- latest_followup_date: `{latest_followup_date}`")
        lines.append(f"- calendar_days_elapsed: `{review.calendar_days_elapsed}`")
        lines.append(f"- trading_days_elapsed: `{review.trading_days_elapsed}`")
        lines.append(f"- valid_followup_snapshot_days: `{review.valid_followup_snapshot_days}`")
        lines.append(f"- expected_followup_days: `{review.expected_followup_days}`")
        lines.append(f"- snapshot_coverage_pct: `{review.snapshot_coverage_pct}%`")
        lines.append(f"- missing_followup_days_count: `{review.missing_followup_days_count}`")
        lines.append(f"- missing_followup_dates: `{json.dumps(review.missing_followup_dates, default=str)}`")
        lines.append(f"- candidate_count: `{len(detail.candidates)}`")
        lines.append(f"- followup_snapshot_count: `{followup_snapshot_count}`")
        if review.snapshot_coverage_warning:
            lines.append(f"- warning: {review.snapshot_coverage_warning}")
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
                snapshot = row.selected_structure_snapshot if isinstance(row.selected_structure_snapshot, dict) else {}
                selected_trigger_state = snapshot.get("trigger_state")
                selected_trigger_score = snapshot.get("trigger_score")
                selected_trigger_threshold = snapshot.get("trigger_threshold")
                selected_blocked_by = row.selected_blocked_by
                if selected_blocked_by == "none":
                    selected_blocked_by = self._blocked_by_from_risk_flags(row.selected_risk_flags, fallback="none")
                selected_displayed_score = (
                    row.selected_displayed_score
                    if row.selected_displayed_score and row.selected_displayed_score > 0
                    else (row.selected_score if row.selected_score > 0 else row.selected_final_score_capped)
                )
                selected_confirm_text = self._build_confirm_entry_text(
                    trigger_state=str(selected_trigger_state) if selected_trigger_state is not None else None,
                    trigger_score=float(selected_trigger_score) if isinstance(selected_trigger_score, (int, float)) else None,
                    trigger_threshold=float(selected_trigger_threshold) if isinstance(selected_trigger_threshold, (int, float)) else None,
                    blocked_by=selected_blocked_by,
                )
                lines.append(f"- Company: {row.selected_company_name or 'unknown'}")
                lines.append(f"- Sector: {row.selected_sector or 'unknown'}")
                lines.append(f"- Industry: {row.selected_industry or 'unknown'}")
                lines.append(f"- Original why selected: {row.selected_reason}")
                score_formula = (
                    f"{row.selected_base_score:.2f} base + {row.selected_category_boost:.2f} boost + "
                    f"{row.selected_data_quality_penalty:.2f} data_quality_penalty => {selected_displayed_score:.2f} displayed"
                )
                lines.append(f"- Score Breakdown: `{score_formula}`")
                lines.append(f"- Candidate Type: `{row.selected_candidate_type}`")
                lines.append(f"- Entry Readiness: `{row.selected_entry_readiness}`")
                lines.append(f"- Blocked By: `{selected_blocked_by}`")
                lines.append(f"- Readiness Explanation: {row.selected_readiness_explanation or '-'}")
                lines.append(f"- Main Opportunity Reason: {row.selected_main_opportunity_reason or '-'}")
                lines.append(f"- Main Risk: {row.selected_main_risk_reason or '-'}")
                lines.append(f"- Original selection-time confirm condition: {selected_confirm_text}")
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
            candidate_by_symbol = {cand.symbol: cand for cand in detail.candidates}
            if not detail.latest_states:
                lines.append("- No follow-up snapshot exists yet.")
            for state in detail.latest_states:
                selected = candidate_by_symbol.get(state.symbol)
                selected_threshold = 65.0
                if selected and isinstance(selected.selected_structure_snapshot, dict):
                    raw_thr = selected.selected_structure_snapshot.get("trigger_threshold")
                    if isinstance(raw_thr, (int, float)):
                        selected_threshold = float(raw_thr)
                trigger_confirmed = (
                    str(state.current_trigger_state or "").lower() == "confirmed"
                    or (
                        state.current_trigger_score is not None
                        and float(state.current_trigger_score) >= selected_threshold
                    )
                )
                current_confirm_text = self._build_confirm_entry_text(
                    trigger_state=state.current_trigger_state,
                    trigger_score=state.current_trigger_score,
                    trigger_threshold=selected_threshold,
                    blocked_by=state.blocked_by,
                )
                lines.append(
                    f"- {state.symbol}: latest_date={state.latest_followup_date} "
                    f"company={state.selected_company_name or 'unknown'} "
                    f"sector={state.selected_sector or 'unknown'} "
                    f"industry={state.selected_industry or 'unknown'} "
                    f"return_since_selection={state.return_since_selection if state.return_since_selection is not None else 'pending'} "
                    f"1D={state.return_1d if state.return_1d is not None else 'pending'} "
                    f"3D={state.return_3d if state.return_3d is not None else 'pending'} "
                    f"7D={state.return_7d if state.return_7d is not None else 'pending'} "
                    f"14D={state.return_14d if state.return_14d is not None else 'pending'} "
                    f"28D={state.return_28d if state.return_28d is not None else 'pending'} "
                    f"validity={state.validity_state} blocked_by={state.blocked_by}"
                )
                if selected:
                    lines.append(
                        f"  - selected_price={selected.selected_price if selected.selected_price is not None else 'pending'} "
                        f"latest_price={state.current_price if state.current_price is not None else 'pending'} "
                        f"return_since_selection={state.return_since_selection if state.return_since_selection is not None else 'pending'}"
                    )
                if state.data_quality_flags:
                    lines.append(f"  - data_quality_flags={','.join(state.data_quality_flags)}")
                lines.append(f"  - readiness={state.entry_readiness}; explanation={state.readiness_explanation}")
                lines.append(f"  - current_confirm_entry_condition={current_confirm_text}")
        if report_mode == CohortReportMode.LIFECYCLE:
            lines.append("")
            lines.append("## Full Follow-up Timeline")
            if not detail.snapshots:
                lines.append("- No follow-up snapshot exists yet.")
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
            lines.append(f"- 28D price horizon available: `{str(review.horizon_28d_available).lower()}`")
            lines.append(f"- Horizon outcome review: `{'available' if review.horizon_outcome_review_available else 'pending'}`")
            lines.append(f"- Daily snapshot coverage: `{review.valid_followup_snapshot_days}/{review.expected_followup_days} days ({review.snapshot_coverage_pct}%)`")
            lines.append(f"- Daily path review: `{'complete' if review.daily_path_review_complete else 'incomplete until backfill'}`")
            if review.snapshot_coverage_warning:
                lines.append(f"- Snapshot coverage caveat: {review.snapshot_coverage_warning}")
            lines.append("")
            lines.append("### Horizon Outcome Stats")
            lines.append(f"- 28D candidates available: `{review.deterministic_stats.horizon_28d_candidate_count}/{len(detail.candidates)}`")
            lines.append(f"- 28D positive/negative: `{review.deterministic_stats.horizon_28d_positive_count}/{review.deterministic_stats.horizon_28d_negative_count}`")
            lines.append(f"- Best candidate by 28D: `{review.deterministic_stats.best_candidate_by_28d or '-'}`")
            lines.append(f"- Worst candidate by 28D: `{review.deterministic_stats.worst_candidate_by_28d or '-'}`")
            lines.append(f"- Best category by 28D: `{review.deterministic_stats.best_category_by_28d or '-'}`")
            lines.append(f"- Worst category by 28D: `{review.deterministic_stats.worst_category_by_28d or '-'}`")
            lines.append("")
            lines.append("### Category Returns")
            lines.append(f"- Return since selection by category: `{json.dumps(review.deterministic_stats.return_since_selection_by_category, default=str)}`")
            lines.append(f"- 7D return by category: `{json.dumps(review.deterministic_stats.return_7d_by_category, default=str)}`")
            lines.append(f"- 14D return by category: `{json.dumps(review.deterministic_stats.return_14d_by_category, default=str)}`")
            lines.append(f"- 28D return by category: `{json.dumps(review.deterministic_stats.return_28d_by_category, default=str)}`")
            lines.append("")
            lines.append("### Daily Path Stats")
            lines.append(f"- false_positives: `{review.deterministic_stats.false_positives}`")
            lines.append(f"- missed_follow_through: `{review.deterministic_stats.missed_follow_through}`")
            lines.append(f"- stayed_valid: `{review.deterministic_stats.stayed_valid}`")
            lines.append(f"- invalidated_quickly: `{review.deterministic_stats.invalidated_quickly}`")
            lines.append(f"- score_delta_vs_return_note: {review.deterministic_stats.score_delta_vs_return_note}")
            lines.append(f"- LLM summary: {review.llm_summary or 'not generated'}")
        else:
            lines.append("")
            lines.append("## Review Snapshot")
            lines.append(f"- Readiness: {review.readiness_message}")
            lines.append(f"- start_date: `{review.start_date}`")
            lines.append(f"- latest_followup_date: `{review.latest_followup_date}`")
            lines.append(f"- calendar_days_elapsed: `{review.calendar_days_elapsed}`")
            lines.append(f"- trading_days_elapsed: `{review.trading_days_elapsed}`")
            lines.append(f"- daily snapshot coverage: `{review.valid_followup_snapshot_days}/{review.expected_followup_days} days ({review.snapshot_coverage_pct}%)`")
            lines.append(f"- missing_followup_days_count: `{review.missing_followup_days_count}`")
            lines.append(f"- missing_followup_dates: `{json.dumps(review.missing_followup_dates, default=str)}`")
            lines.append(f"- 28D price horizon: `{'available' if review.horizon_28d_available else 'pending or partial'}`")
            lines.append(f"- horizon outcome review: `{'available' if review.horizon_outcome_review_available else 'pending'}`")
            lines.append(f"- daily path review: `{'complete' if review.daily_path_review_complete else 'incomplete until backfill'}`")
            if review.snapshot_coverage_warning:
                lines.append(f"- snapshot coverage caveat: {review.snapshot_coverage_warning}")
            lines.append("")
            lines.append("### Category Returns")
            lines.append(f"- Return since selection by category: `{json.dumps(review.deterministic_stats.return_since_selection_by_category, default=str)}`")
            lines.append(f"- 7D return by category: `{json.dumps(review.deterministic_stats.return_7d_by_category, default=str)}`")
            lines.append(f"- 14D return by category: `{json.dumps(review.deterministic_stats.return_14d_by_category, default=str)}`")
            lines.append(f"- 28D return by category: `{json.dumps(review.deterministic_stats.return_28d_by_category, default=str)}`")
            lines.append("")
            lines.append("### 28D Outcome")
            lines.append(f"- 28D candidates available: `{review.deterministic_stats.horizon_28d_candidate_count}/{len(detail.candidates)}`")
            lines.append(f"- 28D positive/negative: `{review.deterministic_stats.horizon_28d_positive_count}/{review.deterministic_stats.horizon_28d_negative_count}`")
            lines.append(f"- Best candidate by 28D: `{review.deterministic_stats.best_candidate_by_28d or '-'}`")
            lines.append(f"- Worst candidate by 28D: `{review.deterministic_stats.worst_candidate_by_28d or '-'}`")
            lines.append(f"- Best category by 28D: `{review.deterministic_stats.best_category_by_28d or '-'}`")
            lines.append(f"- Worst category by 28D: `{review.deterministic_stats.worst_category_by_28d or '-'}`")
            if review.deterministic_stats.sector_candidate_distribution:
                lines.append(f"- Sector distribution: `{json.dumps(review.deterministic_stats.sector_candidate_distribution, default=str)}`")
            if review.deterministic_stats.average_return_by_sector_7d:
                lines.append(f"- Average return by sector (7D): `{json.dumps(review.deterministic_stats.average_return_by_sector_7d, default=str)}`")
            if review.deterministic_stats.sector_concentration_warning:
                lines.append(f"- Sector concentration warning: {review.deterministic_stats.sector_concentration_warning}")
        markdown = "\n".join(lines).strip() + "\n"
        export_path = self.base_dir / "exports" / filename
        export_path.write_text(markdown, encoding="utf-8")
        self._append_pipeline_event(
            step_name="cohort_export_completed",
            status="success",
            cohort_id=detail.cohort.id,
            cohort_name=detail.cohort.name,
            message=f"action=export selected_cohort_id={selected_cohort_id_used} cohort_name={detail.cohort.name} report_mode={mode_label} file={filename}",
        )
        return IntelligenceRunReportExport(
            run_id=cohort_id,
            filename=filename,
            report_mode=mode_label,
            cohort_id=cohort_id,
            selected_cohort_id_used=selected_cohort_id_used,
            exported_at=exported_at,
            start_date=review.start_date,
            latest_followup_date=latest_followup_date,
            calendar_days_elapsed=review.calendar_days_elapsed,
            trading_days_elapsed=review.trading_days_elapsed,
            valid_followup_snapshot_days=review.valid_followup_snapshot_days,
            expected_followup_days=review.expected_followup_days,
            snapshot_coverage_pct=review.snapshot_coverage_pct,
            missing_followup_days_count=review.missing_followup_days_count,
            missing_followup_dates=review.missing_followup_dates,
            followup_snapshot_count=followup_snapshot_count,
            markdown=markdown,
        )

    @staticmethod
    def _json_safe(value: Any) -> Any:
        return json.loads(json.dumps(value, default=str))

    @staticmethod
    def _slug(text: str) -> str:
        slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in (text or "").strip()).strip("-")
        while "--" in slug:
            slug = slug.replace("--", "-")
        return slug or "cohort"

    @staticmethod
    def _fmt_pct(value: float | None) -> str:
        return "pending" if value is None else f"{value:.2f}%"

    @staticmethod
    def _avg(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 3) if values else None

    @staticmethod
    def _observed_fixed_holiday(year: int, month: int, day: int) -> date:
        holiday = date(year, month, day)
        if holiday.weekday() == 5:
            return holiday - timedelta(days=1)
        if holiday.weekday() == 6:
            return holiday + timedelta(days=1)
        return holiday

    @staticmethod
    def _nth_weekday(year: int, month: int, weekday: int, nth: int) -> date:
        cursor = date(year, month, 1)
        while cursor.weekday() != weekday:
            cursor += timedelta(days=1)
        return cursor + timedelta(days=7 * (nth - 1))

    @staticmethod
    def _last_weekday(year: int, month: int, weekday: int) -> date:
        cursor = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
        while cursor.weekday() != weekday:
            cursor -= timedelta(days=1)
        return cursor

    @staticmethod
    def _easter_date(year: int) -> date:
        # Anonymous Gregorian algorithm, used here only to derive Good Friday.
        a = year % 19
        b = year // 100
        c = year % 100
        d = b // 4
        e = b % 4
        f = (b + 8) // 25
        g = (b - f + 1) // 3
        h = (19 * a + b - d - g + 15) % 30
        i = c // 4
        k = c % 4
        l = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * l) // 451
        month = (h + l - 7 * m + 114) // 31
        day = ((h + l - 7 * m + 114) % 31) + 1
        return date(year, month, day)

    @classmethod
    def _us_market_holidays(cls, year: int) -> set[date]:
        holidays = {
            cls._observed_fixed_holiday(year, 1, 1),
            cls._nth_weekday(year, 1, 0, 3),  # Martin Luther King Jr. Day
            cls._nth_weekday(year, 2, 0, 3),  # Washington's Birthday
            cls._easter_date(year) - timedelta(days=2),  # Good Friday
            cls._last_weekday(year, 5, 0),  # Memorial Day
            cls._observed_fixed_holiday(year, 6, 19),
            cls._observed_fixed_holiday(year, 7, 4),
            cls._nth_weekday(year, 9, 0, 1),  # Labor Day
            cls._nth_weekday(year, 11, 3, 4),  # Thanksgiving
            cls._observed_fixed_holiday(year, 12, 25),
        }
        next_new_year = cls._observed_fixed_holiday(year + 1, 1, 1)
        if next_new_year.year == year:
            holidays.add(next_new_year)
        return holidays

    @classmethod
    def _is_us_trading_day(cls, day: date) -> bool:
        return day.weekday() < 5 and day not in cls._us_market_holidays(day.year)

    def _previous_trading_day(self, day: date) -> date:
        cursor = day
        while not self._is_us_trading_day(cursor):
            cursor -= timedelta(days=1)
        return cursor

    def _trading_days_between(self, start: date, end: date) -> list[date]:
        if end < start:
            return []
        days: list[date] = []
        cursor = start
        while cursor <= end:
            if self._is_us_trading_day(cursor):
                days.append(cursor)
            cursor += timedelta(days=1)
        return days

    def _valid_followup_report_dates(self, cohort_id: str, *, through_date: date | None = None) -> set[date]:
        dates: set[date] = set()
        try:
            for row in self.daily_report_store.list_reports(cohort_id):
                if row.report_date and self._is_us_trading_day(row.report_date):
                    if row.followup_snapshot_count <= 0:
                        continue
                    if through_date is None or row.report_date <= through_date:
                        deterministic = row.deterministic_stats_json if isinstance(row.deterministic_stats_json, dict) else {}
                        if deterministic.get("trading_day") is False:
                            continue
                        dates.add(row.report_date)
        except Exception:
            pass
        for snap in self._read_cohort_snapshots():
            if snap.cohort_id != cohort_id:
                continue
            if through_date is not None and snap.snapshot_date > through_date:
                continue
            if self._is_us_trading_day(snap.snapshot_date):
                dates.add(snap.snapshot_date)
        return dates

    def _valid_followup_day_count(self, cohort: CandidateCohort, report_date: date) -> int:
        start = cohort.followup_start_date or cohort.start_date
        target = max(1, int(cohort.followup_target_days or 28))
        eligible = set(self._trading_days_between(start, report_date)[:target])
        valid_dates = self._valid_followup_report_dates(cohort.id, through_date=report_date)
        return len(eligible.intersection(valid_dates))

    @staticmethod
    def _calendar_day_count(start: date, end: date) -> int:
        if end < start:
            return 0
        return (end - start).days + 1

    @staticmethod
    def _parse_schedule_time(schedule: str | None) -> tuple[int, int]:
        raw = (schedule or "23:30").strip()
        if " " in raw:
            raw = raw.split()[-1]
        parts = raw.split(":")
        try:
            hour = max(0, min(23, int(parts[0])))
            minute = max(0, min(59, int(parts[1]) if len(parts) > 1 else 0))
            return hour, minute
        except (TypeError, ValueError):
            return 23, 30

    def _latest_due_report_date(self, *, now: datetime | None = None, schedule: str | None = None) -> date | None:
        tz = ZoneInfo(self.settings.daily_cohort_followup_timezone)
        local_now = (now or datetime.now(UTC)).astimezone(tz)
        hour, minute = self._parse_schedule_time(schedule or self.settings.daily_cohort_followup_schedule)
        scheduled_at = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        candidate = local_now.date()
        if not self._is_us_trading_day(candidate) or local_now < scheduled_at:
            candidate -= timedelta(days=1)
        return self._previous_trading_day(candidate)

    def should_run_daily_cohort_followup_job(self, *, now: datetime | None = None) -> bool:
        if not self.settings.daily_cohort_followup_enabled:
            return False
        if not self.daily_report_store.configured:
            if not self._daily_followup_db_warning_logged:
                self._logger.warning("daily_cohort_followup_job skipped: DATABASE_URL is not configured")
                self.log_daily_followup_scheduler_event(
                    "job_failed",
                    status="failed",
                    error_message="DATABASE_URL is not configured",
                )
                self._daily_followup_db_warning_logged = True
            return False
        due_date = self._latest_due_report_date(now=now)
        if due_date is None:
            return False
        for cohort in self._active_followup_cohorts():
            missing = self._missing_report_dates_for_cohort(cohort, due_date=due_date, backfill=True)
            if missing:
                return True
        return False

    def run_due_daily_cohort_followup_job(self) -> CohortDailyReportRunResponse:
        return self.run_daily_cohort_followup_job(backfill=True, include_llm=True, force=False)

    def run_daily_cohort_followup_job(
        self,
        *,
        cohort_id: str | None = None,
        report_date: date | None = None,
        backfill: bool = True,
        include_llm: bool = True,
        force: bool = False,
    ) -> CohortDailyReportRunResponse:
        run_at = datetime.now(UTC)
        job_started = datetime.now(UTC)
        self.log_daily_followup_scheduler_event(
            "job_started",
            status="running",
            cohort_id=cohort_id,
            report_date=report_date.isoformat() if report_date else None,
            include_llm=include_llm,
            backfill=backfill,
            force=force,
        )
        response = CohortDailyReportRunResponse(run_at=run_at, requested_cohort_id=cohort_id)
        cohorts = self._read_cohorts()
        if cohort_id:
            selected = next((row for row in cohorts if row.id == cohort_id), None)
            if selected is None:
                raise FileNotFoundError(f"Cohort not found: {cohort_id}")
            target_cohorts = [selected]
        else:
            target_cohorts = self._active_followup_cohorts()
        self.log_daily_followup_scheduler_event(
            "job_discovered_active_cohorts",
            status="success",
            active_followup_cohorts_count=len(target_cohorts),
        )
        if not target_cohorts:
            response.skipped = 1
            response.errors.append("No active cohorts are marked for automated follow-up.")
            self.log_daily_followup_scheduler_event(
                "job_skipped_no_active_cohorts",
                status="success",
                duration_ms=int((datetime.now(UTC) - job_started).total_seconds() * 1000),
            )
            return response

        for cohort in target_cohorts:
            due_date = report_date or self._latest_due_report_date(schedule=cohort.followup_schedule)
            if due_date is None:
                response.skipped += 1
                self.log_daily_followup_scheduler_event(
                    "job_skipped_market_closed",
                    status="success",
                    cohort_id=cohort.id,
                    duration_ms=int((datetime.now(UTC) - job_started).total_seconds() * 1000),
                )
                continue
            if report_date:
                target_dates = [report_date]
            else:
                target_dates = self._missing_report_dates_for_cohort(cohort, due_date=due_date, backfill=backfill)
            if not target_dates and force:
                target_dates = [due_date]
            if not target_dates:
                response.skipped += 1
                continue
            for target_date in target_dates:
                try:
                    self._append_pipeline_event(
                        step_name="daily_cohort_followup_job_started",
                        status="running",
                        cohort_id=cohort.id,
                        cohort_name=cohort.name,
                        message=f"report_date={target_date.isoformat()} include_llm={str(include_llm).lower()}",
                    )
                    detail = self._generate_and_store_daily_report(
                        cohort_id=cohort.id,
                        report_date=target_date,
                        include_llm=include_llm,
                    )
                    self.log_daily_followup_scheduler_event(
                        "job_report_upserted",
                        status="success",
                        cohort_id=cohort.id,
                        cohort_name=cohort.name,
                        report_date=target_date.isoformat(),
                        export_path=detail.export_path,
                        fallback_used=detail.fallback_used,
                    )
                    if detail.export_path:
                        self.log_daily_followup_scheduler_event(
                            "job_markdown_exported",
                            status="success",
                            cohort_id=cohort.id,
                            cohort_name=cohort.name,
                            report_date=target_date.isoformat(),
                            export_path=detail.export_path,
                        )
                    response.generated += 1
                    response.report_dates.append(target_date)
                    response.reports.append(CohortDailyReportSummary.model_validate(detail.model_dump()))
                    self._append_pipeline_event(
                        step_name="daily_cohort_followup_job_completed",
                        status="success",
                        cohort_id=cohort.id,
                        cohort_name=cohort.name,
                        message=f"report_date={target_date.isoformat()} export_path={detail.export_path}",
                    )
                except Exception as exc:
                    response.failed += 1
                    error = f"{cohort.name} {target_date.isoformat()}: {type(exc).__name__}: {exc}"
                    response.errors.append(error)
                    self.log_daily_followup_scheduler_event(
                        "job_failed",
                        status="failed",
                        cohort_id=cohort.id,
                        cohort_name=cohort.name,
                        report_date=target_date.isoformat(),
                        duration_ms=int((datetime.now(UTC) - job_started).total_seconds() * 1000),
                        error_message=str(exc),
                    )
                    self._append_pipeline_event(
                        step_name="daily_cohort_followup_job_completed",
                        status="failed",
                        cohort_id=cohort.id,
                        cohort_name=cohort.name,
                        message=f"report_date={target_date.isoformat()}",
                        error_message=str(exc),
                    )
                    self._logger.exception("daily_cohort_followup_job failed cohort_id=%s report_date=%s", cohort.id, target_date)
            self._mark_followup_completed_if_needed(cohort.id)
        self.log_daily_followup_scheduler_event(
            "job_completed",
            status="success" if response.failed == 0 else "failed",
            duration_ms=int((datetime.now(UTC) - job_started).total_seconds() * 1000),
            generated=response.generated,
            skipped=response.skipped,
            failed=response.failed,
            error_message="; ".join(response.errors) if response.errors else None,
        )
        return response

    def backfill_cohort_followup(
        self,
        cohort_id: str,
        from_date: date | None = None,
        to_date: date | None = None,
        *,
        include_llm: bool = False,
    ) -> CohortDailyReportRunResponse:
        detail = self.get_cohort_detail(cohort_id)
        start_date = from_date or detail.cohort.followup_start_date or detail.cohort.start_date
        latest_followup_date = self._latest_followup_date_for_cohort(cohort_id, detail.snapshots)
        end_date = to_date or latest_followup_date or self._latest_due_report_date(schedule=detail.cohort.followup_schedule) or date.today()
        response = CohortDailyReportRunResponse(run_at=datetime.now(UTC), requested_cohort_id=cohort_id)
        if end_date < start_date:
            response.skipped = 1
            response.errors.append(f"Backfill end date {end_date.isoformat()} is before start date {start_date.isoformat()}.")
            return response
        target_dates = self._trading_days_between(start_date, end_date)
        existing_dates = self._existing_daily_report_dates(cohort_id)
        missing_dates = [target_date for target_date in target_dates if target_date not in existing_dates]
        self.log_daily_followup_scheduler_event(
            "backfill_started",
            status="running",
            cohort_id=detail.cohort.id,
            cohort_name=detail.cohort.name,
            report_date=end_date.isoformat(),
            include_llm=include_llm,
            from_date=start_date.isoformat(),
            to_date=end_date.isoformat(),
            missing_days=len(missing_dates),
        )
        self._append_pipeline_event(
            step_name="cohort_followup_backfill_started",
            status="running",
            cohort_id=detail.cohort.id,
            cohort_name=detail.cohort.name,
            message=f"from_date={start_date.isoformat()} to_date={end_date.isoformat()} missing_days={len(missing_dates)} include_llm={str(include_llm).lower()}",
        )
        if not self.daily_report_store.configured:
            response.failed = len(missing_dates) or 1
            response.errors.append("DATABASE_URL is not configured; backfill requires Postgres daily report storage.")
            self.log_daily_followup_scheduler_event(
                "backfill_failed",
                status="failed",
                cohort_id=detail.cohort.id,
                cohort_name=detail.cohort.name,
                error_message=response.errors[-1],
            )
            return response
        if not missing_dates:
            response.skipped = 1
            self.log_daily_followup_scheduler_event(
                "backfill_skipped_no_missing_days",
                status="success",
                cohort_id=detail.cohort.id,
                cohort_name=detail.cohort.name,
                from_date=start_date.isoformat(),
                to_date=end_date.isoformat(),
            )
            return response
        for target_date in missing_dates:
            try:
                report = self._generate_and_store_daily_report(
                    cohort_id=cohort_id,
                    report_date=target_date,
                    include_llm=include_llm,
                )
                response.generated += 1
                response.report_dates.append(target_date)
                response.reports.append(CohortDailyReportSummary.model_validate(report.model_dump()))
            except Exception as exc:
                response.failed += 1
                response.errors.append(f"{detail.cohort.name} {target_date.isoformat()}: {type(exc).__name__}: {exc}")
                self._logger.exception("cohort_followup_backfill failed cohort_id=%s report_date=%s", cohort_id, target_date)
        self._mark_followup_completed_if_needed(cohort_id)
        self.log_daily_followup_scheduler_event(
            "backfill_completed",
            status="success" if response.failed == 0 else "failed",
            cohort_id=detail.cohort.id,
            cohort_name=detail.cohort.name,
            from_date=start_date.isoformat(),
            to_date=end_date.isoformat(),
            generated=response.generated,
            failed=response.failed,
            error_message="; ".join(response.errors) if response.errors else None,
        )
        self._append_pipeline_event(
            step_name="cohort_followup_backfill_completed",
            status="success" if response.failed == 0 else "failed",
            cohort_id=detail.cohort.id,
            cohort_name=detail.cohort.name,
            message=f"generated={response.generated} failed={response.failed}",
            error_message="; ".join(response.errors) if response.errors else None,
        )
        return response

    def _active_followup_cohorts(self) -> list[CandidateCohort]:
        return [
            row
            for row in self._read_cohorts()
            if row.status == CandidateCohortStatus.ACTIVE
            and row.followup_enabled
            and not row.followup_completed
        ]

    def _existing_daily_report_dates(self, cohort_id: str) -> set[date]:
        try:
            return {row.report_date for row in self.daily_report_store.list_reports(cohort_id)}
        except Exception as exc:
            self._logger.warning("cohort_daily_reports lookup unavailable cohort_id=%s error=%s", cohort_id, exc)
            return {row.snapshot_date for row in self._read_cohort_snapshots() if row.cohort_id == cohort_id}

    def _missing_report_dates_for_cohort(self, cohort: CandidateCohort, *, due_date: date, backfill: bool) -> list[date]:
        start = cohort.followup_start_date or cohort.start_date
        target_days = max(1, int(cohort.followup_target_days or 28))
        eligible = self._trading_days_between(start, due_date)[:target_days]
        if not eligible:
            return []
        existing = self._existing_daily_report_dates(cohort.id)
        missing = [day for day in eligible if day not in existing]
        return missing if backfill else missing[-1:]

    def _mark_followup_completed_if_needed(self, cohort_id: str) -> None:
        cohorts = self._read_cohorts()
        changed = False
        next_rows: list[CandidateCohort] = []
        for cohort in cohorts:
            if cohort.id != cohort_id:
                next_rows.append(cohort)
                continue
            target_days = max(1, int(cohort.followup_target_days or 28))
            valid_dates = self._valid_followup_report_dates(cohort_id)
            if len(valid_dates) >= target_days and not cohort.followup_completed:
                cohort = cohort.model_copy(update={"followup_completed": True, "status": CandidateCohortStatus.COMPLETED})
                changed = True
            next_rows.append(cohort)
        if changed:
            self._save_cohorts(next_rows)

    def _generate_and_store_daily_report(self, *, cohort_id: str, report_date: date, include_llm: bool) -> CohortDailyReportDetail:
        trading_day = self._is_us_trading_day(report_date)
        market_open = trading_day
        followup = self.run_cohort_followup(CohortFollowupRequest(cohort_id=cohort_id, report_date=report_date))
        detail = self.get_cohort_detail(cohort_id)
        snapshots_for_date = [row for row in followup.snapshots if row.snapshot_date == report_date]
        market_context = self._collect_market_context(report_date)
        market_context["trading_day"] = trading_day
        market_context["market_open"] = market_open
        if not trading_day:
            market_context.setdefault("event_flags", [])
            market_context["limitations"] = list(market_context.get("limitations", [])) + [
                "Report date is not a US trading day; follow-up snapshot count does not advance."
            ]
        candidate_rows = self._build_candidate_followup_rows(detail.candidates, snapshots_for_date, report_date)
        followup_day_number = self._followup_day_number(detail.cohort, report_date)
        valid_followup_day_count = followup_day_number
        calendar_day_count = self._calendar_day_count(detail.cohort.followup_start_date or detail.cohort.start_date, report_date)
        deterministic_stats = self._compute_daily_report_stats(
            cohort=detail.cohort,
            candidate_rows=candidate_rows,
            followup_day_number=followup_day_number,
            trading_day=trading_day,
            market_open=market_open,
            valid_followup_day_count=valid_followup_day_count,
            calendar_day_count=calendar_day_count,
        )
        coverage = self._cohort_followup_coverage(
            detail.cohort,
            detail.snapshots,
            days_required=max(1, int(detail.cohort.followup_target_days or 28)),
            through_date=report_date,
        )
        deterministic_stats.update(coverage)
        fallback_used = False
        error_messages: list[str] = []
        market_note = None
        llm_summary = None
        llm_provider = self._normalize_provider(self.settings.llm_provider)
        llm_model = self.settings.daily_report_llm_model
        if include_llm:
            market_note, market_meta = self._generate_market_context_note(market_context)
            if market_note:
                market_context["llm_note"] = market_note
            market_context["llm_metadata"] = market_meta
            fallback_used = fallback_used or bool(market_meta.get("fallback_used"))
            if market_meta.get("error_message"):
                error_messages.append(str(market_meta["error_message"]))
            llm_summary, daily_meta = self._generate_daily_report_summary(
                detail.cohort,
                report_date,
                deterministic_stats,
                candidate_rows,
                market_context,
            )
            llm_provider = str(daily_meta.get("provider") or llm_provider)
            llm_model = str(daily_meta.get("model") or llm_model)
            fallback_used = fallback_used or bool(daily_meta.get("fallback_used"))
            if daily_meta.get("error_message"):
                error_messages.append(str(daily_meta["error_message"]))
        else:
            llm_summary = "LLM summary skipped by request; deterministic report is available."
            fallback_used = True
        if not llm_summary:
            llm_summary = self._deterministic_daily_summary(deterministic_stats, market_context)
            fallback_used = True
        markdown = self._render_daily_report_markdown(
            cohort=detail.cohort,
            report_date=report_date,
            followup_day_number=followup_day_number,
            candidate_rows=candidate_rows,
            deterministic_stats=deterministic_stats,
            market_context=market_context,
            llm_summary=llm_summary,
            fallback_used=fallback_used,
            error_message="; ".join(error_messages) if error_messages else None,
            llm_provider=llm_provider,
            llm_model=llm_model,
            prompt_version=DAILY_REPORT_PROMPT_VERSION,
            llm_context_summary_present=bool(llm_summary),
            followup_snapshot_count=len(snapshots_for_date),
        )
        export_path = self._write_daily_report_markdown(detail.cohort, report_date, markdown)
        record = {
            "id": str(uuid4()),
            "cohort_id": cohort_id,
            "cohort_name": detail.cohort.name,
            "report_date": report_date,
            "report_mode": "followup",
            "candidate_count": len(detail.candidates),
            "followup_snapshot_count": len(snapshots_for_date),
            "deterministic_stats_json": self._json_safe(deterministic_stats),
            "candidate_followup_json": self._json_safe(candidate_rows),
            "market_context_json": self._json_safe(market_context),
            "llm_context_summary": llm_summary,
            "report_markdown": markdown,
            "export_path": str(export_path),
            "engine_version": self._engine_version(),
            "git_commit": self._git_commit(),
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "prompt_version": DAILY_REPORT_PROMPT_VERSION,
            "fallback_used": fallback_used,
            "error_message": "; ".join(error_messages) if error_messages else None,
        }
        return self.daily_report_store.upsert_report(record)

    def _followup_day_number(self, cohort: CandidateCohort, report_date: date) -> int:
        target = max(1, int(cohort.followup_target_days or 28))
        return min(max(0, self._valid_followup_day_count(cohort, report_date)), target)

    def _market_proxy_returns(self, symbol: str, report_date: date) -> dict[str, Any]:
        try:
            requested_symbol = normalize_symbol(symbol, "us").strip().upper()
            bundle = self.analysis_engine.data_service.get_market_data(symbol, market="us", period="2y", use_cache=False)
            bundle_symbol = str(getattr(bundle, "normalized_ticker", "") or "").strip().upper()
            if requested_symbol and bundle_symbol and requested_symbol != bundle_symbol:
                raise RuntimeError(f"source symbol mismatch: requested={requested_symbol} source={bundle_symbol}")
            close = bundle.daily["close"].dropna().astype(float)
            close = close[close.index.map(lambda ts: ts.date() <= report_date)]
            if close.empty:
                raise RuntimeError("missing price series")
            latest = float(close.iloc[-1])
            latest_date = close.index[-1].date()
            returns: dict[str, float | None] = {}
            for days, label in [(1, "1d"), (3, "3d"), (7, "7d"), (14, "14d"), (28, "28d")]:
                if len(close) <= days:
                    returns[label] = None
                    continue
                ref = float(close.iloc[-(days + 1)])
                returns[label] = round(float((latest - ref) / ref * 100.0), 4) if ref > 0 else None
            return {
                "symbol": symbol,
                "as_of_date": latest_date.isoformat(),
                "latest_price": latest,
                "returns": returns,
                "error": None,
            }
        except Exception as exc:
            return {
                "symbol": symbol,
                "as_of_date": None,
                "latest_price": None,
                "returns": {"1d": None, "3d": None, "7d": None, "14d": None, "28d": None},
                "error": str(exc),
            }

    def _collect_market_context(self, report_date: date) -> dict[str, Any]:
        broad = {symbol: self._market_proxy_returns(symbol, report_date) for symbol in ["SPY", "QQQ", "IWM"]}
        sector_map = {
            "semiconductors": "SMH",
            "technology": "XLK",
            "financials": "XLF",
            "healthcare": "XLV",
            "energy": "XLE",
            "staples": "XLP",
            "consumer_discretionary": "XLY",
            "communication_services": "XLC",
        }
        sectors = {key: self._market_proxy_returns(symbol, report_date) for key, symbol in sector_map.items()}
        macro = {
            "VIX": self._market_proxy_returns("^VIX", report_date),
            "US_10Y_YIELD": self._market_proxy_returns("^TNX", report_date),
            "DXY": self._market_proxy_returns("DX-Y.NYB", report_date),
        }
        event_flags = self._derive_market_event_flags(broad, sectors, macro)
        spy_1d = self._return_from_context(broad.get("SPY"), "1d")
        qqq_1d = self._return_from_context(broad.get("QQQ"), "1d")
        vix_1d = self._return_from_context(macro.get("VIX"), "1d")
        if "broad_market_risk_off" in event_flags:
            regime_note = "risk_off"
        elif spy_1d is not None and qqq_1d is not None and spy_1d > 0 and qqq_1d > 0 and (vix_1d is None or vix_1d <= 0):
            regime_note = "risk_on"
        else:
            regime_note = "mixed"
        return {
            "report_date": report_date.isoformat(),
            "broad_market": broad,
            "sector_theme_proxies": sectors,
            "macro_proxies": macro,
            "event_flags": event_flags,
            "regime_note": regime_note,
            "limitations": ["Event calendar and news integration are not connected in this deterministic snapshot."],
        }

    @staticmethod
    def _return_from_context(row: dict[str, Any] | None, label: str) -> float | None:
        if not isinstance(row, dict):
            return None
        returns = row.get("returns")
        if not isinstance(returns, dict):
            return None
        value = returns.get(label)
        return float(value) if isinstance(value, (int, float)) else None

    def _derive_market_event_flags(
        self,
        broad: dict[str, dict[str, Any]],
        sectors: dict[str, dict[str, Any]],
        macro: dict[str, dict[str, Any]],
    ) -> list[str]:
        flags: list[str] = []
        spy_1d = self._return_from_context(broad.get("SPY"), "1d")
        qqq_1d = self._return_from_context(broad.get("QQQ"), "1d")
        vix_1d = self._return_from_context(macro.get("VIX"), "1d")
        smh_1d = self._return_from_context(sectors.get("semiconductors"), "1d")
        smh_3d = self._return_from_context(sectors.get("semiconductors"), "3d")
        if (smh_1d is not None and smh_1d <= -3.0) or (smh_3d is not None and smh_3d <= -5.0):
            flags.append("major_semiconductor_selloff")
        if (
            spy_1d is not None
            and qqq_1d is not None
            and spy_1d <= -1.5
            and qqq_1d <= -1.5
        ) or (vix_1d is not None and vix_1d >= 8.0):
            flags.append("broad_market_risk_off")
        sector_1d = [self._return_from_context(row, "1d") for row in sectors.values()]
        sector_1d = [float(x) for x in sector_1d if x is not None]
        if sector_1d and (max(sector_1d) - min(sector_1d)) >= 3.0:
            flags.append("sector_rotation")
        return sorted(set(flags))

    def _sector_proxy_for_candidate(self, cand: CohortCandidate) -> str | None:
        text = f"{cand.selected_sector or ''} {cand.selected_industry or ''}".lower()
        if "semiconductor" in text or "chip" in text:
            return "SMH"
        if "financial" in text or "bank" in text:
            return "XLF"
        if "health" in text or "pharma" in text or "drug" in text or "biotech" in text:
            return "XLV"
        if "energy" in text or "oil" in text or "gas" in text:
            return "XLE"
        if "consumer defensive" in text or "consumer staples" in text or "staples" in text:
            return "XLP"
        if "consumer cyclical" in text or "consumer discretionary" in text or "discretionary" in text:
            return "XLY"
        if "communication" in text or "telecom" in text or "media" in text:
            return "XLC"
        if "technology" in text or "software" in text or "hardware" in text:
            return "XLK"
        return None

    def _return_between_dates(self, symbol: str, market: str, start_date: date, end_date: date) -> float | None:
        try:
            requested_symbol = normalize_symbol(symbol, market).strip().upper()
            bundle = self.analysis_engine.data_service.get_market_data(symbol, market=market, period="2y", use_cache=False)
            bundle_symbol = str(getattr(bundle, "normalized_ticker", "") or "").strip().upper()
            if requested_symbol and bundle_symbol and requested_symbol != bundle_symbol:
                self._logger.warning(
                    "[relative_return] symbol=%s source_symbol=%s status=mismatch",
                    requested_symbol,
                    bundle_symbol,
                )
                return None
            close = bundle.daily["close"].dropna().astype(float)
            start_series = close[close.index.map(lambda ts: ts.date() >= start_date)]
            end_series = close[close.index.map(lambda ts: ts.date() <= end_date)]
            if start_series.empty or end_series.empty:
                return None
            start_price = float(start_series.iloc[0])
            end_price = float(end_series.iloc[-1])
            if start_price <= 0:
                return None
            return round(float((end_price - start_price) / start_price * 100.0), 4)
        except Exception:
            return None

    def _build_candidate_followup_rows(
        self,
        candidates: list[CohortCandidate],
        snapshots: list[CohortDailySnapshot],
        report_date: date,
    ) -> list[dict[str, Any]]:
        snapshot_by_symbol = {row.symbol: row for row in snapshots}
        rows: list[dict[str, Any]] = []
        for cand in sorted(candidates, key=lambda row: row.selected_rank):
            snap = snapshot_by_symbol.get(cand.symbol)
            absolute = snap.return_since_selection if snap else None
            spy_return = self._return_between_dates("SPY", "us", cand.selected_at.date(), report_date)
            qqq_return = self._return_between_dates("QQQ", "us", cand.selected_at.date(), report_date)
            sector_proxy = self._sector_proxy_for_candidate(cand)
            sector_return = self._return_between_dates(sector_proxy, "us", cand.selected_at.date(), report_date) if sector_proxy else None
            relative_spy = round(float(absolute) - spy_return, 4) if absolute is not None and spy_return is not None else None
            relative_qqq = round(float(absolute) - qqq_return, 4) if absolute is not None and qqq_return is not None else None
            relative_sector = round(float(absolute) - sector_return, 4) if absolute is not None and sector_return is not None else None
            data_quality_flags = list(snap.data_quality_flags if snap else [])
            validity_state = str(snap.validity_state if snap else "pending_validation")
            if data_quality_flags:
                validity_state = "needs_data_check"
            if validity_state not in {"pending_validation", "valid", "invalid", "needs_data_check"}:
                validity_state = "pending_validation"
            rows.append(
                {
                    "symbol": cand.symbol,
                    "company_name": cand.selected_company_name,
                    "sector": cand.selected_sector,
                    "industry": cand.selected_industry,
                    "selected_rank": cand.selected_rank,
                    "selected_categories": [x.value if hasattr(x, "value") else str(x) for x in cand.selected_categories],
                    "selected_setup_type": cand.selected_setup_type,
                    "selected_price": cand.selected_price,
                    "latest_price": snap.current_price if snap else None,
                    "absolute_return_since_selection": absolute,
                    "return_since_selection": absolute,
                    "return_1d": snap.return_1d if snap else None,
                    "return_3d": snap.return_3d if snap else None,
                    "return_7d": snap.return_7d if snap else None,
                    "return_14d": snap.return_14d if snap else None,
                    "return_28d": snap.return_28d if snap else None,
                    "relative_to_SPY": relative_spy,
                    "relative_to_QQQ": relative_qqq,
                    "relative_to_sector_proxy": relative_sector,
                    "sector_proxy": sector_proxy,
                    "sector_proxy_return_since_selection": sector_return,
                    "spy_return_since_selection": spy_return,
                    "qqq_return_since_selection": qqq_return,
                    "validity_state": validity_state,
                    "readiness": "needs_data_check" if data_quality_flags else (snap.entry_readiness if snap else "pending_validation"),
                    "blocked_by": "data_quality" if data_quality_flags else (snap.blocked_by if snap else "none"),
                    "invalidation_reason": snap.invalidation_reason if snap else None,
                    "readiness_explanation": snap.readiness_explanation if snap else "Awaiting follow-up snapshot.",
                    "data_quality_flags": data_quality_flags,
                }
            )
        return rows

    def _compute_daily_report_stats(
        self,
        *,
        cohort: CandidateCohort,
        candidate_rows: list[dict[str, Any]],
        followup_day_number: int,
        trading_day: bool,
        market_open: bool,
        valid_followup_day_count: int,
        calendar_day_count: int,
    ) -> dict[str, Any]:
        counts = {"pending_validation": 0, "valid": 0, "invalid": 0, "needs_data_check": 0}
        return_since_by_category: dict[str, list[float]] = {}
        return_7d_by_category: dict[str, list[float]] = {}
        return_14d_by_category: dict[str, list[float]] = {}
        return_28d_by_category: dict[str, list[float]] = {}
        rel_spy_by_category: dict[str, list[float]] = {}
        rel_qqq_by_category: dict[str, list[float]] = {}
        rel_sector_by_category: dict[str, list[float]] = {}
        for row in candidate_rows:
            state = str(row.get("validity_state") or "pending_validation")
            if state not in counts:
                state = "pending_validation"
            counts[state] += 1
            if state == "needs_data_check":
                continue
            categories = [str(x) for x in row.get("selected_categories", [])]
            absolute = row.get("absolute_return_since_selection")
            rel_spy = row.get("relative_to_SPY")
            rel_qqq = row.get("relative_to_QQQ")
            rel_sector = row.get("relative_to_sector_proxy")
            ret7 = row.get("return_7d")
            ret14 = row.get("return_14d")
            ret28 = row.get("return_28d")
            for cat in categories:
                if isinstance(absolute, (int, float)):
                    return_since_by_category.setdefault(cat, []).append(float(absolute))
                if isinstance(ret7, (int, float)):
                    return_7d_by_category.setdefault(cat, []).append(float(ret7))
                if isinstance(ret14, (int, float)):
                    return_14d_by_category.setdefault(cat, []).append(float(ret14))
                if isinstance(ret28, (int, float)):
                    return_28d_by_category.setdefault(cat, []).append(float(ret28))
                if isinstance(rel_spy, (int, float)):
                    rel_spy_by_category.setdefault(cat, []).append(float(rel_spy))
                if isinstance(rel_qqq, (int, float)):
                    rel_qqq_by_category.setdefault(cat, []).append(float(rel_qqq))
                if isinstance(rel_sector, (int, float)):
                    rel_sector_by_category.setdefault(cat, []).append(float(rel_sector))
        avg_by_category = {cat: self._avg(vals) for cat, vals in return_since_by_category.items()}
        avg_by_category = {cat: val for cat, val in avg_by_category.items() if val is not None}
        avg_7d_by_category = {cat: self._avg(vals) for cat, vals in return_7d_by_category.items()}
        avg_7d_by_category = {cat: val for cat, val in avg_7d_by_category.items() if val is not None}
        avg_14d_by_category = {cat: self._avg(vals) for cat, vals in return_14d_by_category.items()}
        avg_14d_by_category = {cat: val for cat, val in avg_14d_by_category.items() if val is not None}
        avg_28d_by_category = {cat: self._avg(vals) for cat, vals in return_28d_by_category.items()}
        avg_28d_by_category = {cat: val for cat, val in avg_28d_by_category.items() if val is not None}
        enough_history = followup_day_number >= max(1, int(cohort.followup_target_days or 28))
        best_category = max(avg_by_category, key=avg_by_category.get) if enough_history and avg_by_category else None
        worst_category = min(avg_by_category, key=avg_by_category.get) if enough_history and avg_by_category else None
        pending_horizon_counts = {
            "7d": sum(1 for row in candidate_rows if row.get("return_7d") is None),
            "14d": sum(1 for row in candidate_rows if row.get("return_14d") is None),
            "28d": sum(1 for row in candidate_rows if row.get("return_28d") is None),
        }
        pending_any_required_horizon_count = sum(
            1
            for row in candidate_rows
            if row.get("return_7d") is None or row.get("return_14d") is None or row.get("return_28d") is None
        )
        return {
            "followup_day_number": followup_day_number,
            "followup_target_days": max(1, int(cohort.followup_target_days or 28)),
            "trading_day": trading_day,
            "market_open": market_open,
            "valid_followup_day_count": valid_followup_day_count,
            "calendar_day_count": calendar_day_count,
            "candidate_count": len(candidate_rows),
            "validity_counts": counts,
            "average_return_by_category": avg_by_category,
            "return_since_selection_by_category": avg_by_category,
            "return_7d_by_category": avg_7d_by_category,
            "return_14d_by_category": avg_14d_by_category,
            "return_28d_by_category": avg_28d_by_category,
            "average_relative_to_SPY_by_category": {cat: self._avg(vals) for cat, vals in rel_spy_by_category.items()},
            "average_relative_to_QQQ_by_category": {cat: self._avg(vals) for cat, vals in rel_qqq_by_category.items()},
            "average_relative_to_sector_proxy_by_category": {cat: self._avg(vals) for cat, vals in rel_sector_by_category.items()},
            "best_category": best_category,
            "worst_category": worst_category,
            "best_worst_deferred": not enough_history,
            "data_quality_exclusion_count": counts["needs_data_check"],
            "pending_horizon_count": pending_any_required_horizon_count,
            "pending_horizon_counts": pending_horizon_counts,
            "pending_7d_count": pending_horizon_counts["7d"],
            "pending_14d_count": pending_horizon_counts["14d"],
            "pending_28d_count": pending_horizon_counts["28d"],
        }

    def _generate_market_context_note(self, market_context: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
        model = self.settings.market_context_llm_model
        provider = self._normalize_provider(self.settings.llm_provider)
        prompt = (
            "You are a context-only market regime summarizer. Do not give trade instructions.\n"
            "Explain broad market, sector pressure/support, event flags, and caveats in <=140 words.\n"
            f"market_context={json.dumps(self._json_safe(market_context))}\n"
        )
        started = datetime.now(UTC)
        try:
            text = self._ollama_generate(
                prompt=prompt,
                model=model,
                timeout_seconds=45.0,
                call_type="market_context_note",
                max_tokens_hint=220,
                prompt_version=MARKET_CONTEXT_PROMPT_VERSION,
            )
            log = self._latest_llm_log(call_type="market_context_note", since=started)
            return text, {
                "provider": log.provider if log else provider,
                "model": log.model if log else model,
                "prompt_version": MARKET_CONTEXT_PROMPT_VERSION,
                "fallback_used": bool(log.fallback_used) if log else False,
                "duration_ms": log.duration_ms if log else None,
                "error_message": None,
            }
        except Exception as exc:
            log = self._latest_llm_log(call_type="market_context_note", since=started)
            return None, {
                "provider": provider,
                "model": model,
                "prompt_version": MARKET_CONTEXT_PROMPT_VERSION,
                "fallback_used": True,
                "duration_ms": log.duration_ms if log else None,
                "error_message": str(exc),
            }

    def _generate_daily_report_summary(
        self,
        cohort: CandidateCohort,
        report_date: date,
        deterministic_stats: dict[str, Any],
        candidate_rows: list[dict[str, Any]],
        market_context: dict[str, Any],
    ) -> tuple[str | None, dict[str, Any]]:
        model = self.settings.daily_report_llm_model
        provider = self._normalize_provider(self.settings.llm_provider)
        compact_candidates = [
            {
                "symbol": row["symbol"],
                "absolute_return_since_selection": row["absolute_return_since_selection"],
                "relative_to_SPY": row["relative_to_SPY"],
                "relative_to_QQQ": row["relative_to_QQQ"],
                "relative_to_sector_proxy": row["relative_to_sector_proxy"],
                "validity_state": row["validity_state"],
                "readiness": row["readiness"],
                "data_quality_flags": row["data_quality_flags"],
            }
            for row in candidate_rows[:60]
        ]
        prompt = (
            "You are TradeGhost's context-only daily cohort reviewer.\n"
            "Do not change deterministic fields, ranking, validity, readiness, score, or category.\n"
            "Do not give trade instructions. Summarize movement drivers and caveats only.\n"
            "Use SPY, QQQ, and sector-relative data to distinguish broad, sector, and stock-specific movement.\n"
            "Keep <=180 words.\n"
            f"cohort={cohort.name} cohort_id={cohort.id} report_date={report_date.isoformat()}\n"
            f"deterministic_stats={json.dumps(self._json_safe(deterministic_stats))}\n"
            f"market_context={json.dumps(self._json_safe(market_context))}\n"
            f"candidates={json.dumps(self._json_safe(compact_candidates))}\n"
        )
        started = datetime.now(UTC)
        try:
            text = self._ollama_generate(
                prompt=prompt,
                model=model,
                timeout_seconds=60.0,
                call_type="daily_cohort_report_summary",
                max_tokens_hint=300,
                prompt_version=DAILY_REPORT_PROMPT_VERSION,
            )
            log = self._latest_llm_log(call_type="daily_cohort_report_summary", since=started)
            return text, {
                "provider": log.provider if log else provider,
                "model": log.model if log else model,
                "prompt_version": DAILY_REPORT_PROMPT_VERSION,
                "fallback_used": bool(log.fallback_used) if log else False,
                "duration_ms": log.duration_ms if log else None,
                "error_message": None,
            }
        except Exception as exc:
            log = self._latest_llm_log(call_type="daily_cohort_report_summary", since=started)
            return None, {
                "provider": provider,
                "model": model,
                "prompt_version": DAILY_REPORT_PROMPT_VERSION,
                "fallback_used": True,
                "duration_ms": log.duration_ms if log else None,
                "error_message": str(exc),
            }

    def _latest_llm_log(self, *, call_type: str, since: datetime) -> LLMDebugLog | None:
        rows = [
            row
            for row in self._read_llm_logs()
            if row.call_type == call_type and row.timestamp >= since
        ]
        return sorted(rows, key=lambda row: row.timestamp, reverse=True)[0] if rows else None

    def _deterministic_daily_summary(self, deterministic_stats: dict[str, Any], market_context: dict[str, Any]) -> str:
        counts = deterministic_stats.get("validity_counts", {})
        regime = market_context.get("regime_note", "mixed")
        return (
            f"Deterministic fallback summary: regime={regime}; "
            f"valid={counts.get('valid', 0)}, pending={counts.get('pending_validation', 0)}, "
            f"invalid={counts.get('invalid', 0)}, needs_data_check={counts.get('needs_data_check', 0)}. "
            "Interpretation is limited to stored metrics and deterministic proxy context."
        )

    def _render_daily_report_markdown(
        self,
        *,
        cohort: CandidateCohort,
        report_date: date,
        followup_day_number: int,
        candidate_rows: list[dict[str, Any]],
        deterministic_stats: dict[str, Any],
        market_context: dict[str, Any],
        llm_summary: str,
        fallback_used: bool,
        error_message: str | None,
        llm_provider: str | None,
        llm_model: str | None,
        prompt_version: str | None,
        llm_context_summary_present: bool,
        followup_snapshot_count: int,
    ) -> str:
        target_days = deterministic_stats.get("followup_target_days", cohort.followup_target_days)
        lines: list[str] = []
        lines.append(f"# TradeGhost Cohort Daily Follow-up - {cohort.name}")
        lines.append("")
        lines.append("## Header")
        lines.append(f"- cohort_id: `{cohort.id}`")
        lines.append(f"- cohort_name: `{cohort.name}`")
        lines.append(f"- report_date: `{report_date.isoformat()}`")
        lines.append(f"- start_date: `{deterministic_stats.get('start_date', cohort.followup_start_date or cohort.start_date)}`")
        lines.append(f"- latest_followup_date: `{deterministic_stats.get('latest_followup_date') or '-'}`")
        lines.append(f"- calendar_days_elapsed: `{deterministic_stats.get('calendar_days_elapsed', deterministic_stats.get('calendar_day_count', '-'))}`")
        lines.append(f"- trading_days_elapsed: `{deterministic_stats.get('trading_days_elapsed', '-')}`")
        lines.append(f"- followup_day_number: `{followup_day_number}/{target_days}`")
        lines.append(
            f"- valid_followup_snapshot_days: "
            f"`{deterministic_stats.get('valid_followup_snapshot_days', deterministic_stats.get('valid_followup_day_count', followup_day_number))}/"
            f"{deterministic_stats.get('expected_followup_days', target_days)}`"
        )
        lines.append(f"- expected_followup_days: `{deterministic_stats.get('expected_followup_days', target_days)}`")
        lines.append(f"- snapshot_coverage_pct: `{deterministic_stats.get('snapshot_coverage_pct', 0.0)}%`")
        lines.append(f"- missing_followup_days_count: `{deterministic_stats.get('missing_followup_days_count', 0)}`")
        lines.append(f"- missing_followup_dates: `{json.dumps(deterministic_stats.get('missing_followup_dates', []), default=str)}`")
        lines.append(f"- trading_day: `{str(deterministic_stats.get('trading_day', False)).lower()}`")
        lines.append(f"- market_open: `{str(deterministic_stats.get('market_open', False)).lower()}`")
        lines.append(f"- candidate_count: `{len(candidate_rows)}`")
        lines.append(f"- snapshot_count: `{followup_snapshot_count}`")
        lines.append(f"- followup_snapshot_count: `{followup_snapshot_count}`")
        lines.append(f"- llm_provider: `{llm_provider or '-'}`")
        lines.append(f"- llm_model: `{llm_model or '-'}`")
        lines.append(f"- prompt_version: `{prompt_version or '-'}`")
        lines.append(f"- fallback_used: `{str(fallback_used).lower()}`")
        lines.append(f"- llm_context_summary_present: `{str(llm_context_summary_present).lower()}`")
        lines.append("")
        lines.append("## Market Context")
        broad = market_context.get("broad_market", {})
        for symbol in ["SPY", "QQQ", "IWM"]:
            row = broad.get(symbol, {}) if isinstance(broad, dict) else {}
            returns = row.get("returns", {}) if isinstance(row, dict) else {}
            lines.append(
                f"- {symbol}: 1D={self._fmt_pct(returns.get('1d'))}, 3D={self._fmt_pct(returns.get('3d'))}, "
                f"7D={self._fmt_pct(returns.get('7d'))}, 14D={self._fmt_pct(returns.get('14d'))}, 28D={self._fmt_pct(returns.get('28d'))}"
            )
        lines.append(f"- regime_note: `{market_context.get('regime_note', 'mixed')}`")
        flags = market_context.get("event_flags", [])
        lines.append(f"- event_flags: `{', '.join(flags) if flags else 'none'}`")
        if market_context.get("llm_note"):
            lines.append(f"- market_context_note: {market_context['llm_note']}")
        lines.append("")
        lines.append("## LLM Context Summary")
        lines.append(llm_summary)
        lines.append("")
        lines.append("## Candidate Follow-up")
        lines.append("| Symbol | Selected | Latest | Since Sel | 1D | 3D | 7D | 14D | 28D | vs SPY | vs QQQ | vs Sector | Validity | Readiness | Blocked By | Data Flags |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|")
        for row in candidate_rows:
            lines.append(
                f"| {row['symbol']} | "
                f"{row['selected_price'] if row['selected_price'] is not None else 'pending'} | "
                f"{row['latest_price'] if row['latest_price'] is not None else 'pending'} | "
                f"{self._fmt_pct(row['absolute_return_since_selection'])} | "
                f"{self._fmt_pct(row['return_1d'])} | {self._fmt_pct(row['return_3d'])} | {self._fmt_pct(row['return_7d'])} | "
                f"{self._fmt_pct(row['return_14d'])} | {self._fmt_pct(row['return_28d'])} | "
                f"{self._fmt_pct(row['relative_to_SPY'])} | {self._fmt_pct(row['relative_to_QQQ'])} | {self._fmt_pct(row['relative_to_sector_proxy'])} | "
                f"{row['validity_state']} | {row['readiness']} | {row['blocked_by']} | {','.join(row['data_quality_flags']) if row['data_quality_flags'] else '-'} |"
            )
        lines.append("")
        lines.append("## Category Summary")
        lines.append(f"- Return since selection by category: `{json.dumps(deterministic_stats.get('return_since_selection_by_category', {}), default=str)}`")
        lines.append(f"- 7D return by category: `{json.dumps(deterministic_stats.get('return_7d_by_category', {}), default=str)}`")
        lines.append(f"- 14D return by category: `{json.dumps(deterministic_stats.get('return_14d_by_category', {}), default=str)}`")
        lines.append(f"- 28D return by category: `{json.dumps(deterministic_stats.get('return_28d_by_category', {}), default=str)}`")
        lines.append(f"- average_relative_to_SPY_by_category: `{json.dumps(deterministic_stats.get('average_relative_to_SPY_by_category', {}), default=str)}`")
        lines.append(f"- average_relative_to_QQQ_by_category: `{json.dumps(deterministic_stats.get('average_relative_to_QQQ_by_category', {}), default=str)}`")
        lines.append(f"- average_relative_to_sector_proxy_by_category: `{json.dumps(deterministic_stats.get('average_relative_to_sector_proxy_by_category', {}), default=str)}`")
        lines.append(f"- validity_counts: `{json.dumps(deterministic_stats.get('validity_counts', {}), default=str)}`")
        if deterministic_stats.get("best_worst_deferred"):
            lines.append("- best_worst_category: deferred until enough history is available.")
        else:
            lines.append(f"- best_category: `{deterministic_stats.get('best_category') or '-'}`")
            lines.append(f"- worst_category: `{deterministic_stats.get('worst_category') or '-'}`")
        lines.append("")
        lines.append("## Caveats")
        if deterministic_stats.get("missing_followup_days_count", 0):
            lines.append("- Snapshot coverage is daily-state coverage, not elapsed time.")
        lines.append("- 28D interpretation uses deterministic price horizons when price data is available.")
        lines.append(f"- pending_horizon_counts: `{json.dumps(deterministic_stats.get('pending_horizon_counts', {}), default=str)}`")
        lines.append(f"- data_quality_exclusion_count: `{deterministic_stats.get('data_quality_exclusion_count', 0)}`")
        lines.append("- Market context uses deterministic proxy symbols only; event/news calendars are not connected yet.")
        lines.append(f"- llm_fallback_used: `{str(fallback_used).lower()}`")
        if error_message:
            lines.append(f"- llm_error_message: `{error_message}`")
        return "\n".join(lines).strip() + "\n"

    def _write_daily_report_markdown(self, cohort: CandidateCohort, report_date: date, markdown: str) -> Path:
        export_dir = self.base_dir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(ZoneInfo(self.settings.daily_cohort_followup_timezone))
        filename = (
            f"tradeghost-cohort-{self._slug(cohort.name)}-{cohort.id[:8].lower()}"
            f"-followup-{report_date.isoformat()}-{now.strftime('%H%M')}.md"
        )
        path = export_dir / filename
        path.write_text(markdown, encoding="utf-8")
        return path

    @staticmethod
    def _engine_version() -> str:
        try:
            return version("tradeghost")
        except PackageNotFoundError:
            return "0.1.0"

    @staticmethod
    def _git_commit() -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            return result.stdout.strip() or "unknown"
        except Exception:
            return "unknown"

    def _next_scheduled_run_at(self, *, now: datetime | None = None) -> datetime | None:
        tz = ZoneInfo(self.settings.daily_cohort_followup_timezone)
        local_now = (now or datetime.now(UTC)).astimezone(tz)
        hour, minute = self._parse_schedule_time(self.settings.daily_cohort_followup_schedule)
        for offset in range(14):
            candidate = local_now.date() + timedelta(days=offset)
            if not self._is_us_trading_day(candidate):
                continue
            scheduled = datetime.combine(candidate, datetime.min.time(), tzinfo=tz).replace(hour=hour, minute=minute)
            if scheduled > local_now:
                return scheduled
        return None

    @staticmethod
    def _entry_timestamp(entry: dict[str, Any]) -> str:
        return str(entry.get("timestamp") or entry.get("created_at") or entry.get("updated_at") or "")

    def _latest_backend_errors(self, limit: int = 25) -> list[dict[str, Any]]:
        errors: list[dict[str, Any]] = []
        for row in self.get_llm_logs(limit=200):
            if row.status == "fail" or row.error_message:
                errors.append(
                    {
                        "timestamp": row.timestamp.isoformat(),
                        "source": "llm_provider",
                        "level": "ERROR",
                        "message": row.error_message or row.status,
                        "provider": row.provider,
                        "model": row.model,
                        "request_id": None,
                    }
                )
        for row in self._read_pipeline_events():
            if row.status == "failed" or row.error_message:
                errors.append(
                    {
                        "timestamp": row.timestamp.isoformat(),
                        "source": "intelligence" if "monitor" not in row.step_name else "monitoring",
                        "level": "ERROR",
                        "message": row.error_message or row.message or row.step_name,
                        "step_name": row.step_name,
                        "cohort_id": row.cohort_id,
                        "symbol": row.symbol,
                    }
                )
        for entry in self._read_scheduler_log_entries(limit=500):
            if str(entry.get("status", "")).lower() in {"failed", "error"} or entry.get("error_message"):
                errors.append(
                    {
                        "timestamp": str(entry.get("timestamp") or ""),
                        "source": "scheduled_followup",
                        "level": "ERROR",
                        "message": entry.get("error_message") or entry.get("event"),
                        "cohort_id": entry.get("cohort_id"),
                        "report_date": entry.get("report_date"),
                    }
                )
        return sorted(errors, key=self._entry_timestamp, reverse=True)[: max(1, min(limit, 100))]

    def get_logs_status(self, *, scheduler_running: bool) -> dict[str, Any]:
        now = datetime.now(UTC)
        scheduler_entries = self._read_scheduler_log_entries(limit=1000)
        last_run = next(
            (row for row in reversed(scheduler_entries) if row.get("event") in {"job_started", "job_completed", "job_failed"}),
            None,
        )
        last_success = next(
            (
                row
                for row in reversed(scheduler_entries)
                if row.get("event") in {"job_completed", "job_report_upserted"} and str(row.get("status")).lower() == "success"
            ),
            None,
        )
        last_failure = next(
            (
                row
                for row in reversed(scheduler_entries)
                if str(row.get("status")).lower() in {"failed", "error"} or row.get("event") == "job_failed"
            ),
            None,
        )
        active = self._active_followup_cohorts()
        active_rows: list[dict[str, Any]] = []
        due_date = self._latest_due_report_date(now=now)
        for cohort in active:
            report_dates: list[date] = []
            try:
                report_dates = [row.report_date for row in self.daily_report_store.list_reports(cohort.id)]
            except Exception:
                report_dates = [row.snapshot_date for row in self._read_cohort_snapshots() if row.cohort_id == cohort.id]
            last_report_date = max(report_dates) if report_dates else None
            current_day = self._followup_day_number(cohort, min(due_date, date.today()) if due_date else date.today())
            active_rows.append(
                {
                    "cohort_id": cohort.id,
                    "cohort_name": cohort.name,
                    "followup_enabled": cohort.followup_enabled,
                    "followup_start_date": cohort.followup_start_date.isoformat() if cohort.followup_start_date else None,
                    "followup_target_days": cohort.followup_target_days,
                    "current_followup_day": current_day,
                    "last_report_date": last_report_date.isoformat() if last_report_date else None,
                    "completed": cohort.followup_completed,
                }
            )
        try:
            daily_reports = {
                "postgres": self.daily_report_store.status_summary(),
                "latest_rows": [row.model_dump(mode="json") for row in self.daily_report_store.list_latest_reports(limit=25)],
            }
        except Exception as exc:
            daily_reports = {
                "postgres": {
                    "configured": self.daily_report_store.configured,
                    "total_daily_reports": 0,
                    "latest_report_date": None,
                    "latest_report_created_at": None,
                    "latest_report_updated_at": None,
                    "latest_export_path": None,
                    "fallback_used": None,
                    "error_message": str(exc),
                },
                "latest_rows": [],
            }
        next_run = self._next_scheduled_run_at(now=now)
        return {
            "scheduler": {
                "scheduler_enabled": self.settings.daily_cohort_followup_enabled,
                "scheduler_running": scheduler_running,
                "timezone": self.settings.daily_cohort_followup_timezone,
                "configured_run_time": self.settings.daily_cohort_followup_schedule,
                "next_run_at": next_run.isoformat() if next_run else None,
                "last_run_at": last_run.get("timestamp") if last_run else None,
                "last_success_at": last_success.get("timestamp") if last_success else None,
                "last_failure_at": last_failure.get("timestamp") if last_failure else None,
                "last_error_message": last_failure.get("error_message") if last_failure else None,
                "active_followup_cohorts_count": len(active),
            },
            "daily_reports": daily_reports,
            "active_followup_cohorts": active_rows,
            "latest_errors": self._latest_backend_errors(limit=30),
        }

    def list_log_files(self) -> dict[str, Any]:
        root = self.settings.logs_dir.resolve()
        groups: dict[str, list[dict[str, Any]]] = {}
        if not root.exists():
            return {"root": str(root), "groups": groups}
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            if any(part.startswith(".") for part in relative.parts):
                continue
            group = relative.parts[0] if len(relative.parts) > 1 else "root"
            groups.setdefault(group, []).append(
                {
                    "path": relative.as_posix(),
                    "name": path.name,
                    "size_bytes": path.stat().st_size,
                    "updated_at": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(),
                }
            )
        return {"root": str(root), "groups": groups}

    def read_log_file(self, *, relative_path: str, tail: int = 200, level: str | None = None) -> dict[str, Any]:
        root = self.settings.logs_dir.resolve()
        requested = Path(relative_path)
        if requested.is_absolute() or ".." in requested.parts:
            raise ValueError("Invalid log path")
        target = (root / requested).resolve()
        if target != root and root not in target.parents:
            raise ValueError("Invalid log path")
        if not target.is_file():
            raise FileNotFoundError(relative_path)
        text = target.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if level:
            needle = level.upper()
            if needle in {"ERROR", "WARNING", "INFO"}:
                lines = [line for line in lines if needle in line.upper()]
        selected = lines[-max(1, min(int(tail), 2000)):]
        return {
            "path": target.relative_to(root).as_posix(),
            "tail": len(selected),
            "total_lines": len(lines),
            "level": level or "",
            "text": "\n".join(selected),
        }

    def list_cohort_daily_reports(self, cohort_id: str) -> list[CohortDailyReportSummary]:
        _ = self.get_cohort_detail(cohort_id)
        return self.daily_report_store.list_reports(cohort_id)

    def get_cohort_daily_report(self, cohort_id: str, report_date: date) -> CohortDailyReportDetail:
        _ = self.get_cohort_detail(cohort_id)
        report = self.daily_report_store.get_report(cohort_id, report_date, report_mode="followup")
        if report is None:
            raise FileNotFoundError(f"Daily report not found for cohort_id={cohort_id} report_date={report_date}")
        return report

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
        model = req.model or self.settings.llmq_chat_model
        try:
            text = self._ollama_generate(
                prompt="Reply with exactly: OK",
                model=model,
                timeout_seconds=req.timeout_seconds,
                call_type="health_probe",
            )
            elapsed_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
            threshold_ms = int(req.threshold_seconds * 1000)
            return LLMResponseTestResult(
                ok=True,
                model=model,
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
                model=model,
                endpoint=endpoint,
                response_time_ms=elapsed_ms,
                threshold_ms=threshold_ms,
                within_threshold=False,
                status="fail",
                error=str(exc),
                checked_at=checked_at,
            )
