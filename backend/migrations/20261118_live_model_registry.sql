-- Additive Phase 5 live-registry schema. Do not apply to production without approval.
CREATE TABLE IF NOT EXISTS provider_catalog_refreshes (
    refresh_id UUID PRIMARY KEY, provider TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed', 'abandoned')),
    started_at TIMESTAMPTZ NOT NULL, finished_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ NOT NULL, last_success_at TIMESTAMPTZ,
    error_code TEXT, error_message_safe TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS provider_catalog_refresh_running_idx ON provider_catalog_refreshes (provider) WHERE status = 'running';
CREATE INDEX IF NOT EXISTS provider_catalog_refresh_history_idx ON provider_catalog_refreshes (provider, started_at DESC);

CREATE TABLE IF NOT EXISTS model_catalog_snapshots (
    snapshot_id UUID PRIMARY KEY, provider TEXT NOT NULL, model_id TEXT NOT NULL,
    snapshot JSONB NOT NULL, lifecycle_status TEXT NOT NULL,
    adapter_compatible BOOLEAN NOT NULL, metadata_status TEXT NOT NULL,
    discovered_at TIMESTAMPTZ NOT NULL, refresh_id UUID NOT NULL REFERENCES provider_catalog_refreshes(refresh_id),
    UNIQUE (provider, model_id, refresh_id)
);
CREATE INDEX IF NOT EXISTS model_catalog_snapshot_current_idx ON model_catalog_snapshots (provider, model_id, discovered_at DESC);

CREATE TABLE IF NOT EXISTS model_lifecycle_events (
    event_id UUID PRIMARY KEY, snapshot_id UUID REFERENCES model_catalog_snapshots(snapshot_id),
    event_type TEXT NOT NULL, previous_status TEXT, new_status TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL, refresh_id UUID REFERENCES provider_catalog_refreshes(refresh_id)
);
CREATE INDEX IF NOT EXISTS model_lifecycle_event_history_idx ON model_lifecycle_events (snapshot_id, occurred_at DESC);

CREATE OR REPLACE VIEW current_model_catalog_snapshots AS
SELECT DISTINCT ON (provider, model_id) * FROM model_catalog_snapshots
ORDER BY provider, model_id, discovered_at DESC;
