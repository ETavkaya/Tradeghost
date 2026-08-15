from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5


@dataclass(frozen=True)
class ReportProjection:
    report: dict[str, Any]
    segment: dict[str, Any]
    assets: list[dict[str, Any]]
    signals: list[dict[str, Any]]


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

    def project(self, payload: dict[str, Any]) -> None:
        projection = build_report_projection(payload)
        with self._driver() as driver:
            with driver.session(database="neo4j") as session:
                session.execute_write(self._write_projection, projection)

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


def _without_none(properties: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in properties.items() if value is not None}
