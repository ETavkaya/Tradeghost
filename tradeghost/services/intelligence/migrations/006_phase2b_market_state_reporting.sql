CREATE TABLE IF NOT EXISTS market_state_snapshots (
    id UUID PRIMARY KEY,
    idempotency_key text NOT NULL UNIQUE,
    payload_hash text NOT NULL,
    market text NOT NULL,
    as_of_date date NOT NULL,
    observed_at timestamptz NOT NULL,
    source_market_regime_id UUID REFERENCES market_regime_snapshots(id),
    source_market_regime_payload_hash text,
    state_version text NOT NULL,
    data_version text NOT NULL,
    availability_status text NOT NULL,
    inputs_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    state_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_versions_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    data_quality_flags_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    unavailable_inputs_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT market_state_snapshots_identity UNIQUE (market, as_of_date, state_version, data_version)
);

CREATE INDEX IF NOT EXISTS market_state_snapshots_lookup_idx
ON market_state_snapshots (market, as_of_date DESC, state_version);

CREATE TABLE IF NOT EXISTS operational_reports (
    id UUID PRIMARY KEY,
    idempotency_key text NOT NULL UNIQUE,
    payload_hash text NOT NULL,
    report_type text NOT NULL,
    report_version text NOT NULL,
    market text NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    as_of_date date NOT NULL,
    generated_at timestamptz NOT NULL,
    status text NOT NULL,
    market_state_id UUID REFERENCES market_state_snapshots(id),
    summary_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_versions_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    data_quality_flags_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    supersedes_report_id UUID REFERENCES operational_reports(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT operational_reports_period_valid CHECK (period_start <= period_end),
    CONSTRAINT operational_reports_type_valid CHECK (report_type IN ('weekly', 'monthly'))
);

CREATE INDEX IF NOT EXISTS operational_reports_lookup_idx
ON operational_reports (market, report_type, period_end DESC, generated_at DESC);
