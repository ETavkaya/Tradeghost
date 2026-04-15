from __future__ import annotations

from enum import StrEnum


class MarketCode(StrEnum):
    US = "us"
    BIST = "bist"


def normalize_market(market: str | None) -> MarketCode:
    raw = (market or MarketCode.US).strip().lower()
    if raw == MarketCode.BIST:
        return MarketCode.BIST
    return MarketCode.US


def normalize_symbol(symbol: str, market: str | MarketCode | None = None) -> str:
    normalized_market = normalize_market(str(market) if market is not None else None)
    base = symbol.strip().upper()
    if normalized_market == MarketCode.BIST:
        return base if base.endswith(".IS") else f"{base}.IS"
    return base


def display_symbol(symbol: str, market: str | MarketCode | None = None) -> str:
    normalized_market = normalize_market(str(market) if market is not None else None)
    base = symbol.strip().upper()
    if normalized_market == MarketCode.BIST and base.endswith(".IS"):
        return base[:-3]
    return base
