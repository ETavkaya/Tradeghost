# TradeGhost Knowledge Graph V1

## Purpose and scope

This V1 turns a daily Intelligence report into traceable market knowledge without changing the deterministic analysis engine into a self-training model. It records what TradeGhost observed, what it predicted, the exact evidence and market context behind that prediction, and the independently measured outcome. Future report generation can retrieve this history as advisory context, but historical performance never rewrites source evidence or the original prediction.

The existing `CohortDailyReportStore` remains the immediate source of report data. Its `cohort_daily_reports` rows already retain deterministic statistics, candidate follow-ups, market context, generated markdown, engine version, prompt version, provider, model, and fallback state. This V1 introduces a graph projection beside that store; it does not replace it.

## Storage ownership

| Store | V1 responsibility | Authoritative data |
| --- | --- | --- |
| Postgres | transactional records, raw report payload, prediction lifecycle, canonical OHLC snapshots, evaluations, extraction outbox | reports, predictions, outcomes, price observations |
| Neo4j | idempotent projection and relationship queries | graph nodes and edges derived from Postgres IDs |
| Vector store | semantic retrieval over report segments and approved pattern summaries | embeddings keyed to immutable segment and pattern IDs |
| Agent/orchestrator | extraction, validation orchestration, retrieval, and write coordination | no permanent memory or outcome authority |

V1 should use Postgres tables for daily OHLC data and evaluation results. A time-series extension such as TimescaleDB is an implementation optimization once symbol and interval volume requires it, not a separate source of truth. Use a dedicated vector store such as Qdrant when semantic retrieval is implemented; until then, Neo4j full-text search over `ReportSegment` is a limited fallback, not an embedding substitute.

## Existing-system integration

The integration seam is immediately after `IntelligenceService._generate_and_store_daily_report()` persists a `cohort_daily_reports` row in `tradeghost/services/intelligence/service.py`. A new ingestion worker should consume a Postgres outbox record, not write Neo4j in the request path. This keeps report persistence available when Neo4j or the vector service is unavailable and prevents cross-store partial writes.

Suggested modules:

```text
tradeghost/services/knowledge_graph/
  contracts.py       # strict extraction and evaluation Pydantic models
  ingestion.py       # report -> validated extraction candidates
  outbox.py          # durable events and retry state
  projection.py      # idempotent Neo4j MERGE operations
  retrieval.py       # graph/vector/statistical context queries
  evaluation.py      # canonical price-series outcome evaluator
```

`KNOWLEDGE_GRAPH_ENABLED` is intentionally `false` by default until those workers exist. The configuration fields added now define the future API connection without making daily report creation dependent on Neo4j.

## Identity and common provenance

All primary IDs are generated in Postgres as UUIDs and copied unchanged to Neo4j. Nodes use a label-specific ID property such as `prediction_id`; graph projection writes use `MERGE` on that property. Every extracted assertion carries the following where applicable:

- `source_report_id`, `source_segment_id`, and a verbatim `source_excerpt`
- `extraction_run_id`, `extractor_model`, `prompt_version`, `schema_version`, and `created_at`
- `source_data_version` for deterministic inputs and `content_sha256` for immutable report text

The source text is stored outside the graph in Postgres/object storage. `ReportSegment` keeps a bounded excerpt only, plus the authoritative source reference and vector point ID. A correction creates a new extraction run and projection version; it never edits the historical report, original prediction, or previous outcome.

### Implemented projections

The initial report projection writes only deterministic facts already present in `cohort_daily_reports`: `Report`, a bounded `ReportSegment`, `Asset`, and `Signal` nodes for selected category, setup type, and current validity. These are joined by `HAS_SEGMENT`, `REPORT_MENTIONS`, `HAS_SIGNAL`, `SIGNAL_FOR`, and `EXTRACTED_FROM` relationships.

Phase 2D projects only immutable relational records already committed by deterministic Phase 2B/2C code. `research.market_regime.committed.v1`, `research.prediction.committed.v1`, and `research.outcome.committed.v1` events create `MarketRegime`, `Prediction`, deterministic `Condition`, and `Outcome` nodes keyed by their Postgres UUIDs. The projection creates `PREDICTS`, `VALID_IF`, `INVALIDATED_BY`, `PERFORMED_UNDER`, `RESULTED_IN`, `EVALUATES`, `SOURCE_REPORT`, and `SUPERSEDES` edges when their committed IDs exist.

It does not create a `Prediction` or `Outcome` from a cohort candidate, report prose, or LLM output. Missing report nodes and benchmark data remain explicit gaps rather than inferred graph facts.

## Exact graph model

### Nodes

| Label | Identity | Required V1 properties | Meaning |
| --- | --- | --- | --- |
| `Asset` | `asset_key` | `symbol`, `market`, `asset_type`, `provider_symbol` | A tradable instrument, keyed as `market:symbol` such as `crypto:BTC-USD`. |
| `Report` | `report_id` | `published_at`, `report_date`, `report_type`, `content_sha256`, `source_system` | Immutable daily report metadata; full text remains in Postgres. |
| `ReportSegment` | `segment_id` | `report_id`, `ordinal`, `text`, `content_sha256`, `vector_point_id` | A traceable report excerpt used as an evidence and retrieval anchor. |
| `ExtractionRun` | `extraction_run_id` | `started_at`, `extractor_model`, `prompt_version`, `schema_version`, `status` | Versioned record of one structured extraction attempt. |
| `Signal` | `signal_id` | `signal_type`, `state`, `observed_at`, `timeframe`, `value`, `unit`, provenance fields | A normalized observation or deterministic indicator state, never an outcome claim. |
| `Event` | `event_id` | `event_type`, `occurred_at`, `status`, provenance fields | A dated external or market event, such as an ETF-flow change or Fed decision. |
| `MarketRegime` | `regime_id` | `classification`, `market`, `as_of`, `method_version`, `confidence` | A reproducibly classified market condition, with the classifier/version retained. |
| `Condition` | `condition_id` | `condition_type`, `expression`, `operator`, `threshold`, `timeframe`, `status` | A machine-evaluable activation, validity, or invalidation rule. |
| `Prediction` | `prediction_id` | `direction`, `status`, `created_at`, `activation_at`, `evaluation_due_at`, `target_price`, `confidence_raw`, `semantic_hash`, `source_report_id` | The central immutable claim being evaluated. |
| `Outcome` | `outcome_id` | `evaluation_status`, `evaluated_at`, `target_reached`, `actual_return`, `mae`, `mfe`, `price_source`, `price_series_version` | A deterministic evaluation of exactly one prediction against canonical market data. |
| `Strategy` | `strategy_id` | `name`, `version`, `mode`, `rules_hash` | The deterministic analysis/strategy configuration in force. |
| `Pattern` | `pattern_id` | `pattern_key`, `status`, `sample_size`, `success_count`, `win_rate`, `effect_size`, `statistics_version`, `calculated_at` | A statistically supported recurring setup, never a free-form LLM discovery. |

`Prediction` must also store `asset_key`, `horizon_trading_days`, `activation_rule_text`, `invalidation_rule_text`, `market_regime_id`, `strategy_id`, and optional `confidence_calibrated`. `confidence_raw` records the report-time belief. `confidence_calibrated` is absent until an approved calibration calculation has sufficient data; it never overwrites the raw value.

### Relationships

Every relationship includes `created_at`, `source_report_id` where evidence-based, and `extraction_run_id` when produced by an agent. `confidence` on a relationship is extraction confidence, not trading confidence.

| Relationship | From -> To | Meaning |
| --- | --- | --- |
| `REPORT_MENTIONS` | `Report -> Asset` | The report explicitly discusses the asset. |
| `HAS_SEGMENT` | `Report -> ReportSegment` | Ordered report text segment. |
| `EXTRACTED_FROM` | `Signal/Event/Condition/Prediction -> ReportSegment` | Verbatim evidence anchor for the extracted object. |
| `PRODUCED` | `ExtractionRun -> Signal/Event/Condition/Prediction` | The extraction version that proposed the object. |
| `HAS_SIGNAL` | `Report -> Signal` | The report contains the normalized signal. |
| `SIGNAL_FOR` | `Signal -> Asset` | The asset the signal describes. |
| `OBSERVES` | `Signal -> Event` | The signal records or reacts to an event; it does not establish causality. |
| `CAUSED_BY` | `Signal/Prediction -> Event` | A source-attributed causal claim, always marked `claim_status=unverified` unless independently tested. |
| `CLASSIFIES` | `Report -> MarketRegime` | The report-time regime classification. |
| `MAKES_PREDICTION` | `Report -> Prediction` | The report contains the prediction. |
| `PREDICTS` | `Prediction -> Asset` | The asset and direction being predicted. |
| `SUPPORTED_BY` | `Prediction -> Signal/Event/ReportSegment` | Evidence supporting the original prediction. |
| `VALID_IF` | `Prediction -> MarketRegime/Condition` | A prerequisite that must hold for the prediction to remain valid. |
| `ACTIVATED_WHEN` | `Prediction -> Condition` | The condition that starts evaluation for conditional predictions. |
| `INVALIDATED_BY` | `Prediction -> Condition` | The condition that invalidates the prediction before its horizon. |
| `PERFORMED_UNDER` | `Prediction -> MarketRegime` | The regime assigned at activation time. |
| `USES_STRATEGY` | `Prediction -> Strategy` | The deterministic configuration used to form the report. |
| `RESULTED_IN` | `Prediction -> Outcome` | One append-only terminal evaluation record. |
| `EVALUATES` | `Outcome -> Asset` | The exact asset whose canonical price path was evaluated. |
| `SOURCE_REPORT` | `Prediction -> Report` | Optional committed report provenance; omitted when no persisted source report ID exists. |
| `SUPERSEDES` | `Prediction/Outcome -> Prediction/Outcome` | Explicit immutable correction lineage. |
| `CORRELATED_WITH` | `Pattern -> Signal/MarketRegime/Event` | A statistically calculated association with `sample_size`, `effect_size`, `p_value`, and `calculated_at`. |
| `SIMILAR_TO` | `Pattern/Prediction -> Pattern/Prediction` | A versioned similarity result with method and score; it is advisory only. |
| `INSTANCE_OF` | `Prediction -> Pattern` | An evaluated setup belongs to an approved historical pattern. |

`CAUSED_BY`, `CORRELATED_WITH`, and `SIMILAR_TO` must never be emitted as unqualified facts by the LLM. The first is a quoted claim, and the latter two are created only by a deterministic statistics job.

## Prediction lifecycle and outcome rules

```text
EXTRACTED -> VALIDATED -> ACTIVE -> EVALUATED
                 |          |          |
                 |          +-> INVALIDATED -> EVALUATED
                 +-> REJECTED
ACTIVE -> EXPIRED -> EVALUATED
```

1. **Extracted**: the agent returns strict JSON with asset, direction, condition, target, invalidation, horizon, confidence, source segment, and evidence IDs. It cannot write any datastore directly.
2. **Validated**: deterministic code normalizes symbol, prices, units, dates, rule grammar, and semantic hash. Missing target, horizon, invalidation, or evidence rejects the candidate. Deduplication links a new report mention to an existing open prediction only when the immutable semantic hash matches.
3. **Active**: an unconditional prediction activates at the next valid market timestamp after publication. A conditional prediction activates only when its `ACTIVATED_WHEN` condition appears in canonical OHLC data. `activation_at` and `evaluation_due_at` are frozen at this point.
4. **Invalidated or expired**: an invalidation rule hit before the target changes terminal reason to `invalidated`; a non-activated condition reaches `expired_untriggered`; an activated prediction with no resolution by the due timestamp reaches `expired_at_horizon`.
5. **Evaluated**: the evaluator creates one immutable `Outcome` for every terminal path, including rejected, untriggered, and failed predictions. A later data-vendor correction produces a new outcome version linked by `SUPERSEDES`; aggregate performance uses the latest approved version while preserving history.

The evaluator reads canonical, persisted OHLC bars only. For a bullish prediction it measures target reach, return from activation, maximum adverse excursion (MAE), and maximum favourable excursion (MFE); bearish logic is the symmetric inverse. If target and invalidation are both crossed inside the same OHLC bar and intrabar ordering is unavailable, outcome status is `ambiguous_intrabar` and it is excluded from win-rate calculations. No LLM determines whether a prediction succeeded.

## Ingestion and feedback flow

```text
Existing daily report + deterministic inputs
  -> Postgres report row and immutable source payload
  -> agent structured-extraction JSON
  -> deterministic validator and semantic deduplicator
  -> Postgres predictions/conditions/outbox transaction
  -> idempotent Neo4j projection + vector segment indexing
  -> canonical OHLC collector
  -> deterministic outcome evaluator
  -> approved pattern/statistics job
  -> retrieval context for a later report
```

The agent retrieves three separately labelled context classes for later reports: relevant report segments from the vector store, evidence and setup relationships from Neo4j, and performance aggregates from Postgres. Retrieval output must state its time window, sample size, data-quality exclusions, pattern/statistics version, and whether it is evidence, correlation, or source-attributed commentary. The agent uses that context to formulate a new report; it never changes old predictions, facts, or outcomes.

## Current operational flow

Each report upsert writes a `cohort_daily_report.upserted.v1` event in the same Postgres transaction. Each committed deterministic market-regime, Prediction, and Outcome write likewise emits its typed research event in the same transaction. The outbox has stable aggregate deduplication keys, versioned payloads, row locking, retry timing, and stale-processing recovery. The worker claims events only after source transactions commit, projects each payload through Neo4j `MERGE` operations, and marks the matching event version complete. A later source write increments the event version and remains pending for another projection, preventing an older worker from marking newer content complete.

Use these API endpoints after graph connectivity is enabled:

```text
GET  /intelligence/knowledge-graph/status
POST /intelligence/knowledge-graph/process?limit=25
POST /intelligence/knowledge-graph/backfill?limit=100
POST /intelligence/knowledge-graph/research-backfill?limit=100
```

## Read-only historical evidence retrieval

Phase 2E exposes `POST /intelligence/reasoning/similar-setups` for deterministic case-based evidence retrieval. It reads authoritative Postgres Prediction and Outcome records at an explicit, separately labeled `horizon_days` value (default `28`) rather than treating Neo4j as a price or evaluation authority. A Prediction projects to its multiple `Outcome` nodes through `HAS_OUTCOME {horizon_days}` and retains the existing `RESULTED_IN` lineage. Returned Prediction, Outcome, and market-regime IDs are the same IDs projected to Neo4j, so callers may traverse the graph after receiving the evidence response.

The request can constrain symbol, category, setup, trend, extension, trigger, blocker, risk flags, selection regime, and coarse price/EMA200, support-distance, or resistance-room buckets. `exact` mode requires every supplied criterion; `weighted` mode uses the fraction of supplied deterministic criteria that match and requires at least 50% similarity.

The response is evidence, not a recommendation. It only includes selections and observed outcome dates before the request's `as_of_date` (or older data-quality evaluations with no observed date), uses the latest version per Prediction/horizon, excludes `data_quality_excluded` records from metrics, reports incomplete daily-path coverage separately, and withholds performance aggregates until the configured minimum sample size is reached. It also discloses source-window caps and symbol concentration.

## Pattern and confidence policy

A `Pattern` begins as `candidate` only after a deterministic grouping key derived from normalized selection conditions, regime, horizon, and rule/feature/data versions has occurred at least 30 times with at least 80% evaluable outcomes. Promotion to `approved` additionally requires a predeclared statistical test, a confidence interval, and an effect size beyond a configured minimum versus a baseline. The job records population definition, exclusions, lookback boundaries, calculation code version, and as-of timestamp.

Phase 2G implements this policy first as Postgres `pattern_candidates`: fixed low-dimensional condition groups, `30` observations, `80%` evaluable coverage, at least `3` cohorts, at most `50%` single-symbol concentration, chronological train/validation splits, Wilson intervals, and a two-proportion validation test. Human approval changes only the record to `approved_for_retrieval`; P2G intentionally emits no graph event and creates no Neo4j `Pattern` node or `INSTANCE_OF` edge. A future graph projection must consume only approved candidate IDs and preserve the stored statistics version, source IDs, and as-of date.

Historical performance may calibrate a displayed confidence only through a versioned, regularized calculation that reports sample size and uncertainty. It must not adjust the original `confidence_raw`, suppress losing examples, create targets retroactively, or let the LLM create a pattern based on narrative similarity alone.

## Safeguards

- Preserve immutable source reports, report segments, deterministic input snapshots, prompts, model IDs, schema versions, and extraction runs.
- Use strict typed JSON, deterministic validation, price/rule range checks, and an approval state before an extraction becomes active.
- Use the Postgres transactional outbox and idempotent `MERGE` projection keyed by UUID; retry failures rather than performing untracked dual writes.
- Evaluate every eligible prediction on schedule and store untriggered, invalidated, ambiguous, and unavailable-data outcomes alongside successful ones.
- Keep LLM commentary separate from facts: retrieved history is cited by IDs and source excerpts; the model has no credentials for direct graph, outcome, or pattern writes.
- Make outcome data provider, symbol normalization, OHLC interval, evaluation code version, and data-quality flags auditable.
- Prevent data leakage by retrieving only reports and outcomes whose publication/evaluation timestamps precede the new report timestamp.
- Require sample-size thresholds, confidence intervals, baseline comparison, and versioned deterministic calculations for pattern or correlation edges.
- Monitor drift, missing bars, duplicated semantic hashes, extraction rejection rate, and the difference between raw and calibrated confidence.

## Docker bootstrap

`docker-compose.yml` starts Neo4j Community at `http://localhost:7474` and Bolt at `bolt://localhost:7687`, with durable data and log volumes. The image can set only the initial `neo4j` username, so the bootstrap service first initializes `neo4j/admin`, creates the requested application user `tradeghost/admin`, and runs `tradeghost/knowledge_graph/knowledge_graph_v1.cypher` idempotently.

`admin` is only a local-development credential. It requires lowering Neo4j's default eight-character minimum to five characters, so it must be replaced with a secrets-managed credential for any shared or production deployment. If the persisted Neo4j volume already exists, its existing accounts are retained; remove neither the volume nor its data merely to apply a changed password.

Start and verify the graph service:

```powershell
docker compose up -d tradeghost-neo4j tradeghost-neo4j-init
docker compose ps
docker compose logs tradeghost-neo4j-init
```

Open Neo4j Browser at `http://localhost:7474` and sign in with `tradeghost` / `admin`. The API will not make graph writes until the planned outbox and projection worker are implemented.
