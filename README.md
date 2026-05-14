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
OPENAI_MODEL=gpt-4.1-mini
OPENAI_BASE_URL=https://api.openai.com/v1
OLLAMA_BASE_URL=http://localhost:11435
OLLAMA_MODEL=llama3.2:3b
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
