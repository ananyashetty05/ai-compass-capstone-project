# Phase 4B — Persistent Provider-Aware Registry Design

## Current findings

The registry is an in-process static catalog plus consumer applications. OpenAI and
OpenRouter have credential-gated discovery functions. Phase 5 adds append-only persistence
code and an additive migration artifact, but the migration is intentionally not applied by
startup or this change set.
Adapters exist for OpenAI, Anthropic, Gemini, Groq, and OpenRouter. Discovered entries
are deliberately inactive/incomplete, so ordinary recommendation routing does not wait
for discovery or use an unvalidated model. PostgreSQL currently persists users,
feedback, satisfaction aggregates, and routing-decision ownership—not registry state.

## Provider discovery matrix

| Provider | Design discovery source | Credential/access meaning | Adapter | Decision |
|---|---|---|---|---|
| OpenAI | authenticated `GET /v1/models` (implemented) | Lists models visible to supplied project/key; not entitlement for every feature | Yes | Persist snapshots after validation. |
| OpenRouter | authenticated `GET /api/v1/models` (implemented) | Catalog/pricing metadata; gateway access can still vary by key/route | Yes | Persist snapshots after validation. |
| Anthropic | No model-list API assumed in current design | Key validates only when an actual documented request succeeds | Yes | Keep documentation snapshot; no discovery implementation without verified official API. |
| Gemini | Google Gen AI documented model-list operation must be verified against SDK/API version before implementation | Returned models indicate API visibility, not quota/region guarantee | Yes | Design hook only; verify official contract first. |
| Groq | OpenAI-compatible model-list operation must be verified against current Groq docs before implementation | Returned list indicates key-visible catalog | Yes | Design hook only; verify official contract first. |

No provider discovery result grants routing eligibility by itself. API keys are read only
from server configuration and are never stored in registry tables or returned to clients.

## Minimum Neon schema (proposed; not applied)

`provider_catalog_refreshes`

- `refresh_id UUID PK`, `provider TEXT NOT NULL`
- `status TEXT NOT NULL` (`running|success|failed|abandoned`), `started_at`,
  `finished_at`, `lease_expires_at`
- `last_success_at`, `error_code TEXT NULL`, `error_message_safe TEXT NULL`
- unique partial constraint for one `running` refresh per `provider`; a later worker
  may reclaim only an expired lease after recording the abandoned outcome.

`model_catalog_snapshots`

- `snapshot_id UUID PK`, `provider TEXT NOT NULL`, `model_id TEXT NOT NULL`,
  `snapshot JSONB NOT NULL`, `lifecycle_status`, `adapter_compatible`,
  `metadata_status`, `observed_at`, `refresh_id`.
- Append-only; unique `(provider, model_id, refresh_id)`. A current-catalog view selects
  the newest successful snapshot, while prior metadata remains reproducible.

`model_lifecycle_events`

- append-only `event_id UUID PK`, `snapshot_id UUID`, `event_type`,
  `previous_status`, `new_status`, `occurred_at`, `refresh_id NULL`.

Snapshots retain historical metadata. Existing routing decisions continue to store their
selected string ID; no destructive delete is needed. Organization-scoped persistence is
deferred: `organization_id` must first come from an established server-side membership
model, never from the browser. Until then, use one system catalog and do not claim
organization-specific access.

## Refresh and lifecycle workflow

1. A scheduler or authorized manual endpoint checks provider TTL (suggested 24 hours).
2. Acquire the per-provider running-refresh lease transactionally. The lease has an
   expiry; a later worker may mark an expired `running` refresh as abandoned/failed and
   acquire a new lease. Return active-lease status to concurrent callers.
3. Call only that provider's documented discovery API with a bounded timeout and no
   routing request dependency.
4. Validate ID uniqueness, provider match, adapter compatibility, and minimum metadata.
   Append snapshots/events transactionally only after success; never overwrite earlier
   snapshots.
5. Mark absent previously discovered entries `unavailable` only after a successful
   provider response; never after a failed refresh. Retirement requires explicit provider
   evidence or policy review, not version-name comparison.
6. On failure, record a safe status/error code, retain last-known-good catalog, and show
   stale state. Retry once only for timeout/rate-limit according to provider guidance.

Eligibility requires `active` lifecycle state, documented/validated required metadata,
and adapter compatibility. A provider model-list only establishes catalog visibility; it
does not establish inference access. Mark inference access as `unverified` until a safe,
provider-specific access check or successful inference establishes it. Consumer
applications remain recommendation destinations only.

## Migration, rollback, security, tests

The prepared additive migration is `migrations/20261118_live_model_registry.sql`; it creates
the tables, indexes, and current-snapshot view only. It is not run by application startup.
After explicit approval and migration application, set `LIVE_REGISTRY_ENABLED=true` in the
deployment environment; it defaults to false so ordinary catalog reads remain static-safe.
Backfill no production records; seed append-only snapshots through an approved
manual refresh. Rollback disables readers/writers and leaves history intact—never deletes
snapshots. Restrict refresh APIs to admins, redact upstream errors, use parameterized SQL,
and never persist credentials. Organization fields are intentionally omitted until the
authentication model supplies a server-derived organization identity.

Required isolated-Neon tests: concurrent lease acquisition; expired-lease recovery;
successful append-only snapshot creation; current-view selection; failed refresh fallback;
duplicate prevention; active/deprecated/retired transitions; historical decision lookup;
discovered-but-ineligible exclusion; model-list visibility versus unverified inference
access; credential absence; and safe provider error redaction. Add organization-isolation
tests only after organization identity exists in authentication.

## Unresolved approval decisions

1. Source of `organization_id` and admin authorization (current schema is user-centric);
   organization-scoped catalog persistence is deferred until this is established.
2. Scheduler host/trigger and acceptable TTL/cost.
3. Official Gemini/Groq discovery contract validation before implementation.
4. Dedicated Neon test database and approval for additive migration.

## Implemented Phase 5 boundary

`model_registry_store.py` implements append-only snapshots, provider refresh leases,
lease-expiry recovery, safe failure records, and last-known-good reads after an approved
migration. The registry read path merges persisted live entries with the static catalog, but
discovered records have null unknown metrics, `newly_discovered` lifecycle state, unverified
inference access, and are excluded from routing. Read-only status/history APIs are available.

No refresh API is exposed: the current authentication model has no administrator identity, so
an authenticated user must not be able to trigger provider calls. Add that endpoint only after
server-side admin authorization is approved.
