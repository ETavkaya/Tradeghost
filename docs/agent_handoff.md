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
