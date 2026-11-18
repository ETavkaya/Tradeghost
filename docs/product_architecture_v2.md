# Product Architecture V2

## Status

Product V2 is being delivered in bounded phases. Phases A-C establish the compatibility, reporting, and manual virtual-ledger foundations. Phase D adds the primary workspace navigation on top of those existing APIs; it does not change scanner logic, cohort scheduling, persistence authority, or virtual-trade rules.

## Product Direction

TradeGhost evolves from a cohort-centric research dashboard into a self-hosted daily market-intelligence and portfolio-management product.

The intended primary workflow is:

```text
Discover -> Monitor -> Portfolio
```

`Research`, `Logic`, and `Logs` remain advanced workspaces. Existing cohorts and their Prediction/Outcome records remain the auditable research system; they are not portfolio trades.

## Authority Boundaries

| Layer | Authority |
| --- | --- |
| Scanner | Existing deterministic scores, five categories, gates, setup classification, and `final_entry_decision`. |
| Postgres | Canonical market data, Predictions, Outcomes, research lineage, future Market State, Strategy Lab ledger, and reporting read models. |
| Neo4j | Replayable projection of committed deterministic facts; never the source of prices, rules, or trades. |
| Vector retrieval | Source-text retrieval only; it cannot create a Prediction, Outcome, experiment, or ledger event. |
| LLM | Advisory explanation and summarisation only. It cannot score, rank, select, repair, approve, trade, or mutate rules. |

The current immutable Prediction/Outcome/outbox model is retained. Historical records must remain queryable with their source versions and correction lineage.

## Target Workspaces

| Workspace | Purpose | Phase |
| --- | --- | --- |
| Discover | Daily deterministic scanner results and bounded candidate context. | D |
| Monitor | Watchlists, alerts, freshness, and intraday/daily chart visibility. | D |
| Portfolio | Strategy Lab ledger, virtual experiment positions, performance, and later broker read-only view. | D |
| Research | Cohort, Prediction/Outcome, hypothesis, Pattern, and audit evidence. | Existing / advanced |
| Logic | Deterministic pipeline transparency and configuration. | Existing / advanced |
| Logs | Scheduler, data-quality recovery, outbox, and operational diagnostics. | Existing / advanced |

Navigation must not claim that a capability is live before the associated persistence and endpoint are implemented.

## Planned Data Additions

### Market State

The existing deterministic market-regime snapshot will be extended rather than duplicated. A future versioned `MarketState` record will retain source timestamp, provider freshness, data version, inputs, classifier version, and explicit unknown/stale states. It will cover index regime, VIX, DXY, US 2Y/10Y yields, sector leadership, breadth, and economic-event context where an authoritative source is available.

### Strategy Lab

Strategy Lab V1 is a future-only deterministic virtual experiment with an append-only Postgres ledger. It never converts historical cohorts into positions and never submits broker orders. Its exact contract is frozen in `docs/strategy_lab_v1.md`.

### Operational Reporting

Daily, weekly, and monthly reports will be compact Postgres-backed read models. They will summarise decisions, market state, data freshness, strategy metrics, and operational exceptions; raw forensic audit remains in Research and Logs. The reporting contract is in `docs/operational_reporting_v2.md`.

## Delivery Phases

1. **A — Compatibility and contracts:** complete. Preserves all current behavior and documents data ownership and migration rules.
2. **B — Market State and operational reports:** complete as a manual, feature-gated backend foundation. Adds versioned state provenance and compact Postgres report read models; no scheduler, UI workspace, or report job is activated.
3. **C — Strategy Lab ledger:** complete as a manual, feature-gated backend foundation. Adds future-only experiment configuration, append-only ledger events, positions, 56-session exits, avoided observations, and metrics; no scheduler or Portfolio UI is activated.
4. **D — Product workspaces:** complete. Discover invokes the existing deterministic daily pipeline with fixed bounded defaults; Monitor reuses the existing watchlist/alert workspace; Portfolio is a manual feature-gated UI for Strategy Lab. It does not enable flags, schedule processing, create broker orders, or alter scanner/category logic.
5. **E — Broker read-only:** add a separately enabled Trading 212 account-data adapter with no order capability.

Each phase requires the appropriate migrations, API, user surface, tests, and operational documentation before the next phase starts. Feature flags remain disabled by default until a phase is complete and intentionally enabled.

Phase B adds `market_state_snapshots` and `operational_reports` without changing historical cohort, Prediction, Outcome, regime, scanner, or graph records. Market State links to an existing immutable regime snapshot and its canonical input versions. Weekly/monthly reports contain compact counts, aggregate returns, version groups, a Market State reference, and explicit point-in-time filters; they do not contain cohort snapshots or research audit JSON.

Phase C adds isolated `strategy_lab_*` tables without linking a historical cohort or Prediction to a virtual position. A manual decision references a fresh deterministic daily-run result generated on or after the experiment activation time, freezes that source payload in Postgres, and requires its existing `final_entry_decision`. Canonical next-session bars create fills; canonical session 56 closes the position. The overextended sleeve remains `$100` cash while a separate avoided basket is tracked outside realised P&L.

Phase D is complete. `Discover` is the default workspace and invokes the established deterministic daily pipeline using fixed, bounded defaults without score or gate controls. `Monitor` reuses the existing watchlist and alert workspace. `Portfolio` is a manual, feature-gated Strategy Lab client that displays virtual ledger data and can submit only the existing explicit API actions. It cannot enable flags, schedule processing, create broker orders, alter scanner/category logic, or bypass deterministic API rejections.

## Compatibility Rules

- Do not modify existing scanner scoring, categories, gates, backtests, cohorts, or scheduler behavior for Product V2 work.
- Do not reclassify historical Predictions from risk flags alone. A superseding correction requires frozen evidence of a failed deterministic gate and recorded blocker.
- Keep every historical Prediction, Outcome, cohort, audit export, and Neo4j lineage link accessible.
- Use explicit version fields and append-only corrections instead of in-place truth changes.
- Do not add order placement, broker credential storage, or broker polling in Product V2 before Phase E.

## Runtime Verification

The local migration inventory and Compose configuration were reviewed during Phase A. The current Linux runtime host is `emrebee@192.168.0.230`; it was not contacted during Phase A. No deployment or runtime configuration change is implied by this document.
