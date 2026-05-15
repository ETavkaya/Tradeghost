from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json

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
        self.settings = settings
        self.provider = provider or YFinanceMarketDataProvider()
        self._cache = TTLCache[str, MarketDataBundle](ttl_seconds=settings.data_cache_ttl_seconds)
        self.default_period = settings.data_default_period
        self.default_interval = settings.data_default_interval
        self.metadata_cache_path = settings.cache_dir / "symbol_metadata_cache.json"
        self.metadata_cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._bist_sector_placeholder: dict[str, dict[str, str]] = {
            "THYAO": {"sector": "Industrials", "industry": "Airlines"},
            "AKBNK": {"sector": "Financial Services", "industry": "Banks - Regional"},
            "GARAN": {"sector": "Financial Services", "industry": "Banks - Regional"},
            "ASELS": {"sector": "Industrials", "industry": "Aerospace & Defense"},
            "SISE": {"sector": "Basic Materials", "industry": "Specialty Chemicals"},
            "KCHOL": {"sector": "Industrials", "industry": "Conglomerates"},
            "EREGL": {"sector": "Basic Materials", "industry": "Steel"},
            "BIMAS": {"sector": "Consumer Defensive", "industry": "Discount Stores"},
            "TUPRS": {"sector": "Energy", "industry": "Oil & Gas Refining & Marketing"},
            "ISCTR": {"sector": "Financial Services", "industry": "Banks - Diversified"},
        }

    def _read_metadata_cache(self) -> dict[str, dict]:
        if not self.metadata_cache_path.exists():
            return {}
        try:
            return json.loads(self.metadata_cache_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_metadata_cache(self, rows: dict[str, dict]) -> None:
        self.metadata_cache_path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")

    def _metadata_cache_key(self, market: MarketCode, ticker: str) -> str:
        return f"{market.value}:{ticker.upper()}"

    def _is_metadata_fresh(self, updated_at: str | None) -> bool:
        if not updated_at:
            return False
        try:
            ts = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        except Exception:
            return False
        age = (datetime.now(UTC) - ts.astimezone(UTC)).total_seconds()
        return age <= max(60, int(self.settings.symbol_metadata_ttl_seconds))

    def _fallback_bist_metadata(self, ticker: str, market: MarketCode) -> MarketMetadata:
        mapped = self._bist_sector_placeholder.get(ticker.upper(), {})
        now_iso = datetime.now(UTC).isoformat()
        has_mapping = bool(mapped)
        return MarketMetadata(
            symbol=ticker.upper(),
            market=market.value,
            company_name=None,
            sector=mapped.get("sector"),
            industry=mapped.get("industry"),
            sector_key=None,
            industry_key=None,
            country="TR",
            currency="TRY",
            exchange="BIST",
            source="bist_static_placeholder",
            updated_at=now_iso,
            data_quality_status="ok" if has_mapping else "metadata_missing",
        )

    def get_symbol_metadata(self, ticker: str, market: MarketCode, use_cache: bool = True) -> MarketMetadata:
        key = self._metadata_cache_key(market, ticker)
        cache = self._read_metadata_cache() if use_cache else {}
        cached = cache.get(key)
        if isinstance(cached, dict):
            row = MarketMetadata(**cached)
            if self._is_metadata_fresh(row.updated_at):
                return row
        try:
            fresh = self.provider.get_metadata(ticker, market.value)
            fresh.symbol = ticker.upper()
            fresh.market = market.value
            if market.value == "bist" and not fresh.sector and not fresh.industry:
                fresh = self._fallback_bist_metadata(ticker, market)
            if not fresh.updated_at:
                fresh.updated_at = datetime.now(UTC).isoformat()
            if not fresh.source:
                fresh.source = "yfinance"
            if not fresh.data_quality_status:
                fresh.data_quality_status = "ok" if (fresh.sector or fresh.industry) else "metadata_missing"
            cache[key] = fresh.__dict__
            self._write_metadata_cache(cache)
            return fresh
        except Exception:
            if isinstance(cached, dict):
                row = MarketMetadata(**cached)
                row.data_quality_status = row.data_quality_status or "metadata_stale"
                return row
            if market.value == "bist":
                return self._fallback_bist_metadata(ticker, market)
            return MarketMetadata(
                symbol=ticker.upper(),
                market=market.value,
                source="metadata_unavailable",
                updated_at=datetime.now(UTC).isoformat(),
                data_quality_status="metadata_missing",
            )

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
        metadata = self.get_symbol_metadata(normalized_ticker, normalized_market, use_cache=use_cache)
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
