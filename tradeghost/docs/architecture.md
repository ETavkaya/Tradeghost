# TradeGhost Architecture Notes

## Design Principles

- Deterministic and explainable rule engine
- Separation of concerns per service layer
- Configurable scoring and thresholds
- Provider abstraction for market data portability

## Flow

1. `data` loads daily OHLCV + weekly resample + metadata.
2. `indicators` computes technical features from OHLCV.
3. `interpretation` maps numeric features to semantic states.
4. `scoring` normalizes category values and produces final score.
5. `strategy` builds ATR-aware swing plan.
6. `backtest` applies the same logic historically.
7. `api` exposes results through typed FastAPI endpoints.

## Non-Goals in This Version

- No LLM-driven logic
- No broker connectivity
- No live execution engine

