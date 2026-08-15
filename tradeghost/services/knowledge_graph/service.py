from __future__ import annotations

import logging
from typing import Any

from tradeghost.services.knowledge_graph.outbox import KnowledgeGraphOutboxStore
from tradeghost.services.knowledge_graph.projection import Neo4jReportProjector
from tradeghost.shared.config.settings import Settings


class KnowledgeGraphIngestionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.outbox = KnowledgeGraphOutboxStore(settings.database_url)
        self.projector = Neo4jReportProjector(
            uri=settings.neo4j_uri,
            username=settings.neo4j_username,
            password=settings.neo4j_password,
        )
        self._logger = logging.getLogger(__name__)

    @property
    def enabled(self) -> bool:
        return bool(self.settings.knowledge_graph_enabled and self.outbox.configured and self.projector.configured)

    def process_pending_events(self, limit: int | None = None) -> dict[str, Any]:
        batch_size = max(1, min(int(limit or self.settings.knowledge_graph_batch_size), 200))
        result: dict[str, Any] = {
            "enabled": self.enabled,
            "claimed": 0,
            "projected": 0,
            "failed": 0,
            "errors": [],
        }
        if not self.enabled:
            return result
        events = self.outbox.claim_events(batch_size)
        result["claimed"] = len(events)
        for event in events:
            try:
                self.projector.project(event.payload)
                if self.outbox.mark_processed(event):
                    result["projected"] += 1
            except Exception as exc:  # pragma: no cover - network/runtime boundary
                self._logger.warning("knowledge graph projection failed event_id=%s error=%s", event.id, exc)
                self.outbox.mark_failed(event, str(exc), self.settings.knowledge_graph_retry_seconds)
                result["failed"] += 1
                result["errors"].append(str(exc))
        return result

    def status(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "enabled": self.enabled,
            "configured": {
                "database": self.outbox.configured,
                "neo4j": self.projector.configured,
            },
            "outbox": self.outbox.status_summary(),
        }
        if not self.enabled:
            result["neo4j_connected"] = False
            return result
        try:
            self.projector.verify_connectivity()
            result["neo4j_connected"] = True
        except Exception as exc:  # pragma: no cover - network/runtime boundary
            result["neo4j_connected"] = False
            result["neo4j_error"] = str(exc)
        return result
