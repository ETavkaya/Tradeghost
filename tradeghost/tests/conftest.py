from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tradeghost.services.data.market_data_service import MarketDataService
from tradeghost.services.data.providers import MarketDataProvider, MarketMetadata


class FakeProvider(MarketDataProvider):
    def __init__(self, daily: pd.DataFrame) -> None:
        self._daily = daily

    def get_ohlcv(self, ticker: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
        return self._daily.copy()

    def get_metadata(self, ticker: str) -> MarketMetadata:
        return MarketMetadata(market_cap=10_000_000_000, sector="Tech", industry="Software")


@pytest.fixture
def sample_daily_df() -> pd.DataFrame:
    idx = pd.bdate_range("2023-01-02", periods=320)
    base = np.linspace(100, 150, len(idx))
    seasonal = 2 * np.sin(np.linspace(0, 16, len(idx)))
    close = base + seasonal
    open_ = close - 0.4
    high = close + 1.2
    low = close - 1.2
    volume = (1_000_000 + np.linspace(0, 200_000, len(idx))).astype(int)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


@pytest.fixture
def market_data_service(sample_daily_df: pd.DataFrame) -> MarketDataService:
    provider = FakeProvider(sample_daily_df)
    return MarketDataService(provider=provider)

