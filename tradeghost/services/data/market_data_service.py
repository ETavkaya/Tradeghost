from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from tradeghost.services.data.providers import MarketDataProvider, MarketMetadata, YFinanceMarketDataProvider
from tradeghost.shared.config.settings import get_settings
from tradeghost.shared.utils.cache import TTLCache


@dataclass
class MarketDataBundle:
    ticker: str
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

    def get_market_data(self, ticker: str, use_cache: bool = True) -> MarketDataBundle:
        normalized_ticker = ticker.strip().upper()
        if use_cache:
            cached = self._cache.get(normalized_ticker)
            if cached is not None:
                return cached

        daily = self.provider.get_ohlcv(
            ticker=normalized_ticker,
            period=self.default_period,
            interval=self.default_interval,
        )
        weekly = self._to_weekly(daily)
        metadata = self.provider.get_metadata(normalized_ticker)
        bundle = MarketDataBundle(
            ticker=normalized_ticker,
            daily=daily,
            weekly=weekly,
            metadata=metadata,
        )
        if use_cache:
            self._cache.set(normalized_ticker, bundle)
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

