from __future__ import annotations

from tradeghost.services.analysis_engine import AnalysisEngine
from tradeghost.services.backtest.engine import BacktestEngine


def test_analysis_output(market_data_service) -> None:
    engine = AnalysisEngine(data_service=market_data_service)
    result = engine.analyze("MSFT")
    assert result.ticker == "MSFT"
    assert 0 <= result.final_score <= 100
    assert isinstance(result.swing_candidate, bool)
    assert "rsi_state" in result.interpreted_signals


def test_backtest_flow(market_data_service) -> None:
    analysis_engine = AnalysisEngine(data_service=market_data_service)
    backtest_engine = BacktestEngine(analysis_engine=analysis_engine)
    summary = backtest_engine.run("MSFT")
    assert summary.ticker == "MSFT"
    assert summary.trades >= 0
    assert 0 <= summary.win_rate <= 100

