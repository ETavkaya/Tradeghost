from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd
import yfinance as yf


@dataclass
class MarketMetadata:
    market_cap: float | None
    sector: str | None
    industry: str | None


class MarketDataProvider(ABC):
    @abstractmethod
    def get_ohlcv(self, ticker: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def get_metadata(self, ticker: str) -> MarketMetadata:
        raise NotImplementedError


class YFinanceMarketDataProvider(MarketDataProvider):
    def get_ohlcv(self, ticker: str, period: str = "2y", interval: str = "1d") -> pd.DataFrame:
        df = yf.download(
            tickers=ticker,
            period=period,
            interval=interval,
            auto_adjust=False,
            progress=False,
        )
        if df.empty:
            raise ValueError(f"No OHLCV data returned for ticker={ticker}")

        renamed = df.rename(
            columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Adj Close": "adj_close",
                "Volume": "volume",
            }
        )
        required = ["open", "high", "low", "close", "volume"]
        out = renamed[required].copy()
        out.index = pd.to_datetime(out.index)
        out = out.dropna()
        return out

    def get_metadata(self, ticker: str) -> MarketMetadata:
        info = yf.Ticker(ticker).info or {}
        return MarketMetadata(
            market_cap=info.get("marketCap"),
            sector=info.get("sector"),
            industry=info.get("industry"),
        )

