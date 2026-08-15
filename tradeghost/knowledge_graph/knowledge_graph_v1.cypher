CREATE CONSTRAINT asset_key_unique IF NOT EXISTS FOR (node:Asset) REQUIRE node.asset_key IS UNIQUE;
CREATE CONSTRAINT report_id_unique IF NOT EXISTS FOR (node:Report) REQUIRE node.report_id IS UNIQUE;
CREATE CONSTRAINT report_segment_id_unique IF NOT EXISTS FOR (node:ReportSegment) REQUIRE node.segment_id IS UNIQUE;
CREATE CONSTRAINT extraction_run_id_unique IF NOT EXISTS FOR (node:ExtractionRun) REQUIRE node.extraction_run_id IS UNIQUE;
CREATE CONSTRAINT signal_id_unique IF NOT EXISTS FOR (node:Signal) REQUIRE node.signal_id IS UNIQUE;
CREATE CONSTRAINT event_id_unique IF NOT EXISTS FOR (node:Event) REQUIRE node.event_id IS UNIQUE;
CREATE CONSTRAINT market_regime_id_unique IF NOT EXISTS FOR (node:MarketRegime) REQUIRE node.regime_id IS UNIQUE;
CREATE CONSTRAINT condition_id_unique IF NOT EXISTS FOR (node:Condition) REQUIRE node.condition_id IS UNIQUE;
CREATE CONSTRAINT prediction_id_unique IF NOT EXISTS FOR (node:Prediction) REQUIRE node.prediction_id IS UNIQUE;
CREATE CONSTRAINT outcome_id_unique IF NOT EXISTS FOR (node:Outcome) REQUIRE node.outcome_id IS UNIQUE;
CREATE CONSTRAINT strategy_id_unique IF NOT EXISTS FOR (node:Strategy) REQUIRE node.strategy_id IS UNIQUE;
CREATE CONSTRAINT pattern_id_unique IF NOT EXISTS FOR (node:Pattern) REQUIRE node.pattern_id IS UNIQUE;

CREATE INDEX report_published_at IF NOT EXISTS FOR (node:Report) ON (node.published_at);
CREATE INDEX signal_observed_at IF NOT EXISTS FOR (node:Signal) ON (node.observed_at);
CREATE INDEX prediction_due IF NOT EXISTS FOR (node:Prediction) ON (node.status, node.evaluation_due_at);
CREATE INDEX outcome_evaluated_at IF NOT EXISTS FOR (node:Outcome) ON (node.evaluated_at);
CREATE INDEX pattern_status IF NOT EXISTS FOR (node:Pattern) ON (node.status, node.sample_size);
CREATE FULLTEXT INDEX report_segment_text IF NOT EXISTS FOR (node:ReportSegment) ON EACH [node.text];
