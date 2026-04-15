# TradeGhost

TradeGhost is a production-style, deterministic, rule-based swing trading analysis engine for US equities.

This MVP is intentionally focused on:
- Analysis and scoring
- Strategy planning
- Historical backtesting
- API delivery via FastAPI
- Product UI delivery via Next.js dashboard

This version explicitly does **not** include:
- LLM features
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
- Legacy compatibility endpoints remain available:
  - `GET /analyze?ticker=TSLA`
  - `GET /score?ticker=TSLA`
  - `GET /trade-plan?ticker=TSLA`
  - `GET /backtest?ticker=TSLA&window=6m`

## Frontend Navigation

- `Analysis`
- `Backtest` (enabled after a successful analysis context is created)

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
