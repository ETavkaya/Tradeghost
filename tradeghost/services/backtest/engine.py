from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

import pandas as pd

from tradeghost.services.analysis_engine import AnalysisEngine
from tradeghost.services.indicators.calculations import compute_indicator_snapshot, ema
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
    ChartCandle,
    ChartLinePoint,
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


@dataclass
class _Position:
    entry_idx: int
    entry_date: pd.Timestamp
    entry_price: float
    stop_loss: float
    take_profit: float


class BacktestEngine:
    def __init__(self, analysis_engine: AnalysisEngine | None = None) -> None:
        self.analysis_engine = analysis_engine or AnalysisEngine()
        self.settings = get_settings()

    @staticmethod
    def _normalize_window(window: str | None) -> str:
        raw = (window or "6m").strip().lower()
        return raw if raw in _WINDOW_TO_PERIOD else "6m"

    def _simulate(
        self,
        daily: pd.DataFrame,
        weekly: pd.DataFrame,
        market_cap: float | None,
        min_score_to_enter: float,
        max_hold_days: int,
    ) -> list[BacktestTrade]:
        trades: list[BacktestTrade] = []
        position: _Position | None = None
        warmup = min(self.settings.backtest_warmup_bars, max(20, len(daily) // 3))

        for i in range(warmup, len(daily)):
            slice_daily = daily.iloc[: i + 1]
            current_row = slice_daily.iloc[-1]
            current_date = slice_daily.index[-1]
            current_weekly = weekly[weekly.index <= current_date]
            if len(current_weekly) < 10:
                continue

            if position is None:
                snapshot = compute_indicator_snapshot(slice_daily, current_weekly, market_cap)
                interpreted = interpret_snapshot(snapshot)
                category_scores, final_score = score_analysis(interpreted)
                swing_candidate, plan = build_trade_plan(
                    final_score=final_score,
                    close=snapshot["close"],
                    atr=max(snapshot["atr"], 0.01),
                    support=snapshot["support_resistance"]["support"],
                    resistance=snapshot["support_resistance"]["resistance"],
                    trend_score=category_scores.trend_score,
                    momentum_score=category_scores.momentum_score,
                )
                if swing_candidate and final_score >= min_score_to_enter:
                    entry_price = float(current_row["close"])
                    position = _Position(
                        entry_idx=i,
                        entry_date=current_date,
                        entry_price=entry_price,
                        stop_loss=plan.stop_loss,
                        take_profit=plan.take_profit_1,
                    )
            else:
                low = float(current_row["low"])
                high = float(current_row["high"])
                close = float(current_row["close"])
                hold_days = i - position.entry_idx

                exit_price = None
                exit_reason = None
                if low <= position.stop_loss:
                    exit_price = position.stop_loss
                    exit_reason = "loss"
                elif high >= position.take_profit:
                    exit_price = position.take_profit
                    exit_reason = "win"
                elif hold_days >= max_hold_days:
                    exit_price = close
                    exit_reason = "timeout"

                if exit_price is not None:
                    ret = (exit_price - position.entry_price) / position.entry_price
                    trades.append(
                        BacktestTrade(
                            entry_date=position.entry_date.date(),
                            exit_date=current_date.date(),
                            entry_price=round(position.entry_price, 2),
                            exit_price=round(exit_price, 2),
                            stop_loss=round(position.stop_loss, 2),
                            take_profit=round(position.take_profit, 2),
                            return_pct=round(ret * 100, 2),
                            hold_days=hold_days,
                            result=exit_reason,
                        )
                    )
                    position = None

        if position is not None:
            last_date = daily.index[-1]
            last_close = float(daily.iloc[-1]["close"])
            ret = (last_close - position.entry_price) / position.entry_price
            trades.append(
                BacktestTrade(
                    entry_date=position.entry_date.date(),
                    exit_date=last_date.date(),
                    entry_price=round(position.entry_price, 2),
                    exit_price=round(last_close, 2),
                    stop_loss=round(position.stop_loss, 2),
                    take_profit=round(position.take_profit, 2),
                    return_pct=round(ret * 100, 2),
                    hold_days=len(daily) - 1 - position.entry_idx,
                    result="forced_close",
                )
            )

        return trades

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

    def _build_chart(self, daily: pd.DataFrame, window: str, trade_plan, trades: list[BacktestTrade]) -> tuple[AnalysisChart, list[BacktestMarker]]:
        bars = _WINDOW_TO_BARS[window]
        display = daily.tail(bars)
        dates_in_window = {idx.date() for idx in display.index}

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
        ema_20 = [ChartLinePoint(date=idx.date(), value=float(value)) for idx, value in ema(daily["close"], 20).tail(len(display)).items()]
        ema_50 = [ChartLinePoint(date=idx.date(), value=float(value)) for idx, value in ema(daily["close"], 50).tail(len(display)).items()]

        weekly = daily.resample("W-FRI").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
        snapshot = compute_indicator_snapshot(daily, weekly)

        markers: list[BacktestMarker] = []
        for trade in trades:
            if trade.entry_date in dates_in_window:
                markers.append(
                    BacktestMarker(
                        date=trade.entry_date,
                        price=trade.entry_price,
                        marker_type="entry",
                        label="Entry",
                    )
                )
            if trade.exit_date in dates_in_window:
                markers.append(
                    BacktestMarker(
                        date=trade.exit_date,
                        price=trade.exit_price,
                        marker_type="exit",
                        label=f"Exit ({trade.result})",
                    )
                )

        if not math.isnan(trade_plan.stop_loss):
            markers.append(
                BacktestMarker(
                    date=display.index[-1].date(),
                    price=trade_plan.stop_loss,
                    marker_type="stop",
                    label="Reference Stop",
                )
            )
            markers.append(
                BacktestMarker(
                    date=display.index[-1].date(),
                    price=trade_plan.take_profit_1,
                    marker_type="take_profit",
                    label="Reference TP1",
                )
            )

        chart = AnalysisChart(
            candles=candles,
            ema_20=ema_20,
            ema_50=ema_50,
            current_price=float(daily.iloc[-1]["close"]),
            support_levels=[float(snapshot["support_resistance"]["support"])],
            resistance_levels=[float(snapshot["support_resistance"]["resistance"])],
            fibonacci_levels={str(k): float(v) for k, v in snapshot["fibonacci"].items()},
            trade_plan_overlay=trade_plan,
        )
        return chart, markers

    def run(self, ticker: str, window: str | None = None, market: str | None = None) -> BacktestSummary:
        normalized_window = self._normalize_window(window)
        period = _WINDOW_TO_PERIOD[normalized_window]
        bundle = self.analysis_engine.data_service.get_market_data(ticker, market=market, period=period)

        trades = self._simulate(
            daily=bundle.daily,
            weekly=bundle.weekly,
            market_cap=bundle.metadata.market_cap,
            min_score_to_enter=self.settings.backtest_min_score_to_enter,
            max_hold_days=self.settings.backtest_max_hold_days,
        )
        metrics = self._compute_metrics(trades)

        return BacktestSummary(
            ticker=bundle.ticker,
            period_start=bundle.daily.index[0].date(),
            period_end=bundle.daily.index[-1].date(),
            trades=int(metrics["trades"]),
            win_rate=metrics["win_rate"],
            average_return=metrics["average_return"],
            max_drawdown=metrics["max_drawdown"],
            average_hold_days=metrics["average_hold_days"],
            expectancy=metrics["expectancy"],
            sample_trades=trades[:20],
        )

    def run_from_analysis(self, context: BacktestFromAnalysisRequest) -> BacktestFromAnalysisResponse:
        window = self._normalize_window(context.window)
        period = _WINDOW_TO_PERIOD[window]
        bundle = self.analysis_engine.data_service.get_market_data(context.ticker, market=context.market, period=period)

        min_score_to_enter = max(self.settings.backtest_min_score_to_enter, context.quantedge_final_score * 0.85)
        if not context.swing_candidate:
            min_score_to_enter += 2.0

        trades = self._simulate(
            daily=bundle.daily,
            weekly=bundle.weekly,
            market_cap=bundle.metadata.market_cap,
            min_score_to_enter=min_score_to_enter,
            max_hold_days=self.settings.backtest_max_hold_days,
        )
        metrics = self._compute_metrics(trades)
        chart, markers = self._build_chart(bundle.daily, window, context.trade_plan, trades)

        return BacktestFromAnalysisResponse(
            ticker=bundle.ticker,
            normalized_ticker=bundle.normalized_ticker,
            market=bundle.market,
            window=window,
            generated_from_analysis=True,
            analysis_as_of=context.analysis_as_of or date.today(),
            period_start=bundle.daily.index[0].date(),
            period_end=bundle.daily.index[-1].date(),
            trades=int(metrics["trades"]),
            win_rate=metrics["win_rate"],
            average_return=metrics["average_return"],
            max_drawdown=metrics["max_drawdown"],
            average_hold_days=metrics["average_hold_days"],
            expectancy=metrics["expectancy"],
            trades_table=trades,
            chart=chart,
            markers=markers,
        )
