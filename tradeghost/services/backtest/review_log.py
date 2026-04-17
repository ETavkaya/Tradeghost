from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from tradeghost.shared.config.settings import get_settings
from tradeghost.shared.models.schemas import (
    BacktestFromAnalysisResponse,
    BacktestSnapshot,
    BacktestSnapshotComment,
    BacktestSnapshotCommentCreateRequest,
    BacktestSnapshotCreateRequest,
    BacktestSnapshotMetrics,
    BacktestSnapshotSkipSummary,
)


class BacktestReviewLogService:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_dir = settings.logs_dir / "backtest_reviews"
        self.snapshots_dir = self.base_dir / "snapshots"
        self.artifacts_dir = self.base_dir / "artifacts"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def _snapshot_path(self, snapshot_id: str) -> Path:
        return self.snapshots_dir / f"{snapshot_id}.json"

    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    def _read_snapshot(self, path: Path) -> BacktestSnapshot:
        return BacktestSnapshot.model_validate_json(path.read_text(encoding="utf-8"))

    def create_snapshot(self, req: BacktestSnapshotCreateRequest) -> BacktestSnapshot:
        result: BacktestFromAnalysisResponse = req.result
        snapshot_id = str(uuid4())
        now = datetime.now(UTC)

        artifact_scope = self.artifacts_dir / snapshot_id / "scope.json"
        artifact_trades = self.artifacts_dir / snapshot_id / "trades_summary.json"
        artifact_skips = self.artifacts_dir / snapshot_id / "skip_summary.json"

        self._write_json(
            artifact_scope,
            {
                "evaluation_history": result.evaluation_history_window,
                "visible_window": result.visible_chart_window,
                "fetched_data_range": [str(result.fetched_data_range_start), str(result.fetched_data_range_end)],
                "evaluation_range": [str(result.evaluation_start), str(result.evaluation_end)],
                "visible_chart_range": [str(result.visible_start), str(result.visible_end)],
                "warmup_bars": result.warmup_bars_used,
                "evaluated_bars": result.evaluated_bars,
            },
        )
        self._write_json(
            artifact_trades,
            {
                "trades": [t.model_dump(mode="json") for t in result.trades_table],
            },
        )
        self._write_json(
            artifact_skips,
            {
                "decision_log_sample": [s.model_dump(mode="json") for s in result.decision_log_sample],
            },
        )

        snapshot = BacktestSnapshot(
            id=snapshot_id,
            timestamp=now,
            symbol=result.ticker,
            market=result.market,
            mode=result.strategy_mode_used,
            review_status=req.review_status,
            experiment_group=req.experiment_group,
            evaluation_history=result.evaluation_history_window,
            visible_window=result.visible_chart_window,
            config=result.analysis_config,
            metrics=BacktestSnapshotMetrics(
                total_trades=result.trades,
                win_rate=result.win_rate,
                expectancy=result.expectancy,
                max_drawdown=result.max_drawdown,
            ),
            trades_summary={
                "entries_considered": result.entries_considered,
                "entries_triggered": result.entries_triggered,
                "visible_trades_estimate": sum(
                    1
                    for t in result.trades_table
                    if (result.visible_start <= t.entry_date <= result.visible_end)
                    or (result.visible_start <= t.exit_date <= result.visible_end)
                ),
            },
            skip_summary=BacktestSnapshotSkipSummary(
                threshold_fail=result.skipped_due_to_threshold,
                regime_fail=result.skipped_regime,
                location_fail=result.skipped_location,
                trigger_fail=result.skipped_trigger,
                overextended_fail=result.skipped_overextended,
                resistance_room_fail=result.skipped_resistance_room,
                ema200_transition_fail=result.skipped_ema200_transition,
            ),
            artifacts={
                "scope_snapshot": str(artifact_scope),
                "trades_snapshot": str(artifact_trades),
                "skip_snapshot": str(artifact_skips),
            },
            comments=[],
            github_mapping_hint={
                "issue_title": f"[Backtest Review] {result.ticker} {result.evaluation_history_window}",
                "issue_body_template": "Use snapshot id and skip summary for collaborative investigation.",
                "pr_title_template": f"[Strategy Tuning] {result.ticker} mode={result.strategy_mode_used.value}",
            },
        )
        self._write_json(self._snapshot_path(snapshot.id), snapshot.model_dump(mode="json"))
        return snapshot

    def list_snapshots(self) -> list[BacktestSnapshot]:
        rows: list[BacktestSnapshot] = []
        for path in sorted(self.snapshots_dir.glob("*.json"), reverse=True):
            rows.append(self._read_snapshot(path))
        return rows

    def get_snapshot(self, snapshot_id: str) -> BacktestSnapshot:
        path = self._snapshot_path(snapshot_id)
        if not path.exists():
            raise FileNotFoundError(snapshot_id)
        return self._read_snapshot(path)

    def add_comment(self, snapshot_id: str, req: BacktestSnapshotCommentCreateRequest) -> BacktestSnapshot:
        snapshot = self.get_snapshot(snapshot_id)
        comment = BacktestSnapshotComment(
            id=str(uuid4()),
            snapshot_id=snapshot_id,
            commentator=req.commentator.strip() or "anonymous",
            timestamp=datetime.now(UTC),
            content=req.content.strip(),
            tags=req.tags,
        )
        snapshot.comments.append(comment)
        self._write_json(self._snapshot_path(snapshot.id), snapshot.model_dump(mode="json"))
        return snapshot
