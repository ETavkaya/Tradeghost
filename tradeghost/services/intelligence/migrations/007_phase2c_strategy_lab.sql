CREATE TABLE IF NOT EXISTS strategy_lab_experiments (
    id UUID PRIMARY KEY,
    idempotency_key text NOT NULL UNIQUE,
    payload_hash text NOT NULL,
    name text NOT NULL,
    market text NOT NULL,
    currency text NOT NULL,
    activation_at timestamptz NOT NULL,
    status text NOT NULL,
    policy_version text NOT NULL,
    rule_version text NOT NULL,
    feature_version text NOT NULL,
    data_version text NOT NULL,
    config_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS strategy_lab_sleeves (
    id UUID PRIMARY KEY,
    experiment_id UUID NOT NULL REFERENCES strategy_lab_experiments(id),
    sleeve_key text NOT NULL,
    sleeve_type text NOT NULL,
    initial_cash numeric(18, 6) NOT NULL,
    max_positions integer NOT NULL,
    allocation_per_slot numeric(18, 6) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT strategy_lab_sleeves_identity UNIQUE (experiment_id, sleeve_key)
);

CREATE TABLE IF NOT EXISTS strategy_lab_decisions (
    id UUID PRIMARY KEY,
    idempotency_key text NOT NULL UNIQUE,
    payload_hash text NOT NULL,
    experiment_id UUID NOT NULL REFERENCES strategy_lab_experiments(id),
    sleeve_id UUID REFERENCES strategy_lab_sleeves(id),
    position_id UUID,
    source_run_id text NOT NULL,
    source_run_at timestamptz NOT NULL,
    source_run_date date NOT NULL,
    symbol text NOT NULL,
    market text NOT NULL,
    category text NOT NULL,
    decision_status text NOT NULL,
    reason_codes_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    final_entry_decision boolean NOT NULL,
    source_candidate_hash text NOT NULL,
    source_candidate_json jsonb NOT NULL,
    rule_version text NOT NULL,
    feature_version text NOT NULL,
    data_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS strategy_lab_decisions_experiment_idx
ON strategy_lab_decisions (experiment_id, source_run_at DESC, symbol);

CREATE TABLE IF NOT EXISTS strategy_lab_positions (
    id UUID PRIMARY KEY,
    experiment_id UUID NOT NULL REFERENCES strategy_lab_experiments(id),
    sleeve_id UUID NOT NULL REFERENCES strategy_lab_sleeves(id),
    decision_id UUID NOT NULL UNIQUE REFERENCES strategy_lab_decisions(id),
    symbol text NOT NULL,
    market text NOT NULL,
    status text NOT NULL,
    allocated_cash numeric(18, 6) NOT NULL,
    quantity numeric(24, 12),
    entry_date date,
    entry_price numeric(24, 12),
    entry_data_version text,
    exit_date date,
    exit_price numeric(24, 12),
    exit_data_version text,
    realised_pnl numeric(24, 12),
    latest_valuation_date date,
    latest_valuation_price numeric(24, 12),
    scheduled_exit_sessions integer NOT NULL DEFAULT 56,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS strategy_lab_positions_active_idx
ON strategy_lab_positions (experiment_id, status, symbol);

CREATE TABLE IF NOT EXISTS strategy_lab_ledger_events (
    id UUID PRIMARY KEY,
    idempotency_key text NOT NULL UNIQUE,
    experiment_id UUID NOT NULL REFERENCES strategy_lab_experiments(id),
    sleeve_id UUID REFERENCES strategy_lab_sleeves(id),
    position_id UUID REFERENCES strategy_lab_positions(id),
    decision_id UUID REFERENCES strategy_lab_decisions(id),
    event_type text NOT NULL,
    event_date date NOT NULL,
    cash_delta numeric(24, 12) NOT NULL DEFAULT 0,
    quantity numeric(24, 12),
    price numeric(24, 12),
    source_bar_date date,
    price_source text,
    data_version text NOT NULL,
    details_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    reverses_event_id UUID REFERENCES strategy_lab_ledger_events(id),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS strategy_lab_ledger_events_experiment_idx
ON strategy_lab_ledger_events (experiment_id, event_date, created_at);

CREATE TABLE IF NOT EXISTS strategy_lab_avoided_observations (
    id UUID PRIMARY KEY,
    idempotency_key text NOT NULL UNIQUE,
    experiment_id UUID NOT NULL REFERENCES strategy_lab_experiments(id),
    decision_id UUID NOT NULL UNIQUE REFERENCES strategy_lab_decisions(id),
    symbol text NOT NULL,
    market text NOT NULL,
    source_run_date date NOT NULL,
    planned_allocation numeric(18, 6) NOT NULL,
    status text NOT NULL,
    entry_date date,
    entry_price numeric(24, 12),
    exit_date date,
    exit_price numeric(24, 12),
    return_pct numeric(24, 12),
    data_version text NOT NULL,
    details_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS strategy_lab_avoided_experiment_idx
ON strategy_lab_avoided_observations (experiment_id, status, source_run_date);
