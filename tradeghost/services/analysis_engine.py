from __future__ import annotations

import math
from typing import Any

from tradeghost.services.charts.payloads import WINDOW_TO_PERIOD, build_analysis_chart
from tradeghost.services.data.market_data_service import MarketDataService
from tradeghost.services.strategy.config import build_analysis_config
from tradeghost.services.strategy.pipeline import run_analysis_pipeline
from tradeghost.services.strategy.planner import build_trade_plan
from tradeghost.shared.config.settings import get_settings
from tradeghost.shared.models.schemas import (
    AnalysisResponse,
    ChartMapSection,
    CombinedAnalysisResponse,
    DetectedLevel,
    QuantEdgeSection,
    ScoreResponse,
    StrategyMode,
    SwingPulseSection,
    TradePlanResponse,
)


class AnalysisEngine:
    def __init__(self, data_service: MarketDataService | None = None) -> None:
        self.data_service = data_service or MarketDataService()
        self.settings = get_settings()

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
    def _score_dynamics_state(snapshot: dict[str, Any]) -> str:
        rsi14 = float(snapshot.get("rsi", 50.0))
        macd_hist = float(snapshot.get("macd_hist", 0.0))
        if macd_hist >= 0.2 and rsi14 >= 60:
            return "accelerating"
        if macd_hist >= 0.05 and rsi14 >= 52:
            return "improving"
        if macd_hist <= -0.2 and rsi14 <= 42:
            return "deteriorating"
        if macd_hist <= -0.05 or rsi14 <= 48:
            return "weakening"
        return "stable"

    def analyze_combined(
        self,
        ticker: str,
        window: str | None = None,
        market: str | None = None,
        strategy_mode: StrategyMode | str | None = None,
        score_threshold: float | None = None,
        warmup_bars: int | None = None,
        regime_mode: str | None = None,
        max_support_distance_pct: float | None = None,
        min_resistance_room_pct: float | None = None,
        min_trigger_score: float | None = None,
        max_overextension_ema20_pct: float | None = None,
        max_overextension_ema50_pct: float | None = None,
        max_overextension_ema100_pct: float | None = None,
        max_overextension_ema200_pct: float | None = None,
    ) -> CombinedAnalysisResponse:
        analysis_config = build_analysis_config(
            ticker=ticker,
            market=market,
            lookback_window=window,
            strategy_mode=strategy_mode,
            score_threshold=score_threshold,
            warmup_bars=warmup_bars,
            regime_mode=regime_mode,
            max_support_distance_pct=max_support_distance_pct,
            min_resistance_room_pct=min_resistance_room_pct,
            min_trigger_score=min_trigger_score,
            max_overextension_ema20_pct=max_overextension_ema20_pct,
            max_overextension_ema50_pct=max_overextension_ema50_pct,
            max_overextension_ema100_pct=max_overextension_ema100_pct,
            max_overextension_ema200_pct=max_overextension_ema200_pct,
        )
        period = WINDOW_TO_PERIOD[analysis_config.lookback_window]
        bundle = self.data_service.get_market_data(analysis_config.ticker, market=analysis_config.market, period=period)

        pipeline = run_analysis_pipeline(
            daily=bundle.daily,
            weekly=bundle.weekly,
            market_cap=bundle.metadata.market_cap,
            config=analysis_config,
        )
        snapshot = pipeline.snapshot
        snapshot["fundamentals"] = {
            "market_cap": bundle.metadata.market_cap,
            "sector": bundle.metadata.sector,
            "industry": bundle.metadata.industry,
            "price_to_book": bundle.metadata.price_to_book,
            "price_to_earnings": bundle.metadata.price_to_earnings,
        }
        interpreted = pipeline.interpreted
        category_scores = pipeline.category_scores
        final_score = pipeline.final_score
        support_resistance = snapshot["support_resistance"]
        _, trade_plan = build_trade_plan(
            final_score=final_score,
            close=self._safe_float(snapshot.get("close")),
            atr=max(self._safe_float(snapshot.get("atr"), 1.0), 0.01),
            support=self._safe_float(support_resistance.get("support")),
            resistance=self._safe_float(support_resistance.get("resistance")),
            trend_score=category_scores.trend_score,
            momentum_score=category_scores.momentum_score,
        )
        regime = pipeline.regime
        location = pipeline.location
        trigger = pipeline.trigger
        setup_interpretation = pipeline.setup_interpretation
        entry_gate = pipeline.entry_gate
        swing_candidate = entry_gate.final_entry_decision and trade_plan.bias == "bullish"

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
        ema100 = self._safe_float(snapshot.get("ema_100"), close)
        ema200 = self._safe_float(snapshot.get("ema_200"), close)
        nearest_support = self._safe_float(support_resistance.get("support"), close)
        nearest_resistance = self._safe_float(support_resistance.get("resistance"), close)

        fib = snapshot.get("fibonacci", {})
        nearest_fib = None
        nearest_fib_level = None
        distance_to_nearest_fib_pct = None
        next_fib_target = None
        fib_target_room_pct = None
        if fib:
            nearest_fib = min(fib.keys(), key=lambda key: abs(self._safe_float(fib[key]) - close))
            nearest_fib_level = self._safe_float(fib.get(nearest_fib))
            distance_to_nearest_fib_pct = abs((close - nearest_fib_level) / max(close, 0.01)) * 100
            above = sorted([(name, self._safe_float(val)) for name, val in fib.items() if self._safe_float(val) > close], key=lambda x: x[1])
            if above:
                next_fib_target = above[0][0]
                fib_target_room_pct = ((above[0][1] - close) / max(close, 0.01)) * 100

        fib_ema_confluence_score = 0.0
        fib_support_confluence = False
        if nearest_fib_level is not None:
            dist_ema100 = abs((ema100 - nearest_fib_level) / max(nearest_fib_level, 0.01)) * 100
            dist_ema200 = abs((ema200 - nearest_fib_level) / max(nearest_fib_level, 0.01)) * 100
            dist_support = abs((nearest_support - nearest_fib_level) / max(nearest_fib_level, 0.01)) * 100
            fib_ema_confluence_score = max(0.0, 100.0 - (dist_ema100 * 18.0) - (dist_ema200 * 18.0) - (dist_support * 12.0))
            fib_support_confluence = dist_support <= 1.5

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
        stack_ok = ema20 > ema50 > ema100 > ema200
        above_200 = close > ema200
        score_dynamics = self._score_dynamics_state(snapshot)

        setup_type = setup_interpretation.setup_type
        opportunity_type = setup_type
        if setup_type == "pullback" and location.extension_state == "controlled_extension":
            opportunity_type = "momentum_continuation"
        interest_reason = (
            f"{opportunity_type.replace('_', ' ')} with dynamics={score_dynamics}, "
            f"confluence={fib_ema_confluence_score:.1f}, trigger={trigger.trigger_type}."
        )
        risk_reason = (
            f"Risk from extension={location.extension_state}, resistance room={location.resistance_room_pct:.2f}%, "
            f"regime={regime.regime_reason_code}."
        )
        ema_summary = (
            f"Price is {((close - ema20) / max(ema20, 0.01)) * 100:.2f}% vs EMA20 and "
            f"{((close - ema50) / max(ema50, 0.01)) * 100:.2f}% vs EMA50, "
            f"{((close - ema100) / max(ema100, 0.01)) * 100:.2f}% vs EMA100, "
            f"and {((close - ema200) / max(ema200, 0.01)) * 100:.2f}% vs EMA200. "
            f"EMA stack quality: {'strong bullish stack' if stack_ok else 'mixed stack'}. "
            f"Price {'is' if above_200 else 'is not'} above EMA200."
        )

        chart = build_analysis_chart(bundle.daily, snapshot, trade_plan, analysis_config.lookback_window)

        return CombinedAnalysisResponse(
            ticker=bundle.ticker,
            normalized_ticker=bundle.normalized_ticker,
            market=bundle.market,
            window=analysis_config.lookback_window,
            as_of=bundle.daily.index[-1].date(),
            analysis_config=analysis_config,
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
                strategy_mode_used=analysis_config.strategy_mode,
                score_threshold_used=analysis_config.score_threshold,
            ),
            chartmap=ChartMapSection(
                ema_proximity_summary=ema_summary,
                nearest_support=nearest_support,
                nearest_resistance=nearest_resistance,
                nearest_fib_zone=nearest_fib,
                nearest_fib_level=nearest_fib_level,
                distance_to_nearest_fib_pct=round(distance_to_nearest_fib_pct, 2) if distance_to_nearest_fib_pct is not None else None,
                fib_ema_confluence_score=round(fib_ema_confluence_score, 2),
                fib_support_confluence=fib_support_confluence,
                next_fib_target=next_fib_target,
                fib_target_room_pct=round(fib_target_room_pct, 2) if fib_target_room_pct is not None else None,
                market_state=market_state,
                candle_confirmation_summary=candle_summary,
                opportunity_type=opportunity_type,
                opportunity_interest_reason=interest_reason,
                opportunity_risk_reason=risk_reason,
                detected_levels=[
                    DetectedLevel(level_name="Support", value=nearest_support, level_type="support"),
                    DetectedLevel(level_name="Resistance", value=nearest_resistance, level_type="resistance"),
                    *[
                        DetectedLevel(level_name=f"Fib {name}", value=self._safe_float(value), level_type="fibonacci")
                        for name, value in fib.items()
                    ],
                ],
            ),
            regime=regime,
            location=location,
            trigger=trigger,
            setup_interpretation=setup_interpretation,
            entry_gate=entry_gate,
            analysis_pipeline=pipeline.pipeline_result,
            strategy_mode_used=analysis_config.strategy_mode,
            interpreted_signals=interpreted["signals"],
            indicator_summary=self._sanitize(snapshot),
            trade_plan_summary=(
                f"Opportunity {opportunity_type.replace('_', ' ')}. "
                f"Bias {trade_plan.bias}. Entry {trade_plan.entry_zone[0]:.2f}-{trade_plan.entry_zone[1]:.2f}, "
                f"SL {trade_plan.stop_loss:.2f}, TP1 {trade_plan.take_profit_1:.2f}, TP2 {trade_plan.take_profit_2:.2f}. "
                f"Confluence {fib_ema_confluence_score:.1f}, next fib target {next_fib_target or 'n/a'}."
            ),
        )

    def analyze(
        self,
        ticker: str,
        market: str | None = None,
        strategy_mode: StrategyMode | str | None = None,
    ) -> AnalysisResponse:
        combined = self.analyze_combined(ticker=ticker, window="6m", market=market, strategy_mode=strategy_mode)
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
        analysis = self.analyze(ticker, market=market, strategy_mode=StrategyMode.BALANCED)
        return ScoreResponse(
            ticker=analysis.ticker,
            as_of=analysis.as_of,
            final_score=analysis.final_score,
            category_scores=analysis.category_scores,
            interpreted_signals=analysis.interpreted_signals,
        )

    def trade_plan_only(self, ticker: str, market: str | None = None) -> TradePlanResponse:
        analysis = self.analyze(ticker, market=market, strategy_mode=StrategyMode.BALANCED)
        return TradePlanResponse(
            ticker=analysis.ticker,
            as_of=analysis.as_of,
            final_score=analysis.final_score,
            swing_candidate=analysis.swing_candidate,
            trade_plan=analysis.trade_plan,
        )
