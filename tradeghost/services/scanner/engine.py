from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date

from tradeghost.services.analysis_engine import AnalysisEngine
from tradeghost.services.charts.payloads import WINDOW_TO_PERIOD
from tradeghost.services.strategy.config import build_analysis_config
from tradeghost.services.strategy.pipeline import run_analysis_pipeline
from tradeghost.shared.models.schemas import (
    ScannerCategory,
    ScannerDuration,
    ScannerPriority,
    ScannerRuleField,
    ScannerRuleOperator,
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


@dataclass
class _LevelTests:
    resistance_test_count: int
    ema200_test_count: int
    repeated_test_count: int


@dataclass
class _Eligibility:
    strict: bool
    relaxed: bool


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

    @staticmethod
    def _tradingview_url(market: str, symbol: str) -> str:
        exchange_prefix = "BIST" if market == "bist" else "NASDAQ"
        return f"https://www.tradingview.com/chart/?symbol={exchange_prefix}%3A{symbol}"

    @staticmethod
    def _count_test_events(mask) -> int:
        return int((mask & ~mask.shift(1).fillna(False)).sum())

    def _level_test_counts(self, daily, snapshot: dict) -> _LevelTests:
        close = daily["close"]
        ema200 = close.ewm(span=200, adjust=False).mean()
        resistance = float(snapshot.get("support_resistance", {}).get("resistance", close.iloc[-1]))

        near_ema200 = ((close - ema200).abs() / ema200.clip(lower=0.01) * 100) <= 1.0
        resistance_gap_pct = ((resistance - close) / close.clip(lower=0.01)) * 100
        near_resistance = (resistance_gap_pct >= 0) & (resistance_gap_pct <= 1.5)

        ema_tests = self._count_test_events(near_ema200)
        resistance_tests = self._count_test_events(near_resistance)
        repeated_tests = ema_tests + resistance_tests
        return _LevelTests(
            resistance_test_count=int(resistance_tests),
            ema200_test_count=int(ema_tests),
            repeated_test_count=int(repeated_tests),
        )

    def _category_eligibility(self, *, category: ScannerCategory, regime, location, setup, trigger, dynamics: _ScoreDynamics, snapshot: dict) -> _Eligibility:
        breakout_candidate = bool(snapshot.get("breakout_candidate", False))
        compression = self._compression_state(location.support_distance_pct, location.resistance_room_pct)
        improving = dynamics.score_dynamics_state in {"improving", "accelerating"}

        if category == ScannerCategory.TREND_MODE:
            strict = bool(
                regime.price_above_ema200
                and regime.ema200_slope_state in {"flat", "rising"}
                and setup.trend_state in {"bullish_trend", "weakening_trend", "early_trend_transition"}
            )
            relaxed = bool(
                regime.price_above_ema200
                or regime.ema200_slope_state in {"flat", "rising"}
                or setup.trend_state in {"bullish_trend", "weakening_trend", "early_trend_transition"}
            )
            return _Eligibility(strict=strict, relaxed=relaxed)

        if category == ScannerCategory.BUILD_UP:
            near_ema200 = abs(regime.price_vs_ema200_pct) <= 8.0
            reclaiming = regime.bars_since_reclaim is not None and regime.bars_since_reclaim <= 15
            strict = bool((near_ema200 or reclaiming) and compression in {"compressed", "balanced"})
            relaxed = bool(
                near_ema200
                or reclaiming
                or compression == "compressed"
                or setup.setup_status in {"watchlist", "early_trend_transition"}
            )
            return _Eligibility(strict=strict, relaxed=relaxed)

        if category == ScannerCategory.MOMENTUM_MODE:
            strict = bool(
                regime.price_above_ema200
                and setup.trend_state in {"bullish_trend", "weakening_trend", "early_trend_transition"}
                and (breakout_candidate or improving or trigger.trigger_state in {"pending", "confirmed"})
            )
            relaxed = bool(
                (regime.price_above_ema200 and setup.trend_state in {"bullish_trend", "weakening_trend", "early_trend_transition"})
                or breakout_candidate
                or improving
            )
            return _Eligibility(strict=strict, relaxed=relaxed)

        strict = bool(location.overextended_flag or location.overextension_ema20_pct >= 8.0)
        relaxed = bool(strict or location.support_distance_pct >= 8.0 or regime.price_above_ema200)
        return _Eligibility(strict=strict, relaxed=relaxed)

    @staticmethod
    def _range_metrics(daily, range_start: date | None, range_end: date | None) -> tuple[float | None, float | None, float | None, float | None]:
        if range_start is None or range_end is None:
            return None, None, None, None
        if range_end < range_start:
            return None, None, None, None

        window = daily[(daily.index.date >= range_start) & (daily.index.date <= range_end)]
        if window.empty:
            return None, None, None, None

        range_low = float(window["low"].min())
        range_high = float(window["high"].max())
        close = float(daily["close"].iloc[-1])
        from_low = ((close - range_low) / max(range_low, 0.01)) * 100
        to_high = ((range_high - close) / max(close, 0.01)) * 100
        return round(range_low, 2), round(range_high, 2), round(from_low, 2), round(to_high, 2)

    @staticmethod
    def _field_value(field: ScannerRuleField, *, regime, location, setup, snapshot: dict) -> float | str:
        if field == ScannerRuleField.PRICE_VS_EMA200_PCT:
            return float(regime.price_vs_ema200_pct)
        if field == ScannerRuleField.DISTANCE_TO_EMA20_PCT:
            return float(location.distance_to_ema20_pct)
        if field == ScannerRuleField.DISTANCE_TO_EMA50_PCT:
            return float(location.distance_to_ema50_pct)
        if field == ScannerRuleField.RSI_14:
            return float(snapshot.get("rsi_14", 0.0))
        if field == ScannerRuleField.VOLUME_RATIO_20:
            return float(snapshot.get("volume", {}).get("volume_ratio", 0.0))
        if field == ScannerRuleField.SUPPORT_DISTANCE_PCT:
            return float(location.support_distance_pct)
        if field == ScannerRuleField.RESISTANCE_ROOM_PCT:
            return float(location.resistance_room_pct)
        if field == ScannerRuleField.EMA200_SLOPE_STATE:
            return str(regime.ema200_slope_state)
        if field == ScannerRuleField.TREND_STATE:
            return str(setup.trend_state)
        return 0.0

    @staticmethod
    def _rule_matches(*, actual: float | str, operator: ScannerRuleOperator, value_number: float | None, value_text: str | None, value_list: list[str]) -> bool:
        if operator in {ScannerRuleOperator.GT, ScannerRuleOperator.GTE, ScannerRuleOperator.LT, ScannerRuleOperator.LTE}:
            if not isinstance(actual, (int, float)) or value_number is None:
                return False
            if operator == ScannerRuleOperator.GT:
                return actual > value_number
            if operator == ScannerRuleOperator.GTE:
                return actual >= value_number
            if operator == ScannerRuleOperator.LT:
                return actual < value_number
            return actual <= value_number

        if operator == ScannerRuleOperator.EQ:
            if isinstance(actual, (int, float)):
                return value_number is not None and float(actual) == float(value_number)
            return value_text is not None and str(actual) == value_text

        if operator == ScannerRuleOperator.IN:
            normalized = {str(item) for item in value_list}
            return str(actual) in normalized

        return False

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

    def _score_for_category(self, category: ScannerCategory, final_score: float, regime, location, setup, trigger, dynamics: _ScoreDynamics, snapshot: dict, volume_ratio_20: float) -> _Eval:
        dynamics_boost = max(0.0, (dynamics.score_delta_short * 1.5) + (dynamics.score_delta_medium * 0.8))
        dynamics_penalty = max(0.0, ((-dynamics.score_delta_short) * 1.5) + ((-dynamics.score_delta_medium) * 0.8))
        breakout_candidate = bool(snapshot.get("breakout_candidate", False))

        if category == ScannerCategory.TREND_MODE:
            score = (
                (0.50 * final_score)
                + (20.0 if regime.price_above_ema200 else 0.0)
                + (12.0 if regime.ema200_slope_state in {"flat", "rising"} else 0.0)
                + (10.0 if regime.ema_stack_alignment in {"partial_bullish", "stacked_bullish"} else 0.0)
                + (6.0 if volume_ratio_20 >= 1.1 else 0.0)
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
                + (5.0 if volume_ratio_20 >= 1.05 else 0.0)
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
                + (8.0 if volume_ratio_20 >= 1.15 else 0.0)
                + (0.8 * dynamics_boost)
                - extension_penalty
                - blowoff_penalty
                - (0.25 * dynamics_penalty)
            )
            momentum_note = "Controlled extension accepted" if location.extension_state == "controlled_extension" else "Momentum structure intact"
            if location.extension_state == "blowoff_extension":
                momentum_note = "Blowoff extension risk"
            return _Eval(
                score=max(0.0, min(100.0, score)),
                tag="momentum_mode",
                reason=f"Expansion candidate with bullish structure and {dynamics.score_dynamics_state} dynamics. {momentum_note}.",
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
        symbols = [sym.strip().upper() for sym in req.symbol_overrides if sym.strip()] if req.symbol_overrides else self._universe(req.market.value, req.universe_scope)
        strict_results: list[ScannerResult] = []
        relaxed_results: list[ScannerResult] = []
        processed = 0
        partial = False
        partial_note = None
        category_eligible_count = 0
        relaxed_eligible_count = 0
        custom_filtered_count = 0

        config = build_analysis_config(
            ticker="DUMMY",
            market=req.market,
            lookback_window=req.duration.value,
            strategy_mode="momentum_continuation" if req.category == ScannerCategory.MOMENTUM_MODE else "balanced",
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
                snapshot = state.snapshot
                volume_ratio_20 = float(snapshot.get("volume", {}).get("volume_ratio", 0.0))
                counts = self._level_test_counts(bundle.daily, snapshot)
                dynamics = self._compute_score_dynamics(
                    daily=bundle.daily,
                    weekly=bundle.weekly,
                    market_cap=bundle.metadata.market_cap,
                    config=per_symbol_config,
                    current_score=float(state.final_score),
                )
                scored = self._score_for_category(req.category, state.final_score, regime, location, setup, trigger, dynamics, snapshot, volume_ratio_20)
                eligibility = self._category_eligibility(
                    category=req.category,
                    regime=regime,
                    location=location,
                    setup=setup,
                    trigger=trigger,
                    dynamics=dynamics,
                    snapshot=snapshot,
                )

                if req.use_custom_rules and req.custom_rules:
                    matched = 0
                    for rule in req.custom_rules:
                        actual = self._field_value(rule.field, regime=regime, location=location, setup=setup, snapshot=snapshot)
                        if self._rule_matches(
                            actual=actual,
                            operator=rule.operator,
                            value_number=rule.value_number,
                            value_text=rule.value_text,
                            value_list=rule.value_list,
                        ):
                            matched += 1
                    if matched != len(req.custom_rules):
                        custom_filtered_count += 1
                        processed += 1
                        continue
                    scored = _Eval(
                        score=min(100.0, scored.score + min(10.0, 2.0 * matched)),
                        tag=f"{scored.tag}_custom",
                        reason=f"{scored.reason} Matched {matched}/{len(req.custom_rules)} custom rules.",
                    )

                range_low, range_high, from_low_pct, to_high_pct = self._range_metrics(
                    bundle.daily,
                    req.range_start,
                    req.range_end,
                )
                row = ScannerResult(
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
                    momentum_fit_score=round(scored.score if req.category == ScannerCategory.MOMENTUM_MODE else 0.0, 2),
                    momentum_continuation_candidate=bool(
                        req.category == ScannerCategory.MOMENTUM_MODE and state.entry_gate.final_entry_decision
                    ),
                    trend_state=setup.trend_state,
                    setup_status=setup.setup_status,
                    extension_state=location.extension_state,
                    price_vs_ema200_pct=regime.price_vs_ema200_pct,
                    ema200_slope_state=regime.ema200_slope_state,
                    ema_stack_alignment=regime.ema_stack_alignment,
                    support_distance_pct=location.support_distance_pct,
                    resistance_room_pct=location.resistance_room_pct,
                    volume_ratio_20=round(volume_ratio_20, 2),
                    resistance_test_count=counts.resistance_test_count,
                    ema200_test_count=counts.ema200_test_count,
                    repeated_test_count=counts.repeated_test_count,
                    distance_from_range_low_pct=from_low_pct,
                    distance_to_range_high_pct=to_high_pct,
                    range_low=range_low,
                    range_high=range_high,
                    tradingview_url=self._tradingview_url(req.market.value, bundle.normalized_ticker),
                    bars_since_reclaim=regime.bars_since_reclaim,
                    compression_state=self._compression_state(location.support_distance_pct, location.resistance_room_pct),
                )
                if eligibility.strict:
                    category_eligible_count += 1
                    strict_results.append(row)
                if eligibility.relaxed:
                    relaxed_eligible_count += 1
                    relaxed_results.append(row)
                processed += 1
            except Exception:
                processed += 1
                continue

        source = strict_results
        used_relaxed_fallback = False
        if len(source) == 0 and len(relaxed_results) > 0:
            source = [
                row.model_copy(
                    update={
                        "short_reason": f"{row.short_reason} Relaxed scanner fallback used (broad discovery mode).",
                    }
                )
                for row in relaxed_results
            ]
            used_relaxed_fallback = True

        ranked = sorted(
            source,
            key=lambda row: (
                row.scanner_score,
                row.current_score,
                row.score_delta_short,
                row.score_delta_medium,
                0 if row.priority == ScannerPriority.HIGH else 1 if row.priority == ScannerPriority.MEDIUM else 2,
            ),
            reverse=True,
        )
        ranked_count = len(ranked)
        final_rows = ranked[: req.max_results]

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
                category_eligible_count=category_eligible_count,
                relaxed_eligible_count=relaxed_eligible_count,
                custom_filtered_count=custom_filtered_count,
                ranked_count=ranked_count,
                final_returned_count=len(final_rows),
                used_relaxed_fallback=used_relaxed_fallback,
            ),
            results=final_rows,
        )
