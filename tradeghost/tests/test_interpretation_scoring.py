from __future__ import annotations

from tradeghost.services.indicators.calculations import compute_indicator_snapshot
from tradeghost.services.interpretation.rules import interpret_snapshot
from tradeghost.services.scoring.engine import score_analysis


def test_interpretation_and_scoring_ranges(market_data_service) -> None:
    bundle = market_data_service.get_market_data("AAPL", use_cache=False)
    snapshot = compute_indicator_snapshot(bundle.daily, bundle.weekly, bundle.metadata.market_cap)
    interpreted = interpret_snapshot(snapshot)
    category_scores, final_score = score_analysis(interpreted)

    assert "signals" in interpreted
    assert "category_raw" in interpreted
    assert 0 <= category_scores.momentum_score <= 100
    assert 0 <= category_scores.trend_score <= 100
    assert 0 <= category_scores.volatility_score <= 100
    assert 0 <= category_scores.structure_score <= 100
    assert 0 <= category_scores.context_score <= 100
    assert 0 <= final_score <= 100

