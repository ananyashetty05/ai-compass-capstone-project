# AI Compass: backend research validation plan

This file documents what the current implementation can support and the experiments
that should be completed before making comparative research claims.

## Implemented pipeline

1. Deterministic keyword/length query profiling.
2. Candidate filtering using active status, supported tasks/domains, context window,
   optional cost/latency limits, and required capabilities.
3. Weighted candidate scoring using quality, cost, latency, reliability, risk, and
   query-to-model capability-fit metadata.
4. Model-specific template-based prompt adaptation.
5. Deterministic response checks and fallback escalation.
6. Human-readable explanation derived from scores, weights, query profile, and user profile.

## Interpretation limits

- Query analysis is heuristic; it is not a trained classifier.
- Registry quality, cost, latency, reliability, and risk values are metadata/priors.
  They must not be reported as observed measurements unless their provenance and
  measurement procedure support that claim.
- `preference_alignment` is currently a proxy for query-to-model task/domain fit.
  It is not a direct semantic measurement of an individual user's preferences.
- The response evaluator uses lexical overlap, response length, refusal patterns, and
  a small set of risk phrases. It is a heuristic acceptance check, not a factuality,
  safety, or semantic-quality benchmark.
- The existing baseline endpoint runs strongest-model, cheapest-model, and static
  ranking strategies, but it does not by itself establish statistical superiority.

## Recommended controlled experiment

1. Freeze the model pool, query dataset, user profiles, prompts, and configuration.
2. Use the same query IDs and eligibility constraints for each routing strategy.
3. Include AI Compass, strongest-model, cheapest-model, static-ranking, and a
   clearly specified cascade baseline where feasible.
4. Apply a consistent prompt policy across strategies, or report prompt adaptation
   as a separate experimental factor.
5. Log per query: strategy, selected/final model, acceptance score, evaluator version,
   provider latency, token usage, actual/estimated cost, escalation attempts, and errors.
6. Repeat runs where providers are stochastic; report sample size, means/medians,
   dispersion, and confidence intervals where appropriate.
7. Run ablations: remove profile weights, risk dimension, prompt adaptation, and
   escalation one at a time. Compare quality/cost/latency/reliability trade-offs.
8. Validate the response evaluator against a labeled subset or an independent evaluator.

Do not claim a research gap is closed solely because the modules exist. The claim should
be tied to reproducible evidence from this protocol.
