from __future__ import annotations

import json
from datetime import date
from typing import Any

from tradeghost.shared.models.schemas import CohortDailyReportDetail, CohortDailyReportSummary


class CohortDailyReportStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = (database_url or "").strip()

    @property
    def configured(self) -> bool:
        return bool(self.database_url)

    def _connect(self):
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is not configured")
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - dependency/environment guard
            raise RuntimeError("psycopg is required for cohort_daily_reports persistence") from exc
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cohort_daily_reports (
                    id UUID PRIMARY KEY,
                    cohort_id UUID NOT NULL,
                    cohort_name text,
                    report_date date NOT NULL,
                    report_mode text NOT NULL,
                    candidate_count int,
                    followup_snapshot_count int,
                    deterministic_stats_json jsonb,
                    candidate_followup_json jsonb,
                    market_context_json jsonb,
                    llm_context_summary text,
                    report_markdown text,
                    export_path text,
                    engine_version text,
                    git_commit text,
                    llm_provider text,
                    llm_model text,
                    prompt_version text,
                    fallback_used boolean DEFAULT false,
                    error_message text,
                    created_at timestamptz DEFAULT now(),
                    updated_at timestamptz DEFAULT now(),
                    CONSTRAINT cohort_daily_reports_unique UNIQUE (cohort_id, report_date, report_mode)
                )
                """
            )
            conn.commit()

    def upsert_report(self, record: dict[str, Any]) -> CohortDailyReportDetail:
        self.ensure_schema()
        payload = dict(record)
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO cohort_daily_reports (
                    id,
                    cohort_id,
                    cohort_name,
                    report_date,
                    report_mode,
                    candidate_count,
                    followup_snapshot_count,
                    deterministic_stats_json,
                    candidate_followup_json,
                    market_context_json,
                    llm_context_summary,
                    report_markdown,
                    export_path,
                    engine_version,
                    git_commit,
                    llm_provider,
                    llm_model,
                    prompt_version,
                    fallback_used,
                    error_message
                )
                VALUES (
                    %(id)s::uuid,
                    %(cohort_id)s::uuid,
                    %(cohort_name)s,
                    %(report_date)s,
                    %(report_mode)s,
                    %(candidate_count)s,
                    %(followup_snapshot_count)s,
                    %(deterministic_stats_json)s::jsonb,
                    %(candidate_followup_json)s::jsonb,
                    %(market_context_json)s::jsonb,
                    %(llm_context_summary)s,
                    %(report_markdown)s,
                    %(export_path)s,
                    %(engine_version)s,
                    %(git_commit)s,
                    %(llm_provider)s,
                    %(llm_model)s,
                    %(prompt_version)s,
                    %(fallback_used)s,
                    %(error_message)s
                )
                ON CONFLICT (cohort_id, report_date, report_mode)
                DO UPDATE SET
                    cohort_name = EXCLUDED.cohort_name,
                    candidate_count = EXCLUDED.candidate_count,
                    followup_snapshot_count = EXCLUDED.followup_snapshot_count,
                    deterministic_stats_json = EXCLUDED.deterministic_stats_json,
                    candidate_followup_json = EXCLUDED.candidate_followup_json,
                    market_context_json = EXCLUDED.market_context_json,
                    llm_context_summary = EXCLUDED.llm_context_summary,
                    report_markdown = EXCLUDED.report_markdown,
                    export_path = EXCLUDED.export_path,
                    engine_version = EXCLUDED.engine_version,
                    git_commit = EXCLUDED.git_commit,
                    llm_provider = EXCLUDED.llm_provider,
                    llm_model = EXCLUDED.llm_model,
                    prompt_version = EXCLUDED.prompt_version,
                    fallback_used = EXCLUDED.fallback_used,
                    error_message = EXCLUDED.error_message,
                    updated_at = now()
                RETURNING *
                """,
                self._encode_payload(payload),
            ).fetchone()
            conn.commit()
        return self._detail_from_row(row)

    def list_reports(self, cohort_id: str) -> list[CohortDailyReportSummary]:
        self.ensure_schema()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM cohort_daily_reports
                WHERE cohort_id = %s::uuid
                ORDER BY report_date DESC, updated_at DESC
                """,
                (cohort_id,),
            ).fetchall()
        return [self._summary_from_row(row) for row in rows]

    def list_latest_reports(self, limit: int = 25) -> list[CohortDailyReportSummary]:
        self.ensure_schema()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM cohort_daily_reports
                ORDER BY report_date DESC, updated_at DESC
                LIMIT %s
                """,
                (max(1, min(int(limit), 200)),),
            ).fetchall()
        return [self._summary_from_row(row) for row in rows]

    def status_summary(self) -> dict[str, Any]:
        self.ensure_schema()
        with self._connect() as conn:
            total = conn.execute("SELECT count(*) AS count FROM cohort_daily_reports").fetchone()
            latest = conn.execute(
                """
                SELECT *
                FROM cohort_daily_reports
                ORDER BY report_date DESC, updated_at DESC
                LIMIT 1
                """
            ).fetchone()
        latest_summary = self._summary_from_row(latest).model_dump(mode="json") if latest else None
        return {
            "configured": True,
            "total_daily_reports": int((total or {}).get("count") or 0),
            "latest_report_date": latest_summary.get("report_date") if latest_summary else None,
            "latest_report_created_at": latest_summary.get("created_at") if latest_summary else None,
            "latest_report_updated_at": latest_summary.get("updated_at") if latest_summary else None,
            "latest_export_path": latest_summary.get("export_path") if latest_summary else None,
            "fallback_used": latest_summary.get("fallback_used") if latest_summary else None,
            "error_message": latest.get("error_message") if latest else None,
        }

    def get_report(self, cohort_id: str, report_date: date, report_mode: str = "followup") -> CohortDailyReportDetail | None:
        self.ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM cohort_daily_reports
                WHERE cohort_id = %s::uuid
                  AND report_date = %s
                  AND report_mode = %s
                """,
                (cohort_id, report_date, report_mode),
            ).fetchone()
        return self._detail_from_row(row) if row else None

    @staticmethod
    def _encode_payload(payload: dict[str, Any]) -> dict[str, Any]:
        encoded = dict(payload)
        for key in ("deterministic_stats_json", "candidate_followup_json", "market_context_json"):
            encoded[key] = json.dumps(encoded.get(key) if encoded.get(key) is not None else {})
        return encoded

    @staticmethod
    def _coerce_json(value: Any, fallback: Any) -> Any:
        if value is None:
            return fallback
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return fallback
        return value

    @classmethod
    def _summary_from_row(cls, row: dict[str, Any]) -> CohortDailyReportSummary:
        deterministic = cls._coerce_json(row.get("deterministic_stats_json"), {})
        market_context = cls._coerce_json(row.get("market_context_json"), {})
        return CohortDailyReportSummary(
            id=str(row.get("id")) if row.get("id") is not None else None,
            cohort_id=str(row.get("cohort_id")),
            cohort_name=row.get("cohort_name"),
            report_date=row.get("report_date"),
            report_mode=str(row.get("report_mode")),
            followup_day_number=deterministic.get("followup_day_number") if isinstance(deterministic, dict) else None,
            candidate_count=int(row.get("candidate_count") or 0),
            followup_snapshot_count=int(row.get("followup_snapshot_count") or 0),
            deterministic_stats_json=deterministic if isinstance(deterministic, dict) else {},
            market_context_json=market_context if isinstance(market_context, dict) else {},
            llm_model=row.get("llm_model"),
            fallback_used=bool(row.get("fallback_used")),
            export_path=row.get("export_path"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    @classmethod
    def _detail_from_row(cls, row: dict[str, Any]) -> CohortDailyReportDetail:
        summary = cls._summary_from_row(row).model_dump()
        candidate_followup = cls._coerce_json(row.get("candidate_followup_json"), [])
        return CohortDailyReportDetail(
            **summary,
            candidate_followup_json=candidate_followup if isinstance(candidate_followup, list) else [],
            llm_context_summary=row.get("llm_context_summary"),
            report_markdown=row.get("report_markdown"),
            engine_version=row.get("engine_version"),
            git_commit=row.get("git_commit"),
            llm_provider=row.get("llm_provider"),
            prompt_version=row.get("prompt_version"),
            error_message=row.get("error_message"),
        )
