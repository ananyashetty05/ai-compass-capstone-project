# AI Compass: Algorithm V2 Specification

Status: **DRAFT FOR APPROVAL. Design only. No application code, schema, credential, deployment or GitHub state was changed to produce this document.**
Scope: model/tool *recommendation* only. AI Compass does not call the recommended product, does not read an answer, and does not escalate.
Basis: the repository as inspected on 2026-11-20 (`POOL_SOURCE=approved`, 37 approved products, cap 50), including the uncommitted working-tree changes made earlier in this project.

> **ERRATA (2026-11-20): this draft has been superseded in part by `backend/ALGORITHM_V2_REVIEW.md`. It is NOT approved for implementation.** The review found, among other things: the frontier-first ranking key breaks the removal/insertion properties claimed in 8.4 (P3 is false for it); `σ` must use the best rival's `H` (example 3.3 gives −0.255, not −0.175; the lower-bound order there is A, B, D, C); the relative-scaling breakpoint ε* overstates stability (use a weight-space margin; 0.0778 in example 3.4); the ε-tie rule is non-transitive; clipping biases midpoints; observed T3 reliability/latency conflicts with the recommendation-only boundary; and estimated token counts cannot support a budget guarantee. Where this text conflicts with the review, the review governs. The original text below is left unchanged.

Numbers in sections 3 and 6 are either (a) arithmetic you can redo by hand, or (b) the output of a throw-away prototype that lives outside the repository (`/tmp/v2/*.py`) and exists only to check that the equations behave. **They are not benchmark results.** Nothing here measures how good any model is.

---

## 0. How to read this document

| Section | Content |
|---|---|
| 1 | Audit of the existing algorithm (what it really does, what is unsupported) |
| 2 | Formal specification, stages A to H |
| 3 | Worked numerical examples |
| 4 | Algorithm comparison and the recommendation |
| 5 | Data requirements and schema changes |
| 6 | Pseudocode and complexity |
| 7 | Confidence methodology |
| 8 | Sensitivity analysis |
| 9 | Test specification and offline evaluation design |
| 10 | Research contribution and limitations |
| 11 | Migration and backward compatibility |
| 12 | Implementation roadmap |

Terminology used throughout:

- **Tier** (evidence tier): `T0` unknown, `T1` estimated (editorial or registry estimate), `T2` published (vendor documentation, price page), `T3` measured (benchmark with a documented method, or observed history with a sample size).
- **Interval** `[lo, hi]`: the range a value may plausibly take given its tier. It is *not* a confidence interval unless the tier is `T3` with a sample size.
- **Policy parameter**: a number the designers choose and document (for example the width of a `T1` interval). It is never presented as a measured statistic and is swept in the sensitivity analysis.

---

## 1. Audit of the existing algorithm

### 1.1 The actual path from query to recommendation

There are two scoring regimes behind one pipeline (`routing_engine/pipeline.py`).

```
query
 └─ understanding.analyze()            lexical rules -> intents, domain, complexity, risk, tokens, explicit/inferred requirements
     ├─ audience.assess()              conversational vs developer (regex), clarification flag
     └─ ecosystem.resolve()            approved pool only: ONE of 7 categories (regex rule scores)
 └─ preferences.resolve()              base weights (request > saved > default) x query-derived multipliers -> weights; hard constraints
 └─ model_registry.get_catalog_with_exclusions()   pool (approved: 37 products; live: catalogue + applications)
 └─ filtering.filter_candidates()      lifecycle, exclusions, category gate (approved) or audience/modality/capability/context gate (live),
                                       cost / latency / strict-privacy constraints (unknown -> excluded)
 └─ scoring.score_candidates()
     ├─ approved:  score_ecosystem()   alignment (0.55) + user-weighted editorial estimates (0.45)
     └─ live:      6 objectives, log min-max cost/latency, provenance-discounted quality, Wilson reliability
 └─ scoring.select()                   sort by robust score R, tie rules, weight-stability trials, confidence value
 └─ routes/routing._build_response()   one ranking -> Best Match / Suggested (ranks 2-4) / Candidates (approved pool only)
```

Answers to the ten questions in the brief:

1. **Requirement extraction.** `understanding.py` applies hand-written regular expressions and keyword tables (`_score_intents`, `_classify_domain`, `_extract_requirements`, `_detect_ambiguities`). Each `Requirement` carries `origin ∈ {explicit, inferred}` and an `evidence` string, but **no per-requirement confidence and no "unknown" state**. Intent and domain have one scalar confidence each (`understanding.py:238`, `:255-257`).
2. **Categories and capabilities.** Two parallel classifiers exist: `audience.assess()` (conversational vs developer) and `ecosystem.resolve()` (seven approved categories). Capabilities are matched as string tags (`supported_tasks` plus `capabilities` for the live pool, `strengths` for the approved pool).
3. **Filtering.** `filtering.check_model()` runs lifecycle, user exclusions, pool, then either `_category_checks` (approved) or `_audience_checks` plus modality, capability and context checks (live), then `_constraint_checks` (cost, latency, strict privacy). Unknown price, latency or data handling **fails** the corresponding constraint (`cost_unverifiable`, `latency_unverifiable`, `privacy_unverified`). This part is sound.
4. **Objectives.** Live pool: quality, cost, latency, reliability, risk, preference_alignment (task fit). Approved pool: alignment (feature, intent, category fit) plus editorial quality, speed, reliability, risk; cost only on a stated preference.
5. **Normalization.** Live pool: **candidate-relative** log min-max for cost and latency (`scoring.py:202`). Quality, reliability and risk are already 0-1 and used as given. Approved pool: no normalization (ratings are already 0-1).
6. **Missing and estimated metrics.** Missing: utility 0 and confidence 0, flagged ("pessimistic" policy). Estimated: used as if it were a point value, then reduced by `(1-c)·ρ` with `ρ = 0.25` and `c` taken from a constant table by provenance (`scoring.py:45`).
7. **Weights.** `preferences.resolve()`: request override, else saved profile, else `DEFAULT_WEIGHTS = (q .30, c .15, l .15, rel .20, risk .10, fit .10)`; then multiplied by query-derived factors (inferred cap 1.5x, explicit cap 2.5x), renormalised, and quality is floored at 0.18.
8. **Winner.** Highest robust score `R = Σ w_d · max(0, u_d − (1−c_d)·ρ)`; ties within `ε = 0.005` break by preferred provider, evidence confidence, lower cost, approved-list order, model id.
9. **Confidence.** Live pool: `0.5·evidence + 0.3·weight_stability + 0.2·min(1, margin/0.1)`. Approved pool: `0.35·category_conf + 0.35·min(1, margin/0.1) + 0.30·feature_support`, capped at 0.45 or 0.60 for ambiguity. Levels at 0.75 and 0.50.
10. **Frontend.** `RouteQuery.tsx` renders Best Match, Suggested and Candidates from `engine.ranking` for the approved pool. For the live pool it still uses `ranked_alternatives` and registry-derived `tool_recommendations`, which are separate lists.

### 1.2 Findings

Severity: **S1** can change a recommendation for reasons unrelated to the user's request; **S2** weakens a claim; **S3** hygiene.

| # | Sev | Finding | Where | Why it matters |
|---|---|---|---|---|
| F1 | S1 | Cost and latency utilities are **candidate-relative**. Adding or removing an unrelated model changes everyone's score. | `scoring.py:202` | Rank reversal. Example in 3.1: a model's cost utility moves from 0.500 to 0.667 when a fourth, unrelated model is added. |
| F2 | S1 | Two different scoring regimes decide the same question. The approved path gives alignment a fixed 55% share (`ALIGN_SHARE`, `scoring.py:116`) and ignores the user's `preference_alignment` weight (default 0.10). | `scoring.py:116`, `preferences.py:20` | A stated preference weight does not mean the same thing in the two pools. Prototype: with the user-weight regime the winner for "image of a red car" and "cinematic video" differs from the current winner (section 3.6). |
| F3 | S1 | **I introduced hand-set editorial ratings** (`RATINGS` in `data/approved_ecosystem.py`) and they now affect ranking. They are labelled "editorial estimate" in the UI, but they are my judgement, not data. | `approved_ecosystem.py` | Ranking within a category is now partly a function of numbers nobody measured. Section 2 treats them as tier `T1` so they widen intervals instead of acting as facts. |
| F4 | S2 | The selection-confidence value is an **average of constants** (0.5/0.3/0.2 and 0.35/0.35/0.30) and the two pools use different formulas for the same concept. Thresholds 0.75 and 0.50 are unvalidated; `calibration.py` itself says nothing is calibrated. | `scoring.py:176-182`, `:443` | A number like 0.529 reads as a probability. It is not one. |
| F5 | S2 | Missing metrics become utility 0 inside a sum. The "utility" `U` is therefore a mixture of evidence and ignorance, and it is not comparable between a complete and an incomplete model except through the penalty. | `scoring.py:~286-290` | An unknown is indistinguishable from "known to be worst". |
| F6 | S2 | The uncertainty penalty is `(1-c)·ρ`, linear in a constant `c` per provenance label (`measured 1.0, benchmark 0.9, provider_published 0.85, estimated 0.6`). None of these has a derivation. | `scoring.py:45`, `types.py:291` | Looks like an uncertainty model, behaves like a fixed discount. |
| F7 | S2 | Pareto dominance is computed only among candidates with the **same set of known objectives**, lists at most five dominators, and **does not influence selection**. A dominated candidate can outrank its dominator because of the confidence penalty (3.7). | `scoring.py:336-362` | The `pareto_optimal` flag and the ranking can disagree. |
| F8 | S2 | Query-derived weight multipliers (complexity, sensitivity, domain) are invented constants (1.15, 1.2, 1.25, 1.3, 1.4, 1.5, 0.8, 0.85, 0.9) and a quality floor of 0.18 overrides the user's weights. They are reported, but they are still silent preference invention in the sense of the brief. | `preferences.py:68-132` | The final weights are not the user's weights. |
| F9 | S2 | Stability is measured by perturbing **one weight at a time by ±20%** (12 trials). It ignores metric uncertainty, ignores candidate changes, and ±20% is a constant. | `scoring.py:~418`, `types.py:294` | "Stability 0.92" has no stated meaning beyond those 12 trials. |
| F10 | S2 | Heuristic classifications gate eligibility. A wrong category removes the right product with no second chance, except when the rules themselves detect an overlap. Category confidence is `0.6·min(1, top/3.5) + 0.4·margin`. | `ecosystem.py`, `filtering.py:_category_checks` | Ground truth is a regex outcome. |
| F11 | S2 | The learning bonus (±0.2) is added **inside the quality utility** (`scoring.py:~245`). Personal feedback is mixed into a metric that is supposed to describe the model. | `scoring.py` | Quality is no longer a model property. |
| F12 | S2 | Strict privacy cannot be satisfied by any approved product: none has `data_handling_status` documented (default `unknown`), so a strict-privacy request returns "no eligible candidates". This is correct behaviour, but it means the privacy path is untested against real data. | `approved_ecosystem._build` | Semantics are right; coverage is empty. |
| F13 | S3 | The risk objective subtracts a *query* sensitivity term (`exposure`) from every model with undocumented data handling. The term is identical for all of them, so it shifts scores without separating anything. | `scoring.py:303` | Cosmetic for ranking, misleading in the display. |
| F14 | S3 | Duplicated logic: two category systems (`audience`, `ecosystem`), two scorers (live, approved), a separate approved offline-evaluation path (`evaluation._approved_offline`), counterfactuals that re-run the pipeline with fixed ×2 scenarios for only three dimensions. | several | Fixes need to be made in more than one place. |
| F15 | S3 | `ModelMetadata` has no field for measurement method, sample size, or measurement date per metric. Only `metric_provenance` (a string) and a record-level `last_verified_at`. | `schemas/model.py` | The evidence model the brief asks for cannot be expressed. |
| F16 | S3 | Live-pool consistency between Best Match, Suggested and Candidates is not guaranteed because those lists are built separately. | `RouteQuery.tsx`, `routing.py` | Fixed for the approved pool only. |

What works and should be preserved: hard constraints run before scoring and cannot be bought back by a high score; unknown price, latency and privacy fail verified-evidence constraints; credentials never enter filtering or ranking (covered by `test_approved_ecosystem.py`); the pipeline is deterministic for equal inputs; the recommendation-only boundary is enforced.

---

## 2. Formal specification

### 2.0 Sets, indices, notation

| Symbol | Meaning |
|---|---|
| `M` | The catalogue pool, `|M| = N ≤ 50`, ordered by `editorial_order` (approved-list position) |
| `m ∈ M` | A product or model |
| `Q` | The query requirement vector (2.1) |
| `E(m,Q) ∈ {0,1}` | Eligibility (2.2) |
| `M_Q = {m : E(m,Q)=1}` | Eligible set, size `n` |
| `D = {quality, cost, latency, reliability, risk, fit}` | Objectives, `|D| = 6` |
| `u_d(m) = [ℓ_d(m), h_d(m)] ⊂ [0,1]` | Utility interval of `m` on objective `d`. Higher is always better |
| `t_d(m) ∈ {T0,T1,T2,T3}` | Evidence tier of that value |
| `w ∈ Δ^{|D|-1}` | Weight vector, `w_d ≥ 0`, `Σ w_d = 1` |
| `L_m(w), U_m(w), H_m(w)` | Conservative, midpoint and optimistic utility (2.5) |
| `ε` | Relative weight perturbation radius |
| `ε*_m` | Weight breakpoint of the winner (7.2) |

### 2.1 Stage A: structured query representation

```
Q = ( category, task, domain, modality, capabilities, complexity, budget, latency, privacy, preferences )
```

Every component is a **requirement record**:

```
Requirement = {
  field:      one of the ten components above
  value:      the requirement
  status:     explicit | inferred | unknown
  source:     "user_field" | "query_phrase" | "rule:<rule_id>" | "default"
  evidence:   matched text or rule ids
  support:    ordinal in {strong, moderate, weak}   (inferred only)
}
```

Rules:

1. `explicit` means the user stated it in a structured field (max cost, max latency, strict privacy, required capabilities, model pool, excluded providers) or in an unambiguous phrase that a rule recognises as a requirement ("must", "need", "only", "at most").
2. `inferred` means a rule fired on wording the user did not frame as a requirement (for example, `category=image` from "red car"). It carries the list of rule ids that fired and an ordinal `support`.
3. `unknown` means no rule fired. Unknown is **never defaulted into a value that later acts as a constraint**. It may be defaulted into a *soft* default that is shown as such.
4. `support` for an inferred requirement is derived from rule evidence, not from a made-up probability:
   - `strong`: at least one high-specificity rule fired and no competing rule scored within 50% of it.
   - `moderate`: a rule fired and a competing rule scored within 50%.
   - `weak`: only low-specificity rules fired, or the winning rule score is below the one-strong-rule score.

   The 50% margin and "one strong rule" are policy parameters (`P_support`), recorded in the response.
5. **Ambiguity handling.** The query is *qualified* (not blocked) when:
   - the two best categories have `support = moderate` (overlap), or
   - the audience classifier flags `ambiguous`, or
   - any `explicit` requirement could not be matched to a catalogue field.

   A qualified recommendation carries the ambiguity, runs the algorithm for the top two categories, and reports whether Best Match agrees (8.5). The confidence level is capped at `low` when the two category runs disagree and at `moderate` when they agree.
6. Heuristic outputs are labelled `analysis_method = lexical_rule_engine`. No component is reported as ground truth.

Current-code mapping: `QueryProfileV2` already has `explicit_requirements`, `inferred_requirements`, `ambiguities`, `needs_clarification`, `category`, `confidence`. Missing: per-requirement `status=unknown`, `support`, and rule ids on `explicit` items (section 5).

### 2.2 Stage B: hard-constraint eligibility

```
E(m,Q) = Π_{c ∈ C(Q)} 1[ verified(m,c) ∧ sat(m,c) ]
```

`C(Q)` is the set of **mandatory** constraints that apply to this query. `verified(m,c)` is true only if the evidence needed to decide `c` has tier `≥ T2` (published or measured). A constraint that cannot be verified **fails**; an eligible candidate never relies on an estimate to pass a mandatory constraint.

| Constraint | Mandatory when | `sat(m,c)` | Needed evidence | Unknown behaviour |
|---|---|---|---|---|
| Lifecycle / active | always | `active ∧ lifecycle ∉ {retired, incompatible}` | registry state | fail |
| Pool / exclusions | user supplied | `m ∈ pool`, provider and id not excluded | none | n/a |
| Category | approved pool: always | `serves(m, category)` (primary or documented secondary) | curated classification (`T2`) | fail |
| Sub-type | `category` demands one (voice vs music) | `subtype_ok(m, s)` | curated | fail |
| Modality | live pool | `need ⊆ have` | declared modalities (`T2`) | fail |
| Required capabilities | **explicit** requirement only | `req ⊆ capabilities(m)` with each cap at `≥ T2` | declared capability | fail |
| Context window | live pool | `tokens ≤ context` | declared window | fail if request is long (`> 16000` tokens) and window unknown |
| Max budget | explicit field | `cost(m) ≤ B` where `cost = (n_in·p_in + n_out·p_out)/10^6` | published input and output price (`T2`) | **fail** (`cost_unverifiable`) |
| Max latency | explicit field | `latency_p50(m) ≤ T` | observed p50 (`T3`) or published latency (`T2`) | **fail** (`latency_unverifiable`) |
| Strict privacy | explicit field | `data_handling ∈ {provider_documented_restricted, customer_controlled}` | documented data handling (`T2`) | **fail** (`privacy_unverified`) |
| Open weights / free access | developer intent *and* explicit wording | `weights_status = open_weights` / `pricing ∈ free classes` | documented | fail |

Hard versus soft:

- **Hard**: everything in the table above. A hard constraint is never traded against any objective score.
- **Soft** (objectives, section 2.3): quality, cost (absent a budget), latency (absent a limit), reliability, risk (absent strict privacy), fit.
- **Inferred** requirements are never hard. An inferred capability, modality or privacy need can only become an objective or a sensitivity scenario. The category gate is the one inferred item that acts as a gate; it is therefore the only place where a heuristic can remove a candidate, and it is covered by the ambiguity rules in 2.1.
- **Token estimate caveat.** Cost depends on `n_in`, `n_out`, which come from a heuristic token estimator (`profile.tokens.method`, `exact` flag). A budget constraint is evaluated on the estimate, flagged `estimated_tokens`, and a candidate within 10% of the limit is reported as "borderline" (policy parameter `P_budget_band`).

**No eligible candidate**: `M_Q = ∅` returns `status = no_eligible_candidates`, the per-constraint exclusion counts, and the minimal constraint relaxations that would admit at least one candidate (already implemented in `no_candidate_guidance`).

### 2.3 Stage C: objective functions

All objectives are mapped to a **utility** `u ∈ [0,1]`, higher better, as an interval `[ℓ,h]` plus a tier.

| Objective | Input fields (repository) | Raw unit | Direction | Source / tier | Mapping to utility | Missing-data policy |
|---|---|---|---|---|---|---|
| **Quality** `q` | `estimated_quality`, `metric_provenance["quality"]`, `source`, `last_verified_at` | 0-1 score | higher | benchmark = `T3` (needs method id and sample size); vendor-published = `T2`; editorial = `T1` | identity: `u = value` | `T0`: interval `[0,1]` |
| **Cost** `c` | `input_price_per_million`, `output_price_per_million`, `profile.tokens`; approved: `pricing_category` | USD/request; access class | lower | prices = `T2`; token counts = estimates; access class = `T1` | `u = 1 − clip( log10(cost/c_lo) / log10(c_hi/c_lo), 0, 1 )` with **fixed** `c_lo = 1e-5`, `c_hi = 1e-1` USD/request. Approved pool: ordinal map `completely_free/self_hosted 1.0 · free_tier 0.75 · pay_as_you_go 0.5 · paid_subscription 0.3` | `T0`: `[0,1]` (never 0, never 1) |
| **Latency** `l` | `avg_latency_seconds`, observed p50 (`observed.py`), `estimated_latency`; approved: editorial speed | seconds; 0-1 | lower seconds | observed p50 = `T3` (n ≥ `MIN_SAMPLES`); registry seconds with `measured/provider_reported` provenance = `T2`; normalised estimates = `T1` | seconds: `u = 1 − clip( log10(s/s_lo)/log10(s_hi/s_lo), 0, 1 )`, **fixed** `s_lo = 0.2`, `s_hi = 60`. 0-1 estimates: identity | `T0`: `[0,1]` |
| **Reliability** `r` | observed successes and samples; `reliability` | success rate | higher | observed with `n ≥ MIN_SAMPLES` = `T3`, interval is the **two-sided 90% Wilson interval** (a real statistic); registry value = `T1` | `u = value`; interval from Wilson when observed | `T0`: `[0,1]` |
| **Risk / privacy suitability** `k` | `risk_level`, `data_handling_status`, `profile.risk.score` | 0-1 risk (lower better) | lower risk | model risk = `T1/T2`; data handling = `T2` | `u = 1 − max(risk_level, s_Q · 1[data handling not documented])` where `s_Q` is the query sensitivity score | `T0`: `[0,1]` |
| **Task and capability fit** `f` | requested features (`category.features`), declared `strengths` / `capabilities`, detected intents | coverage | higher | deterministic coverage of documented tags: `T2` (the *tags* are vendor positioning, so this is only as true as that positioning) | see 2.3.1 | nothing requested: `u = 1` for **every** candidate (carries no information, so it cannot separate) |

#### 2.3.1 Fit, without hand-set share constants

```
Rx = explicit feature/capability requests   (user said must/need/only)
Ri = inferred feature requests              (rule-derived)

u_f(m) = |Rx ∩ cover(m)| / |Rx|   if |Rx| > 0
         |Ri ∩ cover(m)| / |Ri|   else if |Ri| > 0
         1                        otherwise
```

- Explicit requests take priority over inferred ones; there is no 0.5/0.3/0.2 blend.
- The old *category fit* (`SECONDARY_ROLE_FIT = 0.85`) disappears. A documented secondary category is eligible (stage B). **Role** (primary vs secondary) is used only as a tie-break (2.7), so no constant is needed.
- For the live pool, `intent_fit` becomes coverage of the primary intent first (required), then secondary intents (informational).
- Interval: `T2` tier, half-width `δ_T2` (2.6).

#### 2.3.2 Cost and latency are scored only when the user asked

If the user stated no cost preference and no budget, cost is **displayed with its tier but given weight 0** (this is the current approved-pool behaviour and is retained). The same rule applies to latency when no latency wish is stated and the pool has no seconds data. Rationale: do not let an ordinal access class or an estimated speed rating steer a recommendation the user did not ask to steer.

### 2.4 Stage D: normalization

Principles:

1. **Per-model, set-independent.** `u_d(m)` is a function of `m`'s own fields and the **fixed reference ranges** only. It must not depend on any other candidate.
2. **Fixed, versioned reference ranges** stored in one place (`reference_ranges_v1`): cost `[1e-5, 1e-1]` USD/request, latency `[0.2, 60]` s, both log-scaled, clipped to `[0,1]`. Ranges are versioned; changing them is a schema-level change recorded in `provenance`.
3. **Zero value.** A price or latency of 0 is clipped to `c_lo`/`s_lo` (utility 1); a *missing* value is `T0`, never 0.
4. **Out of range.** Clipped, flagged `clipped_low` / `clipped_high`.
5. **Different units.** Every utility is dimensionless in `[0,1]`; the unit and source of the raw value are kept in the evidence record.
6. **Missing prices.** `T0` → `[0,1]`. A model with only an input price is `T0` for cost (the request needs both).
7. **Incomparable measurements.** Two latency values are comparable only if both are observed p50 *or* both are registry seconds. A mix is allowed because the mapping is per-model and each value carries its own tier and interval; the mix is visible in the tiers.
8. **A new model entering the registry** changes nothing for existing models: `u_d` of every existing model is identical before and after (testable property P1, section 9). The only effect of insertion is on ranks, and only if the new model outranks existing ones.

Why not min-max: min-max over candidates is a function of the candidate set, so adding an unrelated model reverses ranks (F1, example 3.1). Why not z-scores or rank-based normalization: both depend on the set. Fixed reference ranges are the simplest set-independent choice and their breakpoints are readable (1e-5 to 1e-1 USD per request is "a fraction of a cent to ten cents").

### 2.5 Stage E: multi-objective selection

#### 2.5.1 Interval utility

For weights `w`:

```
L_m(w) = Σ_d w_d · ℓ_d(m)            conservative (every uncertain value at its lower bound)
U_m(w) = Σ_d w_d · (ℓ_d(m)+h_d(m))/2 midpoint
H_m(w) = Σ_d w_d · h_d(m)            optimistic
```

In words: a candidate's score is a range, not a point. `L` is what it is *guaranteed* to be worth under the stated uncertainty; `H` is what it could be worth if every uncertain value turned out favourable.

#### 2.5.2 Certain Pareto dominance

```
a ≻ b  (a certainly dominates b)   ⇔   ∀d ∈ D⁺: ℓ_d(a) ≥ h_d(b)    and    ∃d ∈ D⁺: ℓ_d(a) > h_d(b)
```

where `D⁺ = {d : w_d > 0}` are the objectives that actually carry weight. In words: `a` dominates `b` only if `a`'s *worst case* is at least `b`'s *best case* on every weighted objective, and strictly better on one. A `T0` value is `[0,1]`, so an unknown never dominates and is never dominated by something known; this removes the "same missing signature" workaround of the current code.

Frontier `F = {m ∈ M_Q : ¬∃ a ∈ M_Q, a ≻ m}`.

Properties (provable, and tested): (a) if `a ≻ b` and `w_d > 0` for the strict dimension, then `L_a(w) > L_b(w)` and `H_a(w) > H_b(w)`; (b) the relation is a strict partial order, so `F ≠ ∅` when `M_Q ≠ ∅`.

#### 2.5.3 Selection rule

Pareto filtering is used to **order and explain**, not to delete:

- Every eligible candidate stays in the ranking and the Candidates list.
- Candidates not in `F` are flagged "certainly dominated by X" and are ordered **after** every frontier member.
- Best Match is the first frontier member under the ranking key below. Suggested are the next frontier members (up to 3), then non-frontier members if the frontier has fewer than 4 members.

Reason: deleting dominated candidates would hide information and would break the Candidates list; but a dominated candidate must never be Best Match. With `w_d > 0` for all `d` the dominance order is already implied by `L` (property a); the explicit rule matters when some `w_d = 0` (for example cost unscored), where a dominated candidate can tie on `L`.

#### 2.5.4 Ranking key (deterministic)

```
key(m) = ( m ∉ F,             -L_m(w0),   -U_m(w0),   -H_m(w0),
           role(m) ≠ primary, provider ∉ preferred_providers,
           editorial_order(m), model_id )
```

Applied lexicographically, ascending. `w0` is the resolved weight vector (2.5.5). Equal inputs give an identical order (the key is a total order on distinct `model_id`). Floating values are rounded to 12 decimals before comparison so platform floating-point differences cannot reorder.

Why `L` (maximin) first, `U` second: with a conservative score, a candidate whose strength is mostly *measured* beats one whose strength is mostly *assumed*. With equal interval widths the order by `L` equals the order by `U`, so on the current approved pool (every number is `T1`) `L` and `U` agree except for models with a `T2` fit value. The evidence-aware behaviour only appears once candidates differ in tier, which is the point.

#### 2.5.5 Weights

```
w0 = normalize( user saved weights )   if the user has customised them
     DEFAULT_WEIGHTS                   otherwise (documented, versioned)
```

- Explicit user statements ("cheapest", "fastest", "most accurate") apply the **existing explicit multipliers** (documented table, cap 2.5×), reported individually as `explicit` adjustments.
- **Query-inferred multipliers are removed from `w0`.** Complexity, sensitivity and domain no longer change the point weights. They become **sensitivity scenarios** (8.2): the system reports whether the winner would change if the task were treated as quality-heavy or risk-heavy. This is the change that resolves F8: the weights used to rank are the user's (or the documented defaults), and nothing is silently adjusted.
- The `MIN_QUALITY_WEIGHT = 0.18` floor is dropped from ranking and kept as a *warning* ("your weights give quality under 18%").
- Fit weight: the live-pool default `0.10` is kept for compatibility. When the user made an **explicit** feature request, `w_fit` is multiplied by the explicit factor (cap 2.5×) and the change is listed. The approved pool no longer has a private 0.55/0.45 split (F2).
- Learning feedback (`learning_bonus`) is **not** added to quality (F11). It is applied only inside the tie rule between candidates whose `L` differ by less than `ε_tie`, or reported as a separate "personalisation" annotation. Which of the two is a decision for approval (open item O-3).

### 2.6 Stage F: uncertainty and evidence quality

Every metric is stored as a **metric record**:

```
MetricRecord = {
  value:        number | null
  tier:         T0 | T1 | T2 | T3
  unit:         string
  method:       free text or id ("vendor price page", "editorial rating v1", "observed p50")
  source:       URL or dataset id
  n_samples:    int | null          (T3 only)
  measured_at:  ISO date | null
  lo, hi:       number | null       (only when derived from a statistic, e.g. Wilson)
}
```

Interval construction `[ℓ, h]`:

| Tier | Interval | What it claims |
|---|---|---|
| `T3` observed rate with `n` samples | two-sided Wilson interval at 90% | a real statistical interval, valid only for the stated window and the independence assumptions of the Wilson method |
| `T3` benchmark score | `[v − δ_T3, v + δ_T3]` with `δ_T3 = 0.03` | policy width; the benchmark's own sampling error is not available in the registry, so none is claimed |
| `T2` published | `[v − δ_T2, v + δ_T2]`, `δ_T2 = 0.05` | policy width |
| `T1` estimated / editorial | `[v − δ_T1, v + δ_T1]`, `δ_T1 = 0.15` | policy width; stands for "a relative judgement, not a measurement" |
| `T0` unknown | `[0, 1]` | complete ignorance |

All intervals are clipped to `[0,1]`.

**Honesty clause.** The widths `δ_T1, δ_T2, δ_T3` are **policy parameters, not standard deviations**. The repository contains no repeated observations that would let us estimate one, so none is claimed. The only statistical interval is the Wilson interval for observed success rates. The widths are swept in 8.3; if conclusions are sensitive to them, the response says so.

**Recency.** If `measured_at` (or `last_verified_at`) is older than `P_stale = 365` days, the tier is downgraded by one level (`T2 → T1`, `T3 → T2`). No numeric decay is invented.

**Why intervals and not the current `(1−c)·ρ` penalty.** The penalty subtracts a fixed amount from every estimate, which cannot represent "unknown" (it subtracts at most 0.25 from a number that was never known). Intervals represent unknown as `[0,1]`, estimated as a narrow band and measured as a point, and they support a definition of dominance and of certainty that the penalty cannot.

**What is not claimed.** The system does not report a probability that a model is best, does not compute a posterior, and does not propagate distributions. Intervals bound the *set of values consistent with the evidence tier*; they do not carry likelihoods.

### 2.7 Tie-breaking

Candidates with `|L_a − L_b| < ε_tie` (policy `ε_tie = 0.005`, retained) **and** equal membership in `F` are ordered by the remaining keys in 2.5.4: primary role before secondary, preferred provider, approved-list order, model id. A tie is disclosed: "ordered by approved-list position; no measured difference separates them." This stays in the confidence logic (an exact tie caps the level, 7.3).

### 2.8 Stage G: recommendation confidence

Four separate quantities. **None is a probability.**

1. **Query-understanding confidence** `κ_Q`: an ordinal `{strong, moderate, weak}` taken from the `support` of the category requirement, plus a boolean `qualified` from 2.1(5). Not a number.
2. **Evidence confidence** `P(m)` (evidence precision of the winner):
   ```
   P(m) = 1 − Σ_d w_d · ( h_d(m) − ℓ_d(m) )
   ```
   In words: the weight-averaged width of the winner's intervals, subtracted from 1. `P = 1` means every weighted value is a point; `P = 0` means every weighted value is unknown. It is computed from tiers and weights only.
3. **Objective score**: the triple `(L, U, H)` of the winner, reported as numbers with their meaning.
4. **Selection confidence**: an **ordinal level** derived from four indicators by a *weakest-link* rule (7.3). It is not an average and not a probability.

Indicators:

| Indicator | Definition | Computable today? |
|---|---|---|
| `I_req` requirement certainty | `verified` if no ambiguity, category `support ≠ weak`, and every explicit requirement was matched; else `qualified` | yes |
| `I_sep` separation | `σ = L_top(w0) − H_next(w0)`. `certain` if `σ ≥ 0`; `overlapping` otherwise; `tied` if `|L_top − L_next| < ε_tie` | yes |
| `I_stab` weight breakpoint `ε*` | smallest relative weight perturbation that changes Best Match (7.2) | yes |
| `I_evid` evidence precision | `P(top)` as above | yes |

What requires future calibration: whether `high` actually corresponds to "users agreed with the recommendation". That needs labelled outcomes; `calibration.py` already holds the Brier / ECE instruments and a minimum of 200 labelled outcomes. Until then, the levels describe **how robust the recommendation is to its own inputs**, not how often it is right.

### 2.9 Stage H: sensitivity and robustness

Defined in section 8. Summary of what is computed per request, all on `n ≤ 50` candidates:

| Test | Computation | Indicator |
|---|---|---|
| Weight perturbation | axis and pair perturbations of `w0` with radius `ε`; bisection for the breakpoint | `ε*` |
| Metric uncertainty | compare `L_top` with `H_j` for every `j`; also re-rank with the winner's `T0/T1` values at `ℓ` and everyone else's at `h` (worst case for the winner) | `σ`, `worst_case_rank` |
| Candidate removal | remove each non-winner, then the winner | `winner_survives_removal` (always true by design), `successor` |
| Missing metadata | widen the winner's `T1` values to `[0,1]` and re-rank | `survives_missing` |
| Ambiguous classification | rerun with the second category | `category_agreement` |

---

## 3. Worked numerical examples

Every number below can be checked with a calculator. The script that produced the tables is `/tmp/v2/examples.py` (outside the repository).

### 3.1 Normalization and rank reversal

Costs per request: A = $0.0001, B = $0.001, C = $0.01.

**Current** (log min-max over candidates), with `u = 1 − (log10 c − lo)/(hi − lo)`:

| Model | 3 candidates | + unrelated D = $0.1 |
|---|---|---|
| A | 1.000 | 1.000 |
| B | **0.500** | **0.667** |
| C | 0.000 | 0.333 |
| D | n/a | 0.000 |

B's cost utility changed from 0.500 to 0.667 because D joined. B was not touched.

**V2** with fixed range `[1e-5, 1e-1]`, `u = 1 − log10(c/1e-5)/4`:

| Model | cost | u |
|---|---|---|
| A | 1e-4 | `1 − 1/4 = 0.750` |
| B | 1e-3 | `1 − 2/4 = 0.500` |
| C | 1e-2 | `1 − 3/4 = 0.250` |
| D | 1e-1 | `1 − 4/4 = 0.000` |

Adding or removing D changes none of A, B, C.

### 3.2 Hard constraints

Strict privacy and a budget of $0.002 for a request estimated at 1000 input and 500 output tokens.

| Model | `data_handling` | price in / out ($/M) | cost | Eligible? | Reason |
|---|---|---|---|---|---|
| M1 | documented restricted | 1.0 / 3.0 | `(1000·1.0 + 500·3.0)/10^6 = 0.0025` | **no** | exceeds budget |
| M2 | `unknown` | 0.5 / 1.0 | `0.001` | **no** | `privacy_unverified` (strict privacy) |
| M3 | customer controlled | 0.5 / 1.0 | `0.001` | yes | |
| M4 | documented restricted | `null` | not computable | **no** | `cost_unverifiable` (budget) |

M2 may have the best quality in the registry; it still cannot be recommended. No objective score is consulted.

### 3.3 Interval utility, dominance, maximin

Weights `w = (quality .5, cost .3, latency .2)`. Intervals `[ℓ, h]`:

| | quality | cost | latency |
|---|---|---|---|
| A | `[.80, .80]` measured (`T3`, point) | `[.50, .50]` published | `[.55, .85]` estimated (`.70 ± .15`) |
| B | `[.60, .90]` estimated (`.75 ± .15`) | `[.75, .75]` published | `[.50, .80]` estimated (`.65 ± .15`) |
| C | `[0, 1]` unknown | `[.75, .75]` published | `[.85, .95]` published (`.90 ± .05`) |
| D | `[.70, .70]` | `[.40, .40]` | `[.40, .50]` |

Scores:

```
L_A = .5·.80 + .3·.50 + .2·.55 = .40 + .15 + .11 = 0.660
U_A = .40 + .15 + .2·.70                          = 0.690
H_A = .40 + .15 + .2·.85                          = 0.720

L_B = .5·.60 + .3·.75 + .2·.50 = .300 + .225 + .100 = 0.625
U_B = .5·.75 + .225 + .2·.65                       = 0.730
H_B = .5·.90 + .225 + .2·.80                       = 0.835

L_C = .5·0   + .225 + .2·.85                       = 0.395
U_C = .5·.5  + .225 + .2·.90                       = 0.655
H_C = .5·1   + .225 + .2·.95                       = 0.915
```

- **Dominance.** A vs D: `ℓ_A ≥ h_D` on every objective (`.80 ≥ .70`, `.50 ≥ .40`, `.55 ≥ .50`) and strict on all, so **A ≻ D**; D is ranked after A and flagged "certainly dominated by A". A vs B: `ℓ_A(quality) = .80 < h_B(quality) = .90`, so A does **not** dominate B. C has an unknown quality, so nothing dominates it and it dominates nothing. Frontier `F = {A, B, C}`.
- **Ranking by `L`**: A (0.660) > B (0.625) > C (0.395) > D. **Best Match = A.**
- **Ranking by `U` alone** would give B (0.730) > A (0.690) > C: the estimated B looks better on the midpoint. The conservative rule prefers A because A's quality is measured. This is the evidence-aware behaviour.

### 3.4 Weight breakpoint `ε*`

Perturb one weight by factor `(1 + s·ε)` and renormalise. Reduce quality by 35% (`ε = 0.35`, `s = −1`): the quality weight becomes `0.5·0.65 = 0.325`; total `0.325 + 0.3 + 0.2 = 0.825`:

```
w_q = .3939, w_c = .3636, w_l = .2424
L_A = .3939·.80 + .3636·.50 + .2424·.55 = .3151 + .1818 + .1333 = 0.6303
L_B = .3939·.60 + .3636·.75 + .2424·.50 = .2364 + .2727 + .1212 = 0.6303
```

Equal at `ε = 0.35`, so **`ε* = 0.35`** (script bisection agrees to three decimals; any larger quality reduction flips Best Match to B).

### 3.5 Confidence indicators for the same example

| Indicator | Value | Level |
|---|---|---|
| `I_req` | assume verified | strong |
| `I_sep` | `σ = L_A − H_B = 0.660 − 0.835 = −0.175` | overlapping |
| `I_stab` | `ε* = 0.35` | moderate (bands in 7.3) |
| `I_evid` | `P(A) = 1 − (.5·0 + .3·0 + .2·.30) = 0.94` | strong |

Weakest link: **moderate**. A reader sees why: "A leads, but B could be better if its estimated numbers are favourable."

### 3.6 Prototype on the real approved pool (illustration, not a result)

`/tmp/v2/proto.py` ran the real filter and the real approved data (`RATINGS` and `strengths` as they are in the working tree), then applied V2 with `δ_T1 = 0.15`, `δ_T2 = 0.05`, `w0 = DEFAULT_WEIGHTS` with cost unscored (no cost preference stated).

| Query | Category (support) | V2 Best Match | Current Best Match | `L_top − H_next` | `ε*` | `P` | Frontier |
|---|---|---|---|---|---|---|---|
| Write a Python function to reverse a linked list | coding (1.00) | GitHub Copilot | GitHub Copilot | −0.236 | 0.59 | 0.755 | 6 of 6 |
| Generate an image of a red car | image (1.00) | **Canva** | **Nano Banana** | −0.244 | 0.91 | 0.750 | 7 of 7 |
| Explain photosynthesis to a ten year old | conversational (0.61) | ChatGPT | ChatGPT | −0.233 | 1.14 | 0.771 | 6 of 6 |
| Create a cinematic video of a city at night | video (1.00) | **Gemini Omni / Veo** | **Runway Gen-3** | −0.259 | 0.55 | 0.747 | 5 of 5 |

Reading it honestly:

- **No query reaches `σ ≥ 0`.** With every metric at `T1`, the intervals of the top candidates overlap. Under V2 the approved pool would report at most `moderate` selection confidence until some metric reaches `T2/T3`. That is the correct consequence of having no measured data; it is also a visible product change, so it needs explicit approval (O-1).
- **No candidate is certainly dominated**, because the editorial ratings are close and the intervals are wide. On this data the Pareto step has nothing to remove. It would matter once measured data narrows intervals.
- **Two winners differ from the current engine** (image and video). The difference comes from F2: current code gives alignment a fixed 55% share; the prototype uses the user's weight vector, where fit has weight 0.10. This is a *weight-regime* difference, not evidence that either is correct.
- Sweeping `δ_T1 ∈ {0, 0.05, 0.10, 0.15, 0.25}` changed no winner on these four queries, because every candidate shares the same tier and so every interval has the same width. Tier-dependent widths only matter when candidates have different tiers. Four queries are an anecdote, not a test.

### 3.7 Why the current confidence penalty can contradict dominance

One objective, weight 1, `ρ = 0.25`. A: `u = 0.80`, confidence 0.5. B: `u = 0.75`, confidence 1.0.

```
A dominates B on utility (0.80 ≥ 0.75).
R_A = 0.80 − (1 − 0.5)·0.25 = 0.675
R_B = 0.75 − (1 − 1.0)·0.25 = 0.750        → B outranks its dominator.
```

In V2 both would be intervals; A's `L` is still above B's only if A's interval is narrow enough, and dominance is defined on those intervals, so the dominance flag and the ranking cannot disagree (property a of 2.5.2).

### 3.8 Determinism and exact ties

Two candidates with identical intervals, equal role, no preferred provider: ordered by `editorial_order`, then `model_id`. Re-running yields the same order. The response states "ordered by approved-list position; no measured difference separates them."

---

## 4. Algorithm comparison and recommendation

| Criterion | Existing weighted sum | Pareto + weighted utility | TOPSIS | Robust MOO (min-max regret over uncertainty sets) | SMAA (stochastic acceptability) |
|---|---|---|---|---|---|
| Assumptions | additive utility, fixed weights, penalty constant | additive utility; Pareto as order | additive-distance to ideal/anti-ideal; vector normalization | uncertainty sets over weights and metrics; regret criterion | distributions over weights and metrics |
| Interpretability | high | high | medium ("closeness coefficient") | low for end users | medium (rank acceptability indices) |
| Sensitivity to weights | reported in a limited way | reported | high; ideal points move with the set | explicit by construction | explicit by construction |
| Missing data | utility 0 (conflates unknown and bad) | needs a policy | cannot handle; needs imputation | handles with interval sets | handles with a distribution you must choose |
| Uncertainty handling | constant penalty | none by itself | none | native | native, needs distributions the repo does not have |
| Set independence | no (min-max) | yes if normalization is fixed | **no** (vector normalization and ideal points depend on the set; rank reversal is well documented) | yes | yes |
| Complexity (n ≤ 50, 6 objectives) | `O(nD)` | `O(n²D)` ≈ 15 000 ops | `O(nD)` | solving per candidate: LP/enumeration, tens of thousands of ops | Monte Carlo, ~10⁴ samples × `nD` ≈ 3·10⁶ ops, stochastic unless seeded |
| Fit with our metadata | partial | good | poor (missing data) | good but needs interval widths | poor (no distributions) |
| Deterministic | yes | yes | yes | yes | only with a fixed seed |

Recommendation: **EIPMU: Evidence-Interval Pareto with Maximin Utility**, i.e. stages A to H as specified above:

1. Eligibility gate with verified-evidence semantics.
2. Per-objective interval utilities from fixed reference ranges and evidence tiers.
3. Certain-dominance frontier to order and explain.
4. Maximin weighted utility as the ranking key.
5. Deterministic breakpoint-based sensitivity for confidence.

Why this and not the others:

- It is the smallest change that fixes F1 (fixed ranges), F5/F6 (intervals instead of zero and a constant penalty), F7 (dominance defined on the same intervals the ranking uses), F8 (weights stay the user's), F4/F9 (confidence derived from computed indicators).
- TOPSIS is rejected: its normalization and ideal points depend on the candidate set, which re-introduces F1, and it cannot represent unknown values.
- Full robust min-max regret is rejected as the *primary* method: it is harder to explain, and the interval-plus-breakpoint design delivers most of the benefit (worst-case score, weight robustness) with `L`, `H`, and `ε*`.
- SMAA is kept as an **optional Phase 5 diagnostic**. It needs distributions over weights and metrics that we would have to invent today.
- The existing weighted sum is retained as the midpoint score `U` and remains visible, so the new method is a superset rather than a replacement.

It is not chosen because it sounds sophisticated: every component maps to a defect found in section 1.

---

## 5. Data requirements and schema changes

**The current registry cannot express this specification.** Nothing below exists yet.

### 5.1 Per-metric records (additive)

Add to `ModelMetadata` (all optional, default `None`; old fields stay and are adapted):

```python
class MetricRecord(BaseModel):
    value: Optional[float] = None          # 0-1 utility basis, or native unit for price/latency
    tier: Literal["T0","T1","T2","T3"] = "T0"
    unit: str = ""
    method: Optional[str] = None
    source: Optional[str] = None
    n_samples: Optional[int] = None
    measured_at: Optional[str] = None
    lo: Optional[float] = None             # only when derived from a statistic
    hi: Optional[float] = None

class ModelMetadata(BaseModel):
    ...
    metrics: Dict[str, MetricRecord] = {}  # keys: quality, latency, reliability, risk, cost_input, cost_output
    capability_evidence: Dict[str, Literal["T1","T2","T3"]] = {}   # per declared capability
```

Adapter from the old fields (no behaviour change in Phase 1): `estimated_quality` + `metric_provenance["quality"]` → tier by the mapping `measured/observed → T3`, `benchmark → T3 only if a method id is present, else T2`, `provider_published → T2`, `estimated/editorial_estimate → T1`, `unavailable/null → T0`.

### 5.2 Required but missing today

| Need | Today | Change |
|---|---|---|
| Measurement method and sample size per metric | not stored | `MetricRecord.method`, `n_samples` |
| Measurement date per metric | only record-level `last_verified_at` | `MetricRecord.measured_at` |
| Per-capability evidence | list of strings | `capability_evidence` |
| Latency in seconds for approved products | none (only an editorial 0-1 speed) | published or observed seconds, else stays `T0/T1` |
| Prices for approved products | none (only `pricing_category`) | optional `price_*` when a vendor publishes a per-request or per-token price |
| Data-handling documentation for approved products | `unknown` for all 37 | fill from vendor documentation, with `source` |
| Reference ranges | implicit in code | one versioned config object `reference_ranges_v1` |
| Requirement `status`, `support`, rule ids | partial | extend `Requirement` (`status`, `support`, `rule_ids`) |
| Response fields | none | `selection.indicators`, `selection.level`, `candidate.interval`, `candidate.frontier`, `candidate.dominated_by` |

### 5.3 Storage impact

- **Approved pool** lives in code (`approved_ecosystem.py`): no database change.
- **Live registry** columns would need a migration. This is deferred: no Neon write or migration is part of this design task, and none is proposed before approval.
- Response additions are additive JSON fields.

### 5.4 Data that cannot be created by us

Measured quality, latency and reliability for third-party products require either (a) a benchmark we run (not a recommendation-only product's job), (b) a cited public benchmark with its method, or (c) observed history, which only exists after products are actually used. Until then those fields are `T0/T1`, and the specification's output reflects it.

---

## 6. Pseudocode and complexity

```text
function recommend(query, pool M, user, config):
    Q   ← represent(query, user)                                     # 2.1
    w0  ← resolve_weights(user, Q.explicit)                          # 2.5.5
    M_Q, excluded ← eligible(M, Q)                                   # 2.2
    if M_Q is empty: return no_candidates(excluded, relaxations(Q))

    for m in M_Q:                                                    # 2.3, 2.4, 2.6
        for d in D:
            rec   ← metric_record(m, d)           # adapter from fields; tier downgraded if stale
            u_d   ← map_to_utility(rec, reference_ranges)           # per-model only
            [ℓ,h] ← interval(rec.tier, u_d, rec)                    # δ by tier or Wilson
            m.iv[d] ← ([ℓ,h], rec.tier)
        m.fit ← coverage(Q, m)                                       # 2.3.1

    F ← frontier(M_Q)                                                # 2.5.2
    ranking ← sort(M_Q, key = (m∉F, -L(m,w0), -U(m,w0), -H(m,w0),
                                role≠primary, provider∉preferred, editorial_order, model_id))
    best, next ← ranking[0], ranking[1]

    ε*    ← breakpoint(ranking, w0)                                  # 8.1
    ind   ← indicators(Q, best, next, ε*, w0)                        # 2.8
    level ← weakest_link(ind)                                        # 7.3
    stab  ← robustness_report(M_Q, Q, w0)                            # 8.2-8.5
    return Result(best=best, suggested=ranking[1:4], candidates=ranking,
                  frontier=F, indicators=ind, level=level, robustness=stab,
                  provenance=fingerprint(Q, w0, pool, ranges, δ-params))

function frontier(M):                                    # certain dominance
    D⁺ ← {d : w_d > 0}
    for a in M: dominated_by[a] ← [b in M, b≠a, if ∀d∈D⁺ ℓ_d(b) ≥ h_d(a) and ∃d∈D⁺ ℓ_d(b) > h_d(a)]
    return {a : dominated_by[a] = ∅}

function breakpoint(ranking, w0):                        # smallest ε that changes the winner
    top ← ranking[0]
    for each scenario s in axis_scenarios(w0):           # each d in D⁺, sign ±
        ε_s ← bisect ε in (0, ε_max] such that argmax_key(perturb(w0, s, ε)) ≠ top
              # monotone in ε for a single weight; 24 iterations give 1e-7 resolution
    return min_s ε_s                                      # +∞ means stable over (0, ε_max]
```

Complexity (N ≤ 50, D = 6):

| Step | Time | Space |
|---|---|---|
| Eligibility | `O(N·|C|)` | `O(N)` |
| Interval construction | `O(N·D)` | `O(N·D)` |
| Frontier | `O(n²·D)` ≈ 15 000 comparisons | `O(n)` |
| Ranking | `O(n log n + n·D)` | `O(n)` |
| Breakpoint | scenarios `2D = 12`, bisection 24 iterations, each `O(n·D)` ⇒ `12·24·300 ≈ 86 000` ops | `O(n)` |
| Candidate-removal, missing-data, ambiguity runs | `≤ (n + 2 + 1)` re-rankings × `O(n·D)` ≈ 15 000 ops | `O(n)` |

Under a millisecond of arithmetic per request in a compiled language; pure Python stays in the low single-digit milliseconds.

---

## 7. Confidence methodology

### 7.1 What can be calculated reliably now

- `P` (evidence precision), `σ` (interval separation), `ε*` (weight breakpoint), the frontier, the candidate-removal result, the category-agreement result. All are functions of the registry, the weights and the policy parameters.

### 7.2 Weight breakpoint

For scenario `(d, s)` with radius `ε`: `w'_d = w_d (1 + s·ε)`, other weights unchanged, then renormalise to sum 1. `ε*_{d,s}` is the smallest `ε` at which the top-ranked candidate under the full key of 2.5.4 changes. `ε* = min_{d,s} ε*_{d,s}`. It is **computed**, not chosen: the old fixed ±20% is replaced by "how large a change in any single weight does it take?". Pair perturbations (two weights moved in opposite directions) are reported as a second figure `ε*_pair`.

Interpretation: "Best Match stays Best Match unless a weight changes by more than `ε*` (relative)". It says nothing about the probability that the user's true weights lie in that range.

### 7.3 Level rule (weakest link)

| Indicator | strong | moderate | weak |
|---|---|---|---|
| `I_req` | `verified` | n/a | `qualified` |
| `I_sep` | `certain` (`σ ≥ 0`) | `overlapping` with `L_top > L_next` | `tied` (`|ΔL| < ε_tie`) |
| `I_stab` | `ε* ≥ 0.40` | `0.20 ≤ ε* < 0.40` | `ε* < 0.20` |
| `I_evid` | `P ≥ 0.90` | `0.70 ≤ P < 0.90` | `P < 0.70` |

```
level = high      if all four are strong
        moderate  if the worst of the four is moderate (a "weak" in I_req caps at low)
        low       otherwise
```

Thresholds (0.40, 0.20, 0.90, 0.70) are **policy parameters** recorded in `provenance`. Their only justification is that 0.20 equals the existing perturbation constant, 0.40 is twice it, and the `P` bands correspond to "mostly point values", "mostly narrow bands", "mostly wide or unknown". They are not tuned on outcomes.

Why weakest link and not an average: averaging lets a very strong indicator hide a weak one (a certain winner on a query the system barely understood). The weakest-link rule cannot report "high" while any one of the four is weak.

### 7.4 What the number means

The level is an **ordinal robustness statement about the recommendation's own inputs**. It is not "the probability this is the best model" and must be shown with the sentence: *"Robustness of this recommendation to its inputs. Not a probability of being correct."* A probability-like reading needs calibration (`calibration.reliability_bins`, Brier, ECE) on at least 200 labelled outcomes; none exist.

### 7.5 Migration of the numeric value

V1's `confidence_value` is kept in the response for compatibility and marked `deprecated_heuristic: true`. The UI shows the V2 level and the four indicators.

---

## 8. Sensitivity analysis

### 8.1 Weight perturbation

Axis scenarios (12) and pair scenarios (`2·C(6,2) = 30`): for each, bisection finds `ε*`. Reported as `ε*` and `ε*_pair`, plus the name of the objective whose change flips the winner and the candidate that wins instead ("if quality mattered 35% less, B would lead"). This replaces the fixed ±20% trial count.

### 8.2 Query-inferred weight scenarios

The multipliers removed from `w0` (F8) are re-applied as named scenarios: `complex_task_quality_heavy`, `sensitive_content_risk_heavy`, `high_consequence_reliability_heavy`, `simple_task_speed_heavy`. For each: does the winner change? Reported as `inferred_scenarios: [{name, winner, changed}]`. If any changes the winner, the level cannot exceed `moderate` (they are plausible readings of the query).

### 8.3 Metric uncertainty

- **Pairwise certainty**: for each `j`, `σ_j = L_top − H_j`. Winner is a *necessary winner* if all `σ_j ≥ 0`.
- **Worst case for the winner**: set the winner's uncertain values to `ℓ` and everyone else's to `h`; report the winner's worst-case rank.
- **Width sweep**: recompute with `δ_T1 ∈ {0, 0.05, 0.10, 0.15, 0.25}`; report the range of Best Match across them. Conclusions that flip are labelled "depends on the estimate width".

### 8.4 Candidate insertion and removal

By construction (fixed ranges, per-model utilities) scores do not change. Verified properties:

- P1 *score invariance*: inserting or removing any model leaves every other model's `(ℓ, h)` and `L, U, H` unchanged.
- P2 *winner persistence*: removing a non-winner never changes Best Match. Inserting a model changes Best Match only if the new model outranks it.
- P3 *successor*: removing the winner promotes the runner-up exactly (leave-one-out reports who).

The frontier does change on insertion (a new model may dominate others); that is expected and is shown.

### 8.5 Missing metadata and ambiguous classification

- **Missing**: widen the winner's `T1/T2` values to `[0,1]` (as if the evidence were lost) and re-rank; report whether it survives.
- **Ambiguous category**: rerun for the second-best category when `qualified`; report `category_agreement` (same Best Match or not). Different Best Matches across the two readings are shown side by side and cap the level at `low`.

### 8.6 Cost

All of the above are `O(n·D)` ranking passes: under 100 passes per request for `n = 50` (about `12 + 30` weight scenarios with bisection reuse, `n + 1` removals, a handful of metric and category scenarios); each pass is a few hundred arithmetic operations.

---

## 9. Test specification

Tests are specified **before implementation**; IDs are stable references. Expected values in brackets come from section 3.

### 9.1 Unit tests

| ID | Test | Expected |
|---|---|---|
| T-01 | Strict privacy with `data_handling_status = unknown` | candidate excluded, code `privacy_unverified` regardless of score (3.2 M2) |
| T-02 | Explicit budget with missing input or output price | excluded, `cost_unverifiable` (3.2 M4) |
| T-03 | Explicit max latency with no latency data | excluded, `latency_unverifiable` |
| T-04 | Required capability only inferred, not explicit | not a hard constraint; contributes to fit only |
| T-05 | Unknown capability metadata (`T0`) with an explicit capability request | excluded |
| T-06 | Missing quality (`T0`) | interval `[0,1]`; `L` contributes 0, `H` contributes `w_q`; not treated as worst nor best |
| T-07 | Missing reliability | same as T-06 |
| T-08 | Estimated vs measured with equal value | measured has a narrower interval, equal `U`, `L(measured) > L(estimated)` |
| T-09 | Stale `measured_at` (> 365 days) | tier downgraded exactly one level |
| T-10 | Fixed normalization, example 3.1 | A .750, B .500, C .250, D 0.000 |
| T-11 | Score invariance P1: insert unrelated model | all existing `(ℓ,h)`, `L,U,H` identical (exact equality) |
| T-12 | Out-of-range cost and latency | clipped, flagged `clipped_low/high`; zero price → utility 1 |
| T-13 | Certain dominance, example 3.3 | `A ≻ D`; `A` does not dominate `B`; `T0` objective dominates nothing |
| T-14 | Ranking never places a dominated candidate above its dominator, even with `w_d = 0` on the strict dimension | holds |
| T-15 | Example 3.3 scores | `L_A .660, U_A .690, H_A .720, L_B .625, U_B .730, H_B .835, L_C .395, U_C .655, H_C .915` (±1e-9) |
| T-16 | Equal objective scores | ordered by role, provider preference, `editorial_order`, `model_id`; disclosed as a tie |
| T-17 | Determinism | identical input → byte-identical ranking and indicators across 100 runs |
| T-18 | Weight sensitivity, example 3.4 | `ε* = 0.350 ± 0.002`; winner flips to B above it |
| T-19 | Candidate removal P2 and P3 | removing a non-winner keeps Best Match; removing the winner promotes the runner-up |
| T-20 | Ambiguous classification | two-category run executed; level ≤ `moderate` if agree, `low` if disagree |
| T-21 | No eligible candidate | `status = no_eligible_candidates`, exclusion counts, relaxation guidance |
| T-22 | Incomplete evidence | every `T0` objective listed in `missing`; `P` computed per 2.8; level reflects it |
| T-23 | Confidence level, example 3.5 | `I_sep = overlapping`, `ε* = .35`, `P = .94` → `moderate` |
| T-24 | Weakest-link rule | any `weak` indicator forbids `high` |
| T-25 | Weights are the user's | no inferred multiplier changes `w0`; inferred scenarios appear separately (8.2) |
| T-26 | API-key independence | rankings identical with every key present, absent or invalid |
| T-27 | Learning feedback not inside quality | quality utility identical with and without feedback |
| T-28 | Reference-range version change | recorded in `provenance`; changes fingerprint |

### 9.2 Integration and API tests

| ID | Test | Expected |
|---|---|---|
| T-30 | One ranking | `best_match_id = ranking[0]`; `suggested_ids = ranking[1:4]`; `candidates = ranking` (all three views come from one list) |
| T-31 | Frontend consistency (approved **and** live pool) | the Best Match, Suggested and Candidates cards render the same ids in the same order as the response |
| T-32 | Recommendation-only | `execution.status = not_requested`; no provider call; no escalation fields |
| T-33 | Response additive | all V1 fields still present; V2 fields added |
| T-34 | Shadow comparison | with `ALGORITHM=v1` the pre-change outputs are byte-identical on the existing test suite |

### 9.3 Offline comparison design

Pool: the approved ecosystem, queries from a fixed labelled set (the existing 27-case suite plus a held-out set written by someone other than the author of the rules).

Baselines (all computed from registry metadata only):

| Baseline | Rule |
|---|---|
| Strongest | highest quality utility in the resolved category (editorial for now) |
| Cheapest | most open access class in the category (no prices exist) |
| Static | first product in the approved list that serves the category |
| AI Compass V1 | current engine |
| AI Compass V2 | EIPMU |

Metadata-derived metrics (valid statements about *the algorithm*):

- top-1 agreement matrix between methods; Kendall's τ between full rankings;
- constraint violations (must be 0 for V2 by construction);
- rank-reversal rate under leave-one-out and under insertion (V2 must be 0 for non-winners);
- distribution of `ε*`, `σ`, `P` and levels over the query set;
- sensitivity of Best Match to `δ_T1`.

**Real-world performance** (is the recommended product actually the better choice?) cannot be measured from metadata. It needs: a held-out task set, human or expert pairwise judgements of "which product would you use for this request", a pre-registered analysis, and at least the 200 labelled outcomes in `calibration.MIN_OUTCOMES_FOR_VALIDATION`. None of this exists; nothing here fabricates it, and the first report must state that agreement with a baseline is not evidence of better recommendations.

---

## 10. Research contribution and limitations

### 10.1 Is it a defensible contribution?

**Not algorithmic novelty.** Pareto dominance, weighted utility, interval arithmetic, maximin and weight sensitivity are all standard. TOPSIS, SMAA and robust MOO are not novel either, and none of them is presented as one.

**Possibly defensible, as a system and methodology contribution:**

1. **Verified-evidence eligibility semantics** for recommendation over heterogeneous AI tools: unknown cost, latency or data handling **fails** mandatory constraints, and the exclusion is explained by constraint.
2. **Evidence-tiered interval utility** in which measured, published, estimated and unknown values carry different interval widths, so that a ranking prefers verified strength to assumed strength **without** inventing standard deviations.
3. **Breakpoint-based, weakest-link selection confidence**: a recommendation-robustness statement computed from the ranking, the weights and the evidence, explicitly not a probability.
4. **Set-independent normalization with proven rank-stability properties** (P1-P3), compared against candidate-relative normalization on rank reversal.

The claim, stated narrowly: *"a recommender for AI tools whose hard constraints, evidence quality and preference robustness are explicit, testable and explained"*. Anything stronger (it picks better models) is a hypothesis, not a result.

### 10.2 Hypotheses and metrics

| ID | Hypothesis | Metric | Data needed |
|---|---|---|---|
| H1 | Fixed-range normalization removes rank reversal that min-max normalization produces | rank-reversal rate under insertion/removal on the real pool and on synthetic pools | none beyond the registry |
| H2 | Interval utility ranks candidates with measured evidence above equally-scored candidates with estimated evidence, and does so only then | pairwise rank change when tier is swapped | none (synthetic) |
| H3 | `ε*` and `σ` identify recommendations that experts also find fragile | rank correlation between `ε*` and expert disagreement | expert-labelled queries |
| H4 | Verified-evidence eligibility yields zero constraint violations while the old penalty approach permits them under missing metadata | violation count under injected missing data | synthetic injections |
| H5 | The ordinal confidence level is monotone in empirical agreement with a labelled reference | calibration curve, Brier, ECE | ≥ 200 labelled outcomes |

H1, H2 and H4 can be tested now without real-world data; H3 and H5 cannot.

### 10.3 Limitations

- **All third-party quality, latency, reliability and risk values are editorial (`T1`) or unknown (`T0`).** The prototype shows what that does: no recommendation reaches "certain" separation.
- Interval widths are policy parameters, not statistics. Thresholds in 7.3 are policy.
- Category and requirement extraction are regular-expression rules; their errors propagate into the gate. Mitigation is the ambiguity handling, not accuracy.
- Fit depends on vendor-positioning tags, not tested capability.
- Weights express preference, but the preference UI exposes only five objectives; the sixth (fit) has a documented default.
- Four prototype queries and one 27-case suite say nothing about generalisation.
- Maximin is conservative: it favours well-documented products and can under-rank a strong but under-documented one. This is a design choice that a reviewer may reasonably dispute (open item O-2).
- Real-world recommendation quality is not evaluated.

---

## 11. Migration and backward compatibility

1. **Feature flag** `ALGORITHM_VERSION ∈ {v1, v2}` in `core/config.py` (default `v1`). V1 code is untouched in Phases 1-3.
2. **Shadow mode** (Phase 3): V2 runs next to V1 on every request, its output is logged and *not* shown; a comparison report lists disagreements and why.
3. **Adapters, not rewrites**: `MetricRecord` is built from existing fields; the approved list in code gains tiers, not new numbers.
4. **API**: additive fields only (`selection.level`, `selection.indicators`, `candidate.interval`, `candidate.frontier`, `candidate.dominated_by`). `confidence_value` stays and is marked deprecated.
5. **Frontend**: the confidence card shows the level and four indicators; Best Match, Suggested and Candidates keep reading `engine.ranking`; the live-pool path is moved onto the same `ranking` field (F16).
6. **Tests**: V1 tests run under `ALGORITHM_VERSION=v1`; V2 tests are new files. The existing `conftest.py` autouse fixture pattern (pool source per module) extends to the algorithm flag.
7. **Database**: none for the approved pool; any live-registry columns are a separate, explicitly approved migration.
8. **Rollback**: flip the flag. No data migration to undo.
9. **Editorial ratings**: kept as `T1` records with `method = "editorial rating v1"`; replacing one with a measured or published value upgrades its tier and narrows its interval automatically.

---

## 12. Implementation roadmap

| Phase | Content | Exit criterion |
|---|---|---|
| 0 | **This document reviewed and the open items below decided** | written approval |
| 1 | `MetricRecord` schema and adapters from existing fields; `reference_ranges_v1`; no behaviour change | all V1 tests pass unchanged; round-trip tests for adapters |
| 2 | V2 core as pure functions in a new module (eligibility, intervals, frontier, ranking key, breakpoint, indicators); unit tests T-01 to T-28 written first | all T-0x/T-1x/T-2x pass; hand-calculated examples match to 1e-9 |
| 3 | Shadow mode and the offline comparison harness (9.3); disagreement report | report reviewed; no unexplained disagreement |
| 4 | Additive API fields and frontend confidence card; live pool joins the single-ranking contract | T-30 to T-34 pass; browser check at desktop and mobile widths |
| 5 | Flip default to `v2` behind the flag; mark V1 constants deprecated; optional SMAA diagnostic | agreed acceptance review |
| 6 | Calibration and real-world evaluation once labelled outcomes exist | ≥ 200 labelled outcomes; Brier/ECE reported honestly |

### Open items for your decision

| ID | Question |
|---|---|
| O-1 | Accept that, until some metrics reach `T2/T3`, the approved pool cannot report `high` confidence, and every recommendation is at best `moderate`? (This is a visible product change.) |
| O-2 | Rank by the conservative score `L` (maximin) or by the midpoint `U` with `L` as a flag? The spec recommends `L`; `U` is less conservative and ranks estimated products higher. |
| O-3 | Where does personal feedback go: tie-break only, or a separate "personalisation" annotation? |
| O-4 | Keep or retire the editorial `RATINGS` I added? Under V2 they remain `T1` and cost nothing in certainty claims, but they still steer within-category order. |
| O-5 | Accept the policy parameters (`δ_T1 .15`, `δ_T2 .05`, `δ_T3 .03`, `ε` bands .20/.40, `P` bands .70/.90, staleness 365 days, reference ranges)? They are not derived from data. |
| O-6 | Which approved products should get documented data-handling status first, so strict privacy has something to select? |

---

## Appendix A: files inspected

`backend/app/services/routing_engine/`: `pipeline.py`, `understanding.py`, `audience.py`, `filtering.py`, `scoring.py`, `preferences.py`, `ecosystem.py`, `confidence.py`, `counterfactual.py`, `observed.py`, `calibration.py`, `types.py`, `access.py`.
`backend/app/services/`: `model_registry.py`, `multi_objective_router.py`, `offline_evaluation.py`, `ecosystem_evaluation.py`, `pool_stats.py`.
`backend/app/data/approved_ecosystem.py`, `backend/app/schemas/model.py`, `backend/app/api/routes/routing.py`, `backend/app/api/routes/evaluation.py`.
`backend/RESEARCH_VALIDATION.md`, `backend/tests/` (selection, pipeline, approved-ecosystem suites), `frontend/src/pages/RouteQuery.tsx`, `frontend/src/types/api.ts`, `frontend/src/components/evaluation/*`.

## Appendix B: files changed by this task

`backend/ALGORITHM_V2_SPEC.md` (this file). Nothing else. The scratch scripts `/tmp/v2/examples.py` and `/tmp/v2/proto.py` live outside the repository and read it without writing to it.
