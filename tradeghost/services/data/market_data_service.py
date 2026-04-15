from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from tradeghost.services.data.providers import MarketDataProvider, MarketMetadata, YFinanceMarketDataProvider
from tradeghost.shared.config.settings import get_settings
from tradeghost.shared.market import MarketCode, display_symbol, normalize_market, normalize_symbol
from tradeghost.shared.utils.cache import TTLCache


@dataclass
class MarketDataBundle:
    ticker: str
    normalized_ticker: str
    market: MarketCode
    daily: pd.DataFrame
    weekly: pd.DataFrame
    metadata: MarketMetadata


class MarketDataService:
    def __init__(self, provider: MarketDataProvider | None = None) -> None:
        settings = get_settings()
        self.provider = provider or YFinanceMarketDataProvider()
        self._cache = TTLCache[str, MarketDataBundle](ttl_seconds=settings.data_cache_ttl_seconds)
        self.default_period = settings.data_default_period
        self.default_interval = settings.data_default_interval

    def get_market_data(
        self,
        ticker: str,
        market: str | None = None,
        period: str | None = None,
        interval: str | None = None,
        use_cache: bool = True,
    ) -> MarketDataBundle:
        normalized_market = normalize_market(market)
        normalized_ticker = normalize_symbol(ticker, normalized_market)
        ui_ticker = display_symbol(ticker, normalized_market)
        resolved_period = period or self.default_period
        resolved_interval = interval or self.default_interval
        cache_key = f"{normalized_market}:{normalized_ticker}:{resolved_period}:{resolved_interval}"
        if use_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        daily = self.provider.get_ohlcv(
            ticker=normalized_ticker,
            period=resolved_period,
            interval=resolved_interval,
        )
        weekly = self._to_weekly(daily)
        metadata = self.provider.get_metadata(normalized_ticker)
        bundle = MarketDataBundle(
            ticker=ui_ticker,
            normalized_ticker=normalized_ticker,
            market=normalized_market,
            daily=daily,
            weekly=weekly,
            metadata=metadata,
        )
        if use_cache:
            self._cache.set(cache_key, bundle)
        return bundle

    @staticmethod
    def _to_weekly(daily: pd.DataFrame) -> pd.DataFrame:
        agg_map = {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
        weekly = daily.resample("W-FRI").agg(agg_map).dropna()
        return weekly
