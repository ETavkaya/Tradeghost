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
    symbol_metadata_ttl_seconds: int = Field(default=60 * 60 * 24 * 7)

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
    database_url: str = Field(default="")
    research_rule_version: str = Field(default="scanner_rules_v1")
    research_feature_version: str = Field(default="scanner_features_v1")
    research_data_version: str = Field(default="market_data_daily_v1")
    research_outcome_evaluator_version: str = Field(default="outcome_evaluator_v2")
    market_regime_classifier_version: str = Field(default="market_regime_v1")
    research_retrieval_min_sample_size: int = Field(default=10)
    research_retrieval_source_limit: int = Field(default=2000)
    research_pattern_min_sample_size: int = Field(default=30)
    research_pattern_min_evaluable_ratio: float = Field(default=0.80)
    research_pattern_min_distinct_cohorts: int = Field(default=3)
    research_pattern_max_symbol_concentration: float = Field(default=0.50)
    research_pattern_min_effect_size_pct_points: float = Field(default=10.0)
    research_pattern_max_p_value: float = Field(default=0.05)
    research_pattern_source_limit: int = Field(default=5000)
    neo4j_uri: str = Field(default="")
    neo4j_username: str = Field(default="")
    neo4j_password: str = Field(default="")
    knowledge_graph_enabled: bool = Field(default=False)
    knowledge_graph_poll_seconds: int = Field(default=30)
    knowledge_graph_batch_size: int = Field(default=25)
    knowledge_graph_retry_seconds: int = Field(default=60)
    llm_provider: str = Field(default="openai")
    llm_fallback_provider: str = Field(default="ollama")
    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-4o-mini")
    openai_base_url: str = Field(default="https://api.openai.com/v1")
    llmq_chat_model: str = Field(default="gpt-4o-mini")
    daily_report_llm_model: str = Field(default="gpt-4o-mini")
    market_context_llm_model: str = Field(default="gpt-4o-mini")
    final_28d_review_llm_model: str = Field(default="gpt-4o-mini")
    daily_cohort_followup_enabled: bool = Field(default=True)
    daily_cohort_followup_schedule: str = Field(default="23:30")
    daily_cohort_followup_timezone: str = Field(default="Europe/London")
    daily_cohort_followup_poll_seconds: int = Field(default=60)
    ollama_base_url: str = Field(default="http://localhost:11435")
    intelligence_llm_enabled: bool = Field(default=True)
    ollama_model: str = Field(default="llama3.2:3b")
    ollama_temperature: float = Field(default=0.1)
    ollama_top_p: float = Field(default=0.9)
    ollama_repeat_penalty: float = Field(default=1.05)
    ollama_num_predict: int = Field(default=180)
    ollama_num_ctx: int = Field(default=2048)
    ollama_num_thread: int = Field(default=4)
    ollama_keep_alive: str = Field(default="30m")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    return settings
