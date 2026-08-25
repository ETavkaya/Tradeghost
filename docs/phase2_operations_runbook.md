# Phase 2 Research Operations Runbook

## Purpose

Operate the Phase 2 research loop without allowing operational tooling, an LLM, Neo4j, or a review action to change scanner scoring, category logic, trade decisions, or source records. Postgres holds deterministic Prediction, Outcome, regime, hypothesis, and Pattern facts. Neo4j is a replayable projection only.

## Daily Checks

1. Open the `Logs` workspace and confirm the scheduled follow-up heartbeat, latest persisted daily report, and backend errors.
2. Open `Research` and inspect every cohort with `backfill required`, duplicate-state dates, or incomplete daily paths.
3. Review `28D Available` separately from snapshot coverage. A deterministic 28D Outcome may be reviewed even when daily-path snapshots are incomplete; it is a checkpoint and daily tracking continues.
4. Use the Prediction and Outcome identifiers, report IDs, and regime IDs when investigating provenance in Postgres or Neo4j.
5. Download `Export Audit JSON` before a material review. The export is a point-in-time read-only snapshot and includes the authority boundaries.

## Coverage Recovery

1. Select the affected cohort in `Logs`.
2. Run `Backfill Missing Follow-up Days`; it is idempotent and repairs only missing or partial trading dates.
3. Refresh `Research` and confirm that missing/partial dates and `backfill required` are cleared. Investigate duplicate-state dates rather than assuming backfill resolves them.
4. Do not delay a 28D Outcome review solely because daily snapshots are incomplete. Record the coverage caveat in the human review notes.

## Outcome and Graph Operations

1. Deterministically evaluate cohort outcomes through `POST /intelligence/cohorts/{cohort_id}/outcomes/evaluate` when scheduled processing has not done so.
2. Inspect category, setup, and blocker summaries with their available and data-quality-excluded counts. Do not rely on a rate with a small or excluded sample.
3. Check `GET /intelligence/knowledge-graph/status`. If committed outbox events are pending, process them with `POST /intelligence/knowledge-graph/process` in bounded batches.
4. Use `POST /intelligence/knowledge-graph/research-backfill` only to enqueue existing committed deterministic facts. It must never recreate Predictions or Outcomes from report text.
5. Review `7D`/`14D` short-horizon, `28D` standard, `56D`/`90D` medium, and `180D`/`365D` long-horizon outcomes separately. Never aggregate or describe different horizons as one unlabeled result.

## Cohort Lifecycle Operations

1. `active_tracking` cohorts are scheduled before the first `28D` checkpoint; `mature_tracking` cohorts remain scheduled after it.
2. Use `POST /intelligence/cohorts/{cohort_id}/pause-followup` with a reviewer ID when scheduled tracking must stop temporarily. Use `resume-followup` to continue; both actions append a lifecycle audit event.
3. Use `archive-followup` only for an intentional end to tracking. It requires a reviewer ID and reason, sets `archived_manual`, disables follow-up, and preserves every report, snapshot, Prediction, Outcome, and graph projection.
4. Do not treat `followup_completed` as an automatic 28D state. Manually archived cohorts remain visible in `Research` for audit and longer-horizon review.

## Human Reviews

1. A rule hypothesis must have frozen evidence and a qualifying deterministic validation before `Human Accept` is available.
2. Enter a real reviewer ID and notes. The system appends a review event; it does not alter production scanner configuration.
3. A Pattern can be approved only when its fixed statistical eligibility is true. Approval enables read-only retrieval, not trade advice or Neo4j Pattern projection.
4. Reject incomplete, concentrated, data-quality-limited, or otherwise unsuitable candidates with clear review notes.

## Incident Boundaries

- Do not use LLM output as a Prediction, Outcome, rule change, graph fact, or approval justification without the referenced deterministic records.
- Do not repair source facts in Neo4j. Correct authoritative data through the deterministic Postgres workflow, then replay the outbox projection.
- Do not modify `rule_version`, `feature_version`, `data_version`, payload hashes, or idempotency keys in place.
- Escalate persistent database, market-data, or graph connectivity errors with the audit export and relevant log entries.

## Deployment Checks

1. Apply packaged migrations before enabling writers.
2. Verify `/health`, `GET /intelligence/research/dashboard`, and the `Research` UI after deployment.
3. Confirm the dashboard reports the expected Postgres and Neo4j status; use a bounded deterministic Prediction/Outcome backfill only where historical records need it.
4. Verify the JSON export opens and includes the intended cohort before closing the deployment change.
