# AI Compass — Phase 1 Engineering Notes

## Implemented behaviour

AI Compass is a recommendation-first routing system. `POST /api/v1/route-and-generate`
analyses a query, applies hard constraints, ranks eligible catalog entries, returns an
optimised prompt, and identifies an external destination. It does **not** invoke a
provider model in this workflow. Consequently, its response evaluation has method
`not_applicable_recommendation_only`, is not accepted, and is not a quality claim.

The query analyser is a deterministic keyword-and-length heuristic. It exposes its
method, confidence estimate, and uncertainty notes; it is not a trained classifier.

## Routing sequence

1. Validate the query and resolve the authenticated user's saved preferences.
2. Build a heuristic `QueryProfile`.
3. Build the actionable catalog: configured API integrations plus consumer
   applications. Unconfigured API records remain visible through `/models`, but are
   not selected as recommendation destinations.
4. Filter hard constraints before scoring: active status, modality, inferred and
   explicit capabilities, domain, context window, maximum cost, and maximum latency.
5. Score eligible models with normalised weights for quality, cost efficiency,
   latency efficiency, reliability, risk suitability, and capability-fit alignment.
6. Resolve equal scores deterministically by model ID and expose score breakdowns,
   filters, weights, provenance, and uncertainty in the explanation.

No model is fabricated when no candidate passes filtering; the API returns a clear
validation error.

## Metadata and provenance

Bundled registry rows are documentation snapshots. `metric_provenance` identifies
provider-published capabilities/context/pricing separately from estimated quality,
latency, reliability, and risk values. `metadata_status=stale` means the bundled
snapshot must not be interpreted as live verification. Missing price metadata cannot
satisfy an explicit maximum-cost constraint. Estimated scores are routing inputs, not
benchmarks or response-quality guarantees.

## Evaluation, escalation, and inference

`response_evaluator.py` is a deterministic heuristic for actual provider text only.
It uses lexical/rejection signals and is not factuality, semantic-quality, or safety
verification. The current public routing flow does not call it on generated provider
text. Escalation remains reserved for a future/explicit actual-inference flow and is
bounded by `MAX_ESCALATION_ATTEMPTS`; it is not represented as having happened for a
recommendation.

## Feedback and personalisation

Feedback is isolated by user ID and now requires a recorded routing ID owned by that
user and the matching selected model. Satisfaction estimates use a prior, require at
least three ratings before influencing routing, and apply a bounded bonus. They are
not reinforcement learning and are not model training.

## Configuration and deployment

Required production environment variables:

- `JWT_SECRET`: signing secret for JWTs.
- `DATABASE_URL`: PostgreSQL/Neon connection URL for users, decisions, and feedback.
- Provider keys only for providers that AI Compass should mark executable:
  `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`,
  `OPENROUTER_API_KEY`.

Database table creation is idempotent and happens during application lifespan rather
than module import. The app can expose health/OpenAPI while persistence is unavailable;
health reports `degraded` rather than claiming readiness. The restored `api/index.py`
is the Vercel Python entry point. No deployment was performed.

### Isolated Neon testing

Set `TEST_DATABASE_URL` only to a dedicated Neon test branch or separate test
database before running persistence tests. The pytest configuration deliberately
sets `DATABASE_URL` from this test-only variable and never falls back to the normal
`DATABASE_URL`; without it, feedback persistence tests are skipped with an explicit
reason. Do not point `TEST_DATABASE_URL` at production.

The production schema currently requires the idempotent `routing_decisions` table
creation before ownership-validated feedback can be used. This is a backward-
compatible `CREATE TABLE IF NOT EXISTS` change, but it has not been applied to Neon
in this workspace because database mutation/deployment requires explicit approval.

## Verification

Run backend tests from `backend` with its virtual environment:

```bash
.venv/bin/python -m pytest -q
```

Run the frontend production check from `frontend`:

```bash
npm run build
```

The repository virtual environment must contain the dependencies in
`backend/requirements.txt`, including `psycopg[binary]`, for database-backed tests
and application startup with PostgreSQL.
