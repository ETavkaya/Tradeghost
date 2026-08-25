CREATE TABLE IF NOT EXISTS canonical_ohlc_bars (
    id UUID PRIMARY KEY,
    market text NOT NULL,
    symbol text NOT NULL,
    bar_date date NOT NULL,
    provider text NOT NULL,
    adjustment_policy text NOT NULL,
    data_version text NOT NULL,
    retrieved_at timestamptz NOT NULL,
    open numeric,
    high numeric,
    low numeric,
    close numeric NOT NULL,
    volume numeric,
    source_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT canonical_ohlc_bars_identity UNIQUE (market, symbol, bar_date, provider, adjustment_policy, data_version)
);

CREATE INDEX IF NOT EXISTS canonical_ohlc_bars_lookup_idx
ON canonical_ohlc_bars (market, symbol, bar_date, data_version);

CREATE TABLE IF NOT EXISTS prediction_records (
    id UUID PRIMARY KEY,
    idempotency_key text NOT NULL UNIQUE,
    payload_hash text NOT NULL,
    cohort_id UUID NOT NULL,
    symbol text NOT NULL,
    market text NOT NULL,
    selected_at timestamptz NOT NULL,
    selected_date date NOT NULL,
    selected_price numeric,
    categories_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    setup_type text NOT NULL DEFAULT '',
    trend_state text NOT NULL DEFAULT '',
    extension_state text,
    score_dynamics_state text,
    trigger_state text,
    trigger_score numeric,
    trigger_threshold numeric,
    score numeric,
    candidate_type text,
    entry_readiness text,
    blocked_by text,
    risk_flags_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    data_quality_flags_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    expected_horizon_days integer NOT NULL DEFAULT 28,
    expected_direction text NOT NULL DEFAULT 'up',
    prediction_type text NOT NULL,
    invalidation_conditions_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    deterministic_reason text NOT NULL DEFAULT '',
    selection_snapshot_json jsonb NOT NULL,
    source_run_id text,
    source_report_id UUID,
    rule_version text NOT NULL,
    feature_version text NOT NULL,
    data_version text NOT NULL,
    supersedes_prediction_id UUID,
    correction_reason text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS prediction_records_cohort_idx
ON prediction_records (cohort_id, selected_at, symbol);

CREATE TABLE IF NOT EXISTS outcome_records (
    id UUID PRIMARY KEY,
    idempotency_key text NOT NULL UNIQUE,
    payload_hash text NOT NULL,
    prediction_id UUID NOT NULL REFERENCES prediction_records(id),
    cohort_id UUID NOT NULL,
    symbol text NOT NULL,
    market text NOT NULL,
    horizon_days integer NOT NULL,
    selection_date date NOT NULL,
    outcome_date date,
    evaluated_at timestamptz NOT NULL,
    outcome_status text NOT NULL,
    outcome_label text NOT NULL,
    selected_price numeric,
    horizon_price numeric,
    return_pct numeric,
    directional_return_pct numeric,
    max_favorable_excursion_pct numeric,
    max_adverse_excursion_pct numeric,
    price_path_complete boolean NOT NULL DEFAULT false,
    daily_snapshot_path_complete boolean NOT NULL DEFAULT false,
    daily_snapshot_coverage_pct numeric NOT NULL DEFAULT 0,
    followed_through boolean,
    false_positive boolean,
    invalidated_quickly boolean,
    missed_follow_through boolean,
    stayed_valid boolean,
    categories_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    setup_type text,
    blocked_by text,
    data_quality_flags_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    attribution_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    price_source text,
    selection_bar_date date,
    horizon_bar_date date,
    evaluator_version text NOT NULL,
    rule_version text NOT NULL,
    feature_version text NOT NULL,
    data_version text NOT NULL,
    supersedes_outcome_id UUID,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT outcome_records_identity UNIQUE (prediction_id, horizon_days, evaluator_version, data_version)
);

CREATE INDEX IF NOT EXISTS outcome_records_cohort_idx
ON outcome_records (cohort_id, horizon_days, evaluated_at DESC);

CREATE TABLE IF NOT EXISTS outcome_summary_snapshots (
    id UUID PRIMARY KEY,
    cohort_id UUID NOT NULL,
    grouping text NOT NULL,
    group_value text NOT NULL,
    horizon_days integer NOT NULL,
    prediction_count integer NOT NULL,
    available_outcome_count integer NOT NULL,
    data_quality_excluded_count integer NOT NULL,
    positive_count integer NOT NULL,
    negative_count integer NOT NULL,
    average_return_pct numeric,
    rule_version text NOT NULL,
    feature_version text NOT NULL,
    data_version text NOT NULL,
    evaluator_version text NOT NULL,
    calculated_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT outcome_summary_identity UNIQUE (cohort_id, grouping, group_value, horizon_days, rule_version, feature_version, data_version, evaluator_version)
);

CREATE TABLE IF NOT EXISTS data_quality_events (
    id UUID PRIMARY KEY,
    dedupe_key text NOT NULL UNIQUE,
    entity_type text NOT NULL,
    entity_id text NOT NULL,
    cohort_id UUID,
    symbol text,
    event_code text NOT NULL,
    severity text NOT NULL,
    details_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    rule_version text NOT NULL,
    feature_version text NOT NULL,
    data_version text NOT NULL,
    observed_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS data_quality_events_cohort_idx
ON data_quality_events (cohort_id, observed_at DESC);
