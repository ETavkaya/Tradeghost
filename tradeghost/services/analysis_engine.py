from __future__ import annotations

import math
from typing import Any

import pandas as pd

from tradeghost.services.data.market_data_service import MarketDataService
from tradeghost.services.indicators.calculations import compute_indicator_snapshot, ema
from tradeghost.services.interpretation.rules import interpret_snapshot
from tradeghost.services.scoring.engine import score_analysis
from tradeghost.services.strategy.planner import build_trade_plan
from tradeghost.shared.config.settings import get_settings
from tradeghost.shared.models.schemas import (
    AnalysisChart,
    AnalysisResponse,
    CategoryScores,
    ChartCandle,
    ChartLinePoint,
    ChartMapSection,
    CombinedAnalysisResponse,
    DetectedLevel,
    QuantEdgeSection,
    ScoreResponse,
    SwingPulseSection,
    TradePlanResponse,
)

_WINDOW_TO_PERIOD = {
    "5d": "6mo",
    "1m": "1y",
    "3m": "2y",
    "6m": "2y",
    "1y": "2y",
    "5y": "5y",
    "10y": "10y",
}

_WINDOW_TO_BARS = {
    "5d": 5,
    "1m": 22,
    "3m": 66,
    "6m": 132,
    "1y": 252,
    "5y": 1260,
    "10y": 2520,
}


class AnalysisEngine:
    def __init__(self, data_service: MarketDataService | None = None) -> None:
        self.data_service = data_service or MarketDataService()
        self.settings = get_settings()

    def _normalize_window(self, window: str | None) -> str:
        raw = (window or "6m").strip().lower()
        return raw if raw in _WINDOW_TO_PERIOD else "6m"

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            num = float(value)
        except (TypeError, ValueError):
            return default
        if math.isnan(num) or math.isinf(num):
            return default
        return num

    def _sanitize(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {k: self._sanitize(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._sanitize(v) for v in value]
        if isinstance(value, tuple):
            return tuple(self._sanitize(v) for v in value)
        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                return None
            return value
        return value

    @staticmethod
    def _score_summary(final_score: float) -> str:
        if final_score >= 75:
            return "High-conviction bullish setup with strong multi-factor confirmation."
        if final_score >= 65:
            return "Constructive setup with acceptable risk structure for swing consideration."
        if final_score >= 50:
            return "Mixed setup. Wait for stronger trend and momentum alignment."
        return "Weak setup. Risk dominates the reward profile under current rules."

    @staticmethod
    def _build_chart(
        daily: pd.DataFrame,
        snapshot: dict[str, Any],
        trade_plan,
        window: str,
    ) -> AnalysisChart:
        bars = _WINDOW_TO_BARS[window]
        display = daily.tail(bars).copy()
        close = daily["close"]
        ema_20_series = ema(close, 20).tail(len(display))
        ema_50_series = ema(close, 50).tail(len(display))

        candles = [
            ChartCandle(
                date=idx.date(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            for idx, row in display.iterrows()
        ]
        ema_20 = [ChartLinePoint(date=idx.date(), value=float(value)) for idx, value in ema_20_series.items()]
        ema_50 = [ChartLinePoint(date=idx.date(), value=float(value)) for idx, value in ema_50_series.items()]

        sr = snapshot.get("support_resistance", {})
        fib = snapshot.get("fibonacci", {})
        support = float(sr.get("support", 0.0)) if sr.get("support") is not None else 0.0
        resistance = float(sr.get("resistance", 0.0)) if sr.get("resistance") is not None else 0.0

        return AnalysisChart(
            candles=candles,
            ema_20=ema_20,
            ema_50=ema_50,
            current_price=float(snapshot.get("close", 0.0)),
            support_levels=[support],
            resistance_levels=[resistance],
            fibonacci_levels={str(k): float(v) for k, v in fib.items()},
            trade_plan_overlay=trade_plan,
        )

    def analyze_combined(self, ticker: str, window: str | None = None, market: str | None = None) -> CombinedAnalysisResponse:
        normalized_window = self._normalize_window(window)
        period = _WINDOW_TO_PERIOD[normalized_window]
        bundle = self.data_service.get_market_data(ticker, market=market, period=period)

        snapshot = compute_indicator_snapshot(
            daily=bundle.daily,
            weekly=bundle.weekly,
            market_cap=bundle.metadata.market_cap,
        )
        interpreted = interpret_snapshot(snapshot)
        category_scores, final_score = score_analysis(interpreted)
        support_resistance = snapshot["support_resistance"]
        swing_candidate, trade_plan = build_trade_plan(
            final_score=final_score,
            close=self._safe_float(snapshot.get("close")),
            atr=max(self._safe_float(snapshot.get("atr"), 1.0), 0.01),
            support=self._safe_float(support_resistance.get("support")),
            resistance=self._safe_float(support_resistance.get("resistance")),
            trend_score=category_scores.trend_score,
            momentum_score=category_scores.momentum_score,
        )

        score_breakdown = {
            "momentum": round(category_scores.momentum_score * self.settings.score_momentum_weight / 100, 4),
            "trend": round(category_scores.trend_score * self.settings.score_trend_weight / 100, 4),
            "volatility": round(category_scores.volatility_score * self.settings.score_volatility_weight / 100, 4),
            "structure": round(category_scores.structure_score * self.settings.score_structure_weight / 100, 4),
            "context": round(category_scores.context_score * self.settings.score_context_weight / 100, 4),
        }

        close = self._safe_float(snapshot.get("close"))
        ema20 = self._safe_float(snapshot.get("ema_20"), close)
        ema50 = self._safe_float(snapshot.get("ema_50"), close)
        nearest_support = self._safe_float(support_resistance.get("support"), close)
        nearest_resistance = self._safe_float(support_resistance.get("resistance"), close)

        fib = snapshot.get("fibonacci", {})
        nearest_fib = None
        if fib:
            nearest_fib = min(fib.keys(), key=lambda key: abs(self._safe_float(fib[key]) - close))

        breakout = bool(snapshot.get("breakout_candidate", False))
        channel_pct = (nearest_resistance - nearest_support) / max(close, 0.01)
        if breakout:
            market_state = "breakout"
        elif channel_pct < 0.08:
            market_state = "range"
        else:
            market_state = "channel"

        pattern = str(snapshot.get("candlestick_pattern", "none")).replace("_", " ")
        candle_summary = "No clean candle confirmation." if pattern == "none" else f"Pattern confirmation: {pattern}."
        ema_summary = (
            f"Price is {((close - ema20) / max(ema20, 0.01)) * 100:.2f}% vs EMA20 and "
            f"{((close - ema50) / max(ema50, 0.01)) * 100:.2f}% vs EMA50."
        )

        chart = self._build_chart(bundle.daily, snapshot, trade_plan, normalized_window)

        return CombinedAnalysisResponse(
            ticker=bundle.ticker,
            normalized_ticker=bundle.normalized_ticker,
            market=bundle.market,
            window=normalized_window,
            as_of=bundle.daily.index[-1].date(),
            chart=chart,
            quantedge=QuantEdgeSection(
                final_score=final_score,
                category_scores=category_scores,
                summary_interpretation=self._score_summary(final_score),
                structured_score_breakdown=score_breakdown,
            ),
            swingpulse=SwingPulseSection(
                swing_candidate=swing_candidate,
                setup_quality=round((0.35 * category_scores.trend_score) + (0.35 * category_scores.momentum_score) + (0.3 * category_scores.structure_score), 2),
                entry_zone=trade_plan.entry_zone,
                stop_loss=trade_plan.stop_loss,
                take_profit_levels=[trade_plan.take_profit_1, trade_plan.take_profit_2],
                risk_reward=trade_plan.risk_reward,
                invalidation_note=trade_plan.invalidation_note,
            ),
            chartmap=ChartMapSection(
                ema_proximity_summary=ema_summary,
                nearest_support=nearest_support,
                nearest_resistance=nearest_resistance,
                nearest_fib_zone=nearest_fib,
                market_state=market_state,
                candle_confirmation_summary=candle_summary,
                detected_levels=[
                    DetectedLevel(level_name="Support", value=nearest_support, level_type="support"),
                    DetectedLevel(level_name="Resistance", value=nearest_resistance, level_type="resistance"),
                    *[
                        DetectedLevel(level_name=f"Fib {name}", value=self._safe_float(value), level_type="fibonacci")
                        for name, value in fib.items()
                    ],
                ],
            ),
            interpreted_signals=interpreted["signals"],
            indicator_summary=self._sanitize(snapshot),
            trade_plan_summary=(
                f"Bias {trade_plan.bias}. Entry {trade_plan.entry_zone[0]:.2f}-{trade_plan.entry_zone[1]:.2f}, "
                f"SL {trade_plan.stop_loss:.2f}, TP1 {trade_plan.take_profit_1:.2f}, TP2 {trade_plan.take_profit_2:.2f}."
            ),
        )

    def analyze(self, ticker: str, market: str | None = None) -> AnalysisResponse:
        combined = self.analyze_combined(ticker=ticker, window="6m", market=market)
        return AnalysisResponse(
            ticker=combined.ticker,
            as_of=combined.as_of,
            final_score=combined.quantedge.final_score,
            category_scores=combined.quantedge.category_scores,
            indicator_summary=combined.indicator_summary,
            interpreted_signals=combined.interpreted_signals,
            swing_candidate=combined.swingpulse.swing_candidate,
            trade_plan=combined.chart.trade_plan_overlay,
        )

    def score_only(self, ticker: str, market: str | None = None) -> ScoreResponse:
        analysis = self.analyze(ticker, market=market)
        return ScoreResponse(
            ticker=analysis.ticker,
            as_of=analysis.as_of,
            final_score=analysis.final_score,
            category_scores=analysis.category_scores,
            interpreted_signals=analysis.interpreted_signals,
        )

    def trade_plan_only(self, ticker: str, market: str | None = None) -> TradePlanResponse:
        analysis = self.analyze(ticker, market=market)
        return TradePlanResponse(
            ticker=analysis.ticker,
            as_of=analysis.as_of,
            final_score=analysis.final_score,
            swing_candidate=analysis.swing_candidate,
            trade_plan=analysis.trade_plan,
        )
