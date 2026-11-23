# Strategy Lab V1

## Status

Phase C implements the manual Postgres ledger foundation and Phase D adds a Portfolio UI client. Strategy Lab remains disabled by default (`STRATEGY_LAB_ENABLED=false`); there is no scheduler or broker call. An operator must intentionally enable both `PRODUCT_V2_ENABLED=true` and `STRATEGY_LAB_ENABLED=true` before the Portfolio UI can read or use the manual APIs. The UI cannot modify those flags.

## Purpose

Strategy Lab measures how a fixed, future-only deterministic sleeve would have performed. It is an experiment ledger, not investment advice, a scanner change, a broker integration, or a rewrite of cohort research.

## V1 Experiment Contract

| Item | Fixed V1 rule |
| --- | --- |
| Activation | Explicit human activation date and immutable experiment configuration. Never backfill historical trades. |
| Starting capital | Five sleeves of `$100` each. |
| Long sleeves | `trend`, `momentum`, `breakout`, and `pullback`; each has at most five open positions and `$20` maximum allocated per slot. |
| Overextended sleeve | Keeps its `$100` as cash. Separately records a hypothetical avoided basket; it is never mixed into realised sleeve P&L. |
| Eligibility | Existing deterministic `final_entry_decision=true` plus the sleeve mapping frozen at selection time. No LLM decision and no new score/category logic. |
| Entry price | Deterministic next eligible session price under a documented source/adjustment policy. Missing or stale data creates an exception, not a guessed fill. |
| Exit | Fixed at 56 eligible trading sessions unless a future versioned experiment explicitly defines another deterministic exit. |
| Arithmetic | `Decimal`, explicit currency, immutable fill/valuation sources, and append-only ledger events. |

The scanner can surface candidates. Strategy Lab alone decides whether an eligible candidate can be represented in a configured sleeve, based only on frozen deterministic policy, remaining slots, cash, and duplicate-position rules.

## Required Ledger Model

Phase C must use Postgres as the authority. Minimum entities are:

- `strategy_lab_experiments`: immutable configuration, activation timestamp, policy/rule/feature/data versions, and status.
- `strategy_lab_sleeves`: fixed allocation, cash balance, capacity, and sleeve identity.
- `strategy_lab_decisions`: deterministic eligibility, selected or rejected result, reason codes, source candidate/prediction IDs, and as-of timestamp.
- `strategy_lab_ledger_events`: append-only cash, reservation, fill, valuation, and close events with idempotency keys.
- `strategy_lab_positions`: projection of ledger events with entry/exit source data and 56-session lifecycle.
- `strategy_lab_avoided_observations`: hypothetical overextended observations, strictly separate from cash and realised returns.

Corrections append a reversing or superseding ledger event. They never mutate a posted event or silently replace a price source.

## Manual API Flow

1. Run the existing deterministic daily pipeline; no Strategy Lab endpoint runs or changes scanner logic.
2. Create a future-only experiment with `POST /intelligence/strategy-lab/experiments`. `activation_at` must be timezone-aware and current/future.
3. If created ahead of time, explicitly activate it after its activation time with `POST /intelligence/strategy-lab/experiments/{experiment_id}/activate`.
4. Submit one decision from a source `run_id`, symbol, and scanner category through `POST /intelligence/strategy-lab/experiments/{experiment_id}/decisions`.
5. Manually process canonical bars with `POST /intelligence/strategy-lab/experiments/{experiment_id}/process?as_of_date=YYYY-MM-DD`.

The Phase D Portfolio workspace exposes the same manual workflow for US or BIST experiments. It shows the four steps directly: run a deterministic discovery, create and manually activate a virtual experiment, record a fresh eligible candidate, then manually process canonical bars. It requires explicit confirmations before creating a virtual experiment or processing canonical bars, and clearly shows a disabled runtime state when the feature flags are off. It does not start a background task or bypass an API rejection.

The decision endpoint rejects a run that predates activation, a missing source symbol/category, a false frozen `final_entry_decision`, source data-quality flags, duplicate exposure, or exhausted sleeve capacity. The processor is idempotent and never runs in the background.

## Safety and Provenance

- An existing cohort or Prediction is research evidence, not a virtual trade. Phase C starts only after the configured activation time.
- Every decision retains scanner versions, market-data version, selection time, price provenance, deterministic eligibility inputs, and source identifiers.
- Market-data quality failures, stale prices, and session-calendar ambiguity are explicit exceptions and exclude the affected metric until resolved.
- The experiment must prevent duplicate open exposure to the same symbol according to a documented, deterministic rule.
- Reporting separates realised, unrealised, cash, avoided-basket, and unavailable-data metrics.
- No LLM, Neo4j projector, vector retrieval, or broker adapter may write the ledger.

## Required Metrics

Metrics are labelled by experiment and sleeve and include realised/unrealised P&L, cash, hit rate, average win/loss, append-only cash/mark-to-market drawdown, capacity use, holding-period distribution, rejected eligibility reasons, and data-quality holds. Cross-sleeve aggregates retain their source scope and never present the avoided basket as realised performance.

## Phase C Acceptance

1. An explicitly activated future experiment records deterministic decisions from fresh daily-run evidence without changing scanner behavior.
2. Identical inputs replay idempotently without duplicate ledger events or positions.
3. A long sleeve cannot exceed five positions or `$20` per slot.
4. The overextended sleeve remains cash while its avoided basket is visible separately.
5. Every 56-session exit is derived from canonical price/session data and remains auditable.
6. No historical cohort is fabricated into a Strategy Lab trade and no broker order can be created.
