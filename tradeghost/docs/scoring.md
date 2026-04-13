# Scoring Logic

## Category Inputs

- Momentum: RSI, MACD, Stochastic, OBV slope, A/D slope, volume state, divergence placeholder
- Trend: MA alignment, ADX strength, weekly trend alignment
- Volatility: Bollinger position, ATR regime, Fibonacci relation
- Structure: support/resistance context, candlestick pattern, breakout check
- Context: 52-week range position, market cap state

## Normalization

Interpretation states map to deterministic raw scores in `[-1, 1]`.
Each category is averaged and normalized to `[0, 100]`.

## Final Score

Weighted average of category scores:

`final = Σ(category_score * configured_weight)`

Weights are configurable via environment variables.

## Candidate Logic

A ticker is a swing candidate when:
- `final_score >= SWING_CANDIDATE_THRESHOLD`
- trend and momentum support a bullish bias

