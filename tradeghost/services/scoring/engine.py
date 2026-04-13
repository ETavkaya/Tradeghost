from __future__ import annotations

from typing import Any

from tradeghost.shared.config.settings import get_settings
from tradeghost.shared.models.schemas import CategoryScores
from tradeghost.shared.utils.math_utils import normalize_score


def score_analysis(interpreted: dict[str, Any]) -> tuple[CategoryScores, float]:
    settings = get_settings()
    raw = interpreted["category_raw"]

    category_scores = CategoryScores(
        momentum_score=round(normalize_score(raw["momentum_raw"]), 2),
        trend_score=round(normalize_score(raw["trend_raw"]), 2),
        volatility_score=round(normalize_score(raw["volatility_raw"]), 2),
        structure_score=round(normalize_score(raw["structure_raw"]), 2),
        context_score=round(normalize_score(raw["context_raw"]), 2),
    )

    final_score = round(
        (category_scores.momentum_score * settings.score_momentum_weight)
        + (category_scores.trend_score * settings.score_trend_weight)
        + (category_scores.volatility_score * settings.score_volatility_weight)
        + (category_scores.structure_score * settings.score_structure_weight)
        + (category_scores.context_score * settings.score_context_weight),
        2,
    )
    return category_scores, final_score

