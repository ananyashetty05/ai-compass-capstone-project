# ER-PCR — Evidence-aware Robust Preference-Constrained Routing

One recommendation algorithm for AI Compass. It replaces the scoring and selection stages of the unified algorithm; the six-stage pipeline, the API shape, the approved-ecosystem category-first design and the registry are unchanged. Deterministic, no LLM, no provider or network call, no database migration.

Status of claims: everything below is **implemented** unless it says *future*. No claim here is a measured accuracy improvement: AI Compass has no independently labelled ground truth, so none can be made.

## 1. Defects found in the previous algorithm (root causes)

| # | Defect | Root cause | Correction |
|---|---|---|---|
| D1 | Hand-set editorial quality, latency, reliability and risk numbers decided winners | Registry numbers were scored as if measured | Tiered evidence; only documented/measured/derived-with-named-process evidence may rank (§3) |
| D2 | A candidate with more filled-in metadata could beat a better candidate | Confidence/evidence coverage was added into the score; missing values were scored as a 0.5 prior minus a penalty | An unknown earns **no credit** and is reported as a gap; coverage never adds to suitability (§4) |
| D3 | Every objective ranked, including ones the user never asked about | Default weights applied to all five dimensions | Only task fit + objectives the **user** prioritised rank; the rest are displayed (§4) |
| D4 | Query-inferred multipliers (difficulty, sensitivity) changed rankings | Hand-set constants (x1.25, x0.9 …) shared the weight vector with stated wishes | Inferred multipliers are display-only; explicit wording ("cheaply", "very accurate") is a stated priority |
| D5 | "cheaply" was not recognised as a cost request | Regex matched `cheap`/`cheapest` only | Lexicon extended (`cheaply`, `cheaper`, `affordable`, `economical`, `low-priced`) |
| D6 | Pool-dependent normalisation | min-max over the current candidates | Fixed log anchors, independent of other candidates (§4) |
| D7 | Ties silently resolved by list order | tolerance window / list order | Exact ordering; any tie is reported as `indistinguishable` with the tied set |
| D8 | Confidence read as accuracy | single heuristic number | Renamed in text: a decision-reliability index, "not a probability"; capped when evidence is insufficient |
| D9 | Offline-evaluation baselines read ranked utilities | utilities used for display and ranking alike | Baselines read the displayed (labelled editorial) value explicitly |

## 2. Pipeline (unchanged stages, new internals)

1. Query understanding (`understanding.py`) — deterministic lexical rules; explicit requests vs inferred difficulty/sensitivity kept apart (`WeightAdjustment.origin`). Not machine learning.
2. Eligibility (`filtering.py`) — hard constraints; unknown price cannot satisfy a cost cap; unknown privacy cannot satisfy a mandatory privacy requirement; every exclusion is a structured record.
3. Evidence cells (`cells.py`, `evidence.py`, `data/evidence_records.py`) — one cell per (candidate, objective).
4. Scoring (`scoring.py`, `decision.py`, `normalization.py`, `policy.py`).
5. Selection + decision status (`scoring.select`, `decision.status`, `robustness.py`).
6. Explanation (`explain.py`).

All thresholds are in `policy.py` (`ErPcrPolicy`).

## 3. Evidence

| Tier | Meaning | May rank |
|---|---|---|
| T3 measured | dated measurement or observed telemetry with a sample | yes |
| T2 documented | published by the provider/vendor, or registry value with named provenance | yes |
| T1 estimate | derived by a named deterministic process (e.g. exposure from the query's sensitivity) | yes |
| T1u unverified estimate | hand-set registry number with no named source or method | **no** — displayed and labelled |
| T0 unknown | no value | no |

Rules: stale evidence is demoted one tier; an undated T3 counts as T2; evidence applies only to the exact `model_id` (ids carry the version) and a matching task scope; freshness windows are per-metric policy (pricing 90 d, benchmark 180 d, telemetry 30 d, capability/privacy 365 d). Each metric carries value, unit, source, tier, date, scope, method, sample size, freshness and a note. `data/evidence_records.py` is the application-level store (empty on purpose — no value is fabricated); adding an `EvidenceRecord` needs no migration. The `plan` field is recorded but not yet matched (*future*).

## 4. Mathematics

Objectives J = {fit, quality, cost, latency, reliability, risk}; every utility u ∈ [0,1], higher always better.

- **Fixed-anchor normalisation.** cost: u = 1 − (log₁₀c − log₁₀c_best)/(log₁₀c_worst − log₁₀c_best), clamped, c in USD/request, anchors 1e-5…0.1; latency likewise with 0.2…60 s; c=0 → 1. NaN, infinite or negative → unknown (never best or worst). Risk suitability = 1 − exposure; exposure is 0 for documented restricted handling (T2), else the query's sensitivity (T1).
- **Primary set P** = {fit} ∪ {d : the user's normalised explicit weight of d exceeds its default share}. Inferred multipliers never enter.
- **Weights.** P = {fit}: w_fit = 1. Otherwise w_fit = f (0.55), w_d = (1−f)·e_d / Σ_{k∈P\{fit}} e_k, e_d the explicit weight of d. Weights are validated (finite, ≥ 0, sum > 0) and rejected, never silently repaired.
- **Score.** S_i = Σ_{d∈P} w_d · u_id · 1[cell (i,d) is rankable]. Display-only best case U_i = Σ w_d · (u_id if rankable else 1). Gaps_i = {d ∈ P : not rankable}. An unknown is neither zero nor perfect: it earns nothing and is reported.
- **Order (exact).** (−round(S,12), −feedback, not preferred_provider, known cost, approved-list order, model_id). Personalisation feedback (bounded ±0.2) can only separate candidates whose evidence-credited scores are exactly equal. The order of two candidates depends only on those two, so adding or removing others cannot change it.
- **Weight margin (exact).** Smallest total-variation weight shift at which the runner-up overtakes the leader, from the fractional-knapsack solution (`robustness.py`, verified against brute force). Stability = min(1, margin/0.10).

Why not minimax/maximin/Hurwicz: with unverifiable unknowns they would let an invented best/worst case decide. The design separates *suitability* (S), *evidence reliability* (gaps, tiers) and *decision robustness* (weight margin, ties) instead.

## 5. Decision status

`no_eligible_candidates` · `needs_clarification` · `insufficient_evidence` (a prioritised objective cannot be verified for the top candidate) · `indistinguishable` (exactly equal evidence; returned as a set via `alternative_ids`) · `qualified` (feedback separated them, or the lead is not robust to a 10 % re-weighting) · `recommended`. `selection.status` keeps its old value ("selected") for client compatibility; `decision_status` is additive.

## 6. API / frontend

Additive fields: `Selection.decision_status/decision_reason/alternative_ids/evidence_gaps/not_ranked`; `CandidateScore.score_upper/evidence_gaps`; `MetricEvidence.tier/used_in_ranking/freshness/source/date/sample_size`. `utilities[d]` may now be `null` (unverified). The Route Query page shows the decision status and the equally-suitable set.

## 7. Runtime

No network or provider call in ranking (asserted by a test that blocks `socket.connect`). Measured on this development machine with `python research/er_pcr_benchmark.py` (median / p95): 50 candidates — filter+score+select 4.9 / 7.4 ms; full pipeline 20.2 / 28.3 ms. 200 candidates — 22.3 / 36.5 ms and 96.3 / 148.7 ms. Machine-specific; not a latency guarantee. Request-level caching of the registry already exists in the pipeline.

## 8. Limitations (honest)

- **No ground truth.** Nothing here shows that recommendations are more *accurate*. The design makes them more *defensible*: every ranking input is documented, measured or derived by a stated rule.
- **Cost of the brief's rule.** Excluding unverified editorial ratings means that without evidence records, many requests cannot be separated. On the 27-query approved-ecosystem evaluation set, 20 queries now return `indistinguishable`, 3 `needs_clarification`, 3 `recommended`, 1 `insufficient_evidence`. Previously every query returned a single ordered answer driven partly by editorial ratings. Filling `evidence_records.py` with sourced benchmarks is the path to more separation.
- Quality-focused requests become `insufficient_evidence` until a benchmark record exists for the model and task.
- The live-pool default ranks on task fit only; price, speed, reliability and quality are shown, and rank only when the user prioritises them (or telemetry exists).
- Task fit comes from declared capabilities/tasks and documented vendor features; it is a lexical match, not a measured capability.
- Freshness windows and anchors are policy choices, not empirical constants.
- The decision-reliability index (0–1) is a heuristic summary, not a calibrated probability.
- The 47 skipped tests need `TEST_DATABASE_URL` (an isolated Neon test database); they were not run. `tests/test_catalog_api.py::test_offline_defaults_are_honest` fails (503 vs 403) independently of this change.
