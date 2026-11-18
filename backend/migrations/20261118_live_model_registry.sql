-- Live Model Pool schema (Phase 5). ADDITIVE and IDEMPOTENT. NOT APPLIED to any database.
-- Apply to an isolated Neon test branch first; production requires explicit approval.
-- Snapshots, lifecycle events and verifications are append-only: current state is derived by view.

CREATE TABLE IF NOT EXISTS provider_catalog_refreshes (
    refresh_id UUID PRIMARY KEY,
    provider TEXT NOT NULL,                       -- lowercase provider key, e.g. 'openai'
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed', 'abandoned')),
    trigger TEXT NOT NULL DEFAULT 'manual' CHECK (trigger IN ('manual', 'scheduled')),
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ NOT NULL,
    last_success_at TIMESTAMPTZ,
    error_code TEXT,
    error_message_safe TEXT,
    entries_seen INTEGER, entries_new INTEGER, entries_changed INTEGER,
    entries_missing INTEGER, entries_rejected INTEGER
);
-- At most one running refresh per provider (concurrency guard); expired leases are marked abandoned first.
CREATE UNIQUE INDEX IF NOT EXISTS provider_catalog_refresh_running_idx
    ON provider_catalog_refreshes (provider) WHERE status = 'running';
CREATE INDEX IF NOT EXISTS provider_catalog_refresh_history_idx
    ON provider_catalog_refreshes (provider, started_at DESC);

CREATE TABLE IF NOT EXISTS model_catalog_snapshots (
    snapshot_id UUID PRIMARY KEY,
    provider TEXT NOT NULL,                       -- lowercase provider key
    model_id TEXT NOT NULL,
    canonical_key TEXT NOT NULL,                  -- '<provider>:<model_id>'
    snapshot JSONB NOT NULL,
    content_hash TEXT NOT NULL,                   -- unchanged content is not re-appended (idempotent refresh)
    lifecycle_status TEXT NOT NULL CHECK (lifecycle_status IN
        ('newly_discovered','pending_validation','active','deprecated','unavailable','retired','incompatible','discovery_failed')),
    adapter_compatible BOOLEAN NOT NULL,
    metadata_status TEXT NOT NULL,
    discovered_at TIMESTAMPTZ NOT NULL,
    refresh_id UUID REFERENCES provider_catalog_refreshes(refresh_id),   -- NULL for snapshots appended by inference verification
    UNIQUE (provider, model_id, refresh_id)
);
CREATE INDEX IF NOT EXISTS model_catalog_snapshot_current_idx
    ON model_catalog_snapshots (provider, model_id, discovered_at DESC);

CREATE TABLE IF NOT EXISTS model_lifecycle_events (
    event_id UUID PRIMARY KEY,
    snapshot_id UUID REFERENCES model_catalog_snapshots(snapshot_id),
    provider TEXT NOT NULL,
    model_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN
        ('discovered','status_changed','metadata_changed','missing_from_successful_refresh','inference_verified','inference_verification_failed')),
    previous_status TEXT,
    new_status TEXT NOT NULL,
    reason TEXT,
    occurred_at TIMESTAMPTZ NOT NULL,
    refresh_id UUID REFERENCES provider_catalog_refreshes(refresh_id)
);
CREATE INDEX IF NOT EXISTS model_lifecycle_event_history_idx
    ON model_lifecycle_events (provider, model_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS model_lifecycle_event_recent_idx ON model_lifecycle_events (occurred_at DESC);

-- Inference access is verified separately from catalog visibility.
CREATE TABLE IF NOT EXISTS model_inference_verifications (
    verification_id UUID PRIMARY KEY,
    provider TEXT NOT NULL,
    model_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('validated', 'failed')),
    error_code TEXT,                              -- classified kind only; never an upstream body
    latency_ms INTEGER,
    verified_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS model_inference_verification_current_idx
    ON model_inference_verifications (provider, model_id, verified_at DESC);

CREATE OR REPLACE VIEW current_model_catalog_snapshots AS
SELECT DISTINCT ON (provider, model_id) * FROM model_catalog_snapshots
ORDER BY provider, model_id, discovered_at DESC, snapshot_id;

CREATE OR REPLACE VIEW current_inference_verifications AS
SELECT DISTINCT ON (provider, model_id) * FROM model_inference_verifications
ORDER BY provider, model_id, verified_at DESC, verification_id;
