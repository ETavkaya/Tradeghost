# Trading 212 Read-Only Integration Plan

## Status

No Trading 212 code, credentials, API calls, polling job, order workflow, or UI is enabled in Phase A. `TRADING212_READ_ONLY_ENABLED=false` is a reserved kill switch for a later, separately reviewed Phase E implementation.

## Scope

The integration is account visibility only. It may eventually import account balance, cash, positions, instrument identifiers, executed-order history, and transaction history into a clearly labelled broker-read-only workspace.

It must never:

- submit, amend, cancel, or simulate a live broker order;
- turn Scanner, Monitor, Research, Strategy Lab, Neo4j, vector retrieval, or LLM output into broker action;
- use broker data to mutate an immutable Prediction, Outcome, historical cohort, or Strategy Lab ledger event;
- silently treat a broker position as a Strategy Lab position.

## Prerequisites for Phase E

1. Confirm the official Trading 212 API's supported read-only account capabilities, terms, rate limits, identity requirements, and sandbox/paper availability at implementation time.
2. Add provider-specific credentials through Docker secrets or an equivalent secret store, never committed `.env` values or client-side variables.
3. Define an explicit feature flag, capability allowlist, reconnect/backoff policy, rate limit, and manual disable path.
4. Establish canonical broker-account, instrument-mapping, position, transaction, and sync-run tables in Postgres.
5. Add a human-readable data-delay disclaimer and a clear separation between broker facts and Strategy Lab experiment facts.

## Adapter Boundary

Phase E should introduce a small backend-only adapter with read-only methods such as `get_account`, `list_positions`, `list_transactions`, and `list_orders`. The adapter returns normalized source payloads plus retrieval time, provider IDs, pagination cursor, and raw payload hash. A separate deterministic synchronizer writes an append-only sync record before deriving current-position projections.

The web application receives only sanitized read models. Browser code never receives credentials and never calls the broker directly.

## Safety Tests Required Before Enablement

- The adapter rejects every non-GET/order-changing method at its own boundary.
- The feature flag prevents all broker network calls when disabled.
- Retries cannot duplicate transactions or position changes.
- Credential values never appear in logs, responses, audit exports, or graph properties.
- A broker position and a Strategy Lab position remain distinguishable even when they reference the same instrument.
- A network/API failure leaves the last successful sync explicitly stale; it does not fabricate current data.

Any future expansion beyond read-only account visibility requires a new product decision, security review, legal/compliance review, separate architecture document, and explicit user approval.
