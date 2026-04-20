from __future__ import annotations

import time
from dataclasses import dataclass

from tradeghost.services.analysis_engine import AnalysisEngine
from tradeghost.services.charts.payloads import WINDOW_TO_PERIOD
from tradeghost.services.strategy.config import build_analysis_config
from tradeghost.services.strategy.pipeline import run_analysis_pipeline
from tradeghost.shared.models.schemas import (
    ScannerCategory,
    ScannerDuration,
    ScannerPriority,
    ScannerRequest,
    ScannerResponse,
    ScannerResult,
    ScannerScopeSummary,
    ScannerUniverseScope,
)

US_WATCHLIST = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "GOOGL",
    "TSLA",
    "AMD",
    "NFLX",
    "AVGO",
    "JPM",
    "XOM",
]

US_FULL_UNIVERSE = [
    *US_WATCHLIST,
    "INTC", "QCOM", "ADBE", "ORCL", "CRM", "UBER", "PLTR", "MU", "SHOP", "SNOW",
    "DIS", "COST", "WMT", "HD", "NKE", "MCD", "KO", "PEP", "PFE", "MRK",
    "UNH", "ABBV", "TMO", "LLY", "CVX", "SLB", "BA", "GE", "CAT", "DE",
    "GS", "MS", "V", "MA", "PYPL", "SQ", "T", "VZ", "CSCO", "IBM",
]

BIST_WATCHLIST = [
    "THYAO", "AKBNK", "GARAN", "ASELS", "SISE", "KCHOL", "EREGL", "BIMAS", "TUPRS", "ISCTR",
]

BIST_FULL_UNIVERSE = [
    *BIST_WATCHLIST,
    "YKBNK", "SAHOL", "HALKB", "TCELL", "VAKBN", "PETKM", "FROTO", "TOASO", "ENKAI", "ARCLK",
    "PGSUS", "ALARK", "KRDMD", "HEKTS", "SASA", "ODAS", "KOZAL", "KOZAA", "MAVI", "DOHOL",
    "CCOLA", "TTKOM", "CIMSA", "TTRAK", "GUBRF", "ULKER", "ECILC", "VESBE", "OTKAR", "BRSAN",
]

CATEGORY_RECOMMENDED_DURATION: dict[ScannerCategory, ScannerDuration] = {
    ScannerCategory.TREND_MODE: ScannerDuration.TWO_YEAR,
    ScannerCategory.BUILD_UP: ScannerDuration.TWO_YEAR,
    ScannerCategory.MOMENTUM_MODE: ScannerDuration.ONE_YEAR,
    ScannerCategory.OVEREXTENDED: ScannerDuration.ONE_YEAR,
}


@dataclass
class _Eval:
    score: float
    tag: str
    reason: str


@dataclass
class _ScoreDynamics:
    current_score: float
    score_delta_short: float
    score_delta_medium: float
    score_dynamics_state: str


class ScannerEngine:
    def __init__(self, analysis_engine: AnalysisEngine | None = None) -> None:
        self.analysis_engine = analysis_engine or AnalysisEngine()

    def _universe(self, market: str, scope: ScannerUniverseScope) -> list[str]:
        if market == "bist":
            full = BIST_FULL_UNIVERSE
            watch = BIST_WATCHLIST
        else:
            full = US_FULL_UNIVERSE
            watch = US_WATCHLIST

        if scope == ScannerUniverseScope.WATCHLIST:
            return watch
        if scope == ScannerUniverseScope.CAPPED:
            return full[:30]
        return full

    @staticmethod
    def _priority(score: float) -> ScannerPriority:
        if score >= 78:
            return ScannerPriority.HIGH
        if score >= 60:
            return ScannerPriority.MEDIUM
        return ScannerPriority.LOW

    @staticmethod
    def _compression_state(support_distance_pct: float, resistance_room_pct: float) -> str:
        channel = support_distance_pct + resistance_room_pct
        if channel <= 6.0:
            return "compressed"
        if channel <= 12.0:
            return "balanced"
        return "expanded"

    @staticmethod
    def _classify_score_dynamics(short_delta: float, medium_delta: float) -> str:
        if short_delta >= 4.0 and medium_delta >= 8.0:
            return "accelerating"
        if short_delta >= 1.5 and medium_delta >= 3.0:
            return "improving"
        if short_delta <= -4.0 and medium_delta <= -8.0:
            return "deteriorating"
        if short_delta <= -1.5 or medium_delta <= -3.0:
            return "weakening"
        return "stable"

    def _compute_score_dynamics(self, *, daily, weekly, market_cap, config, current_score: float) -> _ScoreDynamics:

        short_score = current_score
        if len(daily) > 25:
            short_daily = daily.iloc[:-5]
            short_weekly = weekly[weekly.index <= short_daily.index[-1]]
            if len(short_weekly) >= 10:
                short_state = run_analysis_pipeline(daily=short_daily, weekly=short_weekly, market_cap=market_cap, config=config)
                short_score = float(short_state.final_score)

        medium_score = current_score
        if len(daily) > 40:
            medium_daily = daily.iloc[:-20]
            medium_weekly = weekly[weekly.index <= medium_daily.index[-1]]
            if len(medium_weekly) >= 10:
                medium_state = run_analysis_pipeline(daily=medium_daily, weekly=medium_weekly, market_cap=market_cap, config=config)
                medium_score = float(medium_state.final_score)

        short_delta = round(current_score - short_score, 2)
        medium_delta = round(current_score - medium_score, 2)
        return _ScoreDynamics(
            current_score=round(current_score, 2),
            score_delta_short=short_delta,
            score_delta_medium=medium_delta,
            score_dynamics_state=self._classify_score_dynamics(short_delta, medium_delta),
        )

    def _score_for_category(self, category: ScannerCategory, final_score: float, regime, location, setup, trigger, dynamics: _ScoreDynamics, snapshot: dict) -> _Eval:
        dynamics_boost = max(0.0, (dynamics.score_delta_short * 1.5) + (dynamics.score_delta_medium * 0.8))
        dynamics_penalty = max(0.0, ((-dynamics.score_delta_short) * 1.5) + ((-dynamics.score_delta_medium) * 0.8))
        breakout_candidate = bool(snapshot.get("breakout_candidate", False))

        if category == ScannerCategory.TREND_MODE:
            score = (
                (0.50 * final_score)
                + (20.0 if regime.price_above_ema200 else 0.0)
                + (12.0 if regime.ema200_slope_state in {"flat", "rising"} else 0.0)
                + (10.0 if regime.ema_stack_alignment in {"partial_bullish", "stacked_bullish"} else 0.0)
                + (0.35 * dynamics_boost)
                - (10.0 if location.overextended_flag else 0.0)
                - (0.4 * dynamics_penalty)
            )
            return _Eval(
                score=max(0.0, min(100.0, score)),
                tag="trend_mode",
                reason="Constructive continuation structure with EMA regime support.",
            )

        if category == ScannerCategory.BUILD_UP:
            near_reclaim = regime.bars_since_reclaim is not None and regime.bars_since_reclaim <= 8
            near_ema200 = abs(regime.price_vs_ema200_pct) <= 3.5
            score = (
                (0.30 * final_score)
                + (25.0 if near_reclaim else 0.0)
                + (18.0 if near_ema200 else 0.0)
                + (10.0 if trigger.trigger_state in {"pending", "confirmed"} else 0.0)
                + (8.0 if setup.setup_status in {"watchlist", "early_trend_transition"} else 0.0)
                + (0.55 * dynamics_boost)
                - max(0.0, abs(regime.price_vs_ema200_pct) - 5.0) * 2.2
                - max(0.0, location.support_distance_pct - 6.0) * 2.4
            )
            return _Eval(
                score=max(0.0, min(100.0, score)),
                tag="build_up",
                reason="Structure rebuilding near EMA200 with potential pre-breakout behavior.",
            )

        if category == ScannerCategory.MOMENTUM_MODE:
            extension_penalty = max(0.0, location.support_distance_pct - 10.0) * 1.8
            blowoff_penalty = max(0.0, location.overextension_ema20_pct - 12.0) * 1.2
            score = (
                (0.45 * final_score)
                + (20.0 if regime.price_above_ema200 else 0.0)
                + (12.0 if regime.ema200_slope_state in {"flat", "rising"} else 0.0)
                + (10.0 if regime.ema_stack_alignment in {"partial_bullish", "stacked_bullish"} else 0.0)
                + (8.0 if setup.trend_state in {"bullish_trend", "weakening_trend", "early_trend_transition"} else 0.0)
                + (8.0 if breakout_candidate or trigger.trigger_type in {"breakout_confirmation", "pullback_continuation"} else 0.0)
                + (0.8 * dynamics_boost)
                - extension_penalty
                - blowoff_penalty
                - (0.25 * dynamics_penalty)
            )
            return _Eval(
                score=max(0.0, min(100.0, score)),
                tag="momentum_mode",
                reason="Expansion candidate with bullish structure and improving score dynamics.",
            )

        score = (
            (0.30 * final_score)
            + (25.0 if location.overextended_flag else 0.0)
            + max(0.0, min(25.0, location.overextension_ema20_pct))
            + (8.0 if regime.price_above_ema200 else 0.0)
            - (0.20 * dynamics_boost)
        )
        return _Eval(
            score=max(0.0, min(100.0, score)),
            tag="overextended",
            reason="Extended move detected; monitor for pullback planning and caution.",
        )

    def scan(self, req: ScannerRequest) -> ScannerResponse:
        started = time.monotonic()
        symbols = self._universe(req.market.value, req.universe_scope)
        results: list[ScannerResult] = []
        processed = 0
        partial = False
        partial_note = None

        config = build_analysis_config(
            ticker="DUMMY",
            market=req.market,
            lookback_window=req.duration.value,
            strategy_mode="balanced",
        )
        period = WINDOW_TO_PERIOD[req.duration.value]

        for symbol in symbols:
            elapsed = time.monotonic() - started
            if elapsed >= req.max_runtime_seconds:
                partial = True
                partial_note = (
                    f"Partial scan returned: runtime budget {req.max_runtime_seconds:.1f}s reached "
                    f"after {processed}/{len(symbols)} symbols."
                )
                break

            try:
                bundle = self.analysis_engine.data_service.get_market_data(
                    symbol,
                    market=req.market,
                    period=period,
                )
                per_symbol_config = config.model_copy(update={"ticker": symbol})
                state = run_analysis_pipeline(daily=bundle.daily, weekly=bundle.weekly, market_cap=bundle.metadata.market_cap, config=per_symbol_config)
                regime = state.regime
                location = state.location
                setup = state.setup_interpretation
                trigger = state.trigger
                dynamics = self._compute_score_dynamics(
                    daily=bundle.daily,
                    weekly=bundle.weekly,
                    market_cap=bundle.metadata.market_cap,
                    config=per_symbol_config,
                    current_score=float(state.final_score),
                )
                scored = self._score_for_category(req.category, state.final_score, regime, location, setup, trigger, dynamics, state.snapshot)
                results.append(
                    ScannerResult(
                        symbol=bundle.ticker,
                        normalized_symbol=bundle.normalized_ticker,
                        scanner_score=round(scored.score, 2),
                        category_tag=scored.tag,
                        priority=self._priority(scored.score),
                        short_reason=scored.reason,
                        current_score=dynamics.current_score,
                        score_delta_short=dynamics.score_delta_short,
                        score_delta_medium=dynamics.score_delta_medium,
                        score_dynamics_state=dynamics.score_dynamics_state,
                        trend_state=setup.trend_state,
                        setup_status=setup.setup_status,
                        price_vs_ema200_pct=regime.price_vs_ema200_pct,
                        ema200_slope_state=regime.ema200_slope_state,
                        ema_stack_alignment=regime.ema_stack_alignment,
                        support_distance_pct=location.support_distance_pct,
                        resistance_room_pct=location.resistance_room_pct,
                        bars_since_reclaim=regime.bars_since_reclaim,
                        compression_state=self._compression_state(location.support_distance_pct, location.resistance_room_pct),
                    )
                )
                processed += 1
            except Exception:
                processed += 1
                continue

        ranked = sorted(
            results,
            key=lambda row: (
                row.scanner_score,
                row.current_score,
                row.score_delta_short,
                row.score_delta_medium,
                0 if row.priority == ScannerPriority.HIGH else 1 if row.priority == ScannerPriority.MEDIUM else 2,
            ),
            reverse=True,
        )[: req.max_results]

        runtime = round(time.monotonic() - started, 2)
        return ScannerResponse(
            scope=ScannerScopeSummary(
                market=req.market,
                category=req.category,
                duration=req.duration,
                recommended_duration=CATEGORY_RECOMMENDED_DURATION[req.category],
                universe_scope=req.universe_scope,
                symbol_count=len(symbols),
                processed_count=processed,
                max_results=req.max_results,
                runtime_seconds=runtime,
                partial_scan=partial,
                partial_scan_note=partial_note,
            ),
            results=ranked,
        )
