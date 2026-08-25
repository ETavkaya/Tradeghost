CREATE TABLE IF NOT EXISTS pattern_candidates (
    id UUID PRIMARY KEY,
    idempotency_key text NOT NULL UNIQUE,
    payload_hash text NOT NULL,
    pattern_key text NOT NULL,
    market text NOT NULL,
    horizon_days integer NOT NULL,
    condition_set_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    population_definition_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    metrics_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_prediction_ids_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_outcome_ids_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    sample_size integer NOT NULL,
    evaluable_case_count integer NOT NULL,
    success_count integer NOT NULL,
    success_rate_pct numeric,
    average_return_pct numeric,
    effect_size_pct_points numeric,
    p_value numeric,
    confidence_interval_low_pct numeric,
    confidence_interval_high_pct numeric,
    approval_eligible boolean NOT NULL DEFAULT false,
    status text NOT NULL,
    rule_version text NOT NULL,
    feature_version text NOT NULL,
    data_version text NOT NULL,
    statistics_version text NOT NULL,
    as_of_date date NOT NULL,
    review_notes text,
    reviewed_by text,
    reviewed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pattern_candidates_status_check CHECK (status IN ('candidate', 'approved_for_retrieval', 'rejected', 'archived'))
);

CREATE INDEX IF NOT EXISTS pattern_candidates_lookup_idx
ON pattern_candidates (market, horizon_days, as_of_date DESC, status, created_at DESC);

CREATE TABLE IF NOT EXISTS pattern_candidate_reviews (
    id UUID PRIMARY KEY,
    pattern_candidate_id UUID NOT NULL REFERENCES pattern_candidates(id),
    action text NOT NULL,
    from_status text,
    to_status text NOT NULL,
    reviewer_id text NOT NULL,
    reviewer_notes text NOT NULL DEFAULT '',
    details_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS pattern_candidate_reviews_lookup_idx
ON pattern_candidate_reviews (pattern_candidate_id, created_at ASC);
