# Autonomous model catalogue — design, operations and limits

AI Compass discovers, compares, selects and redirects. It is **not** an inference provider, so discovery never needs a
paid inference API or key. Three things are kept separate everywhere: *discoverable* (we know it exists), *externally
accessible* (a provider offers it) and *executable through AI Compass* (we have an adapter and a credential).

## Pipeline

```
sources ──► observations ──► merge ──► availability ──► retention ──► publication guard ──► one versioned commit
(untrusted)   (per offering)  (per model,    (from offerings)  (per lineage,    (>25% drop /          (atomic; stale
                              provenance)                      2 generations)   invariants abort)      writer loses)
```

* `app/services/catalog/sources.py` — adapters. OpenRouter public catalogue (aggregator), Hugging Face developer
  repositories (rotating organisations, time-budgeted), and the bundled documentation snapshot (offline, labelled stale).
  None needs a key. All fetches go through `safe_http.py` (https only, host allow-list, DNS must resolve to public
  addresses, no credentials in URLs, redirects re-validated, size and time caps, JSON only).
* `merge.py` — canonical model = `developer:canonical_slug`; **offering** = one provider's way to access it, which owns its
  own price and URLs. The highest-authority source wins each field; disagreements are stored as conflicts. Unknown stays
  `null`; a price of `-1`/missing is never converted to 0 (an explicit `"0"` is a real free price).
* `versions.py` — generic generation classifier (no vendor names in code). Versions are numeric tuples (3.10 > 3.9) or date
  tuples; names with no marker are *unmanaged* and never retired.
* `retention.py` — per lineage (`developer:family:track`: text, image, embedding… are independent) the latest **two verified**
  generations stay active; older verified ones become *superseded* (kept, labelled retired, removed from every active
  surface). Variants follow their generation. Ambiguity (mixed version schemes, low-confidence parse, a higher version
  released clearly *before* a lower one) → `pending_review`, no destructive action. A lineage can never end with zero retained.
* `engine.py` — due-source scheduling with exponential back-off, time budget, completeness checks, absence counting (a model
  missing from a response is **not** discontinued: it needs 3 consecutive complete, in-scope, plausibly-sized responses and
  then only the *offering* becomes unlisted), mass-removal guard, events, optimistic commit. A refresh that changes nothing
  writes nothing but source health.
* `registry.py` — the single read-side registry. Model Pool, Inspect, comparison, evaluation, routing and recommendations all
  read `published_models()`; `all_models()` / `/models/detail` still resolve retired models so logs and evaluations stay
  readable. Works offline from the bundled snapshot; a database failure serves the last good view, never an empty one.

## Verification levels
`detected` (one source) → `corroborated` (two distinct sources, or an aggregator listing that persisted ≥24 h for a
registered developer) → `officially_confirmed` (official documentation or the developer's own repository). Only
`corroborated`+ is published. An aggregator announcement alone never retires anything.

## Database
`migrations/20261121_model_catalog.sql` — new tables only, idempotent, **not applied anywhere**. Models are never deleted;
retirement is a state. `catalog_events` is the audit trail; `catalog_refresh_runs` the refresh history.

## Scheduling and operations
* Vercel Cron → `GET /api/v1/catalog/cron` with `Authorization: Bearer $CRON_SECRET`; runs only sources that are due.
  `vercel.json` currently schedules **daily** (the safe value for every plan; Hobby rejects anything more frequent).
  Raise it (e.g. `0 */3 * * *`) on a plan that allows it; per-source intervals then take effect.
* Admin: `POST /api/v1/catalog/refresh?force=true[&source=openrouter]` with `X-Registry-Admin-Token`.
* Add a developer without code: add it to `app/data/developers.json`, or `POST /api/v1/catalog/developers` (admin).
* Enable: apply the migration to an approved database, then set `CATALOG_PERSISTENCE_ENABLED=true`, `CRON_SECRET`,
  `REGISTRY_ADMIN_TOKEN`. Until then the app serves the offline snapshot and says so.

## Known limits
* Live endpoints were not reachable from the development sandbox: adapters are tested on fixtures built from the public
  response schemas, not on live responses. First live run must be watched.
* No local PostgreSQL was available: `PgStore` and the migration are verified for statement shape and ordering (fake
  connection, SQL parse) but not executed against PostgreSQL.
* Discovered models have no benchmark data. Quality, latency, reliability and risk stay unknown (never averaged in); the router
  treats unknown pessimistically, so a newly discovered model will rarely be *chosen* until curated or measured.
* OpenRouter coverage is limited to models OpenRouter lists; developers' own announcement feeds are not scraped (no stable,
  documented public feed was integrated). Developers outside OpenRouter/Hugging Face are covered only by the snapshot.
* Neon's pooled endpoint does not keep session state; the advisory lock is only an optimisation, correctness rests on the
  versioned commit.
* Vercel `crons` alongside the `services` layout in `vercel.json` has not been exercised on a deployment.

## Addendum (2026-11-19): benchmarks, pagination, announcements
- **Benchmark evidence.** OpenRouter relays Artificial Analysis indices (0-100). They are stored on the model as `benchmarks` with source/via/scale and
  are used ONLY as `estimated_quality = intelligence_index / 100` when no curated estimate exists, labelled `metric_provenance.quality = "benchmark_reported"`.
  Latency, reliability and risk stay unknown. A curated estimate always wins. Absent or out-of-range values are dropped, never defaulted.
- **Pagination.** Hugging Face follows `Link: rel="next"` for up to `MAX_PAGES` (3) per organisation; an organisation is only "completely listed" when no
  further page exists and the last page was not full, so absence is never inferred from a truncated list.
- **Source statuses.** `ok | partial | failed | rate_limited | timed_out`; none of them ever remove catalogue data.
- **Release announcements** (`announcements.py`, source `announcements`). Official RSS feeds listed per developer in `developers.json` (`release_feeds`,
  must be https on the developer's `official_domains`). Verified feeds today: OpenAI, Google. Anthropic publishes no feed at the URL I tried (404), so none
  is registered. A post that names an already-tracked family followed by a version becomes an `announcement_detected` event labelled `already_listed` or
  `not_yet_listed`. Announcements never create, publish or retire a model; verification still comes from catalogue sources. Limitation: a brand-new family
  name that the catalogue does not track yet cannot be recognised from a title.
- **Rotating Hugging Face window.** Six of the registered organisations are read per run, so a second run legitimately sees different ones; idempotency is
  therefore asserted on stable sources only (see `scripts/catalog_db_check.py`).

## Addendum: Model Pool classification and counts
- `app/services/model_classifier.py` assigns ONE `primary_category` (conversational | developer | application | unclassified) plus a `category_kind` from structured evidence only: curated taxonomy, declared input/output modalities, OpenRouter chat-completions listing, and name tokens the developer itself uses (instruct/chat/it, coder, rerank, whisper...). Provider name is never evidence. HF repositories without an instruct-style name are `base_model`; this is a naming heuristic, flagged `classification_basis: derived`.
- `capability_tags` overlap by design and are never summed. `use_categories` (routing audience tags) are derived from the primary category.
- `GET /models/pool-stats` (`app/services/pool_stats.py`) computes every headline figure from the same list `/models` returns, with an integrity audit (exactly one primary category, reconciliation, no duplicate canonical keys, retired excluded, applications not counted as models, offerings counted separately).
