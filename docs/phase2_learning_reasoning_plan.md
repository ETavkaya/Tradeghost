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

Planned for Phase 2B, not implemented in Phase 2A:

1. A deterministic cohort selection creates exactly one immutable prediction record per selected symbol and selection event.
2. The record captures selection timestamp and price, cohort ID, symbol and market, categories, normalized setup, blockers, invalidation condition, source run/report, and rule/feature/data versions.
3. The record includes a deterministic payload hash and idempotency key such as `cohort_id + normalized_symbol + selected_at + rule_version`.
4. Corrections create a superseding record with a reason and lineage; the original remains queryable.
5. The scanner remains the source of the prediction. An LLM can describe its evidence but cannot create or modify it.

## 5. Outcome Lifecycle

Planned for Phase 2B, not implemented in Phase 2A:

1. A deterministic evaluator checks 7, 14, and 28 trading-day horizons from the prediction selection date. For the existing cohort lifecycle, the selection session is trading day 1, so the 28D outcome is available on the 28th eligible cohort trading day.
2. It obtains each horizon from canonical, exact-symbol OHLC data and records source, observed bar date, evaluator version, and data version.
3. Each immutable outcome records availability, return, maximum favorable/adverse excursion, price path completeness, data-quality flags, and evaluation timestamp.
4. A horizon outcome is available when its required price data exists; incomplete daily snapshots do not suppress it.
5. Outcome records are idempotent per prediction, horizon, evaluator version, and data version. Re-evaluation creates an explicit superseding version when the underlying data changes.

## 6. Market Regime Context

Phase 2C adds deterministic market-regime snapshots at selection and outcome evaluation. The first version should use measurable fields only: benchmark trend/volatility, breadth, relative strength, yields/DXY context where available, and a versioned classifier output. Regime labels remain descriptive evidence and must retain the raw inputs and classifier version that produced them.

## 7. Graph Layer

Neo4j is the relationship and provenance layer, not the source of price truth or rule execution. The current projection contains deterministic `Report`, `ReportSegment`, `Asset`, and `Signal` facts. Future projections will link immutable relational records after they are committed and validated.

The graph answers questions such as: which signals, regime, report, and rule version preceded an observed outcome; and which historical records are structurally similar. It must not infer new facts or allow a graph query to modify deterministic storage.

## 8. LLM Role

The LLM is advisory only. It may summarize selected evidence, retrieve linked historical observations, explain coverage caveats, and draft a clearly labeled hypothesis for human review. It may not determine cohort membership, labels, outcomes, confidence, rule changes, or graph writes. Any LLM output is stored separately from factual records with model, prompt, source-record IDs, and a non-authoritative status.

## 9. Human-Gated Loop

Every proposal follows a gated workflow:

1. A human or deterministic monitor identifies a measurable issue or possible rule hypothesis.
2. The system records the hypothesis, scope, evidence IDs, and proposed comparison without altering production logic.
3. A deterministic backtest validates the frozen hypothesis against a defined period and baseline.
4. A human approves, rejects, or requests revision.
5. Only an approved, versioned change can enter a separately controlled scanner-rule release.

## 10. Rule Hypothesis Lifecycle

Phase 2F introduces `rule_hypotheses` with statuses `draft`, `evidence_ready`, `backtest_running`, `validated`, `rejected`, and `approved_for_release`. Each hypothesis contains a statement, expected metric, candidate rule diff, affected universe, temporal split, evidence references, and author/reviewer metadata. Hypotheses never mutate production rules directly.

## 11. Backtest Validation

Validation uses deterministic, versioned data and rules. It must compare a frozen candidate rule version with its baseline across train/validation/out-of-sample periods, account for survivorship and availability limitations, publish sample size and confidence caveats, and reject apparent improvements that do not meet predefined robustness thresholds. No graph pattern or LLM narrative is sufficient validation by itself.

## 12. UI/UX Plan

Phase 2H adds a Research/Intelligence view with:

- cohort follow-up readiness: elapsed days, complete daily coverage, missing dates, partial-state counts, and backfill status;
- prediction cards with immutable selection facts and lineage;
- horizon outcome cards showing availability separately from daily-path completeness;
- category/setup/blocker summaries with sample size and data-quality caveats;
- evidence and graph links that expose source report, signal, regime, and outcome records;
- hypothesis and backtest review screens that require human approval actions.

## 13. API Plan

Phase 2A retains current cohort APIs and makes their readiness data explicit. Later endpoints should be read-first and versioned:

- `GET /intelligence/cohorts/{cohort_id}/coverage`
- `POST /intelligence/cohorts/{cohort_id}/followup/backfill`
- `GET /research/predictions` and `GET /research/predictions/{prediction_id}`
- `GET /research/outcomes` and grouped summary endpoints
- `GET /research/patterns` for statistically supported, read-only patterns
- `POST /research/hypotheses` and human review endpoints

Create/evaluate endpoints for predictions and outcomes are internal deterministic jobs, not LLM-facing APIs.

## 14. Database Schema Plan

Postgres remains the system of record for operational and outcome facts. Planned tables:

| Table | Ownership and purpose |
| --- | --- |
| `prediction_records` | Immutable deterministic selection-time fact, source IDs, conditions, and rule/feature/data versions. |
| `outcome_records` | Immutable fixed-horizon evaluation linked to a prediction and canonical bar references. |
| `canonical_ohlc_bars` | Exact-symbol market data with provider, retrieval time, adjustment policy, and data version. |
| `market_regime_snapshots` | Deterministic regime inputs and classifier output/version. |
| `outcome_summary_snapshots` | Rebuildable aggregates by category, setup, blocker, regime, and horizon. |
| `data_quality_events` | Explicit missing, mismatch, duplicate, split, and coverage anomalies. |
| `rule_hypotheses` / `rule_reviews` | Human-gated proposal and approval trail. |

Every prediction and outcome must include `cohort_id`, `rule_version`, `feature_version`, and `data_version`. Natural idempotency keys and unique constraints prevent duplicate records.

## 15. Neo4j Extension

After Postgres commits are stable, the transactional outbox projects them to Neo4j. Planned nodes include `Prediction`, `Outcome`, `MarketRegime`, `Condition`, and statistically supported `Pattern`. Planned relationships include `SIGNAL_FOR`, `PREDICTS`, `VALID_IF`, `RESULTED_IN`, `PERFORMED_UNDER`, `SUPPORTS`, and provenance links back to `Report` and `ReportSegment`.

Projection is one-way, idempotent, and replayable. Neo4j never becomes the authority for prices, outcomes, or rules, and no LLM writes directly to it.

## 16. Sprint Breakdown

- **2A — Data Truth Foundation:** complete candidate-day coverage, partial-day backfill, consistent report dates/counts, exact-symbol horizon safeguards, and regression tests.
- **2B — Prediction and Outcome Records:** Postgres migrations, immutable deterministic records, canonical OHLC references, and outcome evaluator.
- **2C — Market Context:** versioned regime snapshots and deterministic relative-performance fields.
- **2D — Graph Projection:** outbox events and Neo4j projection for committed predictions, outcomes, regimes, and provenance.
- **2E — Evidence Retrieval:** read-only historical lookup and outcome summaries with sample-size caveats.
- **2F — Hypotheses and Validation:** human-gated hypothesis records and versioned backtest comparison.
- **2G — Pattern Discovery:** statistically supported pattern candidates with conservative thresholds and review gates.
- **2H — UI, Operations, and Documentation:** research UI, monitoring, runbooks, and audit exports.

## 17. Acceptance Criteria

- A cohort with 28 elapsed trading days can show 28-day outcomes even when daily snapshots are incomplete.
- Daily-path completeness is calculated only from complete candidate-day states and lists missing dates.
- Backfill repairs missing or partial trading dates without duplicate candidate states.
- Every later prediction/outcome is deterministic, immutable, versioned, and traceable to source data.
- Exact-symbol verification rejects mismatched price sources.
- Aggregates disclose sample size, exclusions, and data-quality flags.
- LLM outputs remain advisory and cannot mutate rules, scores, records, or graph facts.

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
- [ ] **P2A-007:** Add an operational coverage monitor for partial/duplicate state anomalies.
- [ ] **P2B-001:** Add Postgres migrations for canonical OHLC, prediction records, outcome records, and data-quality events.
- [ ] **P2B-002:** Create selection-time prediction records through deterministic cohort creation only.
- [ ] **P2B-003:** Implement idempotent 7D/14D/28D outcome evaluation and category/setup/blocker summaries.
- [ ] **P2C-001:** Add versioned deterministic market-regime snapshots.
- [ ] **P2D-001:** Project committed prediction/outcome/regime records to Neo4j through the outbox.
- [ ] **P2E-001:** Add read-only historical evidence retrieval with sample-size safeguards.
- [ ] **P2F-001:** Add human-gated rule hypotheses and frozen backtest validation.
- [ ] **P2G-001:** Define statistical thresholds and review workflow for pattern candidates.
- [ ] **P2H-001:** Build research UI, audit exports, monitoring, and operating runbooks.
