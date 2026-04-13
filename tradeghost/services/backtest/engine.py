from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from tradeghost.services.analysis_engine import AnalysisEngine
from tradeghost.services.indicators.calculations import compute_indicator_snapshot
from tradeghost.services.interpretation.rules import interpret_snapshot
from tradeghost.services.scoring.engine import score_analysis
from tradeghost.services.strategy.planner import build_trade_plan
from tradeghost.shared.config.settings import get_settings
from tradeghost.shared.models.schemas import BacktestSummary, BacktestTrade


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

    def run(self, ticker: str) -> BacktestSummary:
        bundle = self.analysis_engine.data_service.get_market_data(ticker)
        daily = bundle.daily.copy()
        weekly = bundle.weekly.copy()

        trades: list[BacktestTrade] = []
        position: _Position | None = None
        equity = 1.0
        equity_curve: list[float] = [equity]

        warmup = self.settings.backtest_warmup_bars
        for i in range(warmup, len(daily)):
            slice_daily = daily.iloc[: i + 1]
            current_row = slice_daily.iloc[-1]
            current_date = slice_daily.index[-1]
            current_weekly = weekly[weekly.index <= current_date]
            if len(current_weekly) < 50:
                continue

            if position is None:
                snapshot = compute_indicator_snapshot(slice_daily, current_weekly, bundle.metadata.market_cap)
                interpreted = interpret_snapshot(snapshot)
                category_scores, final_score = score_analysis(interpreted)
                swing_candidate, plan = build_trade_plan(
                    final_score=final_score,
                    close=snapshot["close"],
                    atr=snapshot["atr"],
                    support=snapshot["support_resistance"]["support"],
                    resistance=snapshot["support_resistance"]["resistance"],
                    trend_score=category_scores.trend_score,
                    momentum_score=category_scores.momentum_score,
                )
                if swing_candidate and final_score >= self.settings.backtest_min_score_to_enter:
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
                elif hold_days >= self.settings.backtest_max_hold_days:
                    exit_price = close
                    exit_reason = "timeout"

                if exit_price is not None:
                    ret = (exit_price - position.entry_price) / position.entry_price
                    equity *= 1 + ret
                    equity_curve.append(equity)
                    trades.append(
                        BacktestTrade(
                            entry_date=position.entry_date.date(),
                            exit_date=current_date.date(),
                            entry_price=round(position.entry_price, 2),
                            exit_price=round(exit_price, 2),
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
            equity *= 1 + ret
            equity_curve.append(equity)
            trades.append(
                BacktestTrade(
                    entry_date=position.entry_date.date(),
                    exit_date=last_date.date(),
                    entry_price=round(position.entry_price, 2),
                    exit_price=round(last_close, 2),
                    return_pct=round(ret * 100, 2),
                    hold_days=len(daily) - 1 - position.entry_idx,
                    result="forced_close",
                )
            )

        returns = [t.return_pct / 100 for t in trades]
        wins = [r for r in returns if r > 0]
        losses = [r for r in returns if r <= 0]
        win_rate = (len(wins) / len(trades) * 100) if trades else 0.0
        average_return = (sum(returns) / len(returns) * 100) if trades else 0.0
        average_hold_days = sum(t.hold_days for t in trades) / len(trades) if trades else 0.0

        peak = -math.inf
        max_dd = 0.0
        for x in equity_curve:
            peak = max(peak, x)
            dd = (peak - x) / peak if peak else 0.0
            max_dd = max(max_dd, dd)

        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0
        expectancy = ((win_rate / 100) * avg_win) - ((1 - (win_rate / 100)) * avg_loss)

        return BacktestSummary(
            ticker=bundle.ticker,
            period_start=daily.index[0].date(),
            period_end=daily.index[-1].date(),
            trades=len(trades),
            win_rate=round(win_rate, 2),
            average_return=round(average_return, 2),
            max_drawdown=round(max_dd * 100, 2),
            average_hold_days=round(average_hold_days, 2),
            expectancy=round(expectancy * 100, 2),
            sample_trades=trades[:10],
        )

