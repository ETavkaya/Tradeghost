from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

import pandas as pd

from tradeghost.services.analysis_engine import AnalysisEngine
from tradeghost.services.charts.payloads import WINDOW_TO_BARS, WINDOW_TO_PERIOD, build_analysis_chart, normalize_window, visible_window_slice
from tradeghost.services.indicators.calculations import compute_indicator_snapshot
from tradeghost.services.interpretation.rules import interpret_snapshot
from tradeghost.services.scoring.engine import score_analysis
from tradeghost.services.strategy.filters import (
    evaluate_entry_gate,
    evaluate_location,
    evaluate_regime,
    evaluate_trigger,
    get_strategy_mode_config,
    normalize_strategy_mode,
)
from tradeghost.services.strategy.planner import build_trade_plan
from tradeghost.shared.config.settings import get_settings
from tradeghost.shared.models.schemas import (
    AnalysisChart,
    BacktestFromAnalysisRequest,
    BacktestFromAnalysisResponse,
    BacktestMarker,
    BacktestSummary,
    BacktestTrade,
    SkippedEntrySignal,
    StrategyMode,
)


@dataclass
class _Position:
    trade_id: int
    entry_idx: int
    entry_date: pd.Timestamp
    entry_price: float
    stop_loss: float
    take_profit: float
    entry_reason: str
    threshold_used: float
    score_at_entry: float
    major_conditions_met: list[str]
    strategy_mode_used: StrategyMode
    regime_valid: bool
    location_valid: bool
    trigger_valid: bool
    trigger_type: str
    regime_reason: str
    location_reason: str
    trigger_reason: str
    support_distance_pct: float
    resistance_distance_pct: float
    overextended_flag: bool
    entry_quality_score: float


@dataclass
class _SimulationResult:
    trades: list[BacktestTrade]
    entries_considered: int
    entries_triggered: int
    skipped_due_to_threshold: int
    skipped_due_to_setup: int
    skipped_regime: int
    skipped_location: int
    skipped_trigger: int
    skipped_overextended: int
    skipped_resistance_room: int
    skipped_signals_sample: list[SkippedEntrySignal]
    warmup_bars_used: int


class BacktestEngine:
    def __init__(self, analysis_engine: AnalysisEngine | None = None) -> None:
        self.analysis_engine = analysis_engine or AnalysisEngine()
        self.settings = get_settings()

    @staticmethod
    def _exit_marker_type(result: str) -> str:
        mapping = {
            "stop_exit": "exit_stop",
            "target_exit": "exit_target",
            "score_exit": "exit_score",
            "timeout_exit": "exit_timeout",
            "forced_close": "exit_forced",
        }
        return mapping.get(result, "exit")

    @staticmethod
    def _format_major_conditions(final_score: float, entry_gate, regime, location, trigger) -> list[str]:
        return [
            f"Final score: {final_score:.2f}",
            f"Threshold pass: {'yes' if entry_gate.score_threshold_passed else 'no'}",
            f"Regime valid: {'yes' if regime.regime_valid else 'no'} ({regime.regime_mode_used})",
            f"Location valid: {'yes' if location.location_valid else 'no'}",
            f"Trigger valid: {'yes' if trigger.trigger_valid else 'no'} ({trigger.trigger_type})",
            f"Support distance: {location.support_distance_pct:.2f}%",
            f"Resistance room: {location.resistance_distance_pct:.2f}%",
            f"Overextended: {'yes' if location.overextended_flag else 'no'}",
        ]

    def _simulate(
        self,
        daily: pd.DataFrame,
        weekly: pd.DataFrame,
        market_cap: float | None,
        min_score_to_enter: float,
        max_hold_days: int,
        window: str,
        strategy_mode: StrategyMode,
    ) -> _SimulationResult:
        trades: list[BacktestTrade] = []
        position: _Position | None = None

        bars = WINDOW_TO_BARS[window]
        visible_start_idx = max(0, len(daily) - bars)
        warmup = min(self.settings.backtest_warmup_bars, max(20, len(daily) // 3))
        sim_start_idx = max(warmup, visible_start_idx)

        entries_considered = 0
        entries_triggered = 0
        skipped_due_to_threshold = 0
        skipped_due_to_setup = 0
        skipped_regime = 0
        skipped_location = 0
        skipped_trigger = 0
        skipped_overextended = 0
        skipped_resistance_room = 0
        skipped_signals_sample: list[SkippedEntrySignal] = []
        next_trade_id = 1

        for i in range(sim_start_idx, len(daily)):
            slice_daily = daily.iloc[: i + 1]
            current_row = slice_daily.iloc[-1]
            current_date = slice_daily.index[-1]
            current_weekly = weekly[weekly.index <= current_date]
            if len(current_weekly) < 10:
                continue

            snapshot = compute_indicator_snapshot(slice_daily, current_weekly, market_cap)
            interpreted = interpret_snapshot(snapshot)
            category_scores, final_score = score_analysis(interpreted)

            if position is None:
                entries_considered += 1
                _, plan = build_trade_plan(
                    final_score=final_score,
                    close=snapshot["close"],
                    atr=max(snapshot["atr"], 0.01),
                    support=snapshot["support_resistance"]["support"],
                    resistance=snapshot["support_resistance"]["resistance"],
                    trend_score=category_scores.trend_score,
                    momentum_score=category_scores.momentum_score,
                )

                regime = evaluate_regime(snapshot, strategy_mode)
                location = evaluate_location(snapshot, strategy_mode)
                trigger = evaluate_trigger(snapshot, strategy_mode, location)
                entry_gate = evaluate_entry_gate(
                    final_score=final_score,
                    score_threshold_used=min_score_to_enter,
                    regime=regime,
                    location=location,
                    trigger=trigger,
                )

                if not entry_gate.final_entry_decision:
                    reason = entry_gate.skip_reason or "setup_filter"
                    if reason == "score_threshold":
                        skipped_due_to_threshold += 1
                    elif reason == "regime_filter":
                        skipped_regime += 1
                    elif reason in {"location_filter", "overextended_filter", "resistance_room_filter"}:
                        skipped_location += 1
                        if reason == "overextended_filter":
                            skipped_overextended += 1
                        if reason == "resistance_room_filter":
                            skipped_resistance_room += 1
                    elif reason == "trigger_filter":
                        skipped_trigger += 1
                    else:
                        skipped_due_to_setup += 1

                    if len(skipped_signals_sample) < 30:
                        skipped_signals_sample.append(
                            SkippedEntrySignal(
                                date=current_date.date(),
                                final_score=round(final_score, 2),
                                threshold_used=round(min_score_to_enter, 2),
                                reason=reason,
                                swing_candidate=False,
                                strategy_mode_used=strategy_mode,
                                regime_valid=regime.regime_valid,
                                location_valid=location.location_valid,
                                trigger_valid=trigger.trigger_valid,
                            )
                        )
                    continue

                entry_price = float(current_row["close"])
                major_conditions = self._format_major_conditions(final_score, entry_gate, regime, location, trigger)
                entry_reason = (
                    f"Entry gate passed ({strategy_mode.value}). Score {final_score:.2f}/{min_score_to_enter:.2f}; "
                    f"regime={regime.ema_stack_quality}, location={location.location_score:.1f}, trigger={trigger.trigger_type}."
                )
                position = _Position(
                    trade_id=next_trade_id,
                    entry_idx=i,
                    entry_date=current_date,
                    entry_price=entry_price,
                    stop_loss=plan.stop_loss,
                    take_profit=plan.take_profit_1,
                    entry_reason=entry_reason,
                    threshold_used=min_score_to_enter,
                    score_at_entry=final_score,
                    major_conditions_met=major_conditions,
                    strategy_mode_used=strategy_mode,
                    regime_valid=regime.regime_valid,
                    location_valid=location.location_valid,
                    trigger_valid=trigger.trigger_valid,
                    trigger_type=trigger.trigger_type,
                    regime_reason=regime.regime_reason,
                    location_reason=location.location_reason,
                    trigger_reason=trigger.trigger_reason,
                    support_distance_pct=location.support_distance_pct,
                    resistance_distance_pct=location.resistance_distance_pct,
                    overextended_flag=location.overextended_flag,
                    entry_quality_score=entry_gate.entry_quality_score,
                )
                entries_triggered += 1
                next_trade_id += 1
                continue

            low = float(current_row["low"])
            high = float(current_row["high"])
            close = float(current_row["close"])
            hold_days = i - position.entry_idx

            exit_price: float | None = None
            result = ""
            exit_reason = ""

            if low <= position.stop_loss:
                exit_price = position.stop_loss
                result = "stop_exit"
                exit_reason = "Price hit stop-loss level."
            elif high >= position.take_profit:
                exit_price = position.take_profit
                result = "target_exit"
                exit_reason = "Price reached take-profit target."
            elif final_score < (position.threshold_used * 0.7):
                exit_price = close
                result = "score_exit"
                exit_reason = (
                    f"Score deterioration: {final_score:.2f} dropped below maintenance level {(position.threshold_used * 0.7):.2f}."
                )
            elif hold_days >= max_hold_days:
                exit_price = close
                result = "timeout_exit"
                exit_reason = f"Max hold of {max_hold_days} bars reached."

            if exit_price is None:
                continue

            ret = (exit_price - position.entry_price) / position.entry_price
            trades.append(
                BacktestTrade(
                    trade_id=position.trade_id,
                    entry_date=position.entry_date.date(),
                    exit_date=current_date.date(),
                    entry_price=round(position.entry_price, 2),
                    exit_price=round(exit_price, 2),
                    stop_loss=round(position.stop_loss, 2),
                    take_profit=round(position.take_profit, 2),
                    return_pct=round(ret * 100, 2),
                    hold_days=hold_days,
                    result=result,
                    entry_reason=position.entry_reason,
                    exit_reason=exit_reason,
                    threshold_used=round(position.threshold_used, 2),
                    score_at_entry=round(position.score_at_entry, 2),
                    score_at_exit=round(final_score, 2),
                    major_conditions_met=position.major_conditions_met,
                    score_exit_threshold=round(position.threshold_used * 0.7, 2),
                    strategy_mode_used=position.strategy_mode_used,
                    regime_valid=position.regime_valid,
                    location_valid=position.location_valid,
                    trigger_valid=position.trigger_valid,
                    trigger_type=position.trigger_type,
                    regime_reason=position.regime_reason,
                    location_reason=position.location_reason,
                    trigger_reason=position.trigger_reason,
                    support_distance_pct=position.support_distance_pct,
                    resistance_distance_pct=position.resistance_distance_pct,
                    overextended_flag=position.overextended_flag,
                    entry_quality_score=position.entry_quality_score,
                )
            )
            position = None

        if position is not None:
            last_date = daily.index[-1]
            last_close = float(daily.iloc[-1]["close"])
            ret = (last_close - position.entry_price) / position.entry_price
            trades.append(
                BacktestTrade(
                    trade_id=position.trade_id,
                    entry_date=position.entry_date.date(),
                    exit_date=last_date.date(),
                    entry_price=round(position.entry_price, 2),
                    exit_price=round(last_close, 2),
                    stop_loss=round(position.stop_loss, 2),
                    take_profit=round(position.take_profit, 2),
                    return_pct=round(ret * 100, 2),
                    hold_days=len(daily) - 1 - position.entry_idx,
                    result="forced_close",
                    entry_reason=position.entry_reason,
                    exit_reason="Position closed on final available bar.",
                    threshold_used=round(position.threshold_used, 2),
                    score_at_entry=round(position.score_at_entry, 2),
                    major_conditions_met=position.major_conditions_met,
                    score_exit_threshold=round(position.threshold_used * 0.7, 2),
                    strategy_mode_used=position.strategy_mode_used,
                    regime_valid=position.regime_valid,
                    location_valid=position.location_valid,
                    trigger_valid=position.trigger_valid,
                    trigger_type=position.trigger_type,
                    regime_reason=position.regime_reason,
                    location_reason=position.location_reason,
                    trigger_reason=position.trigger_reason,
                    support_distance_pct=position.support_distance_pct,
                    resistance_distance_pct=position.resistance_distance_pct,
                    overextended_flag=position.overextended_flag,
                    entry_quality_score=position.entry_quality_score,
                )
            )

        return _SimulationResult(
            trades=trades,
            entries_considered=entries_considered,
            entries_triggered=entries_triggered,
            skipped_due_to_threshold=skipped_due_to_threshold,
            skipped_due_to_setup=skipped_due_to_setup,
            skipped_regime=skipped_regime,
            skipped_location=skipped_location,
            skipped_trigger=skipped_trigger,
            skipped_overextended=skipped_overextended,
            skipped_resistance_room=skipped_resistance_room,
            skipped_signals_sample=skipped_signals_sample,
            warmup_bars_used=warmup,
        )

    @staticmethod
    def _compute_metrics(trades: list[BacktestTrade]) -> dict[str, float]:
        returns = [t.return_pct / 100 for t in trades]
        wins = [r for r in returns if r > 0]
        losses = [r for r in returns if r <= 0]
        win_rate = (len(wins) / len(trades) * 100) if trades else 0.0
        average_return = (sum(returns) / len(returns) * 100) if trades else 0.0
        average_hold_days = sum(t.hold_days for t in trades) / len(trades) if trades else 0.0

        equity = 1.0
        peak = 1.0
        max_dd = 0.0
        for ret in returns:
            equity *= 1 + ret
            peak = max(peak, equity)
            dd = (peak - equity) / peak if peak else 0.0
            max_dd = max(max_dd, dd)

        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
        expectancy = ((win_rate / 100) * avg_win) - ((1 - (win_rate / 100)) * avg_loss)

        return {
            "trades": len(trades),
            "win_rate": round(win_rate, 2),
            "average_return": round(average_return, 2),
            "max_drawdown": round(max_dd * 100, 2),
            "average_hold_days": round(average_hold_days, 2),
            "expectancy": round(expectancy * 100, 2),
        }

    @staticmethod
    def _trade_hover_text(trade: BacktestTrade, side: str) -> str:
        reason = trade.entry_reason if side == "entry" else trade.exit_reason
        score = trade.score_at_entry if side == "entry" else trade.score_at_exit
        score_text = f"{score:.2f}" if score is not None else "n/a"
        threshold_text = f"{trade.threshold_used:.2f}" if trade.threshold_used is not None else "n/a"
        return (
            f"Trade #{trade.trade_id}<br>"
            f"Mode: {trade.strategy_mode_used.value}<br>"
            f"Entry: {trade.entry_date} @ ${trade.entry_price:.2f}<br>"
            f"Exit: {trade.exit_date} @ ${trade.exit_price:.2f}<br>"
            f"Return: {trade.return_pct:.2f}%<br>"
            f"Score: {score_text}<br>"
            f"Threshold: {threshold_text}<br>"
            f"Trigger: {trade.trigger_type or 'n/a'}<br>"
            f"Support dist: {trade.support_distance_pct if trade.support_distance_pct is not None else 'n/a'}%<br>"
            f"Resistance room: {trade.resistance_distance_pct if trade.resistance_distance_pct is not None else 'n/a'}%<br>"
            f"Reason: {reason or 'n/a'}"
        )

    def _build_chart(self, daily: pd.DataFrame, window: str, trade_plan, trades: list[BacktestTrade]) -> tuple[AnalysisChart, list[BacktestMarker], date, date]:
        display = visible_window_slice(daily, window)
        dates_in_window = {idx.date() for idx in display.index}

        weekly = daily.resample("W-FRI").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
        snapshot = compute_indicator_snapshot(daily, weekly)
        chart = build_analysis_chart(daily=daily, snapshot=snapshot, trade_plan=trade_plan, window=window)

        markers: list[BacktestMarker] = []
        for trade in trades:
            if trade.entry_date in dates_in_window:
                markers.append(
                    BacktestMarker(
                        date=trade.entry_date,
                        price=trade.entry_price,
                        marker_type="entry",
                        label=f"Entry #{trade.trade_id}",
                        hover_text=self._trade_hover_text(trade, "entry"),
                        trade_id=trade.trade_id,
                    )
                )

            if trade.exit_date in dates_in_window:
                markers.append(
                    BacktestMarker(
                        date=trade.exit_date,
                        price=trade.exit_price,
                        marker_type=self._exit_marker_type(trade.result),
                        label=f"Exit #{trade.trade_id}",
                        hover_text=self._trade_hover_text(trade, "exit"),
                        trade_id=trade.trade_id,
                    )
                )

        if not math.isnan(trade_plan.stop_loss):
            last_visible_date = display.index[-1].date()
            markers.append(
                BacktestMarker(
                    date=last_visible_date,
                    price=trade_plan.stop_loss,
                    marker_type="reference_stop",
                    label="Reference Stop",
                    hover_text=f"Reference stop from active trade plan: ${trade_plan.stop_loss:.2f}",
                )
            )
            markers.append(
                BacktestMarker(
                    date=last_visible_date,
                    price=trade_plan.take_profit_1,
                    marker_type="reference_target",
                    label="Reference TP1",
                    hover_text=f"Reference target from active trade plan: ${trade_plan.take_profit_1:.2f}",
                )
            )

        return chart, markers, display.index[0].date(), display.index[-1].date()

    def run(
        self,
        ticker: str,
        window: str | None = None,
        market: str | None = None,
        score_threshold: float | None = None,
        strategy_mode: StrategyMode | str | None = None,
    ) -> BacktestSummary:
        normalized_window = normalize_window(window)
        normalized_mode = normalize_strategy_mode(strategy_mode)
        mode_config = get_strategy_mode_config(normalized_mode)
        period = WINDOW_TO_PERIOD[normalized_window]
        bundle = self.analysis_engine.data_service.get_market_data(ticker, market=market, period=period)

        min_score_to_enter = float(score_threshold) if score_threshold is not None else float(mode_config.score_threshold)
        sim = self._simulate(
            daily=bundle.daily,
            weekly=bundle.weekly,
            market_cap=bundle.metadata.market_cap,
            min_score_to_enter=min_score_to_enter,
            max_hold_days=self.settings.backtest_max_hold_days,
            window=normalized_window,
            strategy_mode=normalized_mode,
        )
        metrics = self._compute_metrics(sim.trades)

        display = visible_window_slice(bundle.daily, normalized_window)
        return BacktestSummary(
            ticker=bundle.ticker,
            period_start=display.index[0].date(),
            period_end=display.index[-1].date(),
            trades=int(metrics["trades"]),
            win_rate=metrics["win_rate"],
            average_return=metrics["average_return"],
            max_drawdown=metrics["max_drawdown"],
            average_hold_days=metrics["average_hold_days"],
            expectancy=metrics["expectancy"],
            score_threshold_used=round(min_score_to_enter, 2),
            strategy_mode_used=normalized_mode,
            sample_trades=sim.trades[:20],
        )

    def run_from_analysis(self, context: BacktestFromAnalysisRequest) -> BacktestFromAnalysisResponse:
        window = normalize_window(context.window)
        strategy_mode = normalize_strategy_mode(context.strategy_mode)
        mode_config = get_strategy_mode_config(strategy_mode)
        period = WINDOW_TO_PERIOD[window]
        bundle = self.analysis_engine.data_service.get_market_data(context.ticker, market=context.market, period=period)

        min_score_to_enter = float(context.backtest_score_threshold) if context.backtest_score_threshold is not None else float(mode_config.score_threshold)
        sim = self._simulate(
            daily=bundle.daily,
            weekly=bundle.weekly,
            market_cap=bundle.metadata.market_cap,
            min_score_to_enter=min_score_to_enter,
            max_hold_days=self.settings.backtest_max_hold_days,
            window=window,
            strategy_mode=strategy_mode,
        )
        metrics = self._compute_metrics(sim.trades)
        chart, markers, visible_start, visible_end = self._build_chart(bundle.daily, window, context.trade_plan, sim.trades)

        return BacktestFromAnalysisResponse(
            ticker=bundle.ticker,
            normalized_ticker=bundle.normalized_ticker,
            market=bundle.market,
            window=window,
            generated_from_analysis=True,
            analysis_as_of=context.analysis_as_of or date.today(),
            period_start=visible_start,
            period_end=visible_end,
            trades=int(metrics["trades"]),
            win_rate=metrics["win_rate"],
            average_return=metrics["average_return"],
            max_drawdown=metrics["max_drawdown"],
            average_hold_days=metrics["average_hold_days"],
            expectancy=metrics["expectancy"],
            score_threshold_used=round(min_score_to_enter, 2),
            strategy_mode_used=strategy_mode,
            warmup_bars_used=sim.warmup_bars_used,
            visible_start=visible_start,
            visible_end=visible_end,
            entries_considered=sim.entries_considered,
            entries_triggered=sim.entries_triggered,
            skipped_due_to_threshold=sim.skipped_due_to_threshold,
            skipped_due_to_setup=sim.skipped_due_to_setup,
            skipped_regime=sim.skipped_regime,
            skipped_location=sim.skipped_location,
            skipped_trigger=sim.skipped_trigger,
            skipped_overextended=sim.skipped_overextended,
            skipped_resistance_room=sim.skipped_resistance_room,
            trades_table=sim.trades,
            skipped_signals_sample=sim.skipped_signals_sample,
            chart=chart,
            markers=markers,
        )
