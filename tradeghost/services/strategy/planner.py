from __future__ import annotations

from tradeghost.shared.config.settings import get_settings
from tradeghost.shared.models.schemas import TradePlan


def build_trade_plan(
    final_score: float,
    close: float,
    atr: float,
    support: float,
    resistance: float,
    trend_score: float,
    momentum_score: float,
) -> tuple[bool, TradePlan]:
    settings = get_settings()

    if trend_score >= 55 and momentum_score >= 55:
        bias = "bullish"
    elif trend_score <= 45 and momentum_score <= 45:
        bias = "bearish"
    else:
        bias = "neutral"

    swing_candidate = bool(final_score >= settings.swing_candidate_threshold and bias == "bullish")

    entry_low = round(max(support, close - 0.5 * atr), 2)
    entry_high = round(min(resistance, close + 0.5 * atr), 2)
    entry_mid = (entry_low + entry_high) / 2

    stop_loss = round(entry_low - settings.strategy_atr_stop_multiple * atr, 2)
    risk_per_share = max(entry_mid - stop_loss, 0.01)
    take_profit_1 = round(entry_mid + risk_per_share * settings.strategy_tp1_rr, 2)
    take_profit_2 = round(entry_mid + risk_per_share * settings.strategy_tp2_rr, 2)
    risk_reward = round((take_profit_1 - entry_mid) / risk_per_share, 2)

    invalidation_note = (
        "Invalidate if close breaks below stop loss or if trend score drops below 50."
        if bias == "bullish"
        else "No valid long swing setup. Wait for trend and momentum alignment."
    )

    plan = TradePlan(
        bias=bias,
        entry_zone=(entry_low, entry_high),
        stop_loss=stop_loss,
        take_profit_1=take_profit_1,
        take_profit_2=take_profit_2,
        risk_reward=risk_reward,
        invalidation_note=invalidation_note,
    )
    return swing_candidate, plan

