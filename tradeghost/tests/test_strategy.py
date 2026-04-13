from __future__ import annotations

from tradeghost.services.strategy.planner import build_trade_plan


def test_trade_plan_shape() -> None:
    swing_candidate, plan = build_trade_plan(
        final_score=72.0,
        close=120.0,
        atr=3.0,
        support=115.0,
        resistance=128.0,
        trend_score=70.0,
        momentum_score=68.0,
    )
    assert isinstance(swing_candidate, bool)
    assert plan.bias in {"bullish", "bearish", "neutral"}
    assert len(plan.entry_zone) == 2
    assert plan.take_profit_1 > plan.stop_loss
    assert plan.risk_reward > 0

