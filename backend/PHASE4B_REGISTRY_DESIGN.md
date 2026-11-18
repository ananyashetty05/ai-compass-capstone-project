# Live Model Pool — Registry Design and Implementation (Phase 4B design, Phase 5 implementation)

**Status (18 Nov 2026):** implemented and tested against an *isolated local PostgreSQL-compatible
database* (PGlite, PostgreSQL 18.6 in WASM). **Not yet applied to Neon.** The migration
`migrations/20261118_live_model_registry.sql` has not been run on any Neon branch; no production data
was read or written. `LIVE_REGISTRY_ENABLED` defaults to `false`, so a deployment behaves exactly as before
until the migration is approved and applied.

## 1. Principles

- Catalog **visibility** ≠ **inference access** ≠ **routing eligibility**. Each is a separate, individually
  reported fact.
- A newer model never retires an older one. Only provider-reported lifecycle or repeated absence from a
  *successful, fully understood* provider list changes a model's lifecycle.
- Unknown metadata stays unknown (`null`). Discovery never invents quality, latency, reliability or risk.
- Ordinary routing never waits on provider discovery and never calls a provider. If registry storage is
  unavailable, routing falls back to the static catalog.
- Snapshots, lifecycle events and verifications are append-only. History is never deleted or rewritten.
- Organization-scoped persistence stays deferred (no server-derived organization identity exists yet);
  the registry is one system-wide catalog.

## 2. Architecture

| Module | Responsibility |
|---|---|
| `services/provider_discovery.py` | Official-API discovery per provider; normalisation, row validation, classified errors |
| `services/registry_lifecycle.py` | Lifecycle states and allowed transitions, each with a reason |
| `services/model_registry_store.py` | Neon persistence: leases, transactional append-only refresh, verifications, history, activity |
| `services/registry_eligibility.py` | Pure eligibility decision with machine-readable exclusion codes |
| `services/registry_service.py` | Read-side merge of static + live + verification + eligibility; routing overlay; 30 s cache |
| `services/inference_verification.py` | One-model, admin-triggered, minimal inference probe through the existing adapter |
| `api/routes/models.py` | Read APIs, token-protected admin APIs, rate limiting |
| `frontend/.../components/registry/LiveRegistry.tsx` | Provider health, refresh controls, activity, server-paged catalogue, detail block |

Existing static catalog, adapters, candidate filter, multi-objective router (weights, tie-breaking,
scoring), explainability, feedback and personalization are unchanged.

## 3. Canonical identity and metadata

- Canonical key: `<provider-lowercase>:<provider model id>` (e.g. `openai:gpt-4.1`). Gemini's
  `models/<id>` resource prefix is stripped so live entries match static entries.
- Static curated entries and live entries with the same key are **one model**: live evidence overlays
  availability/lifecycle on the curated entry; curated scores are never replaced by discovery.
- New `ModelMetadata` fields (all optional): `canonical_key`, `first_seen_at`, `lifecycle_reason`,
  `deprecated_at`, `retires_at`, `consecutive_missing_refreshes`. `RegistryEntry` adds `catalog_origin`
  (`static|live|application`), `eligibility`, `verification`, `catalog_last_confirmed_at`, `catalog_stale`.
- Provenance (`metric_provenance`) distinguishes provider-published, estimated and unavailable values.
  Discovery marks everything it did not receive as `unavailable`.
- Freshness is provider-level (`last_success_at` vs `REGISTRY_REFRESH_TTL_MINUTES`); an unchanged model is
  not re-appended, so per-model timestamps record *change*, not *confirmation*.

## 4. Provider discovery status

| Provider | Mechanism | Pagination | Status |
|---|---|---|---|
| OpenAI | `GET https://api.openai.com/v1/models` (Bearer) | none | Implemented |
| OpenRouter | `GET https://openrouter.ai/api/v1/models` (Bearer) | none | Implemented (pricing, context, input modalities) |
| Groq | `GET https://api.groq.com/openai/v1/models` (Bearer) | none documented | Implemented. The `active` flag is **not** interpreted as a lifecycle signal (not documented as one). |
| Anthropic | official SDK `models.list` | handled by SDK (`after_id` cursor) | Implemented. Provider-reported `lifecycle`, `deprecated_at`, `retires_at` are stored. SDK is used rather than hand-written headers because the documentation page's auth/version header guidance was ambiguous. |
| Google Gemini | official `google-genai` `models.list` | handled by SDK (`pageToken`) | Implemented. |

Endpoints were checked against official documentation in November 2026. **No live provider call has been
made** (no credentials in the build environment); discovery is tested against stubbed provider payloads
only. Verify with real keys on a test branch before relying on it.

Hardening: fixed HTTPS URLs, configurable timeout, 20 MiB response cap, 5 000-model cap, ID pattern
validation, duplicate/malformed row rejection (counted, never silently trusted), negative/invalid prices →
unknown, and a response with rows but *none* usable is treated as `malformed_response`, never as an
authoritative empty list. Errors are classified (`not_configured`, `authentication`, `rate_limited`,
`timeout`, `network`, `malformed_response`, `upstream`) and carry fixed safe messages only.

## 5. Lifecycle

States: `newly_discovered`, `pending_validation`, `active`, `deprecated`, `unavailable`, `retired`,
`incompatible` (plus `discovery_failed`, retained for schema compatibility).

- First sighting: `newly_discovered`; `incompatible` if no adapter exists; `deprecated`/`retired` if the
  provider says so.
- Next successful refresh: `newly_discovered → pending_validation`; `pending_validation → active` once
  inference is verified (also promoted immediately when a verification succeeds).
- Absent from `REGISTRY_MISSING_REFRESHES_BEFORE_UNAVAILABLE` (default 2) consecutive successful, fully
  understood provider lists → `unavailable`. A refresh with any rejected row, or any failed refresh, proves
  nothing about absence.
- Reappearing models re-enter `pending_validation` (or `active` if previously validated and merely
  unavailable/deprecated). `retired` is set only from provider data.
- Provider refresh status (`provider_catalog_refreshes`) and inference verification
  (`model_inference_verifications`) are independent of lifecycle.

## 6. Routing eligibility (`registry_eligibility.py`)

Exclusion codes: `not_inference_model`, `provider_disabled`, `provider_not_configured`,
`adapter_incompatible`, `lifecycle_excluded`, `inference_not_verified`, `inference_verification_stale`,
`inference_verification_failed`, `metadata_incomplete`. Warnings: `deprecated`, `stale_catalog`.

- **Curated static models** keep their existing behaviour (configured + adapter-compatible) unless live
  evidence excludes them: lifecycle `unavailable`/`retired`/`incompatible`, or a latest verification failing
  with `invalid_model`/`authentication`. Transient verification failures (timeout, rate limit) do not exclude.
  *Design decision:* requiring verification of curated models would have changed existing routing behaviour.
- **Live-discovered models** need *all* of: configured, enabled, adapter-compatible, lifecycle `active`, a
  successful verification no older than `REGISTRY_VERIFICATION_MAX_AGE_DAYS` (14), **and** complete
  provider-published scoring metadata (quality, cost, latency, reliability, risk, pricing).
  **Consequence:** discovery alone currently cannot add a model to routing, because providers do not
  publish quality/latency/reliability/risk and this system refuses placeholders. Live discovery therefore
  gives visibility, lifecycle tracking, availability confirmation and exclusion of withdrawn models. An
  explicit enrichment path (admin-supplied or benchmark-derived metadata with provenance) is the next step
  if discovered models should become routable.
- Applications/tools are never API routing candidates.

## 7. Routing integration

`model_registry.get_catalog_with_exclusions(task, modality, live=True)` returns
`(catalog, registry_exclusions)`:

1. Configured static API models + consumer applications (unchanged selection logic).
2. `registry_service.apply_live_registry` removes models excluded by live evidence and admits eligible
   live-only models. It reads a 30-second cache of persisted state, never contacts a provider, and returns
   the input unchanged if anything fails.
3. `routing.py` prepends registry exclusions to `filtered_out`, so the explanation shows
   `Live registry: <reason>`. Selecting an excluded model via `model_ids` yields a clear 422 instead of
   "unknown model".
4. Hard constraints (privacy, capabilities, modality, cost, latency, context) still run in the existing
   candidate filter *before* scoring; scoring weights, normalisation and tie-breaking are untouched.

`get_catalog_for_recommendation` (used by offline evaluation/research) stays static and deterministic.

## 8. Database (Neon PostgreSQL) — additive, idempotent, not applied

`provider_catalog_refreshes` (status, trigger, lease, counts, safe error), `model_catalog_snapshots`
(append-only JSONB + content hash + canonical key), `model_lifecycle_events` (with reason),
`model_inference_verifications` (append-only), and views `current_model_catalog_snapshots`,
`current_inference_verifications`.

- Concurrency: unique partial index → at most one `running` refresh per provider. Expired leases (5 min) are
  marked `abandoned` before a new lease is taken. A refresh that lost its lease cannot write (row-locked
  `status = 'running'` check inside the persistence transaction).
- Atomicity: all snapshots/events/counters of a refresh commit in one transaction; provider-mismatch or
  duplicate IDs roll the whole refresh back.
- Idempotency: content-hash comparison; an unchanged catalog appends nothing.
- Last-known-good: provider failure only records a refresh row; snapshots are untouched.
- Parameterized SQL only; no credentials, prompts or upstream bodies are stored.
- Rollback: disable `LIVE_REGISTRY_ENABLED`; tables hold history only and nothing else depends on them.

## 9. APIs (`/api/v1`)

Read (public, no secrets): `GET /models` (static + apps; `include_live` opt-in), `/models/catalog`
(search, provider, origin, lifecycle, eligible, sort, page, page_size ≤ 100), `/models/detail`,
`/models/eligibility`, `/models/registry-status`, `/models/refresh-history`, `/models/activity`,
`/models/{provider}/{model_id}/lifecycle-history`.

Admin (header `X-Registry-Admin-Token`, constant-time compare, 20 calls/min per instance):
`POST /models/registry/refresh` (`provider?`, `only_if_stale`), `POST /models/registry/verify`
(one model; 10-minute per-model cooldown), and the legacy `POST /models/discover/{openai|openrouter}`,
which previously let any caller spend provider quota and are now protected. With no
`REGISTRY_ADMIN_TOKEN` configured they return 503; with persistence disabled, refresh/verify return 503
without any provider call.

## 10. Refresh orchestration and scheduling

Manual refresh per provider or for all configured providers, sequentially, each bounded by the provider
timeout (lease 5 min). `only_if_stale` honours `REGISTRY_REFRESH_TTL_MINUTES` (default 360). Failures are
recorded with a classified code and fixed message and retried only by the next explicit/scheduled call.

*Scheduled refresh (evaluated, not configured):* the app runs on serverless Vercel, so there is no
long-lived worker. A platform cron calling the protected refresh endpoint with `only_if_stale=true` is the
fit, but it needs a deployment change (`vercel.json`), a secret, and a check of current Vercel cron limits;
none of that was done. The in-process rate limiter is per instance and is not a distributed limit.

## 11. Security

Credentials only from server configuration, never stored/returned/logged; admin token held in browser
memory only (never persisted or placed in URLs); upstream errors reduced to fixed strings; provider IDs
validated against a strict pattern; admin endpoints fail closed; verification limited to one text model per
call with a cooldown; no inference in routing or on page load.
**Limitations:** the admin token is a shared secret, not per-user roles (the user model has none); the rate
limit is per serverless instance; registry reads are unauthenticated like the existing catalog.

## 12. Testing

`tests/test_live_registry.py` — 55 tests. Without `TEST_DATABASE_URL` the 33 pure/unit/API tests run and 22
database tests skip. With an isolated database all pass, including: real SQL migration (twice), first
refresh, idempotency, metadata change, absence threshold and reappearance, partial-response safety, failure
preservation and error sanitisation, rollback on invalid data, live/expired leases, late-writer rejection,
concurrent refresh, TTL, verification promotion, static overlay, the admin API end to end, and real
`/route-and-generate` with live evidence.

Last run: **105 passed, 2 skipped** with an isolated PGlite database (app tables initialised); **70 passed,
37 skipped** without one. Frontend: `tsc -b` clean, `oxlint` 0 warnings/errors on `src`, `vite build` succeeds.
**Not done:** execution against a real Neon branch; live-provider calls; automated or manual browser
interaction testing of the new UI; load testing.

## 13. Approval decisions still open

1. Create an isolated Neon test branch, set `TEST_DATABASE_URL`, run the suite there.
2. Approve applying the migration (test branch first, then production).
3. Set `REGISTRY_ADMIN_TOKEN` and decide who holds it; consider real admin roles later.
4. Approve a scheduled refresh mechanism and TTL.
5. Decide on a metadata-enrichment path if discovered models should become routable.
6. Organization identity (still deferred).
