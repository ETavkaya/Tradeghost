from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from tradeghost.services.knowledge_graph.outbox import KnowledgeGraphOutboxStore
from tradeghost.shared.models.schemas import (
    HypothesisValidationRun,
    MarketRegimeSnapshot,
    OutcomeRecord,
    OutcomeSummaryRecord,
    PatternCandidate,
    PatternCandidateReview,
    PatternCandidateStatus,
    PredictionRecord,
    RuleHypothesis,
    RuleHypothesisReview,
    RuleHypothesisStatus,
)


class ResearchRecordStore:
    def __init__(self, database_url: str) -> None:
        self.database_url = (database_url or "").strip()
        self.migrations_dir = Path(__file__).with_name("migrations")
        self.knowledge_graph_outbox = KnowledgeGraphOutboxStore(self.database_url)

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
            raise RuntimeError("psycopg is required for Phase 2B research record persistence") from exc
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def ensure_schema(self) -> None:
        if not self.configured:
            return
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tradeghost_schema_migrations (
                    version text PRIMARY KEY,
                    applied_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            applied = {
                str(row["version"])
                for row in conn.execute("SELECT version FROM tradeghost_schema_migrations").fetchall()
            }
            for migration_path in sorted(self.migrations_dir.glob("*.sql")):
                if migration_path.name in applied:
                    continue
                statements = [statement.strip() for statement in migration_path.read_text(encoding="utf-8").split(";\n")]
                for statement in statements:
                    if statement:
                        conn.execute(statement)
                conn.execute(
                    """
                    INSERT INTO tradeghost_schema_migrations (version)
                    VALUES (%s)
                    ON CONFLICT (version) DO NOTHING
                    """,
                    (migration_path.name,),
                )
            conn.commit()
        self.knowledge_graph_outbox.ensure_schema()

    def create_predictions(self, records: list[PredictionRecord]) -> tuple[list[PredictionRecord], int]:
        self.ensure_schema()
        if not records:
            return [], 0
        persisted: list[PredictionRecord] = []
        created_count = 0
        with self._connect() as conn:
            for record in records:
                row = conn.execute(
                    """
                    INSERT INTO prediction_records (
                        id, idempotency_key, payload_hash, cohort_id, symbol, market,
                        selected_at, selected_date, selected_price, categories_json,
                        setup_type, trend_state, extension_state, score_dynamics_state,
                        trigger_state, trigger_score, trigger_threshold, score,
                        candidate_type, entry_readiness, blocked_by, risk_flags_json,
                        data_quality_flags_json, expected_horizon_days, expected_direction,
                        prediction_type, invalidation_conditions_json, deterministic_reason,
                        selection_snapshot_json, source_run_id, source_report_id,
                        rule_version, feature_version, data_version,
                        selection_market_regime_id,
                        supersedes_prediction_id, correction_reason, created_at
                    )
                    VALUES (
                        %(id)s::uuid, %(idempotency_key)s, %(payload_hash)s, %(cohort_id)s::uuid, %(symbol)s, %(market)s,
                        %(selected_at)s, %(selected_date)s, %(selected_price)s, %(categories_json)s::jsonb,
                        %(setup_type)s, %(trend_state)s, %(extension_state)s, %(score_dynamics_state)s,
                        %(trigger_state)s, %(trigger_score)s, %(trigger_threshold)s, %(score)s,
                        %(candidate_type)s, %(entry_readiness)s, %(blocked_by)s, %(risk_flags_json)s::jsonb,
                        %(data_quality_flags_json)s::jsonb, %(expected_horizon_days)s, %(expected_direction)s,
                        %(prediction_type)s, %(invalidation_conditions_json)s::jsonb, %(deterministic_reason)s,
                        %(selection_snapshot_json)s::jsonb, %(source_run_id)s, %(source_report_id)s::uuid,
                        %(rule_version)s, %(feature_version)s, %(data_version)s,
                        %(selection_market_regime_id)s::uuid,
                        %(supersedes_prediction_id)s::uuid, %(correction_reason)s, %(created_at)s
                    )
                    ON CONFLICT (idempotency_key) DO NOTHING
                    RETURNING *
                    """,
                    self._prediction_payload(record),
                ).fetchone()
                if row is None:
                    row = conn.execute(
                        "SELECT * FROM prediction_records WHERE idempotency_key = %s",
                        (record.idempotency_key,),
                    ).fetchone()
                else:
                    created_count += 1
                if row is None:  # pragma: no cover - database consistency guard
                    raise RuntimeError(f"Prediction record was not persisted for key={record.idempotency_key}")
                persisted_record = self._prediction_from_row(row)
                persisted.append(persisted_record)
                self.knowledge_graph_outbox.enqueue_with_connection(
                    conn,
                    aggregate_id=persisted_record.id,
                    payload=persisted_record.model_dump(mode="json"),
                    event_type=KnowledgeGraphOutboxStore.prediction_event_type,
                )
            conn.commit()
        return persisted, created_count

    def list_predictions(self, cohort_id: str) -> list[PredictionRecord]:
        self.ensure_schema()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM prediction_records
                WHERE cohort_id = %s::uuid
                ORDER BY selected_at ASC, symbol ASC, created_at ASC
                """,
                (cohort_id,),
            ).fetchall()
        return [self._prediction_from_row(row) for row in rows]

    def create_market_regime_snapshot(self, record: MarketRegimeSnapshot) -> tuple[MarketRegimeSnapshot, bool]:
        self.ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO market_regime_snapshots (
                    id, idempotency_key, payload_hash, market, as_of_date,
                    primary_benchmark_symbol, benchmark_returns_json, volatility_20d_pct,
                    regime_label, classifier_version, raw_inputs_json, data_quality_flags_json,
                    rule_version, feature_version, data_version, created_at
                )
                VALUES (
                    %(id)s::uuid, %(idempotency_key)s, %(payload_hash)s, %(market)s, %(as_of_date)s,
                    %(primary_benchmark_symbol)s, %(benchmark_returns_json)s::jsonb, %(volatility_20d_pct)s,
                    %(regime_label)s, %(classifier_version)s, %(raw_inputs_json)s::jsonb, %(data_quality_flags_json)s::jsonb,
                    %(rule_version)s, %(feature_version)s, %(data_version)s, %(created_at)s
                )
                ON CONFLICT (idempotency_key) DO NOTHING
                RETURNING *
                """,
                self._market_regime_payload(record),
            ).fetchone()
            created = row is not None
            if row is None:
                row = conn.execute(
                    "SELECT * FROM market_regime_snapshots WHERE idempotency_key = %s",
                    (record.idempotency_key,),
                ).fetchone()
            if row is None:  # pragma: no cover - database consistency guard
                raise RuntimeError(f"Market regime snapshot was not persisted for key={record.idempotency_key}")
            persisted = self._market_regime_from_row(row)
            self.knowledge_graph_outbox.enqueue_with_connection(
                conn,
                aggregate_id=persisted.id,
                payload=persisted.model_dump(mode="json"),
                event_type=KnowledgeGraphOutboxStore.market_regime_event_type,
            )
            conn.commit()
        return persisted, created

    def get_market_regime_snapshot(self, snapshot_id: str) -> MarketRegimeSnapshot | None:
        self.ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM market_regime_snapshots WHERE id = %s::uuid",
                (snapshot_id,),
            ).fetchone()
        return self._market_regime_from_row(row) if row else None

    def enqueue_existing_records_for_graph(self, limit: int = 100) -> dict[str, int]:
        self.ensure_schema()
        remaining = max(1, min(int(limit), 1000))
        queued = {"market_regimes": 0, "predictions": 0, "outcomes": 0}
        record_sets: tuple[tuple[str, str, str, Any, str], ...] = (
            (
                "market_regimes",
                "market_regime_snapshots",
                "as_of_date ASC, created_at ASC",
                self._market_regime_from_row,
                KnowledgeGraphOutboxStore.market_regime_event_type,
            ),
            (
                "predictions",
                "prediction_records",
                "selected_at ASC, symbol ASC, created_at ASC",
                self._prediction_from_row,
                KnowledgeGraphOutboxStore.prediction_event_type,
            ),
            (
                "outcomes",
                "outcome_records",
                "evaluated_at ASC, created_at ASC",
                self._outcome_from_row,
                KnowledgeGraphOutboxStore.outcome_event_type,
            ),
        )
        with self._connect() as conn:
            for index, (key, table_name, order_by, mapper, event_type) in enumerate(record_sets):
                if remaining <= 0:
                    break
                types_remaining = len(record_sets) - index
                type_limit = max(1, remaining // types_remaining)
                rows = conn.execute(
                    f"""
                    SELECT source.*
                    FROM {table_name} AS source
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM knowledge_graph_outbox AS outbox
                        WHERE outbox.dedupe_key = (%s || ':' || source.id::text)
                    )
                    ORDER BY {order_by}
                    LIMIT %s
                    """,
                    (event_type, type_limit),
                ).fetchall()
                for row in rows:
                    record = mapper(row)
                    self.knowledge_graph_outbox.enqueue_with_connection(
                        conn,
                        aggregate_id=record.id,
                        payload=record.model_dump(mode="json"),
                        event_type=event_type,
                    )
                queued[key] = len(rows)
                remaining -= len(rows)
            conn.commit()
        return queued

    def create_outcome(self, record: OutcomeRecord) -> tuple[OutcomeRecord, bool]:
        self.ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO outcome_records (
                    id, idempotency_key, payload_hash, prediction_id, cohort_id, symbol, market,
                    horizon_days, selection_date, outcome_date, evaluated_at, outcome_status,
                    outcome_label, selected_price, horizon_price, return_pct, directional_return_pct,
                    max_favorable_excursion_pct, max_adverse_excursion_pct, price_path_complete,
                    daily_snapshot_path_complete, daily_snapshot_coverage_pct, followed_through,
                    false_positive, invalidated_quickly, missed_follow_through, stayed_valid,
                    categories_json, setup_type, blocked_by, data_quality_flags_json, attribution_json,
                    price_source, selection_bar_date, horizon_bar_date, evaluator_version,
                    rule_version, feature_version, data_version, selection_market_regime_id,
                    outcome_market_regime_id, market_regime_label, market_return_pct,
                    sector_proxy_symbol, sector_return_pct, relative_to_spy, relative_to_qqq,
                    relative_to_sector_proxy, attribution_label, supersedes_outcome_id, created_at
                )
                VALUES (
                    %(id)s::uuid, %(idempotency_key)s, %(payload_hash)s, %(prediction_id)s::uuid, %(cohort_id)s::uuid, %(symbol)s, %(market)s,
                    %(horizon_days)s, %(selection_date)s, %(outcome_date)s, %(evaluated_at)s, %(outcome_status)s,
                    %(outcome_label)s, %(selected_price)s, %(horizon_price)s, %(return_pct)s, %(directional_return_pct)s,
                    %(max_favorable_excursion_pct)s, %(max_adverse_excursion_pct)s, %(price_path_complete)s,
                    %(daily_snapshot_path_complete)s, %(daily_snapshot_coverage_pct)s, %(followed_through)s,
                    %(false_positive)s, %(invalidated_quickly)s, %(missed_follow_through)s, %(stayed_valid)s,
                    %(categories_json)s::jsonb, %(setup_type)s, %(blocked_by)s, %(data_quality_flags_json)s::jsonb, %(attribution_json)s::jsonb,
                    %(price_source)s, %(selection_bar_date)s, %(horizon_bar_date)s, %(evaluator_version)s,
                    %(rule_version)s, %(feature_version)s, %(data_version)s, %(selection_market_regime_id)s::uuid,
                    %(outcome_market_regime_id)s::uuid, %(market_regime_label)s, %(market_return_pct)s,
                    %(sector_proxy_symbol)s, %(sector_return_pct)s, %(relative_to_spy)s, %(relative_to_qqq)s,
                    %(relative_to_sector_proxy)s, %(attribution_label)s, %(supersedes_outcome_id)s::uuid, %(created_at)s
                )
                ON CONFLICT (idempotency_key) DO NOTHING
                RETURNING *
                """,
                self._outcome_payload(record),
            ).fetchone()
            created = row is not None
            if row is None:
                row = conn.execute(
                    "SELECT * FROM outcome_records WHERE idempotency_key = %s",
                    (record.idempotency_key,),
                ).fetchone()
            if row is None:  # pragma: no cover - database consistency guard
                raise RuntimeError(f"Outcome record was not persisted for key={record.idempotency_key}")
            persisted = self._outcome_from_row(row)
            self.knowledge_graph_outbox.enqueue_with_connection(
                conn,
                aggregate_id=persisted.id,
                payload=persisted.model_dump(mode="json"),
                event_type=KnowledgeGraphOutboxStore.outcome_event_type,
            )
            conn.commit()
        return persisted, created

    def latest_outcome_id(
        self,
        prediction_id: str,
        *,
        horizon_days: int,
        evaluator_version: str,
    ) -> str | None:
        self.ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id
                FROM outcome_records
                WHERE prediction_id = %s::uuid
                  AND horizon_days = %s
                  AND evaluator_version = %s
                ORDER BY evaluated_at DESC, created_at DESC
                LIMIT 1
                """,
                (prediction_id, horizon_days, evaluator_version),
            ).fetchone()
        return str(row["id"]) if row else None

    def list_outcomes(self, cohort_id: str, horizon_days: int | None = None) -> list[OutcomeRecord]:
        self.ensure_schema()
        query = "SELECT * FROM outcome_records WHERE cohort_id = %s::uuid"
        params: list[Any] = [cohort_id]
        if horizon_days is not None:
            query += " AND horizon_days = %s"
            params.append(int(horizon_days))
        query += " ORDER BY selection_date ASC, symbol ASC, horizon_days ASC, evaluated_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._outcome_from_row(row) for row in rows]

    def list_historical_evidence_cases(
        self,
        *,
        market: str,
        as_of_date: date | None,
        horizon_days: int = 28,
        limit: int = 2000,
    ) -> list[tuple[PredictionRecord, OutcomeRecord, str | None]]:
        self.ensure_schema()
        source_limit = max(1, min(int(limit), 5000))
        with self._connect() as conn:
            rows = conn.execute(
                """
                WITH latest_outcomes AS (
                    SELECT DISTINCT ON (outcome.prediction_id, outcome.horizon_days) outcome.*
                    FROM outcome_records AS outcome
                    WHERE outcome.horizon_days = %s
                      AND outcome.market = %s
                      AND (
                        %s::date IS NULL
                        OR outcome.outcome_date < %s::date
                        OR (outcome.outcome_date IS NULL AND outcome.evaluated_at::date < %s::date)
                      )
                    ORDER BY outcome.prediction_id, outcome.horizon_days, outcome.evaluated_at DESC, outcome.created_at DESC
                )
                SELECT
                    to_jsonb(prediction) AS prediction_json,
                    to_jsonb(outcome) AS outcome_json,
                    selection_regime.regime_label AS selection_market_regime_label
                FROM latest_outcomes AS outcome
                INNER JOIN prediction_records AS prediction ON prediction.id = outcome.prediction_id
                LEFT JOIN market_regime_snapshots AS selection_regime ON selection_regime.id = prediction.selection_market_regime_id
                WHERE prediction.market = %s
                  AND (%s::date IS NULL OR prediction.selected_date < %s::date)
                ORDER BY outcome.evaluated_at DESC, outcome.created_at DESC
                LIMIT %s
                """,
                (
                    int(horizon_days),
                    market.lower(),
                    as_of_date,
                    as_of_date,
                    as_of_date,
                    market.lower(),
                    as_of_date,
                    as_of_date,
                    source_limit,
                ),
            ).fetchall()
        return [
            (
                PredictionRecord.model_validate(self._json(row.get("prediction_json"), {})),
                OutcomeRecord.model_validate(self._json(row.get("outcome_json"), {})),
                str(row["selection_market_regime_label"]) if row.get("selection_market_regime_label") else None,
            )
            for row in rows
        ]

    def get_predictions_by_ids(self, prediction_ids: list[str]) -> list[PredictionRecord]:
        self.ensure_schema()
        if not prediction_ids:
            return []
        placeholders = ", ".join("%s::uuid" for _ in prediction_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM prediction_records WHERE id IN ({placeholders})",
                prediction_ids,
            ).fetchall()
        return [self._prediction_from_row(row) for row in rows]

    def get_outcomes_by_ids(self, outcome_ids: list[str]) -> list[OutcomeRecord]:
        self.ensure_schema()
        if not outcome_ids:
            return []
        placeholders = ", ".join("%s::uuid" for _ in outcome_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM outcome_records WHERE id IN ({placeholders})",
                outcome_ids,
            ).fetchall()
        return [self._outcome_from_row(row) for row in rows]

    def create_rule_hypothesis(self, record: RuleHypothesis) -> tuple[RuleHypothesis, bool]:
        self.ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO rule_hypotheses (
                    id, idempotency_key, payload_hash, title, hypothesis_text, expected_metric,
                    evidence_json, affected_conditions_json, suggested_rule_change,
                    proposed_config_patch_json, affected_universe_json, temporal_split_json,
                    generated_by, submitted_by, status, rule_version, feature_version,
                    data_version, candidate_rule_version, latest_validation_id, review_notes,
                    reviewed_by, reviewed_at, created_at, updated_at
                )
                VALUES (
                    %(id)s::uuid, %(idempotency_key)s, %(payload_hash)s, %(title)s, %(hypothesis_text)s, %(expected_metric)s,
                    %(evidence_json)s::jsonb, %(affected_conditions_json)s::jsonb, %(suggested_rule_change)s,
                    %(proposed_config_patch_json)s::jsonb, %(affected_universe_json)s::jsonb, %(temporal_split_json)s::jsonb,
                    %(generated_by)s, %(submitted_by)s, %(status)s, %(rule_version)s, %(feature_version)s,
                    %(data_version)s, %(candidate_rule_version)s, %(latest_validation_id)s::uuid, %(review_notes)s,
                    %(reviewed_by)s, %(reviewed_at)s, %(created_at)s, %(updated_at)s
                )
                ON CONFLICT (idempotency_key) DO NOTHING
                RETURNING *
                """,
                self._rule_hypothesis_payload(record),
            ).fetchone()
            created = row is not None
            if row is None:
                row = conn.execute(
                    "SELECT * FROM rule_hypotheses WHERE idempotency_key = %s",
                    (record.idempotency_key,),
                ).fetchone()
            if row is None:  # pragma: no cover - database consistency guard
                raise RuntimeError(f"Rule hypothesis was not persisted for key={record.idempotency_key}")
            persisted = self._rule_hypothesis_from_row(row)
            if created:
                self._insert_rule_hypothesis_review(
                    conn,
                    hypothesis_id=persisted.id,
                    action="created",
                    from_status=None,
                    to_status=persisted.status.value,
                    reviewer_id=persisted.submitted_by,
                    reviewer_notes="",
                    details={"generated_by": persisted.generated_by.value},
                )
            conn.commit()
        return persisted, created

    def get_rule_hypothesis(self, hypothesis_id: str) -> RuleHypothesis | None:
        self.ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM rule_hypotheses WHERE id = %s::uuid",
                (hypothesis_id,),
            ).fetchone()
        return self._rule_hypothesis_from_row(row) if row else None

    def list_rule_hypotheses(self, status: RuleHypothesisStatus | None = None) -> list[RuleHypothesis]:
        self.ensure_schema()
        query = "SELECT * FROM rule_hypotheses"
        params: list[Any] = []
        if status is not None:
            query += " WHERE status = %s"
            params.append(status.value)
        query += " ORDER BY created_at DESC, id ASC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._rule_hypothesis_from_row(row) for row in rows]

    def list_rule_hypothesis_reviews(self, hypothesis_id: str) -> list[RuleHypothesisReview]:
        self.ensure_schema()
        with self._connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM rule_hypotheses WHERE id = %s::uuid",
                (hypothesis_id,),
            ).fetchone()
            if exists is None:
                raise FileNotFoundError(f"Rule hypothesis was not found: {hypothesis_id}")
            rows = conn.execute(
                """
                SELECT *
                FROM rule_hypothesis_reviews
                WHERE hypothesis_id = %s::uuid
                ORDER BY created_at ASC, id ASC
                """,
                (hypothesis_id,),
            ).fetchall()
        return [self._rule_hypothesis_review_from_row(row) for row in rows]

    def get_hypothesis_validation_by_input_hash(
        self,
        hypothesis_id: str,
        input_hash: str,
    ) -> HypothesisValidationRun | None:
        self.ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM rule_hypothesis_validation_runs
                WHERE hypothesis_id = %s::uuid AND input_hash = %s
                """,
                (hypothesis_id, input_hash),
            ).fetchone()
        return self._hypothesis_validation_from_row(row) if row else None

    def get_hypothesis_validation_run(self, validation_id: str) -> HypothesisValidationRun | None:
        self.ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM rule_hypothesis_validation_runs WHERE id = %s::uuid",
                (validation_id,),
            ).fetchone()
        return self._hypothesis_validation_from_row(row) if row else None

    def create_hypothesis_validation_run(self, record: HypothesisValidationRun) -> tuple[HypothesisValidationRun, bool]:
        self.ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO rule_hypothesis_validation_runs (
                    id, hypothesis_id, idempotency_key, input_hash, validation_status,
                    qualified_for_review, frozen_input_json, baseline_metrics_json,
                    candidate_metrics_json, criteria_json, caveats_json, errors_json,
                    evaluator_version, started_at, completed_at
                )
                VALUES (
                    %(id)s::uuid, %(hypothesis_id)s::uuid, %(idempotency_key)s, %(input_hash)s, %(validation_status)s,
                    %(qualified_for_review)s, %(frozen_input_json)s::jsonb, %(baseline_metrics_json)s::jsonb,
                    %(candidate_metrics_json)s::jsonb, %(criteria_json)s::jsonb, %(caveats_json)s::jsonb, %(errors_json)s::jsonb,
                    %(evaluator_version)s, %(started_at)s, %(completed_at)s
                )
                ON CONFLICT (hypothesis_id, input_hash) DO NOTHING
                RETURNING *
                """,
                self._hypothesis_validation_payload(record),
            ).fetchone()
            created = row is not None
            if row is None:
                row = conn.execute(
                    """
                    SELECT * FROM rule_hypothesis_validation_runs
                    WHERE hypothesis_id = %s::uuid AND input_hash = %s
                    """,
                    (record.hypothesis_id, record.input_hash),
                ).fetchone()
            if row is None:  # pragma: no cover - database consistency guard
                raise RuntimeError(f"Hypothesis validation was not persisted for key={record.idempotency_key}")
            conn.commit()
        return self._hypothesis_validation_from_row(row), created

    def complete_hypothesis_validation_run(self, record: HypothesisValidationRun) -> HypothesisValidationRun:
        self.ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                """
                UPDATE rule_hypothesis_validation_runs
                SET validation_status = %(validation_status)s,
                    qualified_for_review = %(qualified_for_review)s,
                    baseline_metrics_json = %(baseline_metrics_json)s::jsonb,
                    candidate_metrics_json = %(candidate_metrics_json)s::jsonb,
                    criteria_json = %(criteria_json)s::jsonb,
                    caveats_json = %(caveats_json)s::jsonb,
                    errors_json = %(errors_json)s::jsonb,
                    completed_at = %(completed_at)s
                WHERE id = %(id)s::uuid
                  AND validation_status = 'running'
                RETURNING *
                """,
                self._hypothesis_validation_payload(record),
            ).fetchone()
            if row is None:
                row = conn.execute(
                    "SELECT * FROM rule_hypothesis_validation_runs WHERE id = %s::uuid",
                    (record.id,),
                ).fetchone()
            if row is None:  # pragma: no cover - database consistency guard
                raise RuntimeError(f"Hypothesis validation was not found id={record.id}")
            conn.commit()
        return self._hypothesis_validation_from_row(row)

    def transition_rule_hypothesis(
        self,
        hypothesis_id: str,
        *,
        allowed_current_statuses: set[RuleHypothesisStatus],
        new_status: RuleHypothesisStatus,
        reviewer_id: str,
        reviewer_notes: str = "",
        latest_validation_id: str | None = None,
        action: str,
        details: dict[str, Any] | None = None,
    ) -> RuleHypothesis:
        self.ensure_schema()
        allowed_values = sorted(status.value for status in allowed_current_statuses)
        placeholders = ", ".join("%s" for _ in allowed_values)
        with self._connect() as conn:
            current = conn.execute(
                "SELECT status FROM rule_hypotheses WHERE id = %s::uuid",
                (hypothesis_id,),
            ).fetchone()
            if current is None:
                raise FileNotFoundError(f"Rule hypothesis was not found: {hypothesis_id}")
            row = conn.execute(
                f"""
                UPDATE rule_hypotheses
                SET status = %s,
                    latest_validation_id = COALESCE(%s::uuid, latest_validation_id),
                    review_notes = %s,
                    reviewed_by = %s,
                    reviewed_at = now(),
                    updated_at = now()
                WHERE id = %s::uuid
                  AND status IN ({placeholders})
                RETURNING *
                """,
                (
                    new_status.value,
                    latest_validation_id,
                    reviewer_notes,
                    reviewer_id,
                    hypothesis_id,
                    *allowed_values,
                ),
            ).fetchone()
            if row is None:
                raise ValueError(
                    f"Rule hypothesis {hypothesis_id} cannot transition from {current['status']} to {new_status.value}"
                )
            self._insert_rule_hypothesis_review(
                conn,
                hypothesis_id=hypothesis_id,
                action=action,
                from_status=str(current["status"]),
                to_status=new_status.value,
                reviewer_id=reviewer_id,
                reviewer_notes=reviewer_notes,
                details=details or {},
            )
            conn.commit()
        return self._rule_hypothesis_from_row(row)

    def create_pattern_candidates(self, records: list[PatternCandidate]) -> tuple[list[PatternCandidate], int]:
        self.ensure_schema()
        if not records:
            return [], 0
        persisted: list[PatternCandidate] = []
        created_count = 0
        with self._connect() as conn:
            for record in records:
                row = conn.execute(
                    """
                    INSERT INTO pattern_candidates (
                        id, idempotency_key, payload_hash, pattern_key, market, horizon_days,
                        condition_set_json, population_definition_json, metrics_json,
                        source_prediction_ids_json, source_outcome_ids_json, sample_size,
                        evaluable_case_count, success_count, success_rate_pct, average_return_pct,
                        effect_size_pct_points, p_value, confidence_interval_low_pct,
                        confidence_interval_high_pct, approval_eligible, status, rule_version,
                        feature_version, data_version, statistics_version, as_of_date,
                        review_notes, reviewed_by, reviewed_at, created_at, updated_at
                    )
                    VALUES (
                        %(id)s::uuid, %(idempotency_key)s, %(payload_hash)s, %(pattern_key)s, %(market)s, %(horizon_days)s,
                        %(condition_set_json)s::jsonb, %(population_definition_json)s::jsonb, %(metrics_json)s::jsonb,
                        %(source_prediction_ids_json)s::jsonb, %(source_outcome_ids_json)s::jsonb, %(sample_size)s,
                        %(evaluable_case_count)s, %(success_count)s, %(success_rate_pct)s, %(average_return_pct)s,
                        %(effect_size_pct_points)s, %(p_value)s, %(confidence_interval_low_pct)s,
                        %(confidence_interval_high_pct)s, %(approval_eligible)s, %(status)s, %(rule_version)s,
                        %(feature_version)s, %(data_version)s, %(statistics_version)s, %(as_of_date)s,
                        %(review_notes)s, %(reviewed_by)s, %(reviewed_at)s, %(created_at)s, %(updated_at)s
                    )
                    ON CONFLICT (idempotency_key) DO NOTHING
                    RETURNING *
                    """,
                    self._pattern_candidate_payload(record),
                ).fetchone()
                created = row is not None
                if row is None:
                    row = conn.execute(
                        "SELECT * FROM pattern_candidates WHERE idempotency_key = %s",
                        (record.idempotency_key,),
                    ).fetchone()
                if row is None:  # pragma: no cover - database consistency guard
                    raise RuntimeError(f"Pattern candidate was not persisted for key={record.idempotency_key}")
                persisted_record = self._pattern_candidate_from_row(row)
                persisted.append(persisted_record)
                if created:
                    created_count += 1
                    self._insert_pattern_candidate_review(
                        conn,
                        pattern_candidate_id=persisted_record.id,
                        action="discovered",
                        from_status=None,
                        to_status=persisted_record.status.value,
                        reviewer_id="deterministic_pattern_discovery",
                        reviewer_notes="",
                        details={
                            "approval_eligible": persisted_record.approval_eligible,
                            "statistics_version": persisted_record.statistics_version,
                        },
                    )
            conn.commit()
        return persisted, created_count

    def get_pattern_candidate(self, pattern_candidate_id: str) -> PatternCandidate | None:
        self.ensure_schema()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM pattern_candidates WHERE id = %s::uuid",
                (pattern_candidate_id,),
            ).fetchone()
        return self._pattern_candidate_from_row(row) if row else None

    def list_pattern_candidates(
        self,
        *,
        market: str | None = None,
        status: PatternCandidateStatus | None = None,
        as_of_date: date | None = None,
    ) -> list[PatternCandidate]:
        self.ensure_schema()
        clauses: list[str] = []
        params: list[Any] = []
        if market:
            clauses.append("market = %s")
            params.append(market.lower())
        if status is not None:
            clauses.append("status = %s")
            params.append(status.value)
        if as_of_date is not None:
            clauses.append("as_of_date = %s")
            params.append(as_of_date)
        query = "SELECT * FROM pattern_candidates"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY as_of_date DESC, approval_eligible DESC, sample_size DESC, pattern_key ASC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._pattern_candidate_from_row(row) for row in rows]

    def list_pattern_candidate_reviews(self, pattern_candidate_id: str) -> list[PatternCandidateReview]:
        self.ensure_schema()
        with self._connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM pattern_candidates WHERE id = %s::uuid",
                (pattern_candidate_id,),
            ).fetchone()
            if exists is None:
                raise FileNotFoundError(f"Pattern candidate was not found: {pattern_candidate_id}")
            rows = conn.execute(
                """
                SELECT *
                FROM pattern_candidate_reviews
                WHERE pattern_candidate_id = %s::uuid
                ORDER BY created_at ASC, id ASC
                """,
                (pattern_candidate_id,),
            ).fetchall()
        return [self._pattern_candidate_review_from_row(row) for row in rows]

    def transition_pattern_candidate(
        self,
        pattern_candidate_id: str,
        *,
        allowed_current_statuses: set[PatternCandidateStatus],
        new_status: PatternCandidateStatus,
        reviewer_id: str,
        reviewer_notes: str,
        action: str,
        details: dict[str, Any] | None = None,
    ) -> PatternCandidate:
        self.ensure_schema()
        allowed_values = sorted(status.value for status in allowed_current_statuses)
        placeholders = ", ".join("%s" for _ in allowed_values)
        with self._connect() as conn:
            current = conn.execute(
                "SELECT status FROM pattern_candidates WHERE id = %s::uuid",
                (pattern_candidate_id,),
            ).fetchone()
            if current is None:
                raise FileNotFoundError(f"Pattern candidate was not found: {pattern_candidate_id}")
            row = conn.execute(
                f"""
                UPDATE pattern_candidates
                SET status = %s,
                    review_notes = %s,
                    reviewed_by = %s,
                    reviewed_at = now(),
                    updated_at = now()
                WHERE id = %s::uuid
                  AND status IN ({placeholders})
                RETURNING *
                """,
                (new_status.value, reviewer_notes, reviewer_id, pattern_candidate_id, *allowed_values),
            ).fetchone()
            if row is None:
                raise ValueError(
                    f"Pattern candidate {pattern_candidate_id} cannot transition from {current['status']} to {new_status.value}"
                )
            self._insert_pattern_candidate_review(
                conn,
                pattern_candidate_id=pattern_candidate_id,
                action=action,
                from_status=str(current["status"]),
                to_status=new_status.value,
                reviewer_id=reviewer_id,
                reviewer_notes=reviewer_notes,
                details=details or {},
            )
            conn.commit()
        return self._pattern_candidate_from_row(row)

    def upsert_outcome_summaries(self, records: list[OutcomeSummaryRecord]) -> list[OutcomeSummaryRecord]:
        self.ensure_schema()
        if not records:
            return []
        persisted: list[OutcomeSummaryRecord] = []
        with self._connect() as conn:
            for record in records:
                row = conn.execute(
                    """
                    INSERT INTO outcome_summary_snapshots (
                        id, cohort_id, grouping, group_value, horizon_days,
                        prediction_count, available_outcome_count, data_quality_excluded_count,
                        positive_count, negative_count, average_return_pct,
                        rule_version, feature_version, data_version, evaluator_version, calculated_at
                    )
                    VALUES (
                        %(id)s::uuid, %(cohort_id)s::uuid, %(grouping)s, %(group_value)s, %(horizon_days)s,
                        %(prediction_count)s, %(available_outcome_count)s, %(data_quality_excluded_count)s,
                        %(positive_count)s, %(negative_count)s, %(average_return_pct)s,
                        %(rule_version)s, %(feature_version)s, %(data_version)s, %(evaluator_version)s, %(calculated_at)s
                    )
                    ON CONFLICT (cohort_id, grouping, group_value, horizon_days, rule_version, feature_version, data_version, evaluator_version)
                    DO UPDATE SET
                        prediction_count = EXCLUDED.prediction_count,
                        available_outcome_count = EXCLUDED.available_outcome_count,
                        data_quality_excluded_count = EXCLUDED.data_quality_excluded_count,
                        positive_count = EXCLUDED.positive_count,
                        negative_count = EXCLUDED.negative_count,
                        average_return_pct = EXCLUDED.average_return_pct,
                        calculated_at = EXCLUDED.calculated_at,
                        updated_at = now()
                    RETURNING *
                    """,
                    self._summary_payload(record),
                ).fetchone()
                persisted.append(self._summary_from_row(row))
            conn.commit()
        return persisted

    def list_outcome_summaries(self, cohort_id: str) -> list[OutcomeSummaryRecord]:
        self.ensure_schema()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM outcome_summary_snapshots
                WHERE cohort_id = %s::uuid
                ORDER BY horizon_days ASC, grouping ASC, group_value ASC, calculated_at DESC
                """,
                (cohort_id,),
            ).fetchall()
        return [self._summary_from_row(row) for row in rows]

    def upsert_canonical_bars(self, bars: list[dict[str, Any]]) -> None:
        self.ensure_schema()
        if not bars:
            return
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO canonical_ohlc_bars (
                        id, market, symbol, bar_date, provider, adjustment_policy,
                        data_version, retrieved_at, open, high, low, close, volume, source_hash
                    )
                    VALUES (
                        %(id)s::uuid, %(market)s, %(symbol)s, %(bar_date)s, %(provider)s, %(adjustment_policy)s,
                        %(data_version)s, %(retrieved_at)s, %(open)s, %(high)s, %(low)s, %(close)s, %(volume)s, %(source_hash)s
                    )
                    ON CONFLICT (market, symbol, bar_date, provider, adjustment_policy, data_version) DO NOTHING
                    """,
                    bars,
                )
            conn.commit()

    def list_canonical_bars(
        self,
        *,
        market: str,
        symbol: str,
        data_version: str,
        through_date: Any | None = None,
    ) -> list[dict[str, Any]]:
        self.ensure_schema()
        query = """
            SELECT bar_date, open, high, low, close, volume, provider, adjustment_policy, data_version
            FROM canonical_ohlc_bars
            WHERE market = %s
              AND symbol = %s
              AND data_version = %s
        """
        params: list[Any] = [market, symbol, data_version]
        if through_date is not None:
            query += " AND bar_date <= %s"
            params.append(through_date)
        query += " ORDER BY bar_date ASC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def record_data_quality_event(
        self,
        *,
        id: str,
        dedupe_key: str,
        entity_type: str,
        entity_id: str,
        cohort_id: str,
        symbol: str | None,
        event_code: str,
        severity: str,
        details: dict[str, Any],
        rule_version: str,
        feature_version: str,
        data_version: str,
        observed_at: datetime | None = None,
    ) -> None:
        self.ensure_schema()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO data_quality_events (
                    id, dedupe_key, entity_type, entity_id, cohort_id, symbol,
                    event_code, severity, details_json, rule_version, feature_version,
                    data_version, observed_at
                )
                VALUES (
                    %s::uuid, %s, %s, %s, %s::uuid, %s,
                    %s, %s, %s::jsonb, %s, %s, %s, %s
                )
                ON CONFLICT (dedupe_key) DO NOTHING
                """,
                (
                    id,
                    dedupe_key,
                    entity_type,
                    entity_id,
                    cohort_id,
                    symbol,
                    event_code,
                    severity,
                    json.dumps(details, default=str, sort_keys=True),
                    rule_version,
                    feature_version,
                    data_version,
                    observed_at or datetime.now(UTC),
                ),
            )
            conn.commit()

    @staticmethod
    def _insert_rule_hypothesis_review(
        conn: Any,
        *,
        hypothesis_id: str,
        action: str,
        from_status: str | None,
        to_status: str,
        reviewer_id: str,
        reviewer_notes: str,
        details: dict[str, Any],
    ) -> None:
        conn.execute(
            """
            INSERT INTO rule_hypothesis_reviews (
                id, hypothesis_id, action, from_status, to_status,
                reviewer_id, reviewer_notes, details_json
            )
            VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                str(uuid4()),
                hypothesis_id,
                action,
                from_status,
                to_status,
                reviewer_id,
                reviewer_notes,
                json.dumps(details, default=str, sort_keys=True),
            ),
        )

    @staticmethod
    def _insert_pattern_candidate_review(
        conn: Any,
        *,
        pattern_candidate_id: str,
        action: str,
        from_status: str | None,
        to_status: str,
        reviewer_id: str,
        reviewer_notes: str,
        details: dict[str, Any],
    ) -> None:
        conn.execute(
            """
            INSERT INTO pattern_candidate_reviews (
                id, pattern_candidate_id, action, from_status, to_status,
                reviewer_id, reviewer_notes, details_json
            )
            VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                str(uuid4()),
                pattern_candidate_id,
                action,
                from_status,
                to_status,
                reviewer_id,
                reviewer_notes,
                json.dumps(details, default=str, sort_keys=True),
            ),
        )

    @staticmethod
    def _json(value: Any, fallback: Any) -> Any:
        if value is None:
            return fallback
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return fallback
        return value

    @classmethod
    def _rule_hypothesis_from_row(cls, row: dict[str, Any]) -> RuleHypothesis:
        return RuleHypothesis(
            id=str(row["id"]),
            idempotency_key=str(row["idempotency_key"]),
            payload_hash=str(row["payload_hash"]),
            title=str(row["title"]),
            hypothesis_text=str(row["hypothesis_text"]),
            expected_metric=str(row["expected_metric"]),
            evidence_json=cls._json(row.get("evidence_json"), {}),
            affected_conditions=cls._json(row.get("affected_conditions_json"), {}),
            suggested_rule_change=str(row.get("suggested_rule_change") or ""),
            proposed_config_patch=cls._json(row.get("proposed_config_patch_json"), {}),
            affected_universe=cls._json(row.get("affected_universe_json"), {}),
            temporal_split=cls._json(row.get("temporal_split_json"), {}),
            generated_by=str(row["generated_by"]),
            submitted_by=str(row["submitted_by"]),
            status=str(row["status"]),
            rule_version=str(row["rule_version"]),
            feature_version=str(row["feature_version"]),
            data_version=str(row["data_version"]),
            candidate_rule_version=str(row["candidate_rule_version"]),
            latest_validation_id=str(row["latest_validation_id"]) if row.get("latest_validation_id") else None,
            review_notes=row.get("review_notes"),
            reviewed_by=row.get("reviewed_by"),
            reviewed_at=row.get("reviewed_at"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @classmethod
    def _hypothesis_validation_from_row(cls, row: dict[str, Any]) -> HypothesisValidationRun:
        return HypothesisValidationRun(
            id=str(row["id"]),
            hypothesis_id=str(row["hypothesis_id"]),
            idempotency_key=str(row["idempotency_key"]),
            input_hash=str(row["input_hash"]),
            validation_status=str(row["validation_status"]),
            qualified_for_review=bool(row.get("qualified_for_review")),
            frozen_input_json=cls._json(row.get("frozen_input_json"), {}),
            baseline_metrics_json=cls._json(row.get("baseline_metrics_json"), {}),
            candidate_metrics_json=cls._json(row.get("candidate_metrics_json"), {}),
            criteria_json=cls._json(row.get("criteria_json"), {}),
            caveats=cls._json(row.get("caveats_json"), []),
            errors=cls._json(row.get("errors_json"), []),
            evaluator_version=str(row["evaluator_version"]),
            started_at=row["started_at"],
            completed_at=row.get("completed_at"),
        )

    @classmethod
    def _rule_hypothesis_review_from_row(cls, row: dict[str, Any]) -> RuleHypothesisReview:
        return RuleHypothesisReview(
            id=str(row["id"]),
            hypothesis_id=str(row["hypothesis_id"]),
            action=str(row["action"]),
            from_status=str(row["from_status"]) if row.get("from_status") else None,
            to_status=str(row["to_status"]),
            reviewer_id=str(row["reviewer_id"]),
            reviewer_notes=str(row.get("reviewer_notes") or ""),
            details_json=cls._json(row.get("details_json"), {}),
            created_at=row["created_at"],
        )

    @classmethod
    def _pattern_candidate_from_row(cls, row: dict[str, Any]) -> PatternCandidate:
        return PatternCandidate(
            id=str(row["id"]),
            idempotency_key=str(row["idempotency_key"]),
            payload_hash=str(row["payload_hash"]),
            pattern_key=str(row["pattern_key"]),
            market=str(row["market"]),
            horizon_days=int(row["horizon_days"]),
            condition_set=cls._json(row.get("condition_set_json"), {}),
            population_definition=cls._json(row.get("population_definition_json"), {}),
            metrics_json=cls._json(row.get("metrics_json"), {}),
            source_prediction_ids=cls._json(row.get("source_prediction_ids_json"), []),
            source_outcome_ids=cls._json(row.get("source_outcome_ids_json"), []),
            sample_size=int(row["sample_size"]),
            evaluable_case_count=int(row["evaluable_case_count"]),
            success_count=int(row["success_count"]),
            success_rate_pct=row.get("success_rate_pct"),
            average_return_pct=row.get("average_return_pct"),
            effect_size_pct_points=row.get("effect_size_pct_points"),
            p_value=row.get("p_value"),
            confidence_interval_low_pct=row.get("confidence_interval_low_pct"),
            confidence_interval_high_pct=row.get("confidence_interval_high_pct"),
            approval_eligible=bool(row.get("approval_eligible")),
            status=str(row["status"]),
            rule_version=str(row["rule_version"]),
            feature_version=str(row["feature_version"]),
            data_version=str(row["data_version"]),
            statistics_version=str(row["statistics_version"]),
            as_of_date=row["as_of_date"],
            review_notes=row.get("review_notes"),
            reviewed_by=row.get("reviewed_by"),
            reviewed_at=row.get("reviewed_at"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @classmethod
    def _pattern_candidate_review_from_row(cls, row: dict[str, Any]) -> PatternCandidateReview:
        return PatternCandidateReview(
            id=str(row["id"]),
            pattern_candidate_id=str(row["pattern_candidate_id"]),
            action=str(row["action"]),
            from_status=str(row["from_status"]) if row.get("from_status") else None,
            to_status=str(row["to_status"]),
            reviewer_id=str(row["reviewer_id"]),
            reviewer_notes=str(row.get("reviewer_notes") or ""),
            details_json=cls._json(row.get("details_json"), {}),
            created_at=row["created_at"],
        )

    @classmethod
    def _prediction_from_row(cls, row: dict[str, Any]) -> PredictionRecord:
        return PredictionRecord(
            id=str(row["id"]),
            idempotency_key=str(row["idempotency_key"]),
            payload_hash=str(row["payload_hash"]),
            cohort_id=str(row["cohort_id"]),
            symbol=str(row["symbol"]),
            market=str(row["market"]),
            selected_at=row["selected_at"],
            selected_date=row["selected_date"],
            selected_price=row.get("selected_price"),
            categories=cls._json(row.get("categories_json"), []),
            setup_type=str(row.get("setup_type") or ""),
            trend_state=str(row.get("trend_state") or ""),
            extension_state=row.get("extension_state"),
            score_dynamics_state=row.get("score_dynamics_state"),
            trigger_state=row.get("trigger_state"),
            trigger_score=row.get("trigger_score"),
            trigger_threshold=row.get("trigger_threshold"),
            score=row.get("score"),
            candidate_type=row.get("candidate_type"),
            entry_readiness=row.get("entry_readiness"),
            blocked_by=row.get("blocked_by"),
            risk_flags=cls._json(row.get("risk_flags_json"), []),
            data_quality_flags=cls._json(row.get("data_quality_flags_json"), []),
            expected_horizon_days=int(row.get("expected_horizon_days") or 28),
            expected_direction=str(row.get("expected_direction") or "up"),
            prediction_type=str(row["prediction_type"]),
            invalidation_conditions=cls._json(row.get("invalidation_conditions_json"), {}),
            deterministic_reason=str(row.get("deterministic_reason") or ""),
            selection_snapshot_json=cls._json(row.get("selection_snapshot_json"), {}),
            source_run_id=row.get("source_run_id"),
            source_report_id=str(row["source_report_id"]) if row.get("source_report_id") else None,
            rule_version=str(row["rule_version"]),
            feature_version=str(row["feature_version"]),
            data_version=str(row["data_version"]),
            selection_market_regime_id=(
                str(row["selection_market_regime_id"]) if row.get("selection_market_regime_id") else None
            ),
            supersedes_prediction_id=str(row["supersedes_prediction_id"]) if row.get("supersedes_prediction_id") else None,
            correction_reason=row.get("correction_reason"),
            created_at=row["created_at"],
        )

    @classmethod
    def _outcome_from_row(cls, row: dict[str, Any]) -> OutcomeRecord:
        return OutcomeRecord(
            id=str(row["id"]),
            idempotency_key=str(row["idempotency_key"]),
            payload_hash=str(row["payload_hash"]),
            prediction_id=str(row["prediction_id"]),
            cohort_id=str(row["cohort_id"]),
            symbol=str(row["symbol"]),
            market=str(row["market"]),
            horizon_days=int(row["horizon_days"]),
            selection_date=row["selection_date"],
            outcome_date=row.get("outcome_date"),
            evaluated_at=row["evaluated_at"],
            outcome_status=str(row["outcome_status"]),
            outcome_label=str(row["outcome_label"]),
            selected_price=row.get("selected_price"),
            horizon_price=row.get("horizon_price"),
            return_pct=row.get("return_pct"),
            directional_return_pct=row.get("directional_return_pct"),
            max_favorable_excursion_pct=row.get("max_favorable_excursion_pct"),
            max_adverse_excursion_pct=row.get("max_adverse_excursion_pct"),
            price_path_complete=bool(row.get("price_path_complete")),
            daily_snapshot_path_complete=bool(row.get("daily_snapshot_path_complete")),
            daily_snapshot_coverage_pct=float(row.get("daily_snapshot_coverage_pct") or 0.0),
            followed_through=row.get("followed_through"),
            false_positive=row.get("false_positive"),
            invalidated_quickly=row.get("invalidated_quickly"),
            missed_follow_through=row.get("missed_follow_through"),
            stayed_valid=row.get("stayed_valid"),
            categories=cls._json(row.get("categories_json"), []),
            setup_type=row.get("setup_type"),
            blocked_by=row.get("blocked_by"),
            data_quality_flags=cls._json(row.get("data_quality_flags_json"), []),
            attribution_json=cls._json(row.get("attribution_json"), {}),
            price_source=row.get("price_source"),
            selection_bar_date=row.get("selection_bar_date"),
            horizon_bar_date=row.get("horizon_bar_date"),
            evaluator_version=str(row["evaluator_version"]),
            rule_version=str(row["rule_version"]),
            feature_version=str(row["feature_version"]),
            data_version=str(row["data_version"]),
            selection_market_regime_id=(
                str(row["selection_market_regime_id"]) if row.get("selection_market_regime_id") else None
            ),
            outcome_market_regime_id=(
                str(row["outcome_market_regime_id"]) if row.get("outcome_market_regime_id") else None
            ),
            market_regime_label=row.get("market_regime_label"),
            market_return_pct=row.get("market_return_pct"),
            sector_proxy_symbol=row.get("sector_proxy_symbol"),
            sector_return_pct=row.get("sector_return_pct"),
            relative_to_spy=row.get("relative_to_spy"),
            relative_to_qqq=row.get("relative_to_qqq"),
            relative_to_sector_proxy=row.get("relative_to_sector_proxy"),
            attribution_label=row.get("attribution_label"),
            supersedes_outcome_id=str(row["supersedes_outcome_id"]) if row.get("supersedes_outcome_id") else None,
            created_at=row["created_at"],
        )

    @staticmethod
    def _summary_from_row(row: dict[str, Any]) -> OutcomeSummaryRecord:
        return OutcomeSummaryRecord(
            cohort_id=str(row["cohort_id"]),
            grouping=str(row["grouping"]),
            group_value=str(row["group_value"]),
            horizon_days=int(row["horizon_days"]),
            prediction_count=int(row.get("prediction_count") or 0),
            available_outcome_count=int(row.get("available_outcome_count") or 0),
            data_quality_excluded_count=int(row.get("data_quality_excluded_count") or 0),
            positive_count=int(row.get("positive_count") or 0),
            negative_count=int(row.get("negative_count") or 0),
            average_return_pct=row.get("average_return_pct"),
            rule_version=str(row["rule_version"]),
            feature_version=str(row["feature_version"]),
            data_version=str(row["data_version"]),
            evaluator_version=str(row["evaluator_version"]),
            calculated_at=row["calculated_at"],
        )

    @staticmethod
    def _prediction_payload(record: PredictionRecord) -> dict[str, Any]:
        payload = record.model_dump(mode="json")
        for key in (
            "categories",
            "risk_flags",
            "data_quality_flags",
            "invalidation_conditions",
            "selection_snapshot_json",
        ):
            payload[f"{key}_json" if key != "selection_snapshot_json" else key] = json.dumps(payload.pop(key), sort_keys=True)
        return payload

    @staticmethod
    def _rule_hypothesis_payload(record: RuleHypothesis) -> dict[str, Any]:
        payload = record.model_dump(mode="json")
        for key in (
            "evidence_json",
            "affected_conditions",
            "proposed_config_patch",
            "affected_universe",
            "temporal_split",
        ):
            target_key = {
                "affected_conditions": "affected_conditions_json",
                "proposed_config_patch": "proposed_config_patch_json",
                "affected_universe": "affected_universe_json",
                "temporal_split": "temporal_split_json",
            }.get(key, key)
            payload[target_key] = json.dumps(payload.pop(key), default=str, sort_keys=True)
        return payload

    @staticmethod
    def _hypothesis_validation_payload(record: HypothesisValidationRun) -> dict[str, Any]:
        payload = record.model_dump(mode="json")
        for key in (
            "frozen_input_json",
            "baseline_metrics_json",
            "candidate_metrics_json",
            "criteria_json",
            "caveats",
            "errors",
        ):
            target_key = {"caveats": "caveats_json", "errors": "errors_json"}.get(key, key)
            payload[target_key] = json.dumps(payload.pop(key), default=str, sort_keys=True)
        return payload

    @staticmethod
    def _pattern_candidate_payload(record: PatternCandidate) -> dict[str, Any]:
        payload = record.model_dump(mode="json")
        for key in (
            "condition_set",
            "population_definition",
            "metrics_json",
            "source_prediction_ids",
            "source_outcome_ids",
        ):
            target_key = {
                "condition_set": "condition_set_json",
                "population_definition": "population_definition_json",
                "source_prediction_ids": "source_prediction_ids_json",
                "source_outcome_ids": "source_outcome_ids_json",
            }.get(key, key)
            payload[target_key] = json.dumps(payload.pop(key), default=str, sort_keys=True)
        return payload

    @staticmethod
    def _outcome_payload(record: OutcomeRecord) -> dict[str, Any]:
        payload = record.model_dump(mode="json")
        for key in ("categories", "data_quality_flags", "attribution_json"):
            payload[f"{key}_json" if key != "attribution_json" else key] = json.dumps(payload.pop(key), sort_keys=True)
        return payload

    @classmethod
    def _market_regime_from_row(cls, row: dict[str, Any]) -> MarketRegimeSnapshot:
        return MarketRegimeSnapshot(
            id=str(row["id"]),
            idempotency_key=str(row["idempotency_key"]),
            payload_hash=str(row["payload_hash"]),
            market=str(row["market"]),
            as_of_date=row["as_of_date"],
            primary_benchmark_symbol=row.get("primary_benchmark_symbol"),
            benchmark_returns_json=cls._json(row.get("benchmark_returns_json"), {}),
            volatility_20d_pct=row.get("volatility_20d_pct"),
            regime_label=str(row["regime_label"]),
            classifier_version=str(row["classifier_version"]),
            raw_inputs_json=cls._json(row.get("raw_inputs_json"), {}),
            data_quality_flags=cls._json(row.get("data_quality_flags_json"), []),
            rule_version=str(row["rule_version"]),
            feature_version=str(row["feature_version"]),
            data_version=str(row["data_version"]),
            created_at=row["created_at"],
        )

    @staticmethod
    def _market_regime_payload(record: MarketRegimeSnapshot) -> dict[str, Any]:
        payload = record.model_dump(mode="json")
        for key in ("benchmark_returns_json", "raw_inputs_json", "data_quality_flags"):
            target_key = "data_quality_flags_json" if key == "data_quality_flags" else key
            payload[target_key] = json.dumps(payload.pop(key), sort_keys=True)
        return payload

    @staticmethod
    def _summary_payload(record: OutcomeSummaryRecord) -> dict[str, Any]:
        payload = record.model_dump(mode="json")
        payload["id"] = str(
            uuid5(
                NAMESPACE_URL,
                "tradeghost:outcome-summary:"
                f"{record.cohort_id}:{record.grouping}:{record.group_value}:{record.horizon_days}:"
                f"{record.rule_version}:{record.feature_version}:{record.data_version}:{record.evaluator_version}",
            )
        )
        return payload
