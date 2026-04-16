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


@dataclass
class _SimulationResult:
    trades: list[BacktestTrade]
    entries_considered: int
    entries_triggered: int
    skipped_due_to_threshold: int
    skipped_due_to_setup: int
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
    def _format_major_conditions(snapshot: dict[str, float], category_scores, swing_candidate: bool) -> list[str]:
        return [
            f"Swing candidate: {'yes' if swing_candidate else 'no'}",
            f"Trend score: {category_scores.trend_score:.2f}",
            f"Momentum score: {category_scores.momentum_score:.2f}",
            f"Price {'above' if snapshot['close'] > snapshot['ema_200'] else 'below'} EMA200",
            (
                "EMA stack bullish"
                if snapshot["ema_20"] > snapshot["ema_50"] > snapshot["ema_100"] > snapshot["ema_200"]
                else "EMA stack mixed"
            ),
        ]

    def _simulate(
        self,
        daily: pd.DataFrame,
        weekly: pd.DataFrame,
        market_cap: float | None,
        min_score_to_enter: float,
        max_hold_days: int,
        window: str,
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
                swing_candidate, plan = build_trade_plan(
                    final_score=final_score,
                    close=snapshot["close"],
                    atr=max(snapshot["atr"], 0.01),
                    support=snapshot["support_resistance"]["support"],
                    resistance=snapshot["support_resistance"]["resistance"],
                    trend_score=category_scores.trend_score,
                    momentum_score=category_scores.momentum_score,
                )

                if not swing_candidate:
                    skipped_due_to_setup += 1
                    if len(skipped_signals_sample) < 25:
                        skipped_signals_sample.append(
                            SkippedEntrySignal(
                                date=current_date.date(),
                                final_score=round(final_score, 2),
                                threshold_used=round(min_score_to_enter, 2),
                                reason="setup_not_valid",
                                swing_candidate=False,
                            )
                        )
                    continue

                if final_score < min_score_to_enter:
                    skipped_due_to_threshold += 1
                    if len(skipped_signals_sample) < 25:
                        skipped_signals_sample.append(
                            SkippedEntrySignal(
                                date=current_date.date(),
                                final_score=round(final_score, 2),
                                threshold_used=round(min_score_to_enter, 2),
                                reason="below_threshold",
                                swing_candidate=True,
                            )
                        )
                    continue

                entry_price = float(current_row["close"])
                major_conditions = self._format_major_conditions(snapshot, category_scores, swing_candidate)
                entry_reason = (
                    f"Score {final_score:.2f} met threshold {min_score_to_enter:.2f} with valid swing setup; "
                    f"trend {category_scores.trend_score:.2f}, momentum {category_scores.momentum_score:.2f}."
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
                )
            )

        return _SimulationResult(
            trades=trades,
            entries_considered=entries_considered,
            entries_triggered=entries_triggered,
            skipped_due_to_threshold=skipped_due_to_threshold,
            skipped_due_to_setup=skipped_due_to_setup,
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
            f"Entry: {trade.entry_date} @ ${trade.entry_price:.2f}<br>"
            f"Exit: {trade.exit_date} @ ${trade.exit_price:.2f}<br>"
            f"Return: {trade.return_pct:.2f}%<br>"
            f"Score: {score_text}<br>"
            f"Threshold: {threshold_text}<br>"
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
    ) -> BacktestSummary:
        normalized_window = normalize_window(window)
        period = WINDOW_TO_PERIOD[normalized_window]
        bundle = self.analysis_engine.data_service.get_market_data(ticker, market=market, period=period)

        min_score_to_enter = float(score_threshold) if score_threshold is not None else float(self.settings.backtest_min_score_to_enter)
        sim = self._simulate(
            daily=bundle.daily,
            weekly=bundle.weekly,
            market_cap=bundle.metadata.market_cap,
            min_score_to_enter=min_score_to_enter,
            max_hold_days=self.settings.backtest_max_hold_days,
            window=normalized_window,
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
            sample_trades=sim.trades[:20],
        )

    def run_from_analysis(self, context: BacktestFromAnalysisRequest) -> BacktestFromAnalysisResponse:
        window = normalize_window(context.window)
        period = WINDOW_TO_PERIOD[window]
        bundle = self.analysis_engine.data_service.get_market_data(context.ticker, market=context.market, period=period)

        min_score_to_enter = (
            float(context.backtest_score_threshold)
            if context.backtest_score_threshold is not None
            else float(self.settings.backtest_min_score_to_enter)
        )
        sim = self._simulate(
            daily=bundle.daily,
            weekly=bundle.weekly,
            market_cap=bundle.metadata.market_cap,
            min_score_to_enter=min_score_to_enter,
            max_hold_days=self.settings.backtest_max_hold_days,
            window=window,
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
            warmup_bars_used=sim.warmup_bars_used,
            visible_start=visible_start,
            visible_end=visible_end,
            entries_considered=sim.entries_considered,
            entries_triggered=sim.entries_triggered,
            skipped_due_to_threshold=sim.skipped_due_to_threshold,
            skipped_due_to_setup=sim.skipped_due_to_setup,
            trades_table=sim.trades,
            skipped_signals_sample=sim.skipped_signals_sample,
            chart=chart,
            markers=markers,
        )
