from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class KnowledgeGraphOutboxEvent:
    id: str
    event_type: str
    event_version: int
    aggregate_id: str
    payload: dict[str, Any]
    attempt_count: int


class KnowledgeGraphOutboxStore:
    report_event_type = "cohort_daily_report.upserted.v1"
    event_type = report_event_type
    prediction_event_type = "research.prediction.committed.v1"
    outcome_event_type = "research.outcome.committed.v1"
    market_regime_event_type = "research.market_regime.committed.v1"

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
            raise RuntimeError("psycopg is required for knowledge graph outbox persistence") from exc
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def ensure_schema(self) -> None:
        if not self.configured:
            return
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge_graph_outbox (
                    id UUID PRIMARY KEY,
                    event_type text NOT NULL,
                    aggregate_id UUID NOT NULL,
                    dedupe_key text NOT NULL UNIQUE,
                    event_version integer NOT NULL DEFAULT 1,
                    payload_json jsonb NOT NULL,
                    status text NOT NULL DEFAULT 'pending',
                    attempt_count integer NOT NULL DEFAULT 0,
                    next_attempt_at timestamptz NOT NULL DEFAULT now(),
                    locked_at timestamptz,
                    processed_at timestamptz,
                    last_error text,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS knowledge_graph_outbox_dispatch_idx
                ON knowledge_graph_outbox (status, next_attempt_at, created_at)
                """
            )
            conn.commit()

    def enqueue_with_connection(
        self,
        conn: Any,
        *,
        aggregate_id: str,
        payload: dict[str, Any],
        event_type: str = report_event_type,
        dedupe_key: str | None = None,
    ) -> None:
        event_type = str(event_type).strip()
        if not event_type:
            raise ValueError("Knowledge graph outbox event_type is required")
        dedupe_key = dedupe_key or (
            f"cohort_daily_report:{aggregate_id}"
            if event_type == self.report_event_type
            else f"{event_type}:{aggregate_id}"
        )
        conn.execute(
            """
            INSERT INTO knowledge_graph_outbox (
                id,
                event_type,
                aggregate_id,
                dedupe_key,
                payload_json
            )
            VALUES (%s::uuid, %s, %s::uuid, %s, %s::jsonb)
            ON CONFLICT (dedupe_key)
            DO UPDATE SET
                payload_json = EXCLUDED.payload_json,
                event_version = knowledge_graph_outbox.event_version + 1,
                status = 'pending',
                next_attempt_at = now(),
                locked_at = NULL,
                processed_at = NULL,
                last_error = NULL,
                updated_at = now()
            """,
            (
                str(uuid4()),
                event_type,
                aggregate_id,
                dedupe_key,
                json.dumps(payload),
            ),
        )

    def claim_events(self, limit: int) -> list[KnowledgeGraphOutboxEvent]:
        self.ensure_schema()
        if not self.configured:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                WITH candidates AS (
                    SELECT id
                    FROM knowledge_graph_outbox
                    WHERE (
                        status IN ('pending', 'failed')
                        AND next_attempt_at <= now()
                    ) OR (
                        status = 'processing'
                        AND locked_at <= now() - interval '5 minutes'
                    )
                    ORDER BY created_at ASC
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE knowledge_graph_outbox AS outbox
                SET
                    status = 'processing',
                    locked_at = now(),
                    attempt_count = outbox.attempt_count + 1,
                    updated_at = now()
                FROM candidates
                WHERE outbox.id = candidates.id
                RETURNING outbox.*
                """,
                (max(1, min(int(limit), 200)),),
            ).fetchall()
            conn.commit()
        return [self._event_from_row(row) for row in rows]

    def mark_processed(self, event: KnowledgeGraphOutboxEvent) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                UPDATE knowledge_graph_outbox
                SET
                    status = 'completed',
                    processed_at = now(),
                    locked_at = NULL,
                    last_error = NULL,
                    updated_at = now()
                WHERE id = %s::uuid
                  AND event_version = %s
                RETURNING id
                """,
                (event.id, event.event_version),
            ).fetchone()
            conn.commit()
        return row is not None

    def mark_failed(self, event: KnowledgeGraphOutboxEvent, error_message: str, retry_seconds: int) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                UPDATE knowledge_graph_outbox
                SET
                    status = 'failed',
                    next_attempt_at = now() + (%s * interval '1 second'),
                    locked_at = NULL,
                    last_error = %s,
                    updated_at = now()
                WHERE id = %s::uuid
                  AND event_version = %s
                RETURNING id
                """,
                (
                    max(1, int(retry_seconds)),
                    str(error_message)[:2000],
                    event.id,
                    event.event_version,
                ),
            ).fetchone()
            conn.commit()
        return row is not None

    def status_summary(self) -> dict[str, Any]:
        if not self.configured:
            return {"configured": False, "counts": {}}
        self.ensure_schema()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT event_type, status, count(*) AS count
                FROM knowledge_graph_outbox
                GROUP BY event_type, status
                """
            ).fetchall()
        counts: dict[str, int] = {}
        counts_by_event_type: dict[str, dict[str, int]] = {}
        for row in rows:
            event_type = str(row["event_type"])
            status = str(row["status"])
            count = int(row["count"])
            counts[status] = counts.get(status, 0) + count
            counts_by_event_type.setdefault(event_type, {})[status] = count
        return {
            "configured": True,
            "counts": counts,
            "counts_by_event_type": counts_by_event_type,
        }

    @staticmethod
    def _event_from_row(row: dict[str, Any]) -> KnowledgeGraphOutboxEvent:
        payload = row.get("payload_json")
        if isinstance(payload, str):
            payload = json.loads(payload)
        return KnowledgeGraphOutboxEvent(
            id=str(row["id"]),
            event_type=str(row["event_type"]),
            event_version=int(row["event_version"]),
            aggregate_id=str(row["aggregate_id"]),
            payload=payload if isinstance(payload, dict) else {},
            attempt_count=int(row["attempt_count"]),
        )
