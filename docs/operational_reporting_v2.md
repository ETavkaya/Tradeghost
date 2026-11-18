# Operational Reporting V2

## Status

Phase B implements the manual Postgres foundation. `OPERATIONAL_REPORTING_ENABLED=false` and `MARKET_STATE_ENABLED=false` remain disabled by default; no scheduled report job or Product V2 UI is activated. An operator must intentionally set both flags and `PRODUCT_V2_ENABLED=true` before calling the write APIs.

## Purpose

Operational reporting gives a concise daily operating view without replacing forensic Research or Logs. It answers what the deterministic system observed, decided, tracked, and could not verify. It does not produce trade instructions.

## Report Types

| Report | Timing | Contents |
| --- | --- | --- |
| Daily market brief | After authoritative market-state collection | Market State, freshness, watchlist/scanner counts, material data-quality exceptions, scheduled jobs, and a linkable report ID. |
| Daily Strategy Lab brief | After an active experiment valuation | Ledger decisions, positions, cash, 56-session exits due, valuation completeness, and sleeve-level metrics. |
| Weekly review | Explicit calendar schedule | Market-state changes, scanner/monitor trends, experiment metrics, data gaps, and unresolved operational exceptions. |
| Monthly review | Explicit calendar schedule | Aggregated experiment/reporting metrics, model/data-version changes, exception trends, and human review links. |

Reports are snapshots with generated-at time, as-of market session, source versions, data-quality status, and provenance IDs. A report may be partial or unavailable; it must say so rather than reusing stale data as current.

## Storage and Read Model

Postgres remains authoritative. Phase B adds compact `market_state_snapshots` and `operational_reports` tables with idempotency keys, content hashes, source references, and indexed time-range lookups. A report retains structured summary fields and links to authoritative records; it does not duplicate every raw bar, full cohort audit, or unbounded LLM transcript.

Raw facts stay in their existing locations:

- Prediction/Outcome, cohort, hypothesis, and Pattern provenance stays in Research.
- Scheduler, backfill, graph outbox, and failure detail stays in Logs.
- Canonical market data and future Market State stay in versioned Postgres records.

Neo4j may receive a replayable report provenance projection only after the Postgres record is committed. It does not author a report.

## Market State Contract

Phase B evolves the existing deterministic regime snapshot rather than creating a parallel authority. Each `MarketState` version links the immutable regime snapshot, records observed timestamp, as-of market date, canonical input data versions, derived labels, unavailable inputs, and data-quality flags. V1 captures index regime, VIX, DXY, US 10Y, and a bounded number of sector proxies. US 2Y, breadth, and authoritative economic-event context are explicitly unavailable until a deterministic provider is configured; they are never guessed.

## Manual APIs

- `POST /intelligence/market-states/capture?market=us&as_of_date=YYYY-MM-DD`
- `GET /intelligence/market-states?market=us`
- `POST /intelligence/operational-reports/weekly?market=us&period_end=YYYY-MM-DD`
- `POST /intelligence/operational-reports/monthly?market=us&period_end=YYYY-MM-DD`
- `GET /intelligence/operational-reports?market=us`

The report APIs are manual only. Weekly reports cover the supplied end date and preceding six calendar days; monthly reports cover the first calendar day through the supplied end date. They use terminal Prediction/Outcome lineage, exclude superseded records, and restrict source records to those created/evaluated before the end of the as-of day. A later corrected report supersedes the prior report instead of updating it in place.

## Delivery Controls

- Daily/weekly/monthly cadence, retention, and time zone are explicit configuration, not hidden scheduler assumptions.
- Generation is idempotent for report type and as-of session.
- Report sections identify unavailable, stale, or data-quality-excluded inputs.
- LLM content, if later enabled, is marked advisory and may only summarise already persisted facts.
- Reports never modify scanner rules, Predictions, Outcomes, experiment ledger entries, or broker state.
- Market State capture is bounded to three macro instruments and the configured limited sector-proxy set, then relies on the existing canonical-bar cache. There is no polling loop or large export generation.

## Phase B Acceptance

1. A daily report has a stable Postgres ID, as-of session, provenance, and deterministic freshness status.
2. A missing data source produces an explicit partial/degraded section without blocking unrelated valid facts.
3. Weekly/monthly reports derive only from stored facts in their declared time window.
4. The UI distinguishes operating summaries from Research audit evidence.
5. Re-running a report is idempotent and does not alter source records.
