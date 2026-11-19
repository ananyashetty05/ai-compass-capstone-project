-- Autonomous model catalogue + generation lifecycle. ADDITIVE and IDEMPOTENT. NOT APPLIED to any database.
-- Apply to Neon only after explicit authorisation. It creates new tables only: no existing table is altered or dropped,
-- and no existing data is touched. Models are never deleted by the application; retirement is a state, so routing logs,
-- evaluations and traces that reference a model id stay readable.

CREATE TABLE IF NOT EXISTS catalog_meta (
    id SMALLINT PRIMARY KEY CHECK (id = 1),
    version BIGINT NOT NULL DEFAULT 0,
    published_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS catalog_developers (
    slug TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS catalog_lineages (
    lineage_key TEXT PRIMARY KEY,
    developer_slug TEXT,
    data JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS catalog_generations (
    generation_key TEXT PRIMARY KEY,
    lineage_key TEXT NOT NULL REFERENCES catalog_lineages (lineage_key),
    retention TEXT NOT NULL,
    verification TEXT NOT NULL,
    data JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS catalog_generations_lineage_idx ON catalog_generations (lineage_key, retention);

CREATE TABLE IF NOT EXISTS catalog_models (
    canonical_key TEXT PRIMARY KEY,
    developer_slug TEXT,
    lineage_key TEXT NOT NULL REFERENCES catalog_lineages (lineage_key),
    generation_key TEXT REFERENCES catalog_generations (generation_key),
    verification TEXT NOT NULL,
    retention TEXT NOT NULL,
    lifecycle TEXT NOT NULL,
    publication TEXT NOT NULL,
    availability TEXT NOT NULL,
    data JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS catalog_models_publication_idx ON catalog_models (publication, developer_slug);
CREATE INDEX IF NOT EXISTS catalog_models_lineage_idx ON catalog_models (lineage_key);

-- One row per (underlying model, provider, provider-specific model id): price and URLs belong here, never on the model.
CREATE TABLE IF NOT EXISTS catalog_offerings (
    offering_key TEXT PRIMARY KEY,
    canonical_key TEXT NOT NULL REFERENCES catalog_models (canonical_key),
    provider TEXT NOT NULL,
    listed BOOLEAN NOT NULL DEFAULT TRUE,
    data JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS catalog_offerings_model_idx ON catalog_offerings (canonical_key);

CREATE TABLE IF NOT EXISTS catalog_sources (
    source_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    data JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS catalog_events (
    id BIGSERIAL PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    from_state TEXT,
    to_state TEXT,
    reason TEXT,
    run_id TEXT
);
CREATE INDEX IF NOT EXISTS catalog_events_entity_idx ON catalog_events (entity_key, id DESC);
CREATE INDEX IF NOT EXISTS catalog_events_type_idx ON catalog_events (event_type, id DESC);

CREATE TABLE IF NOT EXISTS catalog_refresh_runs (
    run_id TEXT PRIMARY KEY,
    trigger TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    summary JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS catalog_refresh_runs_started_idx ON catalog_refresh_runs (started_at DESC);
