CREATE TABLE IF NOT EXISTS rule_hypotheses (
    id UUID PRIMARY KEY,
    idempotency_key text NOT NULL UNIQUE,
    payload_hash text NOT NULL,
    title text NOT NULL,
    hypothesis_text text NOT NULL,
    expected_metric text NOT NULL,
    evidence_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    affected_conditions_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    suggested_rule_change text NOT NULL DEFAULT '',
    proposed_config_patch_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    affected_universe_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    temporal_split_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    generated_by text NOT NULL,
    submitted_by text NOT NULL,
    status text NOT NULL,
    rule_version text NOT NULL,
    feature_version text NOT NULL,
    data_version text NOT NULL,
    candidate_rule_version text NOT NULL,
    latest_validation_id UUID,
    review_notes text,
    reviewed_by text,
    reviewed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT rule_hypotheses_generated_by_check CHECK (generated_by IN ('deterministic_analyzer', 'human', 'llm_summary')),
    CONSTRAINT rule_hypotheses_status_check CHECK (status IN ('draft', 'evidence_ready', 'backtest_running', 'validated', 'rejected', 'approved_for_release'))
);

CREATE INDEX IF NOT EXISTS rule_hypotheses_status_idx
ON rule_hypotheses (status, created_at DESC);

CREATE TABLE IF NOT EXISTS rule_hypothesis_validation_runs (
    id UUID PRIMARY KEY,
    hypothesis_id UUID NOT NULL REFERENCES rule_hypotheses(id),
    idempotency_key text NOT NULL UNIQUE,
    input_hash text NOT NULL,
    validation_status text NOT NULL,
    qualified_for_review boolean NOT NULL DEFAULT false,
    frozen_input_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    baseline_metrics_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    candidate_metrics_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    criteria_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    caveats_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    errors_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    evaluator_version text NOT NULL,
    started_at timestamptz NOT NULL,
    completed_at timestamptz,
    CONSTRAINT rule_hypothesis_validation_runs_status_check CHECK (validation_status IN ('running', 'completed', 'failed'))
);

CREATE UNIQUE INDEX IF NOT EXISTS rule_hypothesis_validation_runs_input_idx
ON rule_hypothesis_validation_runs (hypothesis_id, input_hash);

CREATE TABLE IF NOT EXISTS rule_hypothesis_reviews (
    id UUID PRIMARY KEY,
    hypothesis_id UUID NOT NULL REFERENCES rule_hypotheses(id),
    action text NOT NULL,
    from_status text,
    to_status text NOT NULL,
    reviewer_id text NOT NULL,
    reviewer_notes text NOT NULL DEFAULT '',
    details_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS rule_hypothesis_reviews_lookup_idx
ON rule_hypothesis_reviews (hypothesis_id, created_at ASC);
