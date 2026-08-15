# TradeGhost Agent Handoff Memory

Last updated: 2026-05-13

## 1) Active Mission

Upgrade TradeGhost Intelligence Report from a basic daily log into an explainable, deterministic Intelligence Journal.

High-level target:
- deterministic report quality first
- LLM remains advisory
- no buy/sell instructions
- no OpenAI/Gemini integration in this phase
- keep Docker workflow intact

## 2) Latest Confirmed User Directive

Implement the Intelligence Journal upgrade scope with:
- Why Selected blocks per candidate (deterministic)
- structure snapshot fields
- daily change tracking vs previous appearance
- forward performance tracking-ready fields
- richer markdown report format
- explicit review readiness behavior for insufficient history
- data-first 28-day review stats
- Intelligence tab UI upgrades for expanded details/readiness

## 3) Required Deterministic Outputs (Per Candidate)

- why_selected:
  - categories
  - setup type
  - score (+ components if available)
  - score dynamics
  - trend state
  - EMA structure
  - trigger reason
  - main risk reason
- structure_snapshot:
  - trend_state
  - setup_type
  - extension_state
  - score_dynamics_state
  - price_vs_ema20 / ema50 / ema100 / ema200
  - support_distance
  - resistance_room
  - volume_ratio_20 (if available)
  - trigger_state
- daily_change:
  - new/repeated
  - previous/current rank
  - rank delta
  - previous/current score
  - score delta
  - previous/current categories
  - category change notes
- forward_performance fields:
  - price_at_selection
  - selection_date
  - category_tags
  - setup_type
  - final_score
  - rank
  - benchmark_symbol (if available)
  - return_1d/3d/7d/14d (pending until available)
  - max_drawdown_after_selection
  - max_runup_after_selection

## 4) Review Behavior Requirements

- If history is insufficient:
  - do not fail silently
  - show: "Review needs more historical runs. Current history: X days. Target: 28 days."
- If sufficient history exists:
  - generate deterministic review input first:
    - category performance
    - repeated candidates
    - forward returns
    - missed/failed candidates (if available)
  - LLM summary remains optional and secondary

## 5) Current Session Status

Completed in this session:
- Added persistent project-memory bootstrap instructions in `README.md`.
- Added this handoff file as durable context across restarts.

Not yet implemented in this session:
- Intelligence Journal feature code changes listed in Section 2.

## 6) Working Rules

- Keep deterministic engine behavior primary.
- LLM is advisory only; no unsupported claims; no trade advice.
- Preserve existing Ollama/Groq wiring; Groq may remain disabled.
- Keep markdown export and Docker compatibility working.

## 7) Next Steps (Execution Queue)

1. Map current Intelligence models/services/UI to required new fields.
2. Implement deterministic candidate enrichment (`why_selected`, `structure_snapshot`, `daily_change`, forward-performance placeholders).
3. Update markdown export format and review-readiness/review-stats behavior.
4. Update Intelligence UI cards/tables for expanded candidate details and readiness metrics.
5. Verify via API/UI smoke tests, then update this handoff with final file list and results.

## 8) Change Log Convention

When updating this file, append a short dated entry:
- Date
- Request
- Implemented changes
- Files changed
- Validation run
- Remaining risks / TODO

## 9) Latest Entry (2026-05-13)

- Request:
  - Refactor Intelligence into Discovery + Candidate Cohort + Follow-up lifecycle.
  - Add cohort-based review and sticky headers in Intelligence tables.
- Implemented changes:
  - Added backend cohort models, requests, responses, persistence files, and lifecycle methods.
  - Added API routes for create/list/detail/follow-up/review/export cohort flows.
  - Added frontend API/type wiring and Intelligence UI sections for Discovery and Active Cohorts.
  - Added sticky headers to Intelligence scrolling tables.
- Validation run:
  - `python -m py_compile tradeghost/shared/models/schemas.py tradeghost/services/intelligence/service.py tradeghost/apps/api/main.py`
- Remaining TODO:
  - Full frontend build/test run for TypeScript confidence.
  - Optional deeper cohort review metrics tuning and first-column sticky enhancement.

## 10) Latest Entry (2026-05-15)

- Request:
  - Fix cohort lifecycle semantics, export mode/versioning, readiness/blocked reason consistency, setup classification overuse, data-quality handling, and review-readiness wording.
- Implemented changes:
  - Added explicit lifecycle fields for cohort snapshots and latest derived state (`LatestCohortState`) without mutating immutable initial selection snapshots.
  - Added `blocked_by`, `readiness_explanation`, trigger fields, `return_since_selection`, and `needs_data_check` validity support.
  - Added report mode support (`initial`, `followup`, `lifecycle`, `review_28d`) and versioned cohort export filenames with metadata (`exported_at`, `report_mode`, `latest_followup_date`).
  - Improved deterministic setup normalization to reduce overuse of `second_attempt_breakout`/`pullback` for highly-extended names.
  - Added data-quality penalty into displayed score and ranking priority.
  - Updated cohort review to defer false-positive/quick-invalidation conclusions when history is insufficient.
  - Updated Intelligence UI cohort table to show latest-state fields and export mode selector.
- Files changed:
  - `tradeghost/shared/models/schemas.py`
  - `tradeghost/services/intelligence/service.py`
  - `tradeghost/apps/api/main.py`
  - `apps/web/app/api/intelligence/cohorts/[cohortId]/export/route.ts`
  - `apps/web/lib/api.ts`
  - `apps/web/lib/types.ts`
  - `apps/web/app/intelligence/page.tsx`
- Validation run:
  - `python -m py_compile tradeghost/shared/models/schemas.py tradeghost/services/intelligence/service.py tradeghost/apps/api/main.py`
  - Frontend lint could not run in this shell because `next` is unavailable (`node_modules` not installed in current environment).

## 11) Latest Entry (2026-08-14)

- Request:
  - Design the auditable, persistent knowledge-graph V1 for daily reports and run Neo4j in Docker with the requested application credentials.
- Implemented changes:
  - Added a Neo4j Community service, persistent volumes, health check, and idempotent schema bootstrap to Docker Compose.
  - Added the Neo4j application configuration placeholders and disabled graph writes by default until the ingestion worker is implemented.
  - Added the executable graph constraints/indexes and the V1 architecture specification covering evidence provenance, prediction lifecycle, outcome evaluation, storage ownership, and safeguards.
- Files changed:
  - `docker-compose.yml`
  - `.env.example`
  - `tradeghost/shared/config/settings.py`
  - `tradeghost/knowledge_graph/knowledge_graph_v1.cypher`
  - `docs/knowledge_graph_v1.md`
  - `README.md`
- Validation run:
  - `python -m py_compile tradeghost/shared/config/settings.py`
  - `pytest -q` (`12 passed`)
  - Linux Docker host `192.168.0.233`: `docker compose config --quiet`
  - Linux Docker host: started `tradeghost-neo4j` and `tradeghost-neo4j-init`; initializer exited `0`.
  - Linux Docker host: authenticated to Neo4j as `tradeghost`; confirmed `12` constraints and `20` indexes.
- Next steps:
  1. Add the typed extraction contract and transactional-outbox records in Postgres.
  2. Implement the idempotent Neo4j projection worker from the outbox.
  3. Add canonical OHLC persistence and the prediction outcome evaluator.

## 12) Latest Entry (2026-08-15)

- Request:
  - Continue the persistent knowledge-system implementation after Neo4j deployment.
- Implemented changes:
  - Added the versioned Postgres transactional outbox `knowledge_graph_outbox`, written in the same transaction as each cohort daily report upsert.
  - Added an enabled-by-configuration background worker and operational status, process, and backfill endpoints.
  - Added idempotent Neo4j projection for deterministic `Report`, `ReportSegment`, `Asset`, and `Signal` facts only; no prediction or outcome is inferred from incomplete report fields.
  - Added a Neo4j Python driver dependency and a mapper test for report projection provenance.
- Files changed:
  - `pyproject.toml`
  - `tradeghost/apps/api/main.py`
  - `tradeghost/services/intelligence/daily_report_store.py`
  - `tradeghost/services/intelligence/service.py`
  - `tradeghost/services/knowledge_graph/outbox.py`
  - `tradeghost/services/knowledge_graph/projection.py`
  - `tradeghost/services/knowledge_graph/service.py`
  - `tradeghost/shared/config/settings.py`
  - `tradeghost/shared/models/schemas.py`
  - `tradeghost/tests/test_knowledge_graph_projection.py`
- Validation run:
  - `pytest -q` (`13 passed`)
  - Linux Docker host `192.168.0.233`: rebuilt `tradeghost-api`, verified graph status and Neo4j connectivity.
  - Backfilled `29` reports: `29` completed outbox events, `29` report nodes, `20` asset nodes, and `1,827` deterministic signal nodes.
- Next steps:
  1. Add strict LLM extraction contracts for prediction candidates with evidence spans and deterministic rejection rules.
  2. Persist typed predictions, conditions, and canonical OHLC bars in Postgres.
  3. Implement the horizon evaluator to create immutable outcomes and eligible performance aggregates.

## 13) Latest Entry (2026-08-15)

- Request:
  - Clarify the Neo4j relationship display and document current graph contents.
- Implemented changes:
  - Documented the difference between Neo4j schema visualization and persisted graph data.
  - Added the five currently projected relationship types and a Browser query for viewing real report-to-signal-to-asset paths.
- Files changed:
  - `README.md`
- Next steps:
  1. Add strict LLM extraction contracts for prediction candidates with evidence spans and deterministic rejection rules.
  2. Persist typed predictions, conditions, and canonical OHLC bars in Postgres.
3. Implement the horizon evaluator to create immutable outcomes and eligible performance aggregates.

## 14) Latest Entry (2026-08-15)

- Request:
  - Follow the Phase 2 planning prompt without implementing the full Phase 2 persistence layer.
  - Correct cohort follow-up data truth: coverage, date consistency, partial-day repair, and exact-symbol horizon safeguards.
- Current status:
  - Phase 2A data-truth code is implemented locally. A complete follow-up day now requires one deduplicated persisted state for every selected cohort symbol.
  - Elapsed trading time, complete coverage, partial states, expected states, and missing dates are reported separately.
  - Cohort exports now use the review's true latest snapshot date and disclose snapshot-count basis rather than mixing report rows with real candidate states.
  - Backfill identifies incomplete candidate-day states even when a daily report row already exists, then regenerates only those dates through existing upsert paths.
  - 7D/14D/28D horizon calculations use each candidate's selection date and reject mismatched source symbols.
- Blockers / operational follow-up:
  - The target milestone export is not present in the checked-out remote `logs` directory; it must be regenerated after deployment and then inspected.
  - Existing historical partial dates require one bounded backfill run on the Docker host. Price/analysis provider availability may still surface explicit data-quality flags.
  - Durable Prediction and Outcome Postgres records are deliberately deferred to Phase 2B; no LLM may create them.
- Sprint plan:
  1. Phase 2A: deploy this repair, regenerate the milestone cohort, verify coverage/count/date consistency, and add a coverage monitor.
  2. Phase 2B: add canonical OHLC, immutable deterministic Prediction/Outcome records, and outcome summaries.
  3. Phase 2C/D: add deterministic regimes and project committed facts to Neo4j through the transactional outbox.
- Files changed:
  - `tradeghost/services/intelligence/service.py`
  - `tradeghost/shared/models/schemas.py`
  - `tradeghost/tests/test_cohort_review.py`
  - `README.md`
  - `docs/phase2_learning_reasoning_plan.md`
  - `docs/agent_handoff.md`
- Validation run:
  - `python -m py_compile tradeghost/services/intelligence/service.py tradeghost/shared/models/schemas.py`
  - `pytest -q tradeghost/tests/test_cohort_review.py` (`4 passed`)
- Next steps:
  1. Run the full local test suite and deploy the selected Phase 2A files to `192.168.0.233`.
  2. Run cohort backfill for milestone cohort `81711de2` and regenerate its follow-up export.
  3. Inspect the regenerated export for latest-date consistency, `20 x 28 = 560` complete snapshot states, listed missing dates, and horizon availability.

## 15) Latest Entry (2026-08-15)

- Request:
  - Complete the Phase 2A data-truth repair after a Windows interruption and verify the milestone cohort on the Docker host.
- Implemented changes:
  - Made coverage candidate-complete: a trading date is valid only when every selected symbol has a deduplicated persisted state.
  - Added separate actual, complete, partial, and expected snapshot-state counts; exports use the review's true latest snapshot date.
  - Added deterministic report-backed rehydration. It accepts a daily report only when its candidate count, snapshot count, and exact normalized symbol set all match the cohort, then records `state_source=rehydrated_daily_report` and `source_report_id`.
  - Added a persistent `./logs:/app/logs` API mount, preventing cohort JSON state from being lost during container recreation.
  - Serialized scheduled follow-up, manual follow-up, and backfill work with a re-entrant lock to prevent stale snapshot lists overwriting new recovery data.
  - Corrected the cohort horizon boundary: the selection session is trading day 1, so 28D is evaluated on the 28th eligible cohort trading day.
  - Ensured a recovery-only backfill still marks a fully covered cohort as completed.
- Milestone verification:
  - Cohort: `81711de2-ca32-4d00-9ce7-d960e316f671` (`Milestone#Emre`).
  - Backfill restored `22` missing trading dates / `440` states from Postgres on the first durable recovery; a later idempotent run restored `0` further states and marked the cohort complete.
  - Corrected export: `tradeghost-cohort-milestone-emre-81711de2-followup-2026-08-15-0135.md`.
  - Export/review consistency: latest `2026-06-23`, calendar days `41`, trading days `28`, coverage `28/28`, missing dates `0`, and `560 = 20 x 28` covered states.
  - Deterministic 28D review: available for `20/20` candidates; positive/negative `9/11`; best `MU`; worst `TSLA`.
  - Two legacy non-trading-date snapshot sets remain stored outside the 28-day coverage window; they do not contribute to coverage or outcome counts.
- Files changed:
  - `docker-compose.yml`
  - `tradeghost/services/intelligence/service.py`
  - `tradeghost/shared/models/schemas.py`
  - `tradeghost/tests/test_cohort_review.py`
  - `README.md`
  - `docs/phase2_learning_reasoning_plan.md`
  - `docs/agent_handoff.md`
- Validation run:
  - `pytest -q` (`18 passed`; existing FastAPI/pandas warnings only).
  - Docker host `192.168.0.233`: rebuilt `tradeghost-api`, verified `/health`, durable `/home/emrebee/Tradeghost/logs -> /app/logs` mount, and re-enabled `DAILY_COHORT_FOLLOWUP_ENABLED=true`.
- Next steps:
  1. Add the P2A coverage-monitor alert for partial/duplicate state anomalies.
  2. Begin Phase 2B Postgres migrations for canonical OHLC, immutable Prediction records, and immutable fixed-horizon Outcome records.
  3. Project committed Phase 2B facts through the existing Neo4j outbox; LLM remains advisory only.
