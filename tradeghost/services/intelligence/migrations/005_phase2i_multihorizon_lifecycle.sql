ALTER TABLE outcome_records
    ADD COLUMN IF NOT EXISTS max_drawdown_pct double precision;
