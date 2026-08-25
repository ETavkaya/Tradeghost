from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from tradeghost.services.knowledge_graph.outbox import KnowledgeGraphOutboxStore


@dataclass(frozen=True)
class ReportProjection:
    report: dict[str, Any]
    segment: dict[str, Any]
    assets: list[dict[str, Any]]
    signals: list[dict[str, Any]]


@dataclass(frozen=True)
class PredictionProjection:
    prediction: dict[str, Any]
    asset: dict[str, Any]
    confirmation_conditions: list[dict[str, Any]]
    invalidation_conditions: list[dict[str, Any]]


@dataclass(frozen=True)
class OutcomeProjection:
    outcome: dict[str, Any]
    asset: dict[str, Any]


def build_market_regime_projection(payload: dict[str, Any]) -> dict[str, Any]:
    regime_id = _required_id(payload, "id", "market regime")
    return _without_none(
        {
            "regime_id": regime_id,
            "idempotency_key": payload.get("idempotency_key"),
            "payload_hash": payload.get("payload_hash"),
            "market": _normalized_market(payload.get("market")),
            "as_of_date": payload.get("as_of_date"),
            "primary_benchmark_symbol": payload.get("primary_benchmark_symbol"),
            "benchmark_returns_json": _json_property(payload.get("benchmark_returns_json") or {}),
            "volatility_20d_pct": payload.get("volatility_20d_pct"),
            "regime_label": payload.get("regime_label"),
            "classifier_version": payload.get("classifier_version"),
            "raw_inputs_json": _json_property(payload.get("raw_inputs_json") or {}),
            "data_quality_flags": _string_list(payload.get("data_quality_flags")),
            "rule_version": payload.get("rule_version"),
            "feature_version": payload.get("feature_version"),
            "data_version": payload.get("data_version"),
            "created_at": payload.get("created_at"),
            "source_system": "tradeghost.research",
            "projection_version": "phase2d_v1",
        }
    )


def build_prediction_projection(payload: dict[str, Any]) -> PredictionProjection:
    prediction_id = _required_id(payload, "id", "prediction")
    market = _normalized_market(payload.get("market"))
    symbol = str(payload.get("symbol") or "").strip().upper()
    if not symbol:
        raise ValueError("Graph projection prediction payload is missing symbol")
    prediction = _without_none(
        {
            "prediction_id": prediction_id,
            "idempotency_key": payload.get("idempotency_key"),
            "payload_hash": payload.get("payload_hash"),
            "cohort_id": payload.get("cohort_id"),
            "asset_key": f"{market}:{symbol}",
            "symbol": symbol,
            "market": market,
            "selected_at": payload.get("selected_at"),
            "selected_date": payload.get("selected_date"),
            "selected_price": payload.get("selected_price"),
            "categories": _string_list(payload.get("categories")),
            "setup_type": payload.get("setup_type"),
            "trend_state": payload.get("trend_state"),
            "extension_state": payload.get("extension_state"),
            "score_dynamics_state": payload.get("score_dynamics_state"),
            "trigger_state": payload.get("trigger_state"),
            "trigger_score": payload.get("trigger_score"),
            "trigger_threshold": payload.get("trigger_threshold"),
            "score": payload.get("score"),
            "candidate_type": payload.get("candidate_type"),
            "entry_readiness": payload.get("entry_readiness"),
            "blocked_by": payload.get("blocked_by"),
            "risk_flags": _string_list(payload.get("risk_flags")),
            "data_quality_flags": _string_list(payload.get("data_quality_flags")),
            "expected_horizon_days": payload.get("expected_horizon_days"),
            "expected_direction": payload.get("expected_direction"),
            "prediction_type": payload.get("prediction_type"),
            "invalidation_conditions_json": _json_property(payload.get("invalidation_conditions") or {}),
            "deterministic_reason": payload.get("deterministic_reason"),
            "selection_market_regime_id": payload.get("selection_market_regime_id"),
            "source_run_id": payload.get("source_run_id"),
            "source_report_id": payload.get("source_report_id"),
            "rule_version": payload.get("rule_version"),
            "feature_version": payload.get("feature_version"),
            "data_version": payload.get("data_version"),
            "supersedes_prediction_id": payload.get("supersedes_prediction_id"),
            "correction_reason": payload.get("correction_reason"),
            "created_at": payload.get("created_at"),
            "source_system": "tradeghost.research",
            "projection_version": "phase2d_v1",
        }
    )
    conditions = payload.get("invalidation_conditions")
    conditions = conditions if isinstance(conditions, dict) else {}
    return PredictionProjection(
        prediction=prediction,
        asset=_asset_projection(market=market, symbol=symbol),
        confirmation_conditions=_conditions_for_prediction(prediction_id, conditions, "confirmation"),
        invalidation_conditions=_conditions_for_prediction(prediction_id, conditions, "invalidation"),
    )


def build_outcome_projection(payload: dict[str, Any]) -> OutcomeProjection:
    outcome_id = _required_id(payload, "id", "outcome")
    prediction_id = _required_id(payload, "prediction_id", "outcome prediction")
    market = _normalized_market(payload.get("market"))
    symbol = str(payload.get("symbol") or "").strip().upper()
    if not symbol:
        raise ValueError("Graph projection outcome payload is missing symbol")
    outcome = _without_none(
        {
            "outcome_id": outcome_id,
            "idempotency_key": payload.get("idempotency_key"),
            "payload_hash": payload.get("payload_hash"),
            "prediction_id": prediction_id,
            "cohort_id": payload.get("cohort_id"),
            "asset_key": f"{market}:{symbol}",
            "symbol": symbol,
            "market": market,
            "horizon_days": payload.get("horizon_days"),
            "selection_date": payload.get("selection_date"),
            "outcome_date": payload.get("outcome_date"),
            "evaluated_at": payload.get("evaluated_at"),
            "outcome_status": payload.get("outcome_status"),
            "outcome_label": payload.get("outcome_label"),
            "selected_price": payload.get("selected_price"),
            "horizon_price": payload.get("horizon_price"),
            "return_pct": payload.get("return_pct"),
            "directional_return_pct": payload.get("directional_return_pct"),
            "max_favorable_excursion_pct": payload.get("max_favorable_excursion_pct"),
            "max_adverse_excursion_pct": payload.get("max_adverse_excursion_pct"),
            "max_drawdown_pct": payload.get("max_drawdown_pct"),
            "price_path_complete": payload.get("price_path_complete"),
            "daily_snapshot_path_complete": payload.get("daily_snapshot_path_complete"),
            "daily_snapshot_coverage_pct": payload.get("daily_snapshot_coverage_pct"),
            "followed_through": payload.get("followed_through"),
            "false_positive": payload.get("false_positive"),
            "invalidated_quickly": payload.get("invalidated_quickly"),
            "missed_follow_through": payload.get("missed_follow_through"),
            "stayed_valid": payload.get("stayed_valid"),
            "categories": _string_list(payload.get("categories")),
            "setup_type": payload.get("setup_type"),
            "blocked_by": payload.get("blocked_by"),
            "data_quality_flags": _string_list(payload.get("data_quality_flags")),
            "attribution_json": _json_property(payload.get("attribution_json") or {}),
            "selection_market_regime_id": payload.get("selection_market_regime_id"),
            "outcome_market_regime_id": payload.get("outcome_market_regime_id"),
            "market_regime_label": payload.get("market_regime_label"),
            "market_return_pct": payload.get("market_return_pct"),
            "sector_proxy_symbol": payload.get("sector_proxy_symbol"),
            "sector_return_pct": payload.get("sector_return_pct"),
            "relative_to_spy": payload.get("relative_to_spy"),
            "relative_to_qqq": payload.get("relative_to_qqq"),
            "relative_to_sector_proxy": payload.get("relative_to_sector_proxy"),
            "attribution_label": payload.get("attribution_label"),
            "price_source": payload.get("price_source"),
            "selection_bar_date": payload.get("selection_bar_date"),
            "horizon_bar_date": payload.get("horizon_bar_date"),
            "evaluator_version": payload.get("evaluator_version"),
            "rule_version": payload.get("rule_version"),
            "feature_version": payload.get("feature_version"),
            "data_version": payload.get("data_version"),
            "supersedes_outcome_id": payload.get("supersedes_outcome_id"),
            "created_at": payload.get("created_at"),
            "source_system": "tradeghost.research",
            "projection_version": "phase2d_v1",
        }
    )
    return OutcomeProjection(outcome=outcome, asset=_asset_projection(market=market, symbol=symbol))


def build_report_projection(payload: dict[str, Any]) -> ReportProjection:
    report_id = str(payload.get("id") or "").strip()
    if not report_id:
        raise ValueError("Graph projection payload is missing the daily report id")
    report_markdown = str(payload.get("report_markdown") or "")
    summary = str(payload.get("llm_context_summary") or "").strip()
    segment_text = (summary or report_markdown or "Deterministic TradeGhost report metadata.")[:12000]
    market = str(payload.get("market") or "unknown").strip().lower() or "unknown"
    published_at = str(payload.get("created_at") or datetime.now(UTC).isoformat())
    report_date = str(payload.get("report_date") or "")
    content_hash = hashlib.sha256(report_markdown.encode("utf-8")).hexdigest()
    segment_id = str(uuid5(NAMESPACE_URL, f"tradeghost:report-segment:{report_id}:summary"))
    report = _without_none(
        {
            "report_id": report_id,
            "cohort_id": payload.get("cohort_id"),
            "cohort_name": payload.get("cohort_name"),
            "market": market,
            "report_date": report_date,
            "report_type": payload.get("report_mode"),
            "published_at": published_at,
            "content_sha256": content_hash,
            "source_system": "tradeghost.intelligence",
            "engine_version": payload.get("engine_version"),
            "git_commit": payload.get("git_commit"),
            "prompt_version": payload.get("prompt_version"),
            "llm_provider": payload.get("llm_provider"),
            "llm_model": payload.get("llm_model"),
        }
    )
    segment = {
        "segment_id": segment_id,
        "report_id": report_id,
        "ordinal": 0,
        "text": segment_text,
        "content_sha256": hashlib.sha256(segment_text.encode("utf-8")).hexdigest(),
        "created_at": published_at,
    }
    assets: list[dict[str, Any]] = []
    signals: list[dict[str, Any]] = []
    for candidate in payload.get("candidate_followup_json") or []:
        if not isinstance(candidate, dict):
            continue
        symbol = str(candidate.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        asset_key = f"{market}:{symbol}"
        assets.append(
            _without_none(
                {
                    "asset_key": asset_key,
                    "symbol": symbol,
                    "market": market,
                    "asset_type": _asset_type_for_market(market),
                    "company_name": candidate.get("company_name"),
                    "sector": candidate.get("sector"),
                    "industry": candidate.get("industry"),
                }
            )
        )
        for category in candidate.get("selected_categories") or []:
            category_value = str(category).strip()
            if category_value:
                signals.append(
                    _signal(
                        report_id=report_id,
                        segment_id=segment_id,
                        asset_key=asset_key,
                        signal_type="selection_category",
                        state=category_value,
                        observed_at=published_at,
                    )
                )
        setup_type = str(candidate.get("selected_setup_type") or "").strip()
        if setup_type:
            signals.append(
                _signal(
                    report_id=report_id,
                    segment_id=segment_id,
                    asset_key=asset_key,
                    signal_type="setup_type",
                    state=setup_type,
                    observed_at=published_at,
                )
            )
        validity_state = str(candidate.get("validity_state") or "").strip()
        if validity_state:
            signals.append(
                _signal(
                    report_id=report_id,
                    segment_id=segment_id,
                    asset_key=asset_key,
                    signal_type="candidate_validity",
                    state=validity_state,
                    observed_at=published_at,
                )
            )
    unique_assets = {asset["asset_key"]: asset for asset in assets}
    unique_signals = {signal["signal_id"]: signal for signal in signals}
    return ReportProjection(
        report=report,
        segment=segment,
        assets=list(unique_assets.values()),
        signals=list(unique_signals.values()),
    )


class Neo4jReportProjector:
    def __init__(self, *, uri: str, username: str, password: str) -> None:
        self.uri = (uri or "").strip()
        self.username = (username or "").strip()
        self.password = password or ""

    @property
    def configured(self) -> bool:
        return bool(self.uri and self.username and self.password)

    def verify_connectivity(self) -> None:
        with self._driver() as driver:
            driver.verify_connectivity()

    def project(
        self,
        payload: dict[str, Any],
        *,
        event_type: str = KnowledgeGraphOutboxStore.report_event_type,
    ) -> None:
        with self._driver() as driver:
            with driver.session(database="neo4j") as session:
                if event_type == KnowledgeGraphOutboxStore.report_event_type:
                    session.execute_write(self._write_projection, build_report_projection(payload))
                elif event_type == KnowledgeGraphOutboxStore.market_regime_event_type:
                    session.execute_write(self._write_market_regime_projection, build_market_regime_projection(payload))
                elif event_type == KnowledgeGraphOutboxStore.prediction_event_type:
                    session.execute_write(self._write_prediction_projection, build_prediction_projection(payload))
                elif event_type == KnowledgeGraphOutboxStore.outcome_event_type:
                    session.execute_write(self._write_outcome_projection, build_outcome_projection(payload))
                else:
                    raise ValueError(f"Unsupported knowledge graph event_type={event_type}")

    def _driver(self):
        if not self.configured:
            raise RuntimeError("Neo4j connection settings are incomplete")
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:  # pragma: no cover - dependency/environment guard
            raise RuntimeError("neo4j is required for knowledge graph projection") from exc
        return GraphDatabase.driver(self.uri, auth=(self.username, self.password))

    @staticmethod
    def _write_projection(tx: Any, projection: ReportProjection) -> None:
        tx.run(
            """
            MERGE (report:Report {report_id: $report.report_id})
            SET report += $report
            MERGE (segment:ReportSegment {segment_id: $segment.segment_id})
            SET segment += $segment
            MERGE (report)-[:HAS_SEGMENT]->(segment)
            """,
            report=projection.report,
            segment=projection.segment,
        ).consume()
        tx.run(
            """
            MATCH (report:Report {report_id: $report_id})
            UNWIND $assets AS asset_properties
            MERGE (asset:Asset {asset_key: asset_properties.asset_key})
            SET asset += asset_properties
            MERGE (report)-[mention:REPORT_MENTIONS]->(asset)
            SET mention.created_at = $created_at,
                mention.source_report_id = $report_id
            """,
            report_id=projection.report["report_id"],
            created_at=projection.report["published_at"],
            assets=projection.assets,
        ).consume()
        tx.run(
            """
            MATCH (report:Report {report_id: $report_id})
            MATCH (segment:ReportSegment {segment_id: $segment_id})
            UNWIND $signals AS signal_properties
            MATCH (asset:Asset {asset_key: signal_properties.asset_key})
            MERGE (signal:Signal {signal_id: signal_properties.signal_id})
            SET signal += signal_properties
            MERGE (report)-[:HAS_SIGNAL]->(signal)
            MERGE (signal)-[:SIGNAL_FOR]->(asset)
            MERGE (signal)-[:EXTRACTED_FROM]->(segment)
            """,
            report_id=projection.report["report_id"],
            segment_id=projection.segment["segment_id"],
            signals=projection.signals,
        ).consume()

    @staticmethod
    def _write_market_regime_projection(tx: Any, regime: dict[str, Any]) -> None:
        tx.run(
            """
            MERGE (regime:MarketRegime {regime_id: $regime.regime_id})
            SET regime += $regime
            """,
            regime=regime,
        ).consume()

    @staticmethod
    def _write_prediction_projection(tx: Any, projection: PredictionProjection) -> None:
        prediction = projection.prediction
        tx.run(
            """
            MERGE (asset:Asset {asset_key: $asset.asset_key})
            SET asset += $asset
            MERGE (prediction:Prediction {prediction_id: $prediction.prediction_id})
            SET prediction += $prediction
            MERGE (prediction)-[:PREDICTS]->(asset)
            FOREACH (regime_id IN CASE
                WHEN $selection_market_regime_id IS NULL THEN []
                ELSE [$selection_market_regime_id]
            END |
                MERGE (regime:MarketRegime {regime_id: regime_id})
                MERGE (prediction)-[relationship:PERFORMED_UNDER {stage: 'selection'}]->(regime)
                SET relationship.source_prediction_id = $prediction.prediction_id
            )
            FOREACH (prior_id IN CASE
                WHEN $supersedes_prediction_id IS NULL THEN []
                ELSE [$supersedes_prediction_id]
            END |
                MERGE (prior:Prediction {prediction_id: prior_id})
                MERGE (prediction)-[:SUPERSEDES]->(prior)
            )
            """,
            prediction=prediction,
            asset=projection.asset,
            selection_market_regime_id=prediction.get("selection_market_regime_id"),
            supersedes_prediction_id=prediction.get("supersedes_prediction_id"),
        ).consume()
        tx.run(
            """
            MATCH (prediction:Prediction {prediction_id: $prediction_id})
            UNWIND $conditions AS condition_properties
            MERGE (condition:Condition {condition_id: condition_properties.condition_id})
            SET condition += condition_properties
            MERGE (prediction)-[:VALID_IF]->(condition)
            """,
            prediction_id=prediction["prediction_id"],
            conditions=projection.confirmation_conditions,
        ).consume()
        tx.run(
            """
            MATCH (prediction:Prediction {prediction_id: $prediction_id})
            UNWIND $conditions AS condition_properties
            MERGE (condition:Condition {condition_id: condition_properties.condition_id})
            SET condition += condition_properties
            MERGE (prediction)-[:INVALIDATED_BY]->(condition)
            """,
            prediction_id=prediction["prediction_id"],
            conditions=projection.invalidation_conditions,
        ).consume()
        tx.run(
            """
            MATCH (prediction:Prediction {prediction_id: $prediction_id})
            OPTIONAL MATCH (report:Report {report_id: $source_report_id})
            FOREACH (_ IN CASE WHEN report IS NULL THEN [] ELSE [1] END |
                MERGE (prediction)-[:SOURCE_REPORT]->(report)
            )
            """,
            prediction_id=prediction["prediction_id"],
            source_report_id=prediction.get("source_report_id"),
        ).consume()

    @staticmethod
    def _write_outcome_projection(tx: Any, projection: OutcomeProjection) -> None:
        outcome = projection.outcome
        tx.run(
            """
            MERGE (asset:Asset {asset_key: $asset.asset_key})
            SET asset += $asset
            MERGE (prediction:Prediction {prediction_id: $outcome.prediction_id})
            MERGE (outcome:Outcome {outcome_id: $outcome.outcome_id})
            SET outcome += $outcome
            MERGE (prediction)-[:RESULTED_IN]->(outcome)
            MERGE (prediction)-[has_outcome:HAS_OUTCOME {horizon_days: $outcome.horizon_days}]->(outcome)
            SET has_outcome.source_outcome_id = $outcome.outcome_id
            MERGE (outcome)-[:EVALUATES]->(asset)
            FOREACH (regime_id IN CASE
                WHEN $selection_market_regime_id IS NULL THEN []
                ELSE [$selection_market_regime_id]
            END |
                MERGE (regime:MarketRegime {regime_id: regime_id})
                MERGE (outcome)-[relationship:PERFORMED_UNDER {stage: 'selection'}]->(regime)
                SET relationship.source_outcome_id = $outcome.outcome_id
            )
            FOREACH (regime_id IN CASE
                WHEN $outcome_market_regime_id IS NULL THEN []
                ELSE [$outcome_market_regime_id]
            END |
                MERGE (regime:MarketRegime {regime_id: regime_id})
                MERGE (outcome)-[relationship:PERFORMED_UNDER {stage: 'outcome'}]->(regime)
                SET relationship.source_outcome_id = $outcome.outcome_id
            )
            FOREACH (prior_id IN CASE
                WHEN $supersedes_outcome_id IS NULL THEN []
                ELSE [$supersedes_outcome_id]
            END |
                MERGE (prior:Outcome {outcome_id: prior_id})
                MERGE (outcome)-[:SUPERSEDES]->(prior)
            )
            """,
            outcome=outcome,
            asset=projection.asset,
            selection_market_regime_id=outcome.get("selection_market_regime_id"),
            outcome_market_regime_id=outcome.get("outcome_market_regime_id"),
            supersedes_outcome_id=outcome.get("supersedes_outcome_id"),
        ).consume()


def _signal(
    *,
    report_id: str,
    segment_id: str,
    asset_key: str,
    signal_type: str,
    state: str,
    observed_at: str,
) -> dict[str, Any]:
    signal_id = str(uuid5(NAMESPACE_URL, f"tradeghost:signal:{report_id}:{asset_key}:{signal_type}:{state}"))
    return {
        "signal_id": signal_id,
        "asset_key": asset_key,
        "signal_type": signal_type,
        "state": state,
        "observed_at": observed_at,
        "timeframe": "daily",
        "source_report_id": report_id,
        "source_segment_id": segment_id,
        "extractor_type": "deterministic_report_projection",
        "schema_version": "v1",
        "created_at": observed_at,
    }


def _asset_type_for_market(market: str) -> str:
    return "crypto" if market == "crypto" else "equity" if market in {"us", "bist"} else "unknown"


def _asset_projection(*, market: str, symbol: str) -> dict[str, Any]:
    return {
        "asset_key": f"{market}:{symbol}",
        "symbol": symbol,
        "market": market,
        "asset_type": _asset_type_for_market(market),
    }


def _conditions_for_prediction(
    prediction_id: str,
    conditions: dict[str, Any],
    condition_type: str,
) -> list[dict[str, Any]]:
    expression = str(conditions.get(condition_type) or "").strip()
    if not expression:
        return []
    condition_id = str(uuid5(NAMESPACE_URL, f"tradeghost:condition:{prediction_id}:{condition_type}:{expression}"))
    return [
        {
            "condition_id": condition_id,
            "condition_type": condition_type,
            "expression": expression,
            "source_prediction_id": prediction_id,
            "source_system": "tradeghost.research",
            "projection_version": "phase2d_v1",
        }
    ]


def _required_id(payload: dict[str, Any], field: str, record_type: str) -> str:
    value = str(payload.get(field) or "").strip()
    if not value:
        raise ValueError(f"Graph projection {record_type} payload is missing {field}")
    return value


def _normalized_market(value: Any) -> str:
    return str(value or "unknown").strip().lower() or "unknown"


def _json_property(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True, separators=(",", ":"))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({str(item).strip() for item in value if str(item).strip()})


def _without_none(properties: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in properties.items() if value is not None}
