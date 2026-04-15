from __future__ import annotations

from tradeghost.shared.market import MarketCode, display_symbol, normalize_market, normalize_symbol


def test_normalize_market_defaults_to_us() -> None:
    assert normalize_market(None) == MarketCode.US
    assert normalize_market("unknown") == MarketCode.US


def test_us_symbol_unchanged() -> None:
    assert normalize_symbol("tsla", "us") == "TSLA"
    assert display_symbol("NVDA", "us") == "NVDA"


def test_bist_symbol_adds_suffix() -> None:
    assert normalize_symbol("THYAO", "bist") == "THYAO.IS"
    assert normalize_symbol("EREGL.IS", "bist") == "EREGL.IS"
    assert display_symbol("THYAO.IS", "bist") == "THYAO"
