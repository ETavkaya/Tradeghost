from __future__ import annotations

from tradeghost.services.data.market_data_service import MarketDataService
from tradeghost.services.indicators.calculations import compute_indicator_snapshot
from tradeghost.services.interpretation.rules import interpret_snapshot
from tradeghost.services.scoring.engine import score_analysis
from tradeghost.services.strategy.planner import build_trade_plan
from tradeghost.shared.models.schemas import AnalysisResponse, ScoreResponse, TradePlanResponse


class AnalysisEngine:
    def __init__(self, data_service: MarketDataService | None = None) -> None:
        self.data_service = data_service or MarketDataService()

    def analyze(self, ticker: str) -> AnalysisResponse:
        bundle = self.data_service.get_market_data(ticker)
        snapshot = compute_indicator_snapshot(
            daily=bundle.daily,
            weekly=bundle.weekly,
            market_cap=bundle.metadata.market_cap,
        )
        interpreted = interpret_snapshot(snapshot)
        category_scores, final_score = score_analysis(interpreted)
        swing_candidate, trade_plan = build_trade_plan(
            final_score=final_score,
            close=snapshot["close"],
            atr=snapshot["atr"],
            support=snapshot["support_resistance"]["support"],
            resistance=snapshot["support_resistance"]["resistance"],
            trend_score=category_scores.trend_score,
            momentum_score=category_scores.momentum_score,
        )
        return AnalysisResponse(
            ticker=bundle.ticker,
            as_of=bundle.daily.index[-1].date(),
            final_score=final_score,
            category_scores=category_scores,
            indicator_summary=snapshot,
            interpreted_signals=interpreted["signals"],
            swing_candidate=swing_candidate,
            trade_plan=trade_plan,
        )

    def score_only(self, ticker: str) -> ScoreResponse:
        analysis = self.analyze(ticker)
        return ScoreResponse(
            ticker=analysis.ticker,
            as_of=analysis.as_of,
            final_score=analysis.final_score,
            category_scores=analysis.category_scores,
            interpreted_signals=analysis.interpreted_signals,
        )

    def trade_plan_only(self, ticker: str) -> TradePlanResponse:
        analysis = self.analyze(ticker)
        return TradePlanResponse(
            ticker=analysis.ticker,
            as_of=analysis.as_of,
            final_score=analysis.final_score,
            swing_candidate=analysis.swing_candidate,
            trade_plan=analysis.trade_plan,
        )

