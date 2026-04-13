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

        normalized = self._normalize_download_columns(df=df, ticker=ticker)
        renamed = normalized.rename(
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

    @staticmethod
    def _normalize_download_columns(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
        if not isinstance(df.columns, pd.MultiIndex):
            return df

        # yfinance may return columns like (PriceField, Ticker) for a single ticker request.
        if ticker in df.columns.get_level_values(-1):
            return df.xs(ticker, axis=1, level=-1, drop_level=True)

        # Fallback: select first symbol if ticker suffix does not match exactly.
        symbols = [x for x in df.columns.get_level_values(-1).unique() if isinstance(x, str)]
        if symbols:
            return df.xs(symbols[0], axis=1, level=-1, drop_level=True)

        # Last-resort flatten to avoid KeyErrors and surface clearer validation failures upstream.
        df = df.copy()
        df.columns = [col[0] if isinstance(col, tuple) and col else str(col) for col in df.columns]
        return df

    def get_metadata(self, ticker: str) -> MarketMetadata:
        info = yf.Ticker(ticker).info or {}
        return MarketMetadata(
            market_cap=info.get("marketCap"),
            sector=info.get("sector"),
            industry=info.get("industry"),
        )
