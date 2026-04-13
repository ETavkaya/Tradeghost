from __future__ import annotations

from tradeghost.services.indicators.calculations import compute_indicator_snapshot


def test_indicator_snapshot_contains_expected_keys(market_data_service) -> None:
    bundle = market_data_service.get_market_data("TSLA", use_cache=False)
    snapshot = compute_indicator_snapshot(bundle.daily, bundle.weekly, bundle.metadata.market_cap)

    keys = {
        "rsi",
        "macd_line",
        "stoch_k",
        "obv_slope",
        "ad_line_slope",
        "ema_20",
        "sma_50",
        "adx",
        "atr",
        "bb_upper",
        "fibonacci",
        "range_pos_52w",
        "volume",
        "support_resistance",
    }
    assert keys.issubset(set(snapshot.keys()))
    assert 0 <= snapshot["range_pos_52w"] <= 1

