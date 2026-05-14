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
