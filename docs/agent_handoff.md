# TradeGhost Agent Handoff Memory

> **Current infrastructure host:** use `emrebee@192.168.0.230` for all future SSH, deployment, and runtime verification. Historical entries below may reference the former `192.168.0.233` address and are retained only as past deployment records.

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

## 16) Latest Entry (2026-08-16)

- Request:
  - Implement Phase 2B deterministic Prediction and Outcome persistence after completing the P2A coverage monitor.
- Implemented changes:
  - Added an idempotent Postgres migration for canonical OHLC bars, immutable prediction and outcome records, outcome summary snapshots, and data-quality events.
  - Cohort creation now writes one deterministic Prediction per frozen candidate selection snapshot, using a stable UUID, payload hash, idempotency key, and rule/feature/data versions.
  - Added an explicit legacy prediction backfill that reads only immutable historical cohort-candidate snapshots; it cannot use LLM output or current scanner results.
  - Added exact-symbol canonical OHLC ingestion and deterministic 7D/14D/28D outcome evaluation. The selection session is day one, incomplete daily snapshots are reported separately, and source-symbol mismatches create data-quality-excluded outcomes.
  - Added rebuildable summary snapshots by category, setup type, and blocker, plus read/evaluation APIs for cohort predictions and outcomes.
  - Daily persisted follow-up reports now trigger deterministic outcome evaluation without involving an LLM.
- Validation run:
  - `python -m py_compile tradeghost/apps/api/main.py tradeghost/services/intelligence/service.py tradeghost/services/intelligence/research_record_store.py tradeghost/shared/models/schemas.py`
  - `pytest -q` (`21 passed`; existing FastAPI/pandas warnings only).
- Deployment follow-up:
  1. Commit and deploy the P2B migration and API service to `192.168.0.233`.
  2. Run the legacy prediction backfill and deterministic outcome evaluation for cohort `81711de2-ca32-4d00-9ce7-d960e316f671`.
  3. Verify `7D`, `14D`, and `28D` records plus category/setup/blocker summaries, then begin P2C regime snapshots.

## 17) Latest Entry (2026-08-16)

- Request:
  - Implement Phase 2C on top of the local Phase 2B foundation without changing scanner scoring, category logic, or LLM authority.
- Implemented changes:
  - Added replay-safe Postgres migration `002_phase2c_market_regimes.sql` for immutable `market_regime_snapshots`, Prediction selection-regime references, and Outcome benchmark-attribution fields.
  - Selection-time Prediction persistence now records a deterministic regime snapshot. Outcome evaluation records a deterministic snapshot at each available 7D/14D/28D horizon.
  - The benchmark-only V1 classifier uses persisted source versions, 1/7/14/28-session benchmark returns, and 20-session annualized volatility. US uses `SPY`, `QQQ`, and `IWM`; BIST uses `XU100.IS`.
  - Outcomes now retain market/sector proxy returns, relative returns to `SPY`, `QQQ`, and the mapped sector proxy, plus `market_beta_move`, `sector_beta_move`, `stock_specific_move`, or `unattributed` attribution.
  - Benchmark gaps are recorded as regime or attribution evidence and do not invalidate a valid exact-symbol Outcome. Outcome summary snapshots now also group by market regime.
  - Added `GET /intelligence/cohorts/{cohort_id}/market-regimes` and a deterministic P2C test fixture; no LLM creates or changes predictions, outcomes, regimes, or rules.
- Validation run:
  - `git diff --check`
  - `pytest -q` (`22 passed`; existing FastAPI/pandas warnings only).
  - `python -m pip wheel --no-deps --wheel-dir .tmp-wheel .` with the packaged `002_phase2c_market_regimes.sql` verified in the wheel.
- Deployment follow-up:
  1. Review and commit the combined local P2B/P2C changes before deployment; they are not committed or deployed yet.
  2. Deploy to `192.168.0.233`, then run legacy deterministic Prediction backfill and Outcome evaluation for cohort `81711de2-ca32-4d00-9ce7-d960e316f671`.
  3. Verify 7D/14D/28D Outcome attribution, regime summaries, and the read-only market-regimes endpoint before starting P2D graph projection.

## 18) Latest Entry (2026-08-16)

- Request:
  - Complete Phase 2D graph projection on top of the local Phase 2B/2C foundation.
- Implemented changes:
  - Extended the existing transactional `knowledge_graph_outbox` with typed committed-record events for market regimes, Predictions, and Outcomes while preserving the daily-report event contract.
  - Research persistence now emits the relevant outbox payload in the same Postgres transaction as each immutable write. Existing committed research records can be queued without changing their source rows.
  - Added idempotent Neo4j `MERGE` projection keyed by authoritative Postgres UUIDs for `MarketRegime`, `Prediction`, deterministic `Condition`, `Outcome`, and `Asset` nodes.
  - Added deterministic provenance and lineage edges: `PREDICTS`, `VALID_IF`, `INVALIDATED_BY`, `PERFORMED_UNDER`, `RESULTED_IN`, `EVALUATES`, `SOURCE_REPORT`, and `SUPERSEDES`.
  - Added `POST /intelligence/knowledge-graph/research-backfill`; graph status now returns counts split by event type. No LLM, graph query, or projector can create or mutate the Postgres source facts or scanner rules.
- Validation run:
  - `git diff --check`
  - `pytest -q` (`24 passed`; existing FastAPI/pandas warnings only).
  - Wheel build verified both research migrations are packaged.
- Deployment follow-up:
  1. Review and commit the combined local P2B/P2C/P2D changes before deployment; they are not committed or deployed yet.
  2. Deploy to `192.168.0.233`, run deterministic Prediction/Outcome backfill, then call `POST /intelligence/knowledge-graph/research-backfill?limit=100` until all committed facts are queued and projected.
  3. Verify the outbox status by event type and inspect Neo4j paths from `Prediction` through `RESULTED_IN` to `Outcome` and `PERFORMED_UNDER` to `MarketRegime` before starting P2E retrieval.

## 19) Latest Entry (2026-08-19)

- Request:
  - Implement Phase 2E deterministic similar-case evidence retrieval after completing local P2D graph projection.
- Implemented changes:
  - Added `POST /intelligence/reasoning/similar-setups`, a read-only endpoint over authoritative Postgres Prediction and latest 28D Outcome records.
  - Matching is deterministic: exact or weighted criteria cover symbol, category, setup, trend, extension, trigger, blocker, risk flags, selection regime, and coarse location buckets.
  - Retrieval applies an explicit `as_of_date` cutoff to Prediction selection and observed Outcome dates, preventing future-outcome leakage while retaining newly backfilled historical measurements.
  - Performance metrics exclude data-quality outcomes and are withheld until `RESEARCH_RETRIEVAL_MIN_SAMPLE_SIZE` is reached. Responses disclose exclusions, incomplete daily paths, source limits, concentration, and no-recommendation caveats.
  - Returned evidence carries immutable Prediction/Outcome/regime IDs already projected by P2D. No LLM is invoked; a future LLM may only explain these returned cases without changing any facts or rules.
- Validation run:
  - `git diff --check`
  - `pytest -q` (`27 passed`; existing FastAPI/pandas warnings only).
  - Wheel build verified the P2E retrieval module and research migrations are packaged.
- Deployment follow-up:
  1. Review and commit the combined local P2B/P2C/P2D/P2E changes before deployment; they are not committed or deployed yet.
  2. Deploy to `192.168.0.233`, run deterministic Prediction/Outcome backfill, then research graph backfill before querying historical evidence.
  3. Call `POST /intelligence/reasoning/similar-setups` with a bounded selection snapshot and verify sample-size withholding, as-of cutoff, and data-quality caveats before beginning P2F hypotheses.

## 20) Latest Entry (2026-08-20)

- Request:
  - Finish P2F without changing scanner scoring, category logic, trade decisions, or LLM authority.
- Implemented changes:
  - Added replay-safe migration `003_phase2f_rule_hypotheses.sql` with persisted hypotheses, immutable validation runs, and append-only human review events.
  - `POST /intelligence/hypotheses` resolves immutable Prediction/Outcome evidence, requires one common rule/feature/data version, records deterministic failure-cluster counts, rejects LLM-originated writes, and derives a candidate-only rule version.
  - `POST /intelligence/hypotheses/{id}/backtest` freezes symbols, versions, candidate sandbox parameters, criteria, and train/validation/out-of-sample dates. It runs baseline and candidate comparisons without writing scanner settings, then qualifies only complete multi-split results that meet trade, expectancy, and drawdown thresholds.
  - Human `accept` and `reject` endpoints create auditable review events. Acceptance changes only the hypothesis state to `approved_for_release`; a separately controlled release must create and activate any production scanner rule version.
  - Added date-bounded execution to the existing backtest runner solely for the P2F sandbox; scoring and category logic are unchanged.
- Validation run:
  - `python -m compileall tradeghost`
  - `git diff --check`
  - `pytest -q tradeghost/tests/test_hypothesis_workflow.py` (`2 passed`).
- Deployment follow-up:
  1. Review and commit the combined local P2B-P2F work before deployment; it is still uncommitted and undeployed.
  2. Deploy to `192.168.0.233` so migration `003_phase2f_rule_hypotheses.sql` is applied by the API service.
  3. Create a human-submitted hypothesis from persisted 28D evidence, run the frozen three-split backtest, and inspect its review trail before considering a separate scanner-rule release.

## 21) Latest Entry (2026-08-25)

- Request:
  - Finish P2G using the Phase 2 plan's Pattern Discovery scope without changing scanner scoring, category logic, trade decisions, or LLM authority.
- Implemented changes:
  - Added replay-safe migration `004_phase2g_pattern_candidates.sql` for deterministic pattern candidates and append-only human review events.
  - `POST /intelligence/patterns/discover` groups immutable 28D Outcomes by a fixed low-dimensional condition vocabulary and separates populations by market, horizon, and rule/feature/data versions.
  - Candidates require at least 30 observations, 80% evaluable coverage, three cohorts, diversified symbols, chronological train/validation samples, Wilson confidence intervals, a two-proportion test, and a holdout edge versus the independent non-matching population.
  - Human approval changes only `candidate` to `approved_for_retrieval`; it cannot change scanner configuration, make a recommendation, mutate Predictions/Outcomes, or project a Neo4j Pattern node.
- Validation run:
  - `python -m compileall tradeghost`
  - `git diff --check`
  - `pytest -q tradeghost/tests/test_pattern_discovery.py` (`2 passed`).
- Deployment follow-up:
  1. Review and commit the combined local P2B-P2G work before deployment; it is still uncommitted and undeployed.
  2. Deploy to `192.168.0.233` so migration `004_phase2g_pattern_candidates.sql` is applied by the API service.
  3. Run discovery only after enough completed deterministic 28D outcomes exist; inspect candidate source IDs, exclusions, and review events before approving any retrieval status.

## 22) Latest Entry (2026-08-25)

- Request:
  - Finish Phase 2H without changing scanner scoring, category logic, trade decisions, rule mutation controls, or LLM authority.
- Implemented changes:
  - Added `GET /intelligence/research/dashboard`, a read-only aggregate of cohort coverage, immutable Prediction/28D Outcome previews, category/setup/blocker summaries, graph status, review candidates, and recent pipeline failures.
  - Added `GET /intelligence/research/audit-export` for an in-memory, downloadable JSON audit snapshot; it identifies Postgres as authoritative and Neo4j/LLM as non-authoritative layers.
  - Added the Next.js `Research` workspace with separate 28D-outcome and daily-path readiness, missing/partial/backfill dates, provenance IDs, data-quality caveats, and explicit human reviewer-ID controls for existing hypothesis/Pattern transitions.
  - Added `docs/phase2_operations_runbook.md`. The existing `Logs` workspace remains the only UI execution surface for daily follow-up and idempotent backfill.
  - Dashboard polling suppresses the normal coverage-monitor pipeline event so read-only monitoring cannot manufacture operational activity.
- Validation run:
  - `pytest -q` (`32 passed`; existing FastAPI/pandas warnings only).
  - `npx tsc --noEmit` and `npm run build` in `apps/web` (both passed; `/research` and its proxy routes are included in the production build).
  - `git diff --check` and `python -m pip wheel --no-deps --wheel-dir .tmp-wheel .` (passed).
- Deployment follow-up:
  1. Review and commit the combined local P2B-P2H work before deployment; it remains uncommitted and undeployed.
  2. Deploy to `192.168.0.233`, then verify `/intelligence/research/dashboard`, `Research`, and the JSON audit export against the configured Postgres/Neo4j services.
  3. Use the runbook to clear actual coverage gaps and process the graph outbox; do not use P2H tooling to alter scanner rules.

## 23) Latest Entry (2026-08-25)

- Request:
  - Deploy Phase 2 services and clarify empty scheduler status while verifying Neo4j.
- Implemented local follow-up:
  - Added `last_tick_at` to the Logs scheduler status so a healthy polling loop is visible even before a scheduled job has work to process. A blank `last_run_at` is expected while no active follow-up cohort is due.
- Deployment status:
  - Commit `14f0baa` contains the completed P2B-P2H release and was pushed to `Full-analysis-flow---new-backtest`. Host deployment and runtime verification are in progress.

## 24) Latest Entry (2026-08-25)

- Request:
  - Deploy Phase 2, verify scheduler and Neo4j configuration, and investigate empty scheduler statistics.
- Deployed and verified:
  - Deployed commits `14f0baa`, `f39a714`, `8a89cc0`, and `e430ce8` to `192.168.0.233`; API, web, Postgres, and Neo4j containers are running, with Neo4j healthy.
  - The scheduler is enabled in `Europe/London` at `23:30`; `last_tick_at` confirms the one-minute polling loop is alive. `last_run_at` remains empty because there are currently zero follow-up-enabled cohorts due for processing.
  - Confirmed the application Neo4j account, 12 schema constraints, and Postgres research tables. The knowledge-graph status reports a working connection and no projection failures.
  - Backfilled the completed `Milestone#Emre` cohort: 20 deterministic Predictions, 60 deterministic 7D/14D/28D Outcomes, and five MarketRegime snapshots. Neo4j now contains 20 Predictions linked to 60 Outcomes; all 114 queued research/report graph events completed.
  - Corrected two runtime persistence defects found during the live backfill: canonical-bar batches now use a psycopg cursor, and outcome validity reads `PredictionRecord.selected_date`. Both fixes have regression tests.
- Remaining operational follow-up:
  - `Adem` still reports missing 2026-05-19 and 2026-05-20 follow-up dates. Backfill that cohort only if its historical coverage is required; creating or enabling a new cohort will produce a scheduled-run timestamp at the next eligible daily run.

## 25) Latest Entry (2026-08-25)

- Request:
  - Change cohort lifecycle so the 28D review is a checkpoint, not automatic completion; extend deterministic outcome tracking and preserve LLM/scanner guardrails.
- Implemented locally:
  - Added durable JSON-backed cohort lifecycle migration and fields for `active_tracking`, `mature_tracking`, `paused`, and `archived_manual`. Legacy 28D-completed cohorts migrate to enabled `mature_tracking` unless already archived.
  - Scheduled follow-up now includes active and mature cohorts indefinitely and considers every eligible trading date after the start date. It marks `review_ready_28d_at` and transitions to mature tracking without setting `followup_completed`.
  - Added audited pause, resume, and archive APIs; manual archive requires reviewer ID and reason, disables future tracking, and preserves all evidence.
  - Extended deterministic Outcome horizons to 56D, 90D, 180D, and 365D, added explicit `max_drawdown_pct` migration/persistence, horizon-labeled retrieval, and Neo4j `HAS_OUTCOME` edges alongside existing lineage.
  - Updated Logs and Research lifecycle terminology and controls; daily reports now state whether tracking continues and identify latest/next outcome horizons.
- Validation run:
  - `python -m compileall tradeghost`
  - `pytest -q tradeghost/tests/test_cohort_review.py tradeghost/tests/test_research_operations.py tradeghost/tests/test_knowledge_graph_projection.py` (`17 passed`)
  - `npm run build` in `apps/web` and `git diff --check` (passed).
- Deployment follow-up:
  1. Commit and deploy this lifecycle release to `192.168.0.233`; the API startup applies `005_phase2i_multihorizon_lifecycle.sql`.
  2. Verify legacy 28D cohorts are `mature_tracking`, re-enable only cohorts that were automatically completed, and keep manually archived cohorts archived.
  3. Run a bounded Outcome evaluation and graph research backfill to project any newly available 56D+ records and `HAS_OUTCOME` edges.

## 26) Latest Entry (2026-08-25)

- Deployed and verified:
  - Deployed commit `60361fc` to `192.168.0.233`; the rebuilt API and web containers are running, Postgres is available, and Neo4j remains healthy.
  - Migration `005_phase2i_multihorizon_lifecycle.sql` is applied and `outcome_records.max_drawdown_pct` exists.
  - Legacy `Milestone#Emre` is now enabled `mature_tracking` with `review_ready_28d_at=2026-06-23`; it remains part of scheduled follow-up. Scheduler status reports one mature cohort, two paused cohorts, and a current heartbeat.
  - Live deterministic evaluation created 56D evidence for the cohort. Persisted counts are 54 each at 7D/14D/28D (including immutable correction lineage) and 20 at 56D; 90D is next due on 2026-09-21.
  - Neo4j research replay completed without failures. The graph contains 20 Predictions with 80 `HAS_OUTCOME` links across 7D, 14D, 28D, and 56D horizons.
- Next operational checkpoint:
  - Let the scheduler continue daily mature tracking. After 2026-09-21, evaluate the cohort again for 90D outcomes and replay the research graph outbox; do not collapse those results into the 28D review.

## 27) Latest Entry (2026-09-08)

- Request:
  - Fix the intelligence layer OpenAI model error, avoid the `/v1/models` timeout false negative, and make the LLM test/status paths use the actual configured provider.
- Implemented changes:
  - Changed the default OpenAI chat/report/review model settings from `gpt-5-mini` / invalid `gpt-5.4-mini` to `gpt-4o-mini`.
  - Added OpenAI model resolution helpers so the status check can prefer an installed model instead of reporting a hard failure when the configured model is missing.
  - Increased the LLM status probe timeout and fixed the LLM test endpoint to call OpenAI when OpenAI is the primary provider.
  - Added unit coverage for the model resolution behavior.
- Files changed:
  - `tradeghost/shared/config/settings.py`
  - `.env.example`
  - `tradeghost/services/intelligence/service.py`
  - `tradeghost/tests/test_intelligence_llm_models.py`
- Validation run:
  - `python -m py_compile tradeghost/shared/config/settings.py tradeghost/services/intelligence/providers.py tradeghost/services/intelligence/service.py tradeghost/apps/api/main.py tradeghost/tests/test_intelligence_llm_models.py`
  - `pytest -q tradeghost/tests/test_intelligence_llm_models.py` (`3 passed`)
- Remaining risks / TODO:
  - If the account still lacks OpenAI access or the network to `api.openai.com` is unavailable, the service will still fall back to the existing Ollama path for actual generation once the status probe fails.
  - If a different OpenAI model is preferred later, update the defaults in `tradeghost/shared/config/settings.py` and `.env.example` together.

## 28) Latest Entry (2026-11-15)

- Request:
  - Begin the Product V2 simplification and Strategy Lab work incrementally while preserving deterministic scanner and Phase 2 research behavior.
- Implemented Phase A:
  - Added Product V2 architecture, Strategy Lab V1, operational-reporting, and Trading 212 read-only design contracts. The target workflow is `Discover -> Monitor -> Portfolio`; current navigation and existing advanced `Research`, `Logic`, and `Logs` workspaces are unchanged.
  - Added disabled-by-default settings for Product V2, Market State, Strategy Lab, operational reporting, and Trading 212 read-only integration. No flag is wired to a new scheduler, database writer, broker client, or UI yet.
  - Preserved historical Prediction semantics: selection-time `blocked_by` is read from frozen deterministic selection evidence, never inferred from `risk_flags`. A superseding correction now requires an explicitly recorded failed deterministic entry gate and blocker.
  - Added regression coverage for Product V2 default-off compatibility and the no-risk-flag blocker-correction guard.
  - No migration, deployment, broker call, Strategy Lab position, or new report was created in this phase.
- Runtime note:
  - Local migration/Compose inventory was reviewed. Direct runtime verification was not completed; use the current host `emrebee@192.168.0.230` for any future check. No remote configuration was changed.
- Validation run:
  - `python -m py_compile tradeghost/shared/config/settings.py tradeghost/services/intelligence/service.py tradeghost/tests/test_cohort_review.py tradeghost/tests/test_product_v2_phase_a.py`
  - `pytest -q -p no:cacheprovider --basetemp .tmp-product-phase-a-full` (`46 passed`; existing FastAPI/pandas deprecation warnings only).
  - `git diff --check` passed.
- Next steps:
  1. Implement Phase B: evolve the deterministic regime snapshot into a versioned Market State record and compact Postgres reporting read models.
  2. Implement Phase C: add the future-only, append-only Strategy Lab ledger and deterministic 56-session lifecycle.
  3. Implement Phase D: introduce Discover, Monitor, and Portfolio UI views only after their Phase B/C APIs and tests exist.

## 29) Latest Entry (2026-11-15)

- Request:
  - Implement Product V2 Phase B with database-first operational reporting and versioned Market State foundations, without activating schedules, Strategy Lab, or broker execution.
- Implemented:
  - Added additive migration `006_phase2b_market_state_reporting.sql` with indexed Postgres `market_state_snapshots` and `operational_reports` tables. It does not alter cohort, Prediction, Outcome, regime, scanner, or graph tables.
  - Added manual feature-gated Market State capture. It links an existing immutable deterministic regime snapshot, uses canonical bars only through the requested as-of date, records source data versions, unavailable inputs, and data-quality flags, and limits V1 sector proxy collection for Beelink-friendly resource use.
  - Added manual, idempotent weekly/monthly report generation and retrieval APIs. Reports contain compact SQL aggregates, terminal-lineage/version evidence, strict as-of source-created/evaluated filters, and superseding report provenance instead of raw cohort/research JSON.
  - Added `test_phase_b_reporting.py` coverage for state provenance, report idempotency/supersession, feature gates, and additive migration constraints.
  - Updated active deployment/documentation references to use `emrebee@192.168.0.230`; no service, network, or runtime configuration was changed.
- Validation run:
  - `python -m py_compile tradeghost/shared/models/schemas.py tradeghost/shared/config/settings.py tradeghost/services/intelligence/research_record_store.py tradeghost/services/intelligence/service.py tradeghost/apps/api/main.py tradeghost/tests/test_phase_b_reporting.py`
  - `pytest -q -p no:cacheprovider --basetemp .tmp-phase-b-full` (`50 passed`; existing FastAPI/pandas deprecation warnings only).
  - `python -m pip wheel --no-deps --wheel-dir .tmp-wheel-phase-b .` passed with packaged intelligence migrations.
  - `git diff --check` passed.
- Compatibility / operations:
  - Product V2, Market State, and operational reporting flags remain disabled by default. Phase B adds no thread, cron task, polling loop, UI page, LLM writer, Neo4j writer, Strategy Lab ledger, or broker call.
  - V1 explicitly reports unavailable US 2Y, breadth, and economic-event context instead of inferring them. Market State/report `partial` status is expected until those deterministic providers are added.
- Next steps:
  1. Review and, if desired, deploy the additive migration and manual APIs to `emrebee@192.168.0.230` without enabling the feature flags.
  2. Begin Phase C only after that review: create the future-only Strategy Lab experiment configuration and append-only Postgres ledger.

## 30) Latest Entry (2026-11-17)

- Request:
  - Finish Product V2 Phase C as a future-only Strategy Lab while preserving scanner, historical research, Postgres authority, and manual operational control.
- Implemented:
  - Added additive migration `007_phase2c_strategy_lab.sql` for Strategy Lab experiments, sleeves, immutable decisions, positions, append-only ledger events, and separate avoided observations.
  - Added a manual, feature-gated Strategy Lab service and API. It can create/activate a future-only experiment, freeze an eligible deterministic daily-run candidate, reserve a sleeve slot, and manually process canonical next-session fills, valuations, and exact 56-session exits.
  - Fixed V1 experiment contract in code: five `$100` sleeves; four long sleeves each limited to five `$20` slots; global duplicate-open-exposure prevention; and an overextended sleeve that remains cash with a separate hypothetical avoided basket.
  - Source runs before experiment activation, false frozen entry gates, source data-quality flags, missing category evidence, duplicate exposure, and exhausted sleeve capacity are persisted as deterministic rejected decisions. Existing cohorts/Predictions are never used as virtual positions.
  - Added append-only cash/mark-to-market metric calculation including realised P&L, hit rate, win/loss, drawdown, capacity, holding-period distribution, rejection reasons, data-quality holds, and separate avoided-basket metrics.
- Validation run:
  - `python -m py_compile tradeghost/shared/models/schemas.py tradeghost/services/intelligence/research_record_store.py tradeghost/services/strategy_lab/service.py tradeghost/apps/api/main.py tradeghost/tests/test_strategy_lab.py`
  - `pytest -q -p no:cacheprovider --basetemp .tmp-phase-c-full-retry` (`55 passed`; existing FastAPI/pandas deprecation warnings only).
  - Packaged wheel verified `007_phase2c_strategy_lab.sql`; `git diff --check` passed.
- Compatibility / operations:
  - No scanner scoring/category/gate change, no historical cohort conversion, no LLM/Neo4j writer, no broker capability, no background processor, and no Portfolio UI were added.
  - `PRODUCT_V2_ENABLED` and `STRATEGY_LAB_ENABLED` remain disabled by default. No migration was applied remotely and no service was deployed or restarted.
- Next steps:
  1. Review and, if desired, deploy migrations `006` and `007` to `emrebee@192.168.0.230` while keeping Product V2 feature flags disabled.
  2. Begin Phase D: add Discover, Monitor, and Portfolio UI work only on top of these established manual APIs and read models.

## 31) Latest Entry (2026-11-18)

- Request:
  - Complete Product V2 Phase D without changing scanner scoring/category logic, historical research, scheduling, broker boundaries, or LLM authority.
- Implemented:
  - Added `Discover` as the default primary workspace. It invokes the established deterministic daily pipeline with fixed bounded US/default settings and displays persisted candidate evidence without score or gate controls.
  - Promoted `Discover -> Monitor -> Portfolio` to the primary navigation and retained Scanner, Analysis, Backtest, Intelligence, Research, Logic, and Logs as advanced workspaces. Monitor continues to use its existing watchlist/alert implementation.
  - Added feature-gated Strategy Lab proxy routes and a manual `Portfolio` workspace. It displays experiments, sleeves, positions, decisions, and the avoided basket separately from realised P&L; it supports explicit manual creation, activation, decision submission, and canonical-bar processing only when the backend permits it.
  - Portfolio reports a disabled runtime state instead of changing environment flags, creating a schedule, submitting an order, or fabricating a virtual trade. The proxy now preserves POST query strings so the existing `as_of_date` processor contract reaches FastAPI.
- Compatibility / operations:
  - No migration, backend rule change, scanner/category change, scheduler, broker request, LLM ledger writer, remote deployment, or service restart was made in Phase D.
  - `PRODUCT_V2_ENABLED` and `STRATEGY_LAB_ENABLED` remain disabled by default. Use `emrebee@192.168.0.230` for any later explicit deployment or runtime verification.
- Next steps:
  1. Run local frontend/backend validation and review the combined uncommitted Product V2 changes.
  2. If approved, deploy migrations `006` and `007` with the feature flags still disabled; explicitly enable and verify only when an operator is ready to run a future-only virtual experiment.

## 32) Latest Entry (2026-11-18)

- Request:
  - Deploy the completed Phase 2/Product V2 release to the current Linux Docker host.
- Deployed and verified:
  - Pushed release commit `2f2cce6` (`Complete Product V2 workflow and Strategy Lab UI`) and fast-forwarded `emrebee@192.168.0.230` to that commit.
  - Rebuilt and recreated only `tradeghost-api` and `tradeghost-web`; Postgres and Neo4j remained running with their existing persisted volumes. The host's pre-existing untracked `logs/`, `ngrok.log`, and `tradeghost/shared/config/schemas.py` were preserved.
  - API health returned `{"status":"ok","app":"TradeGhost"}` and `/discover` returned HTTP `200`. The new Strategy Lab route is present and correctly returns its disabled-by-default feature-gate response.
  - Ran the deployed idempotent research-schema migration runner without enabling feature flags. `006_phase2b_market_state_reporting.sql` and `007_phase2c_strategy_lab.sql` are recorded in `tradeghost_schema_migrations`; Market State, operational-report, Strategy Lab experiment, and Strategy Lab position tables exist.
  - Neo4j remained healthy and authenticated successfully as the `tradeghost` application account.
- Compatibility / operations:
  - `PRODUCT_V2_ENABLED` and `STRATEGY_LAB_ENABLED` remain disabled. No market-state capture, operational report, Strategy Lab experiment, scheduler, broker action, or LLM writer was enabled or created during deployment.

## 33) Latest Entry (2026-11-19)

- Request:
  - Restore the current OpenAI task model from the stale `gpt-4o-mini` runtime setting to `gpt-5.6`.
- Implemented and deployed:
  - Changed the OpenAI default and all task-specific OpenAI model defaults to `gpt-5.6`; model-resolution fallbacks still retain prior models only when an authenticated account lists them as available.
  - Updated the non-secret host `.env` model fields (`OPENAI_MODEL`, `LLMQ_CHAT_MODEL`, `DAILY_REPORT_LLM_MODEL`, `MARKET_CONTEXT_LLM_MODEL`, and `FINAL_28D_REVIEW_LLM_MODEL`) and rebuilt/recreated only `tradeghost-api`.
  - `55` backend tests passed before deployment. Runtime LLM status now reports `primary_model` and `model_used` as `gpt-5.6`.
- Runtime blocker:
  - OpenAI remains unavailable because the configured API key receives HTTP `401 Unauthorized` from `https://api.openai.com/v1/models`. No API key was viewed, changed, or logged. Replace the host `OPENAI_API_KEY` with an active key that has access to the requested model, then recreate `tradeghost-api` and re-check `/intelligence/llm/status`.

## 34) Latest Entry (2026-11-22)

- Runtime resolution:
  - After the host API container was recreated with the updated non-secret `.env` settings, the OpenAI account authenticated successfully and `gpt-5.6` accepted an actual Responses API request.
  - Added a provider compatibility normalization: `gpt-5.6` converts the unsupported `reasoning.effort=minimal` default to `low`; explicit `gpt-5-pro` handling remains `high`.
  - Added versioned-alias recognition so an account listing `gpt-5.6-sol`, `gpt-5.6-terra`, or another `gpt-5.6-*` variant correctly reports the configured `gpt-5.6` alias as available instead of misreporting `gpt-4o-mini`.
  - Full backend validation passed (`58 passed`). Release commits `3f78801` and `fd12d8e` were deployed by rebuilding/recreating only `tradeghost-api`.
- Live verification:
  - `/intelligence/llm/status` reports OpenAI connected, `primary_model=gpt-5.6`, `model_used=gpt-5.6`, and `model_available=true`.
  - `POST /intelligence/llm/test` returned `OK` in approximately 1.3 seconds, within the 20-second threshold.
  - The local workstation `.env` remains a separate, legacy Groq/Ollama-oriented development configuration and was not overwritten; the Docker host uses its own `/home/emrebee/Tradeghost/.env`.

## 35) Latest Entry (2026-11-23)

- Request:
  - Correct the live Product V2 workflow: allow BIST discovery, explain the Portfolio/Strategy Lab workflow, correct the misleading Logs presentation, and keep Logic current.
- Implemented:
  - Discover now lets the operator choose the existing deterministic `us` or `bist` market request without changing scanner scoring, categories, gates, limits, or LLM involvement.
  - Portfolio now offers the same market choice for future-only virtual experiments, removes the ambiguous `Primary workflow · 3 of 3` label, and presents the explicit four-step manual ledger workflow. It remains brokerless, unscheduled, and LLM-free for decisions.
  - Logs now distinguishes confirmed Postgres persistence from optional LLM enrichment/fallback. The reported `Connection refused` rows from 2026-11-20 are historical OpenAI/fallback enrichment failures, not lost Postgres data: the deterministic report was persisted successfully.
  - Added Docker host-gateway resolution for a host-published Ollama fallback and documented the Docker versus native-local fallback URL. Runtime template flags remain disabled by default.
  - Logic now documents the current deterministic, Postgres-authoritative, Neo4j-projection, and advisory-only LLM boundaries.
- Validation run:
  - `npm run build` in `apps/web` passed.
  - `pytest tradeghost/tests/test_strategy_lab.py tradeghost/tests/test_product_v2_phase_a.py tradeghost/tests/test_phase_b_reporting.py -q` passed (`11 passed`; only an existing local pytest-cache permission warning).
- Deployment follow-up:
  - Enable the already-established manual Strategy Lab runtime flags only on the Linux host when an operator explicitly wants to use Portfolio. This does not create an experiment, run a scheduler, or permit broker execution.
