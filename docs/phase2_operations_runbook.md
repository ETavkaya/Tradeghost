# Phase 2 Research Operations Runbook

## Purpose

Operate the Phase 2 research loop without allowing operational tooling, an LLM, Neo4j, or a review action to change scanner scoring, category logic, trade decisions, or source records. Postgres holds deterministic Prediction, Outcome, regime, hypothesis, and Pattern facts. Neo4j is a replayable projection only.

## Product V2 Compatibility

1. Product V2 flags are disabled by default. Do not enable `PRODUCT_V2_ENABLED`, `MARKET_STATE_ENABLED`, `STRATEGY_LAB_ENABLED`, `OPERATIONAL_REPORTING_ENABLED`, or `TRADING212_READ_ONLY_ENABLED` as part of Phase 2 operations.
2. Existing cohorts remain research evidence. They do not create virtual Strategy Lab positions, portfolio balances, or broker activity.
3. Use `Research` and the audit export for detailed historical evidence; use `Logs` for scheduler, data-quality, and outbox recovery. Future operational reporting is a compact summary layer, not a replacement for either workspace.
4. Do not reclassify a historical Prediction because its `risk_flags` differ from `blocked_by`. A semantic repair requires frozen proof that the deterministic entry gate failed and records its blocker.
5. Keep all Product V2 work behind its documented phase boundary. No current runbook action should change scanner scoring, category logic, trade decisions, broker state, or the existing follow-up scheduler.

## Phase B Manual Reporting

1. Phase B has no scheduler. Do not add one when enabling the manual backend foundation.
2. To capture a Market State, explicitly enable `PRODUCT_V2_ENABLED` and `MARKET_STATE_ENABLED`. To generate a compact weekly/monthly report, also enable `OPERATIONAL_REPORTING_ENABLED`, then use the manual APIs documented in `docs/operational_reporting_v2.md`.
3. Select an explicit `as_of_date` or `period_end`; do not request future dates. The report applies strict end-of-day source-created and outcome-evaluated filters, so a later historical backfill does not silently rewrite a prior point-in-time report.
4. Treat `partial` Market State/report status as operational evidence. V1 deliberately reports unavailable US 2Y, breadth, and economic-event inputs rather than filling them with LLM or stale values.
5. Keep reports compact. Use Research and Logs for raw audit detail, cohort coverage, semantic repairs, or graph-outbox diagnostics.

## Phase C Manual Strategy Lab

1. Strategy Lab has no scheduler and never creates a broker order. Do not add either during Phase C operations.
2. Deliberately enable `PRODUCT_V2_ENABLED` and `STRATEGY_LAB_ENABLED` only when an operator is ready to start a future-only virtual experiment. Existing cohorts and historical Predictions remain research evidence.
3. Create an experiment with a timezone-aware current/future activation time. A scheduled experiment needs an explicit activation API call after that time; do not backdate it.
4. Record decisions only from a fresh existing daily-pipeline `run_id`. The API freezes its deterministic source candidate and rejects false entry gates, data-quality flags, duplicate exposure, or full sleeves.
5. Call the manual processor with an explicit as-of date to create canonical next-session fills, valuations, 56-session exits, and avoided-basket observations. Replays are idempotent.
6. Treat `data_quality_hold` as an exception, not a fill. Keep overextended avoided-basket returns separate from cash, positions, realised P&L, and outcome statistics.

## Daily Checks

1. Open the `Logs` workspace and confirm the scheduled follow-up heartbeat, latest persisted daily report, and backend errors.
2. Open `Research` and inspect every cohort with `backfill required`, duplicate-state dates, or incomplete daily paths.
3. Review `28D Available` separately from snapshot coverage. A deterministic 28D Outcome may be reviewed even when daily-path snapshots are incomplete; it is a checkpoint and daily tracking continues.
4. Use the Prediction and Outcome identifiers, report IDs, and regime IDs when investigating provenance in Postgres or Neo4j.
5. Download `Export Audit JSON` before a material review. The export is a point-in-time read-only snapshot and includes the authority boundaries.
6. Read `Initial 28D Coverage` separately from post-28D tracking. A mature-tracking cohort can have `100%` initial coverage and continue collecting daily snapshots.

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
6. Treat price outcome and setup path as separate facts: a price success can still be `invalidated early`. Use both fields in a review rather than forcing them to agree.

## Prediction Semantic Repair

1. Use `POST /intelligence/cohorts/{cohort_id}/predictions/repair-semantics` only after reviewing an audit that identifies an incorrect selection-time blocker.
2. The repair reads frozen selection snapshots and requires an explicit failed deterministic selection gate plus its recorded blocker. Risk flags alone never trigger a correction; a repair creates a superseding Prediction instead of updating the source record.
3. The repair evaluates only the superseding Prediction's Outcomes because the Prediction identity changed. Original Predictions and Outcomes remain available through provenance and Neo4j `SUPERSEDES` links.
4. Re-export the audit and confirm canonical blockers, correction reasons, and the price-outcome/setup-path split before enabling related hypothesis or Pattern work.

## Cohort Lifecycle Operations

1. `active_tracking` cohorts are scheduled before the first `28D` checkpoint; `mature_tracking` cohorts remain scheduled after it. Initial-28D coverage and post-28D tracking are separate measures.
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
