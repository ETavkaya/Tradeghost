from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "TradeGhost"
    app_env: str = Field(default="dev")
    log_level: str = Field(default="INFO")

    data_provider: str = Field(default="yfinance")
    data_cache_ttl_seconds: int = Field(default=60 * 60 * 6)
    data_default_period: str = Field(default="2y")
    data_default_interval: str = Field(default="1d")

    score_momentum_weight: float = Field(default=0.25)
    score_trend_weight: float = Field(default=0.25)
    score_volatility_weight: float = Field(default=0.15)
    score_structure_weight: float = Field(default=0.20)
    score_context_weight: float = Field(default=0.15)
    swing_candidate_threshold: float = Field(default=65.0)

    strategy_atr_stop_multiple: float = Field(default=1.5)
    strategy_tp1_rr: float = Field(default=1.8)
    strategy_tp2_rr: float = Field(default=3.0)

    backtest_min_score_to_enter: float = Field(default=60.0)
    backtest_max_hold_days: int = Field(default=15)
    backtest_warmup_bars: int = Field(default=120)

    cache_dir: Path = Field(default=Path("./.cache"))
    logs_dir: Path = Field(default=Path("./logs"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    return settings
