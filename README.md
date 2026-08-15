# TradeGhost

TradeGhost is a production-style, deterministic, rule-based swing trading analysis engine for US equities.

## Session Bootstrap (Read First)

To avoid losing context across VS Code / Codex restarts, treat these files as the project memory source of truth:

1. `README.md` (this file): architecture, workflow, constraints, and operating model
2. `docs/agent_handoff.md`: active mission, latest implemented state, decisions, blockers, and next steps

### Required startup behavior for new sessions

- Read `README.md` and `docs/agent_handoff.md` before making changes.
- Continue from the latest handoff state instead of re-discovering scope from scratch.
- If handoff and code disagree, trust code/runtime facts and update handoff immediately.

### Required update behavior after meaningful work

Update `docs/agent_handoff.md` at the end of each meaningful implementation step with:
- what was requested
- what changed (files + behavior)
- decisions/constraints
- current status
- next 1-3 concrete steps

This MVP is intentionally focused on:
- Analysis and scoring
- Strategy planning
- Historical backtesting
- API delivery via FastAPI
- Product UI delivery via Next.js dashboard

This version explicitly does **not** include:
- Broker execution
- Live auto-trading

## Objectives

- Build a modular foundation for a serious self-hosted system
- Keep indicator logic deterministic and explainable
- Separate raw indicators from interpreted signal states
- Aggregate category scores into a final swing suitability score (0-100)
- Produce a practical ATR-aware trade plan
- Run backtests using the same analysis logic used by live endpoints

## Architecture

```text
tradeghost/
  apps/
    api/                 # FastAPI application and endpoints
    web/                 # Next.js TypeScript frontend dashboard
  services/
    data/                # Market data abstraction + yfinance provider + caching
    indicators/          # Technical indicator calculations
    interpretation/      # Deterministic rules (raw values -> semantic states)
    scoring/             # Category score normalization + weighted final score
    strategy/            # Rule-based trade plan generator
    backtest/            # Historical simulation engine
  shared/
    config/              # Environment-driven settings
    models/              # Pydantic response models
    utils/               # Utilities (cache, math helpers)
  tests/                 # pytest coverage
  docker/                # Dockerfiles
  docs/                  # Architecture and scoring docs
```

## Official Analysis Config (Shared)

TradeGhost now uses one explicit `AnalysisConfig` as the single source of truth for both:
- unified analysis
- backtest-from-analysis

`AnalysisConfig` fields:
- `ticker`
- `market`
- `lookback_window`
- `strategy_mode`
- `score_threshold`
- `warmup_bars`
- `regime_filter`
- `location_filter`
- `trigger_filter`

Backtest-from-analysis consumes the same `analysis_config` returned by analysis, preventing silent config drift.

## Official Analysis Pipeline Order

The deterministic pipeline is explicitly defined and shared:
1. `fetch_data`
2. `calculate_indicators`
3. `calculate_category_scores`
4. `evaluate_threshold_gate`
5. `evaluate_regime_gate`
6. `evaluate_location_gate`
7. `evaluate_trigger_gate`
8. `compute_final_entry_decision`

Pipeline result is returned as structured diagnostics (`analysis_pipeline`) with:
- `final_score`
- `threshold_passed`
- `regime_valid`
- `location_valid`
- `trigger_valid`
- `final_entry_decision`
- `setup_status`
- `diagnostics`

Analysis also returns a deterministic `setup_interpretation` block:
- `trend_state`
- `pullback_state`
- `extension_state`
- `resistance_test_state`
- `trigger_state`
- `trigger_type`
- `setup_status` (`actionable`, `watchlist`, `avoid`)
- `reasoning_tags`

## Strategy Modes (Explicit)

Strategy mode presets are explicit and inspectable in backend config:

- `aggressive`
  - threshold: `50`
  - regime: `relaxed`
  - support max distance: `7.5%`
  - min resistance room: `1.5%`
  - trigger min score: `55`
- `balanced`
  - threshold: `60`
  - regime: `medium`
  - support max distance: `5.0%`
  - min resistance room: `2.5%`
  - trigger min score: `65`
- `conservative`
  - threshold: `72`
  - regime: `strict`
  - support max distance: `3.5%`
  - min resistance room: `3.5%`
  - trigger min score: `75`
- `custom`
  - inherits `balanced` defaults initially
  - can be extended with explicit user overrides

UI now displays effective config values (mode, threshold, warmup, filter settings) in analysis/backtest.

## Scoring Model

Category scores are normalized to `0-100`:
- `momentum_score`
- `trend_score`
- `volatility_score`
- `structure_score`
- `context_score`

Final score is weighted:

`final_score = ?(category_score * category_weight)`

Weights are environment configurable:
- `SCORE_MOMENTUM_WEIGHT`
- `SCORE_TREND_WEIGHT`
- `SCORE_VOLATILITY_WEIGHT`
- `SCORE_STRUCTURE_WEIGHT`
- `SCORE_CONTEXT_WEIGHT`

Default threshold:
- `SWING_CANDIDATE_THRESHOLD=65`

## Backend API Endpoints

- `GET /health`
- `GET /analyze-combined?ticker=TSLA&window=6m`
- `POST /backtest-from-analysis`
- Intelligence (cohort-first, current primary flow):
  - `POST /intelligence/discovery/create-cohort`
  - `GET /intelligence/cohorts`
  - `GET /intelligence/cohorts/{cohort_id}`
  - `POST /intelligence/cohorts/follow-up`
  - `POST /intelligence/cohorts/symbol-contexts`
  - `POST /intelligence/cohorts/briefing`
  - `POST /intelligence/cohorts/review`
  - `GET /intelligence/cohorts/{cohort_id}/export`
  - `GET /intelligence/cohorts/{cohort_id}/daily-reports`
  - `GET /intelligence/cohorts/{cohort_id}/daily-reports/{report_date}`
  - `POST /intelligence/cohorts/{cohort_id}/daily-reports/run`
  - `GET /intelligence/dashboard`
  - `GET /intelligence/llm/status`
  - `GET /intelligence/llm/logs`
  - `GET /intelligence/pipeline-events`
  - `POST /intelligence/llm/test`
- Intelligence legacy compatibility endpoints (still available):
  - `POST /intelligence/daily-pipeline`
  - `POST /intelligence/symbol-contexts`
  - `POST /intelligence/daily-briefing`
  - `POST /intelligence/review`
  - `GET /intelligence/report/{run_id}`
  - `GET /intelligence/report/{run_id}/export`
  - `POST /intelligence/report/approve`
- Legacy compatibility endpoints remain available:
  - `GET /analyze?ticker=TSLA`
  - `GET /score?ticker=TSLA`
  - `GET /trade-plan?ticker=TSLA`
  - `GET /backtest?ticker=TSLA&window=6m`

## Frontend Navigation

- `Scanner`
- `Analysis`
- `Backtest` (enabled after a successful analysis context is created)
- `Monitor`
- `Intelligence` (cohort-first deterministic workflow + optional LLM interpretation)
- `Logic` (pipeline + mode + setup-status transparency page)

## Intelligence Workflow

TradeGhost Intelligence now runs as a **cohort lifecycle workflow**:

1. Discovery Run -> `Create New Candidate Cohort`
- runs scanner category-by-category
- applies top-N per category
- merges and deduplicates
- stores immutable cohort candidate snapshots (original why-selected truth)

2. Follow-up Run -> `Run Follow-up for Selected Cohort`
- re-checks the same cohort symbols only
- updates current score/category/trend snapshots
- updates forward performance fields (`1D`, `3D`, `7D`, `14D`, `28D`) when available

3. Optional LLM context layer (advisory only):
- `Generate Cohort Symbol Contexts`
- `Generate Cohort Briefing`
- OpenAI is primary provider; Ollama is fallback
- deterministic engine remains source-of-truth

4. Cohort Review -> `Review Selected Cohort`
- deterministic review stats are generated first
- LLM summary is optional and never allowed to mutate deterministic results
- if history is insufficient, review returns readiness messaging instead of silent failure

### Intelligence UI (current)

- Main actions shown in Active Cohorts:
  - `Run Follow-up for Selected Cohort`
  - `Generate Cohort Symbol Contexts`
  - `Generate Cohort Briefing`
  - `Review Selected Cohort`
  - `Export Cohort Report`
- LLM Console:
  - always available on Intelligence page
  - default minimized
  - expandable with `Expand LLM Console` or `Jump to Console`
  - includes pipeline events + LLM call inspector with expandable rows

## Knowledge Graph V1

TradeGhost's daily Intelligence reports are the evidence source for an auditable knowledge graph. Postgres remains authoritative for raw reports, predictions, outcomes, and price snapshots; Neo4j stores an idempotent graph projection for relationship traversal and historical-setup retrieval. The LLM is an extraction and retrieval client only, never the system of record.

The V1 graph schema, prediction lifecycle, outcome rules, data flow, and anti-feedback safeguards are specified in `docs/knowledge_graph_v1.md`. The executable Neo4j constraints and indexes are in `tradeghost/knowledge_graph/knowledge_graph_v1.cypher`.

When `KNOWLEDGE_GRAPH_ENABLED=true`, new persisted cohort daily reports are added to a Postgres transactional outbox and projected into Neo4j by an idempotent background worker. The operational endpoints are:
- `GET /intelligence/knowledge-graph/status`
- `POST /intelligence/knowledge-graph/process`
- `POST /intelligence/knowledge-graph/backfill`

The first projection stage writes only deterministic report, asset, category, setup, and validity facts. It intentionally does not create `Prediction` or `Outcome` nodes from incomplete report fields.

### Current Graph Contents

`CALL db.schema.visualization()` displays Neo4j's available labels and relationship types. It is a schema view, not a rendering of every persisted report relationship. The initial projection currently writes these relationships for each daily report:

- `(:Report)-[:HAS_SEGMENT]->(:ReportSegment)`
- `(:Report)-[:REPORT_MENTIONS]->(:Asset)`
- `(:Report)-[:HAS_SIGNAL]->(:Signal)`
- `(:Signal)-[:SIGNAL_FOR]->(:Asset)`
- `(:Signal)-[:EXTRACTED_FROM]->(:ReportSegment)`

Use this query in Neo4j Browser to see real connected report data:

```cypher
MATCH path = (:Report)-[:HAS_SIGNAL]->(:Signal)-[:SIGNAL_FOR]->(:Asset)
RETURN path
LIMIT 100
```

The Docker-host backfill currently contains 29 reports, 20 assets, and 1,827 deterministic signals. Labels such as `Prediction`, `Outcome`, `Condition`, and `Pattern` appear in the schema because their constraints are installed, but they will remain unpopulated until the next V1 slice adds strict prediction extraction and deterministic outcome evaluation.
- Discovery Advanced Settings are intentionally reduced to:
  - `LLM Concurrency`
  - `LLM Timeout (sec)`
  - `Review Period Days`

### LLM Provider Configuration (current default)

Use `.env`:

```env
LLM_PROVIDER=openai
LLM_FALLBACK_PROVIDER=ollama
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5-mini
OPENAI_BASE_URL=https://api.openai.com/v1
LLMQ_CHAT_MODEL=gpt-5-mini
DAILY_REPORT_LLM_MODEL=gpt-5-mini
MARKET_CONTEXT_LLM_MODEL=gpt-5-mini
FINAL_28D_REVIEW_LLM_MODEL=gpt-5.4-mini
OLLAMA_BASE_URL=http://localhost:11435
OLLAMA_MODEL=llama3.2:3b
DATABASE_URL=postgresql://tradeghost:tradeghost@localhost:5432/tradeghost
DAILY_COHORT_FOLLOWUP_ENABLED=true
DAILY_COHORT_FOLLOWUP_SCHEDULE=23:30
DAILY_COHORT_FOLLOWUP_TIMEZONE=Europe/London
```

Notes:
- OpenAI is primary for speed/reliability.
- Ollama remains available for local fallback/offline runs.
- API keys stay backend-only and are never exposed to frontend logs.

## Decision Log / Backtest Diagnostics

Backtest now exposes both trade outcomes and setup decisions:
- `entries_considered`, `entries_triggered`
- skip counters by gate (`threshold`, `regime`, `location`, `trigger`)
- focused counters (`skipped_overextended`, `skipped_resistance_room`)
- setup-status counters (`actionable_setups`, `watchlist_setups`, `avoid_setups`)
- sampled decision log rows with numeric reason details

## Market Support (Phase 1)

- `US Stocks` (native symbols, e.g. `TSLA`, `NVDA`)
- `BIST` (normalized to yfinance format, e.g. `THYAO -> THYAO.IS`)

Legacy routes (`/quantedge`, `/swingpulse`, `/temel-analiz`, `/qe-backtest`, `/sp-backtest`) now redirect to the unified flow.

Frontend is served by Next.js at port `3000`.
It uses internal Next API proxy routes (`/api/*`) to call FastAPI through `BACKEND_URL`.

## Quick Start (Docker)

1. Copy environment file:
```bash
cp .env.example .env
```

2. Build and run:
```bash
docker compose up --build
```

3. Open:
- Web UI: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`
- Neo4j Browser: `http://localhost:7474` (`tradeghost` / `admin`)

The Compose bootstrap uses Neo4j's required initial `neo4j` account and then creates the requested application account, `tradeghost` / `admin`, before applying the graph schema. `admin` is deliberately supported for this local V1 only; replace both bootstrap and application credentials with Docker secrets before any non-local deployment.

## Deploy To Your Linux Docker Host

Example host: `emrebee@192.168.1.72`

1. SSH into server:
```bash
ssh emrebee@192.168.1.72
```

2. Clone and enter repo:
```bash
git clone <your-private-repo-url> tradeghost
cd tradeghost
```

3. Create runtime env file:
```bash
cp .env.example .env
```

4. Build and run in background:
```bash
docker compose up -d --build
```

5. Verify:
```bash
docker compose ps
docker compose logs -f tradeghost-api
docker compose logs -f tradeghost-web
```

6. Access from your LAN:
- `http://192.168.1.72:3000`
- `http://192.168.1.72:8000/health`
- `http://192.168.1.72:8000/docs`

### Update Existing Deployment (recommended routine)

If the stack already exists on your Linux Docker host, use:

```bash
git pull origin Full-analysis-flow---new-backtest
docker compose up -d --build
docker compose ps
```

## Local Dev (without Docker)

1. Python backend:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn tradeghost.apps.api.main:app --reload --host 0.0.0.0 --port 8000
```

2. Next.js frontend:
```bash
cd apps/web
npm install
BACKEND_URL=http://localhost:8000 npm run dev
```

3. Run backend tests:
```bash
pytest -q
```

## Quick Localhost Venv Test (Windows PowerShell)

```powershell
cd C:\repos\TradeGhOSt
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .
pytest -q
python -m uvicorn tradeghost.apps.api.main:app --host 127.0.0.1 --port 8000 --reload
```

Then in a new terminal:
```powershell
cd C:\repos\TradeGhOSt\apps\web
npm install
$env:BACKEND_URL="http://127.0.0.1:8000"
npm run dev
```

## Placeholder and Future Extensions

- Divergence analysis is currently a clearly labeled placeholder signal.
- Market context metadata is minimal (market cap/sector/industry from provider).
- Backtest execution model is intentionally simple and can evolve with:
  - Slippage/fees
  - Multi-position management
  - Position sizing
  - Portfolio-level analytics
- Frontend backtest date-range controls are UI-ready; backend still uses default backtest history window.
- Data provider abstraction is ready for migration to institutional feeds.

## Production Notes

- Designed for self-hosted Linux deployment with Docker.
- Configuration is environment-driven (`.env`).
- Business logic is modular for independent upgrades.

## Phase 2 — Evidence-Based Learning & Reasoning

TradeGhost Phase 2 turns cohort reports into a closed-loop research system.

The staged implementation plan, guardrails, data-truth contract, and ticket checklist are in `docs/phase2_learning_reasoning_plan.md`. Phase 2A currently strengthens deterministic follow-up coverage and backfill; durable Prediction and Outcome records are deferred to Phase 2B.

The system learns by:
1. Recording deterministic predictions at selection time.
2. Measuring deterministic outcomes at fixed horizons.
3. Linking setup conditions, market regime, and outcomes in Neo4j.
4. Retrieving similar historical cases for new setups.
5. Generating human-reviewed rule improvement hypotheses.
6. Testing proposed changes through versioned backtests before adoption.

The LLM does not trade, score, rank, or mutate rules.
The LLM can only:
- explain
- retrieve historical evidence
- summarize outcomes
- propose hypotheses
- draft human-reviewable rule changes
