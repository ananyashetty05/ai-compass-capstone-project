-- Route Query Engine 2.0 persistence. ADDITIVE and IDEMPOTENT. NOT APPLIED to any database.
-- Apply to an isolated Neon test branch first; production requires explicit approval.
-- Stores compact decision records and execution outcomes. It never stores prompts, responses or secrets;
-- query_summary is a <=80 character excerpt and is withheld for sensitive queries.

CREATE TABLE IF NOT EXISTS routing_decision_log (
    routing_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    engine_version TEXT NOT NULL,
    scoring_version TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('recommend', 'execute')),
    primary_intent TEXT,
    complexity_score DOUBLE PRECISION,
    sensitivity TEXT,
    optimization_mode TEXT,
    selected_model_id TEXT,
    selected_model_name TEXT,
    final_model_id TEXT,
    final_model_name TEXT,
    candidate_count INTEGER,
    excluded_count INTEGER,
    weights JSONB,
    scores JSONB,
    explanation_summary TEXT,
    execution_status TEXT,
    evaluation_status TEXT,
    routing_latency_ms DOUBLE PRECISION,
    total_latency_ms DOUBLE PRECISION,
    total_cost_usd DOUBLE PRECISION,
    escalated BOOLEAN NOT NULL DEFAULT FALSE,
    query_summary TEXT
);
CREATE INDEX IF NOT EXISTS routing_decision_log_user_idx ON routing_decision_log (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS routing_execution_log (
    id BIGSERIAL PRIMARY KEY,
    routing_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('success', 'error')),
    error_kind TEXT,
    latency_ms DOUBLE PRECISION,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS routing_execution_log_model_idx ON routing_execution_log (model_id, created_at DESC);
