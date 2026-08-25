# TradeGhost Phase 2: Evidence-Based Learning and Reasoning Plan

## 1. Mission

Phase 2 turns deterministic cohort follow-up into an auditable research loop. The system records the rules and evidence present when a candidate enters a cohort, measures subsequent market data at fixed horizons, and uses only validated historical observations to inform future analysis. It is persistent memory and feedback, not daily model retraining.

## 2. Guardrails

- Do not change scanner scoring, category selection, ranking, or deterministic rule logic in Phase 2.
- Do not allow an LLM to create, alter, approve, or delete deterministic facts, predictions, outcomes, rules, or graph relationships.
- Do not present trade instructions. The system reports evidence, conditions, coverage, and measured outcomes.
- Preserve immutable selection-time facts. Corrections are new versioned records or explicit data-quality events, never silent rewrites.
- Require source, timestamp, version, and lineage for every persisted fact used in an outcome or aggregate.

## 3. Data Truth Prerequisites

Phase 2 depends on a reliable cohort follow-up baseline:

- A complete follow-up trading day means one persisted, deduplicated candidate state for every selected symbol.
- Elapsed time and daily-snapshot coverage are separate measures. A 28-day price outcome can exist while daily-path coverage remains incomplete.
- The latest follow-up date is the latest real candidate state, not a derived report row.
- Missing trading dates and partial-state dates are first-class diagnostics and are eligible for idempotent backfill.
- Follow-up state storage must survive API container recreation, and scheduled/manual writers must be serialized to prevent stale snapshot lists from overwriting recovered states.
- Horizon prices must come from the requested normalized symbol, the selection date, and canonical source data. A source-symbol mismatch produces a data-quality flag, not a result.
- Snapshot counts must disclose their basis: complete candidate-day states, partial candidate-day states, and expected candidate-day states.

Phase 2A delivers these prerequisites before introducing durable prediction or outcome tables.

## 4. Prediction Lifecycle

Implemented in Phase 2B:

1. A deterministic cohort selection creates exactly one immutable prediction record per selected symbol and selection event.
2. The record captures selection timestamp and price, cohort ID, symbol and market, categories, normalized setup, blockers, invalidation condition, source run/report, and rule/feature/data versions.
3. The record includes a deterministic payload hash and idempotency key such as `cohort_id + normalized_symbol + selected_at + rule_version`.
4. Corrections create a superseding record with a reason and lineage; the original remains queryable.
5. Phase 2C attaches the deterministic selection-time `market_regime_snapshots` record ID. The scanner remains the source of the prediction; an LLM can describe its evidence but cannot create or modify it.

Existing cohorts may use an explicit deterministic backfill that reads only their frozen `CohortCandidate` selection snapshots. It records the backfill in the pipeline log and uses the same idempotency key as selection-time creation.

## 5. Outcome Lifecycle

Implemented in Phase 2B:

1. A deterministic evaluator checks separately labeled 7, 14, 28, 56, 90, 180, and optional 365 trading-day horizons from the prediction selection date. The selection session is trading day 1, so the 28D Outcome is available on the 28th eligible cohort trading day; it is the first review checkpoint, not the end of tracking.
2. It obtains each horizon from canonical, exact-symbol OHLC data and records source, observed bar date, evaluator version, and data version.
3. Each immutable outcome records availability, return, maximum favorable/adverse excursion, price path completeness, data-quality flags, and evaluation timestamp.
4. A horizon outcome is available when its required price data exists; incomplete daily snapshots do not suppress it. Earlier Outcomes are retained when a later horizon or a data-versioned correction is recorded.
5. Outcome records are idempotent per prediction, horizon, evaluator version, and data version. Re-evaluation creates an explicit superseding version when the underlying data changes.
6. Phase 2C adds deterministic market, SPY, QQQ, and sector-proxy returns where applicable, plus relative returns and a descriptive attribution label. Missing benchmark data is retained as attribution evidence; it does not invalidate an otherwise valid exact-symbol outcome.

## 6. Market Regime Context

Implemented in Phase 2C:

1. `market_regime_snapshots` are created deterministically at cohort selection and at each available outcome horizon. Each carries a stable ID, payload hash, classifier version, raw benchmark-source versions, inputs, quality flags, and rule/feature/data versions.
2. US snapshots use `SPY` as the primary market benchmark with `QQQ` and `IWM` context; BIST snapshots use `XU100.IS`. The V1 classifier uses only persisted benchmark returns and 20-session annualized close-return volatility: `risk_on`, `risk_off`, `tech_led`, `neutral`, or `unavailable`.
3. US outcomes calculate `relative_to_spy`, `relative_to_qqq`, and, when a deterministic sector mapping exists, `relative_to_sector_proxy`. The stored attribution label is `market_beta_move`, `sector_beta_move`, `stock_specific_move`, or `unattributed`.
4. Benchmark source errors and gaps are retained in `attribution_json` and the regime snapshot. They never convert an otherwise valid stock outcome into a data-quality-excluded outcome.

Breadth, yields, DXY, and additional macro inputs remain future additive evidence fields; they are not inferred or fabricated by the classifier.

## 7. Graph Layer

Neo4j is the relationship and provenance layer, not the source of price truth or rule execution. Phase 2D projects deterministic `Report`, `ReportSegment`, `Asset`, `Signal`, `MarketRegime`, `Prediction`, deterministic `Condition`, and `Outcome` facts only after their authoritative Postgres transaction commits.

The graph answers questions such as: which signals, regime, report, and rule version preceded an observed outcome; and which historical records are structurally similar. A Prediction can link to multiple separately labeled Outcome nodes by horizon. Phase 2E retrieves the underlying Postgres records first because they are authoritative, then returns their stable IDs for graph traversal. It must not infer new facts or allow a graph query to modify deterministic storage.

## 8. LLM Role

The LLM is advisory only. It may summarize selected evidence, retrieve linked historical observations, explain coverage caveats, and draft a clearly labeled hypothesis for human review. It may not determine cohort membership, labels, outcomes, confidence, rule changes, or graph writes. An LLM draft cannot call the persisted hypothesis writer; a human or deterministic monitor must submit the frozen evidence references. Any LLM output is stored separately from factual records with model, prompt, source-record IDs, and a non-authoritative status.

## 9. Human-Gated Loop

Every proposal follows a gated workflow:

1. A human or deterministic monitor identifies a measurable issue or possible rule hypothesis.
2. The system records the hypothesis, scope, evidence IDs, and proposed comparison without altering production logic.
3. A deterministic backtest validates the frozen hypothesis against a defined period and baseline.
4. A human approves, rejects, or requests revision.
5. Only an approved, versioned change can enter a separately controlled scanner-rule release.

## 10. Rule Hypothesis Lifecycle

Implemented in Phase 2F: `rule_hypotheses` has statuses `draft`, `evidence_ready`, `backtest_running`, `validated`, `rejected`, and `approved_for_release`. Each hypothesis freezes Prediction/Outcome evidence IDs, their common `rule_version`, `feature_version`, and `data_version`, a statement, expected metric, supported candidate backtest patch, affected universe, temporal split, and author/reviewer metadata. Evidence includes deterministic false-positive, missed-follow-through, and invalidation counts. `rule_hypothesis_validation_runs` stores immutable baseline/candidate metrics and `rule_hypothesis_reviews` is an append-only audit trail. Hypotheses never mutate production rules directly.

## 11. Backtest Validation

Implemented in Phase 2F: validation compares baseline and candidate sandbox parameters across declared train, validation, and out-of-sample date ranges for every supplied symbol. It requires complete symbol coverage, minimum trade counts, an expectancy delta, and a maximum drawdown regression bound in every split. The stored artifact freezes inputs, returned analysis configurations, observed date ranges, metrics, errors, and caveats. It records provider/version availability limits rather than claiming an unavailable replay is exact. No graph pattern or LLM narrative is sufficient validation by itself. `approved_for_release` creates no production mutation: it retains the derived candidate rule version for a separate controlled scanner-rule release.

## 11A. Pattern Discovery

Implemented in Phase 2G: deterministic discovery builds only low-dimensional condition groups from immutable category, setup, trend, trigger, blocker, and selection-regime fields. It separates source populations by market, horizon, and rule/feature/data versions, then requires at least 30 observations, 80% evaluable coverage, three cohorts, and no more than 50% symbol concentration before retaining a candidate. A chronological split requires at least 20 candidate and comparator cases in train and 10 in validation. Promotion eligibility requires a predeclared two-proportion test, a 95% Wilson confidence interval, a minimum 10 percentage-point success-rate edge in both splits, non-negative validation return effect, and `p <= 0.05` in validation.

Candidates, source IDs, exclusions, split boundaries, metrics, and thresholds are persisted in Postgres. A human may approve only an eligible candidate for read-only retrieval; approval cannot create a Neo4j `Pattern` node, mutate a scanner setting, change an existing Prediction/Outcome, or become a trade recommendation. Pattern graph projection remains a later separately controlled step.

## 12. UI/UX Plan

Implemented in Phase 2H: the `/research` workspace exposes a read-only operational view with:

- cohort follow-up readiness: elapsed days, complete daily coverage, missing dates, partial-state counts, and backfill status;
- prediction cards with immutable selection facts and lineage;
- horizon outcome cards showing availability separately from daily-path completeness;
- lifecycle states (`active_tracking`, `mature_tracking`, `paused`, `archived_manual`) with 28D checkpoint readiness, later-horizon due dates, and audited human pause/resume/archive controls;
- category/setup/blocker summaries with sample size and data-quality caveats;
- evidence and graph links that expose source report, signal, regime, and outcome records;
- hypothesis and Pattern review controls that require a reviewer ID and append-only human approval actions. A hypothesis acceptance remains a release-review state only; Pattern approval remains read-only retrieval only.

The dashboard endpoint, `GET /intelligence/research/dashboard`, reads deterministic Postgres records and coverage diagnostics without emitting a coverage-monitor event, invoking an LLM, running a scanner, evaluating prices, or changing any source record. `GET /intelligence/research/audit-export` produces an in-memory JSON audit snapshot for all cohorts or a selected `cohort_id`; the browser downloads it without storing a second mutable export copy. The existing Logs workspace remains the execution surface for daily follow-up and idempotent backfill. P2H operating and recovery procedures are in `docs/phase2_operations_runbook.md`.

## 13. API Plan

Phase 2A retains current cohort APIs and makes their readiness data explicit. The coverage monitor is available at `GET /intelligence/cohorts/{cohort_id}/coverage`; it returns read-only diagnostics and emits a structured pipeline alert. Phase 2B adds deterministic read/evaluation endpoints; later endpoints should also be read-first and versioned:

- `GET /intelligence/cohorts/{cohort_id}/coverage`
- `POST /intelligence/cohorts/{cohort_id}/followup/backfill`
- `GET /intelligence/cohorts/{cohort_id}/predictions`
- `POST /intelligence/cohorts/{cohort_id}/predictions/backfill` for immutable legacy selection snapshots
- `GET /intelligence/cohorts/{cohort_id}/outcomes`
- `POST /intelligence/cohorts/{cohort_id}/outcomes/evaluate`
- `POST /intelligence/cohorts/{cohort_id}/pause-followup`, `resume-followup`, and `archive-followup` with human reviewer attribution
- `GET /intelligence/cohorts/{cohort_id}/market-regimes`
- `POST /intelligence/reasoning/similar-setups`
- `GET /research/predictions` and `GET /research/predictions/{prediction_id}`
- `GET /research/outcomes` and grouped summary endpoints
- `POST /intelligence/patterns/discover`, `GET /intelligence/patterns` / `GET /research/patterns`, and human candidate review endpoints
- `POST /intelligence/hypotheses`, list/detail, immutable review trail, and human review endpoints
- `GET /intelligence/research/dashboard`
- `GET /intelligence/research/audit-export?cohort_id={cohort_id}`

Create/evaluate endpoints for predictions and outcomes are internal deterministic jobs, not LLM-facing APIs.

## 14. Database Schema Plan

Postgres remains the system of record for operational and outcome facts. Phase 2B migration `001_phase2b_research_records.sql` creates the core research tables; Phase 2C migration `002_phase2c_market_regimes.sql` adds regime snapshots and benchmark attribution fields:

| Table | Ownership and purpose |
| --- | --- |
| `prediction_records` | Immutable deterministic selection-time fact, source IDs, conditions, and rule/feature/data versions. |
| `outcome_records` | Immutable fixed-horizon evaluation linked to a prediction and canonical bar references. |
| `canonical_ohlc_bars` | Exact-symbol market data with provider, retrieval time, adjustment policy, and data version. |
| `market_regime_snapshots` | Deterministic regime inputs and classifier output/version. |
| `outcome_summary_snapshots` | Rebuildable aggregates by category, setup, blocker, regime, and horizon. |
| `data_quality_events` | Explicit missing, mismatch, duplicate, split, and coverage anomalies. |
| `rule_hypotheses` / `rule_hypothesis_validation_runs` / `rule_hypothesis_reviews` | Frozen proposal, sandbox comparison, and append-only human review trail. |
| `pattern_candidates` / `pattern_candidate_reviews` | Deterministic statistical candidates and append-only human retrieval-approval trail. |

Every prediction and outcome must include `cohort_id`, `rule_version`, `feature_version`, and `data_version`. Natural idempotency keys and unique constraints prevent duplicate records.

## 15. Neo4j Extension

Implemented in Phase 2D: the shared Postgres transactional outbox emits typed committed-record events for market regimes, Predictions, and Outcomes. The idempotent Neo4j projection uses `MERGE` by Postgres UUID and creates `PREDICTS`, `VALID_IF`, `INVALIDATED_BY`, `PERFORMED_UNDER`, `RESULTED_IN`, `HAS_OUTCOME` (with `horizon_days`), `EVALUATES`, `SOURCE_REPORT`, and `SUPERSEDES` relationships. It serializes nested provenance fields as JSON properties and never lets Neo4j or an LLM create source records.

Implemented in Phase 2E: `POST /intelligence/reasoning/similar-setups` deterministically compares immutable Prediction facts and Outcomes at an explicit `horizon_days` value (default `28`). It supports exact or weighted matching for symbol, category, setup, structure, blocker, risk flags, selection regime, and coarse location buckets. The response discloses case counts, data-quality exclusions, incomplete daily-path coverage, result caps, concentration, and a strict as-of cutoff. Performance aggregates are withheld below `RESEARCH_RETRIEVAL_MIN_SAMPLE_SIZE`; the endpoint returns descriptive evidence only, never trade advice or rule changes.

Projection is one-way, idempotent, and replayable. Neo4j never becomes the authority for prices, outcomes, or rules, and no LLM writes directly to it.

## 16. Sprint Breakdown

- **2A — Data Truth Foundation:** complete candidate-day coverage, partial-day backfill, consistent report dates/counts, exact-symbol horizon safeguards, and regression tests.
- **2B — Prediction and Outcome Records:** Postgres migration, immutable deterministic records, canonical OHLC references, outcome evaluator, and category/setup/blocker summaries.
- **2C — Market Context:** versioned regime snapshots and deterministic relative-performance fields. Implemented with benchmark-only V1 inputs.
- **2D — Graph Projection:** outbox events and Neo4j projection for committed predictions, outcomes, regimes, conditions, and provenance. Implemented.
- **2E — Evidence Retrieval:** read-only historical lookup and outcome summaries with sample-size caveats. Implemented.
- **2F — Hypotheses and Validation:** implemented human-gated hypothesis records, date-split sandbox comparisons, and append-only review audit. No production rule mutation is included.
- **2G — Pattern Discovery:** implemented conservative statistical candidates, chronological holdout checks, and human-gated read-only retrieval approval. Neo4j Pattern projection and scanner mutation are intentionally excluded.
- **2H — UI, Operations, and Documentation:** implemented read-only research UI, operational readiness/error status, JSON audit exports, and runbooks. The existing Logs page remains responsible for manual follow-up and backfill execution.
- **2I — Multi-Horizon Lifecycle:** 28D is a review checkpoint, not auto-completion. Cohorts continue daily `active_tracking`/`mature_tracking` until audited human pause or manual archive; deterministic 56D/90D/180D/365D Outcomes remain separately stored and labeled.

## 17. Acceptance Criteria

- A cohort with 28 elapsed trading days can show 28-day outcomes even when daily snapshots are incomplete.
- Daily-path completeness is calculated only from complete candidate-day states and lists missing dates.
- Backfill repairs missing or partial trading dates without duplicate candidate states.
- Every later prediction/outcome is deterministic, immutable, versioned, and traceable to source data.
- Exact-symbol verification rejects mismatched price sources.
- Aggregates disclose sample size, exclusions, and data-quality flags.
- LLM outputs remain advisory and cannot mutate rules, scores, records, or graph facts.
- A Phase 2F candidate must pass train, validation, and out-of-sample sandbox criteria before human release approval; approval does not change production scanner configuration.
- A Phase 2G Pattern candidate must pass fixed sample, coverage, concentration, confidence-interval, baseline, and holdout thresholds before a human can approve read-only retrieval use.
- The Research dashboard must show 28D outcome availability separately from daily-path coverage, list missing/backfill dates, and keep all review actions human-attributed.
- A 28D-ready cohort must remain scheduled as `mature_tracking` until manually paused or archived; it must retain prior Outcomes while later horizons are evaluated.

## 18. Risk Register

| Risk | Control |
| --- | --- |
| Price-provider changes or adjusted-price anomalies | Canonical bars, data versions, source checks, anomaly events, and re-evaluation lineage. |
| Incomplete historical snapshots | Separate horizon availability from path coverage; show missing dates and backfill status. |
| Self-reinforcing conclusions | Require measurable evidence, frozen backtests, held-out validation, and human approval. |
| Small or concentrated samples | Display counts, concentration, exclusions, and confidence caveats; block pattern promotion below thresholds. |
| Duplicate/replayed jobs | Natural idempotency keys, database constraints, transactional outbox, and idempotent graph merges. |
| LLM overreach | Read-only tools, structured advisory contracts, provenance, and no write credentials for deterministic stores. |

## 19. Testing Strategy

- Unit tests for coverage, partial-day repair, calendar handling, exact-symbol data checks, and deterministic idempotency keys.
- Integration tests for Postgres migrations, prediction/outcome evaluator replays, and transactional outbox delivery.
- Neo4j projection tests using a disposable database and graph-identity assertions.
- Fixture-based tests for splits, missing bars, renamed symbols, provider mismatches, and regime input gaps.
- API tests for readiness messages, missing-date lists, outcome availability, and non-authoritative LLM labeling.
- Migration and rollback rehearsals on a copy of production-shaped data before deployment.

## 20. Deployment and Migration

Deploy each phase behind explicit configuration flags. Add schema migrations before enabling writers, backfill deterministic records in bounded batches, validate counts and hashes, then enable read APIs. Keep old reports readable during migration. Monitor coverage gaps, outcome creation lag, outbox failures, graph projection lag, and source-symbol mismatch rates. Provide a replay command that rebuilds projections from Postgres without changing source records.

## TODO / Ticket Checklist

- [x] **P2A-001:** Count a completed daily follow-up only when every cohort symbol has a persisted state.
- [x] **P2A-002:** Separate elapsed trading time from snapshot coverage and expose missing/partial dates.
- [x] **P2A-003:** Reprocess partial snapshot days idempotently during cohort backfill.
- [x] **P2A-004:** Use candidate selection dates and exact-symbol validation for horizon calculations.
- [x] **P2A-005:** Regenerate and inspect the target milestone cohort export on the Docker host after deployment.
- [x] **P2A-006:** Persist API logs outside the container and serialize scheduled/manual follow-up writers.
- [x] **P2A-007:** Add an operational coverage monitor for partial/duplicate state anomalies.
- [x] **P2B-001:** Add Postgres migration for canonical OHLC, prediction records, outcome records, outcome summaries, and data-quality events.
- [x] **P2B-002:** Create deterministic selection-time prediction records during cohort creation; legacy backfill uses only immutable selection snapshots.
- [x] **P2B-003:** Implement idempotent 7D/14D/28D outcome evaluation and category/setup/blocker summaries without blocking on daily snapshot coverage.
- [x] **P2C-001:** Add versioned deterministic market-regime snapshots and benchmark-relative outcome attribution.
- [x] **P2D-001:** Project committed prediction/outcome/regime records to Neo4j through the outbox.
- [x] **P2E-001:** Add read-only historical evidence retrieval with sample-size safeguards.
- [x] **P2F-001:** Add human-gated rule hypotheses and frozen backtest validation.
- [x] **P2G-001:** Define statistical thresholds and review workflow for pattern candidates.
- [x] **P2H-001:** Build research UI, audit exports, monitoring, and operating runbooks.
- [x] **P2I-001:** Replace 28D auto-completion with audited active/mature/pause/archive lifecycle states and continuous daily tracking.
- [x] **P2I-002:** Add deterministic 56D/90D/180D/365D Outcome horizons, explicit max-drawdown persistence, horizon-labeled retrieval, and Neo4j multi-outcome projection.
