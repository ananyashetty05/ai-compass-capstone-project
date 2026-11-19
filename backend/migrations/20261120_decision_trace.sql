-- XAI decision traces. ADDITIVE and IDEMPOTENT. APPLIED to the Neon production branch on 2026-11-19.
-- Additive and idempotent: safe to re-run.
-- Stores the sanitized structured decision (query profile, candidate funnel, exclusions with reasons, score
-- breakdown, scoring config version, counterfactuals, execution attempts, evaluation checks) so a decision
-- stays inspectable after the request completes. It NEVER stores the query text, the prompt, the response
-- text, credentials or secrets. Retention: rows can be deleted at any time without affecting routing.

CREATE TABLE IF NOT EXISTS routing_decision_trace (
    routing_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    engine_version TEXT NOT NULL,
    scoring_version TEXT NOT NULL,
    trace JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS routing_decision_trace_user_idx ON routing_decision_trace (user_id, created_at DESC);
