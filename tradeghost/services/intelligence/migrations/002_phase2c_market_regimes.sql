CREATE TABLE IF NOT EXISTS market_regime_snapshots (
    id UUID PRIMARY KEY,
    idempotency_key text NOT NULL UNIQUE,
    payload_hash text NOT NULL,
    market text NOT NULL,
    as_of_date date NOT NULL,
    primary_benchmark_symbol text,
    benchmark_returns_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    volatility_20d_pct numeric,
    regime_label text NOT NULL,
    classifier_version text NOT NULL,
    raw_inputs_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    data_quality_flags_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    rule_version text NOT NULL,
    feature_version text NOT NULL,
    data_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT market_regime_snapshots_identity UNIQUE (market, as_of_date, classifier_version, data_version)
);

CREATE INDEX IF NOT EXISTS market_regime_snapshots_lookup_idx
ON market_regime_snapshots (market, as_of_date DESC, classifier_version);

ALTER TABLE prediction_records
ADD COLUMN IF NOT EXISTS selection_market_regime_id UUID;

ALTER TABLE outcome_records
ADD COLUMN IF NOT EXISTS selection_market_regime_id UUID;

ALTER TABLE outcome_records
ADD COLUMN IF NOT EXISTS outcome_market_regime_id UUID;

ALTER TABLE outcome_records
ADD COLUMN IF NOT EXISTS market_regime_label text;

ALTER TABLE outcome_records
ADD COLUMN IF NOT EXISTS market_return_pct numeric;

ALTER TABLE outcome_records
ADD COLUMN IF NOT EXISTS sector_proxy_symbol text;

ALTER TABLE outcome_records
ADD COLUMN IF NOT EXISTS sector_return_pct numeric;

ALTER TABLE outcome_records
ADD COLUMN IF NOT EXISTS relative_to_spy numeric;

ALTER TABLE outcome_records
ADD COLUMN IF NOT EXISTS relative_to_qqq numeric;

ALTER TABLE outcome_records
ADD COLUMN IF NOT EXISTS relative_to_sector_proxy numeric;

ALTER TABLE outcome_records
ADD COLUMN IF NOT EXISTS attribution_label text;
