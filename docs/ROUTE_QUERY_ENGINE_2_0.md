# Route Query Engine 2.0

Status legend used throughout: **Implemented** (built and tested) · **Partial** (built, with stated limits) · **Designed** (documented, not built) · **Unavailable** (blocked by missing data or access).

## 1. What it does

One request flows through a single pipeline (`backend/app/services/routing_engine/pipeline.py`). Each stage is timed and reported to the UI exactly as it ran; skipped stages carry the reason.

| # | Stage | Module | Status |
|---|-------|--------|--------|
| 1 | Input validation | `pipeline.py` | Implemented |
| 2 | Query understanding | `understanding.py` | Implemented (rule-based) |
| 3 | Preference resolution | `preferences.py` | Implemented |
| 4 | Prompt optimization | `optimizer.py` | Implemented |
| 5 | Candidate discovery | `model_registry` (canonical registry) | Implemented |
| 6 | Hard-constraint filtering | `filtering.py` | Implemented |
| 7 | Multi-objective scoring | `scoring.py` | Implemented |
| 8 | Model selection | `scoring.select` | Implemented |
| 9 | Execution (opt-in) | `execution.py` | Implemented; tested with mocked adapters only |
| 10 | Response evaluation | `execution.evaluate_response` | Partial (deterministic checks; no judge model) |
| 11 | Explanation | `explain.py` | Implemented |

Two modes: **recommend** (default; no model is run, nothing is spent) and **execute** (opt-in; uses the configured provider key and can cost money).

## 2. Query understanding

Produces one typed `QueryProfileV2`: primary and secondary intents, domain, complexity (0–1 with the component breakdown), required capabilities and modalities, token estimates, explicit vs inferred requirements, ambiguities (with clarifying questions), and a risk assessment.

* Complexity is a weighted sum of eight features: sub-tasks .20, constraints .15, reasoning depth .20, technical depth .15, context size .10, intent breadth .10, output demand .05, structured output .05. Categories: <0.2 simple, <0.4 moderate, <0.6 complex, otherwise highly complex.
* Token counts are heuristic (≈4 characters per token, or `tiktoken` when importable) and always labelled estimates.
* Risk detection covers credentials, card/ID numbers (Luhn-checked), contact data, and financial, medical, legal and security subject matter. Matched text is never stored or echoed.
* Credentials in a prompt block execution. A query that needs clarification also blocks execution.
* Limit: the analyzer is a lexical rule engine. It does not understand meaning and will misread unusual phrasing.

## 3. Prompt optimizer

Modes: `disabled`, `conservative` (spacing, capitalisation, punctuation), `standard` (adds the constraints you stated and short task guidance), `advanced` (also isolates pasted code/quotes as delimited data and suggests a structure), `custom` (per-option).

Safeguards, verified in code before any rewrite is accepted: pasted code and quoted blocks stay verbatim; prose keeps the same words; every number is kept and none is invented; quoted strings are kept. If a check fails the rewrite is discarded and the normalised original is used, then the original itself. The original is never mutated. Quality figures are heuristic indicators and say they are not validated against answer quality.

The UI lets you preview, edit, restore the original, and choose which prompt is submitted.

## 4. Preferences and precedence

1. Application security and safety constraints.
2. Request-level hard constraints (max cost, max latency, capabilities, privacy, model pool).
3. User-level hard restrictions (excluded providers/models).
4. Weights: request override, then saved profile, then system default.
5. System defaults (quality .30, cost .15, latency .15, reliability .20, risk .10, task fit .10).

Query-derived weight adjustments are bounded (≤1.5×), reported, and re-normalised.

## 5. Hard-constraint filtering

Runs before scoring. Every exclusion is a structured record with a code, the requirement, the reason, evidence and permanence. Unknown values cannot pass a limit: a model with no verifiable price is excluded by a cost cap (`cost_unverifiable`). Both input and output prices are needed to compute a request cost.

## 6. Scoring methodology (SCORING_VERSION 2.0.0)

* All utilities are in [0,1], higher is better.
* **Quality** = registry estimate × task discount `(0.6 + 0.4·fit)` + a feedback adjustment clamped to ±0.2.
* **Cost** = log-min-max of estimated USD per request when every candidate is priced; otherwise `1 − registry estimate`.
* **Latency** = log-min-max of observed or measured seconds when every candidate has them; otherwise `1 − registry estimate`.
* **Reliability** = Wilson lower bound once ≥5 observed requests exist; otherwise the registry estimate.
* **Risk** = `1 − max(model risk, exposure)`; exposure is the query's sensitivity unless the model's data handling is documented as restricted.
* **Task fit** = 0.7 × primary-intent match + 0.3 × secondary-intent coverage.
* **Missing data** is never zero and never best: utility is `None`, confidence is 0 for that dimension, and the robust score subtracts `(1 − confidence) × 0.25` from each utility before weighting.
* Ranking uses the robust score. Ties (within 0.005) break by preferred provider, then data confidence, then lower cost, then model id.
* The Pareto frontier is computed over quality, cost, latency, reliability and risk. Dominated models list their dominators.
* Weight stability re-ranks under ±20% weight perturbations. Selection confidence = 0.5·data confidence + 0.3·stability + 0.2·margin (high ≥0.75, medium ≥0.5). A query that needs clarification caps confidence at 0.45.
* Results are deterministic: the same inputs give the same order.

All static-catalog metrics are labelled `estimated`. Nothing in the catalog is a measurement.

## 7. Execution

Provider adapters are used as before. Retries apply only to errors the adapter marks retryable, with exponential backoff and full jitter, and are bounded per model. Authentication failure skips that provider. Total attempts, escalation depth, wall-clock deadline and USD budget are all bounded; a budget cannot be enforced against an unknown price, so such a model is skipped. Escalation moves only to a higher-quality candidate. Repeated requests with the same `idempotency_key` return the first result (an in-process cache, so it does not survive a restart or span several workers).

## 8. Response evaluation

Acceptance (and therefore escalation) depends only on deterministic checks: non-empty, not a refusal, valid JSON when JSON was requested, stated length limits. The older lexical relevance/completeness heuristic is shown but is advisory and cannot reject a response, because it was rejecting reasonable short answers and triggering paid escalations. **No judge model is configured, and the output says so.**

## 9. Persistence

`backend/migrations/20261119_route_query_engine.sql` creates `routing_decision_log` and `routing_execution_log`. **It has not been applied to any real database.** Until it is, routing works and history endpoints return 404. Stored: ids, weights, scores, statuses, timings, costs and a short summary for non-sensitive queries. Never stored: prompt text, response text, credentials, or any summary of a sensitive query.

## 10. API

* `POST /api/v1/analyze-query` – legacy flat keys plus `profile`.
* `POST /api/v1/optimize-prompt` – `mode`, `options`, `model_id`; returns the original and optimized prompts, changes, checks and warnings.
* `POST /api/v1/route-and-generate` – the previous response shape plus `engine` (stages, profile, preferences, candidates, exclusions, selection, explanation, execution, evaluation). No eligible candidate returns 422 with a string detail.
* `GET /api/v1/routing-history`, `GET /api/v1/routing-history/{id}`.

New request fields: `mode`, `optimization_mode`, `optimization_options`, `optimized_prompt`, `submit_prompt`, `preferred_providers`, `excluded_providers`, `excluded_model_ids`, `weight_overrides`, `budget_usd`, `evaluate_response`, `idempotency_key`.

## 11. Tests and benchmark

* Backend: 174 tests pass without a database; 216 pass with an isolated PGlite database and both migrations applied (three registry API tests assert the no-database behaviour, so they fail only when a test database is configured, as before).
* New engine tests cover understanding, optimizer safety, filtering, scoring decision scenarios, execution with mocked adapters, the pipeline, the API, and the decision log.
* `python -m benchmarks.route_engine_benchmark` compares always-strongest, always-cheapest, a static default ranking, and engine 2.0 on 14 fixed scenarios. All numbers are registry estimates. Real response quality, latency, spend and user satisfaction are reported as **not measured**. The previous engine is kept only as a backup and is not run.

## 12. Known limitations

* Only the configured providers' models are executable; in the current environment that is a single OpenRouter model, so comparison tables show one candidate.
* The analyzer, token estimates and prompt-quality indicators are heuristics.
* Execute mode has been tested only with mocked adapters; no real provider call was made.
* Idempotency is per process.
* The legacy response fields map unavailable utilities to 0.0 for schema compatibility; `engine.candidates[].utilities` keeps `null`, and that is the field the UI uses.
