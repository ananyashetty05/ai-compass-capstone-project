# AI Compass: Algorithm V2 Second-Pass Review and Research Validation

Date: 2026-11-20. Subject: `backend/ALGORITHM_V2_SPEC.md` (draft, **not approved**).
Scope: review and design only. No application code, schema, database, credential, deployment or GitHub state was changed. The only repository writes are this file and a short errata banner at the top of the draft spec (section 11).

## 0. Summary and verdict

**Implementation-readiness verdict: NOT READY.** The draft has real strengths (fixed-range normalization, verified-evidence eligibility, weights that stay the user's) but the second pass found defects that would have shipped wrong behaviour or wrong claims:

| # | Finding | Status |
|---|---|---|
| R1 | The frontier-first ranking key breaks the rank-stability properties the draft claimed. Counterexamples constructed and run: removing the winner does **not** promote the runner-up (14.0% of 4,000 random instances); inserting an unrelated model reorders existing models (6.2%). Best Match itself is unaffected. | Refuted by counterexample and test |
| R2 | The separation indicator `σ` uses the runner-up's optimistic score instead of the best rival's. Draft example: σ = −0.175, correct value −0.255. | Error, corrected here |
| R3 | The weight breakpoint `ε*` as defined (relative scaling of one weight, then renormalizing) overstates stability. Draft example: ε* = 0.35; a two-weight move flips the winner at 0.20; the exact minimum is a 0.078 shift of weight mass (15.6% of the quality weight). The 0.20/0.40 bands are therefore unfounded. | Error, corrected here |
| R4 | Maximin ranking treats an unknown value as the worst case in the rank, which is the legacy "missing = 0" behaviour the draft said it fixed. | Misstatement in the draft |
| R5 | Clipping intervals to [0,1] biases midpoints. Alone, it makes the lower-bound and midpoint rankings disagree in 5.1% of random pools with identical tiers. | Tested |
| R6 | The editorial ratings decide the winner on this pool: with them removed, Best Match changes for 8 of 12 labelled queries. They are my own judgements with no rubric or rater record. | Tested; policy decision needed |
| R7 | Observed T3 reliability and latency (Wilson interval over execution outcomes) conflict with the recommendation-only boundary and with the independence assumption Wilson needs. | Design conflict |
| R8 | A budget "guarantee" cannot rest on an estimated token count. The draft's hard-budget wording over-claims. | Corrected in section 4 |
| R9 | The draft's algorithmic-novelty framing needs tightening. Every ingredient is an established technique, and necessary/possible dominance under uncertain parameters is standard in the MCDM literature. | Corrected in section 7 |
| R10 | The project's literature survey and synopsis are **not available as files** here. Only the names exist in the project context. The comparison below verifies each named paper against its primary source instead. | Limitation |

No formulation is supported by the evidence as the single right choice yet. The evidence does support three narrower conclusions (section 8): rank by a per-model score, drop frontier-first, and use intervals for diagnostics.

### Status labels used in this document

- **[PROVED]**: proof given here and also exercised by the randomized tests in the appendix. Random tests are evidence, not proof.
- **[TESTED]**: executed here on stated data; not a proof.
- **[REFUTED]**: counterexample constructed and executed.
- **[OPEN]**: not established.
- **[NOT RUN]**: designed only.

### What was actually executed in this review

All scripts are outside the repository (`/tmp/v2/*.py`) and are reproduced in the appendix. Real-pool numbers use the 37-entry approved pool in the working tree and **12 labelled queries** (not the 27-case suite) taken from `tests/test_approved_ecosystem.py`.

| Run | Content |
|---|---|
| `review_math.py` | Re-computation of spec examples 3.1 to 3.5; counterexamples; breakpoint and weight-margin checks (including a 200,000-draw brute-force check); clipping and missing-data cases |
| `review_props.py` | 4,000 random instances per ranking rule (frontier-first, lower-bound, midpoint, minimax regret, ε-tie): insertion, removal, runner-up promotion; 300,000-draw dominance transitivity search; 20,000-case frontier-membership check; lower-bound versus midpoint disagreement by tier mix |
| `review_pool2.py` | 12 real queries: V1 versus lower-bound versus midpoint winners, unclipped midpoint, editorial-rating removal, width sweep, true σ, weight-mass margin; missing-metadata (MCAR) pilot, 2,400 draws per level |

---

## 1. Mathematical verification

Notation follows the draft: interval `[ℓ_d(m), h_d(m)]` per objective, `L = Σ w ℓ`, `U = Σ w (ℓ+h)/2`, `H = Σ w h`; `a ≻ b` iff `ℓ_d(a) ≥ h_d(b)` on every weighted objective and `>` on one.

### 1.1 Dominance and maximin (draft 2.5.2)

| Claim | Status | Basis |
|---|---|---|
| (a) `a ≻ b` ⇒ `L_a > L_b` | **[PROVED]** | `L_a − L_b = Σ w_d(ℓ_a − ℓ_b) ≥ Σ w_d(ℓ_a − h_b) ≥ 0`, strict where the strict dimension has `w_d > 0`; true by definition of `D⁺`. 17,234 random dominating pairs, 0 violations |
| `≻` is transitive | **[PROVED]** | `ℓ_a ≥ h_b ≥ ℓ_b ≥ h_c` with strictness carried through. Random search found 61 chains, 0 failures. The count is low because dominance is rare among overlapping intervals, so the test is weak; the proof carries the claim |
| `argmax L` is always on the frontier | **[PROVED]** | If the argmax were dominated, its dominator would have strictly larger `L` by (a). 20,000 random pools, 0 violations |
| Converse of (a) | **[REFUTED]** | `L_a > L_b` does not imply `a ≻ b`. In draft example 3.3, `L_D = 0.55 > L_C = 0.395` but neither dominates the other |

Consequence: under an exact lexicographic key the **winner of the frontier-first ranking is always the winner of the plain lower-bound ranking**. Frontier-first changes only positions 2 to n, and that is where it does harm (1.2).

### 1.2 Candidate insertion and removal (draft 8.4, properties P1 to P3)

Draft claims: P1 insertion leaves existing scores unchanged; P2 removing a non-winner never changes Best Match; P3 removing the winner promotes the runner-up exactly.

| Property | Result | Evidence |
|---|---|---|
| P1 score invariance | **[PROVED]** | Each model's `(ℓ, h)` and `L, U, H` are functions of its own fields and the fixed ranges only |
| P2 Best Match unchanged by removal of a non-winner | **[PROVED]** for the exact-key lower-bound ranking and for frontier-first (by 1.1) | 0 violations in 4,000 instances for both. **[REFUTED]** for the ε-tie rule as written in 2.7 (non-transitive, see 1.5) and for minimax regret (66 of 4,000) |
| P2 for the whole order (draft 8.4 listed the "rest unchanged" intent) | **[REFUTED]** for frontier-first | 249 of 4,000 insertions reorder two existing models. Hand counterexample below |
| P3 runner-up promoted exactly | **[REFUTED]** for frontier-first | 559 of 4,000 (14.0%). Hand counterexample below |
| All of P2 order-stability and P3 | **[PROVED]** for ranking by one per-model score | A per-model score makes pairwise order independent of the other models (independence of irrelevant alternatives). 0 violations in 4,000 for lower-bound and midpoint |

**Counterexample to P3** (weights `x = y = 0.5`; point values):

| Model | `(x, y)` | `L` | Dominated by |
|---|---|---|---|
| T | (0.90, 0.90) | 0.900 | none |
| c | (0.70, 0.70) | 0.700 | T |
| m | (0.10, 0.95) | 0.525 | none (T is worse on y) |

Frontier-first order: T, m, c (m is on the frontier, c is not). Remove T: new order c, m. The runner-up m was **not** promoted; c, previously dominated only by T, took the top. A per-model score orders T, c, m and promotes c correctly.

**Counterexample to order stability under insertion** (same weights):

| Model | `(x, y)` | `L` |
|---|---|---|
| T | (0.90, 0.50) | 0.700 |
| A | (0.60, 0.70) | 0.650 |
| B | (0.30, 0.85) | 0.575 |

Before: T, A, B. Insert N = (0.80, 0.75), `L = 0.775`, which dominates A but not T or B. Frontier-first after insertion: N, T, B, A. **A and B swapped**, caused by a model that dominates A. A per-model score gives N, T, A, B.

**Minimax regret** (alternative C below) shows the same family of failures, as the literature predicts (Savage's rule is known to violate independence of irrelevant alternatives; see arXiv:2203.01420).

**Correction.** The draft's statement "removing the winner promotes the runner-up exactly" and the "frontier-first ranking key" are retracted. Dominance should be an annotation on a per-model ranking, not a component of the key.

### 1.3 Weight breakpoint (draft 7.2, 8.1)

Draft procedure: scale one weight by `(1 + sε)`, renormalize, bisect for the smallest ε that changes the winner; also "pair perturbations" (one weight up, one down).

| Question | Answer | Status |
|---|---|---|
| Is bisection valid? | For a fixed rival `j`, the sign of `L_top − L_j` after renormalization equals the sign of a numerator that is linear in ε, so each rival is overtaken at most once and the predicate "top is no longer the winner" is monotone. Bisection is valid, but a closed form (the linear root) exists, so bisection adds nothing | **[PROVED]** |
| Domain | Downward scaling requires `ε ≤ 1` (weight reaches 0). At `ε = 1` the weighted-objective set `D⁺` changes, which changes the frontier. Upward scaling is unbounded, but the normalized weight saturates at 1, so `ε* = ∞` is possible and must be reported as "no flip" | **[PROVED]** |
| Zero-weight objectives | Relative scaling can never switch on an objective whose weight is 0. In the approved pool cost has weight 0 by design, yet "the user adds a cost preference" is the most plausible weight change. The draft's `ε*` cannot see it | **[REFUTED]** as a robustness measure |
| Pair perturbation | The draft multiplies one weight by `(1+ε)` and another by `(1−ε)`. That moves **different absolute amounts of weight mass** (`ε w_i` and `ε w_j`) and renormalizes, so it is not a transfer. The definition is not canonical | Ill-defined |
| Is the draft example right? | Axis minimum is 0.35 (quality down), as stated. The pair "cost up, quality down" flips at **0.200**. Direct weight-space minimum: 0.0778 of weight mass moved from quality to cost (quality 0.500 → 0.422, cost 0.300 → 0.378). A 200,000-draw random search found 0.078 | **[TESTED]**: the draft's ε* = 0.35 overstates stability |

**Correction.** Replace relative-scaling breakpoints by a **weight-space margin**: the smallest total-variation shift `δ_j*` of weight mass that makes rival `j` at least tie the leader,

```
g_d = ℓ_d(top) − ℓ_d(j),   Δ_j = Σ w_d g_d,
move mass from the largest-g objectives to the smallest-g objectives (fractional knapsack, bounded by available weight);
δ_j* = minimal mass moved such that Δ_j ≤ 0     (∞ if impossible).
margin = min_j δ_j*.
```

For the two-objective-direction case it is `Δ_j / (g_max − g_min)`; in general a small greedy/LP computation, `O(n D log D)`. It is exact, needs no scenario enumeration, includes switching on a zero-weight objective, and has a plain meaning: "the leader stays the leader unless the user's weights shift by more than `margin` of the total". In draft example 3.3: rivals B 0.078, C 0.241, D impossible (>1). **[TESTED]**.

The 0.20 and 0.40 bands in draft 7.3 have no derivation and were calibrated to nothing. They are **removed** until E7 (section 6) supplies a basis.

### 1.4 Separation indicator and example errors

| Item | Draft | Correct | Status |
|---|---|---|---|
| Ranking by `L` in example 3.3 | "A > B > C > D" | **A, B, D, C**: `L_D = 0.55` (also `U_D = 0.56`, `H_D = 0.57`) exceeds `L_C = 0.395`. The draft order A, B, C, D is the frontier-first order, which places the certain-dominated D after the very uncertain C | Error |
| `σ = L_top − H_next` (2.8, 3.5) | −0.175 (B as runner-up) | `σ` must use the **best rival**: `max_j H_j = H_C = 0.915`, so **σ = −0.255**. The prototype in 3.6 reused the runner-up by rank and has the same flaw, although on the 12 pool queries every σ is negative either way | Error |
| 3.5 weakest-link outcome | moderate | With corrected σ and ε*, still "overlapping" separation; stability moves toward the lower band (0.20 pair value). Outcome "moderate" holds only because the bands were arbitrary | Re-derive after bands are set |
| ε* scan in the 3.6 prototype | up to 200% | For downward scaling any ε > 1 is a negative weight and meaningless. Values above 1 in the table arise only from upward scenarios | Misleading |
| Midpoint after clipping | `(ℓ+h)/2` | A value of 0.95 with half-width 0.15 clips to `[0.80, 1.00]`, midpoint 0.90 not 0.95; 0.1 becomes 0.125. Systematic compression of strong ratings. 5.1% of random 8-model pools with identical tiers give different winners under lower-bound versus clipped-midpoint ranking, and the disagreement is caused only by clipping | **[TESTED]** |
| Examples 3.1, 3.2, 3.3 scores, 3.4's single-axis 0.35, 3.5's `P = 0.94` | as in the draft | Re-computed; correct | OK |

### 1.5 Ties

The draft key (2.5.4) is exact and lexicographic but section 2.7 introduces `ε_tie = 0.005`. A tolerance tie is not transitive: `L = 0.500, 0.504, 0.508` gives `a ~ b`, `b ~ c`, but `c` beats `a` by 0.008 > ε. A ranking built on it is not a total order, so removal/insertion properties cannot be proved. Randomized test: 2 order changes in 4,000 for the greedy version, small but nonzero. **Decision:** order only by exact (rounded to 12 decimals) values, keep deterministic tie-breakers, and *report* "within ε of the leader" as a diagnostic, never as ordering.

### 1.6 Confidence indicators and weakest-link rule (draft 2.8, 7.3)

| Item | Finding |
|---|---|
| Weakest-link combination | Fine as a design principle (an average can hide a weak indicator). The thresholds are not derived. They are **policy**, and the draft already says so, but it still labelled the result "confidence" |
| Name | The quantity is a robustness grade of the recommendation to its own inputs and policy parameters, not confidence. Rename to **robustness grade** |
| `P` (evidence precision) | `P = 1 − Σ w(h − ℓ)` depends on `δ_T1, δ_T2` which are policy numbers, so `P` reports policy, not evidence. Replace with **evidence coverage** `C = Σ_d w_d · 1[tier_d ≥ T2]`, i.e. the share of the user's weight resting on documented or measured data, which needs no width policy |
| `σ` | Use best rival (1.4) |
| Stability | Use the weight-space margin (1.3) |
| Pilot result | On the real pool every one of 12 queries has `σ < 0` (range −0.259 to −0.171) because every metric is T1. The grade would be at best "moderate" everywhere: a consequence of the data, not of the algorithm |

---

## 2. Evidence and comparability

### 2.1 Measurement uncertainty versus policy uncertainty

The draft mixes these. They must be reported separately.

| | Measurement uncertainty | Policy uncertainty |
|---|---|---|
| Meaning | Spread caused by finite samples or noisy measurement of a quantity that exists | Spread caused by a modelling choice that no data in the registry can settle |
| Examples | Bootstrap or binomial interval on an observed rate with documented independence; spread across repeated identical benchmark runs | Interval half-widths `δ_T1, δ_T2, δ_T3`; reference ranges `[1e-5, 1e-1]`, `[0.2, 60]`; staleness limit; tier assignment rules; grade bands; weights; conservatism (maximin versus midpoint) |
| Can be estimated from registry? | Only where per-item or repeated data exist. Today: nowhere | No. Must be chosen and swept |
| Presentation | Interval with stated method and `n` | Sensitivity table (section 6, E5 to E7), never folded into a single score silently |

Present state: **no registry field has a measurement interval.** Every interval in the draft is policy. Calling them "evidence intervals" overstates what they are.

### 2.2 Benchmark comparability

Published model or product scores are comparable only under the same dataset and version, prompt and decoding protocol, scoring rule, and evaluation date. The HELM work (Liang et al., TMLR 2023, arXiv:2211.09110) reports that before it, models on average had been evaluated on only 17.9% of its core scenarios, some sharing none, and it standardizes conditions for that reason. The draft's "T3 benchmark ± 0.03" treats any benchmark value as comparable with any other and its half-width has no sampling-error basis.

Rules adopted for the spec revision:

1. A quality value carries `comparison_group = (benchmark id, version, protocol, evaluation window)`. **Values are compared only within a group.** Across groups, only rank-based aggregation is allowed, and only when each model has a result in each group; otherwise the missing groups are T0.
2. T3 requires: dataset id and version, protocol, scorer, number of items, evaluation date, and a bootstrap or exact interval **when per-item results are public**. Without per-item data, a benchmark number is T2 (documented), with a policy-labelled width.
3. No benchmark exists in the registry for the **products** in the approved pool (ChatGPT, Canva, Runway, Suno, and so on are applications, not fixed models). A model benchmark describes a model version; an application changes silently. Product-level quality evidence is therefore, at best, a public human-preference leaderboard where one exists for the category. That has **not** been verified in this review.

### 2.3 Latency comparability

Latency depends on region, time of day, load, prompt length, output length, streaming versus total, client network, and plan tier. Rules:

1. A latency value carries `(metric: time-to-first-token or total, payload class, probe location, window, n)`. Comparable only within the same protocol id.
2. Published vendor figures are T2 and are *typical* values, not guarantees.
3. **Observed latency from AI Compass's own execution logs is not available in the recommendation-only product**: with provider inference removed, no new samples arrive. The legacy `observed.py` path would only reflect historical executions. See 2.4 and section 5.
4. Approved-pool "speed" is currently an editorial 0 to 1 rating, not a latency. It must not be fed through the seconds mapping.

### 2.4 Reliability, sample windows and statistical assumptions

The Wilson interval (Wilson 1927, recommended for binomial proportions by Brown, Cai and DasGupta, Statistical Science 16(2):101-133, 2001, doi:10.1214/ss/1009213286) is valid for independent identically distributed Bernoulli trials. Provider failures come in bursts (outages), so trials are autocorrelated; the Wilson interval would be too narrow. And the only available trials would come from executing providers, which the product no longer does.

**Decision:** remove "observed T3 reliability with Wilson" from the core. If reliability is used later, it must come from a published uptime or error-rate figure with `(window, definition, source)` and tier T2, with a policy half-width, and it must be labelled as uptime, not as probability of a correct answer.

### 2.5 Evidence-tier assignment and provenance

Tiers are only meaningful if the assignment rule is mechanical and auditable.

| Tier | Rule (proposed) | Required record fields |
|---|---|---|
| T3 measured | Measurement with documented method, per-item or repeated data, `n`, date, comparison group; independent of the vendor | `method, comparison_group, n, measured_at, source, interval_method` |
| T2 documented | First-party or third-party document that states the value, with citation, version and date | `source_url, quoted_value, document_date, plan/tier scope` |
| T1 estimated | A named person or process produced a rating against a written rubric; value is a relative judgement | `rater, rubric_id, rated_at`, rationale |
| T1u unanchored | Value with no rater record, no rubric, no source | treated as **T0 for ranking**, shown as "unverified" |
| T0 unknown | No value | none |

The 37 current ratings were written by the assistant from general knowledge, with no sources and no rubric. They meet only T1u. This is a finding about the **draft spec's** treatment (±0.15 interval and a place in the rank), not just a data issue.

**Editorial ratings and ranking (executed).** With the four rated objectives (quality, speed, reliability, risk) set to unknown for every candidate, keeping fit, the winner changes for **8 of 12** queries (ties then resolved by approved-list order). The ratings decide most outcomes. Whether that is acceptable is a product decision: the evidence says they should not silently decide, and that they have no support beyond my own judgement.

### 2.6 Stale evidence

A flat 365-day downgrade is not defensible for AI products that change monthly. Replace with: evidence is **bound to a version identifier**; when the registry cannot show the evidence applies to the current product version, it is downgraded. A calendar limit remains only as a fallback and is swept in experiment E3. No default is claimed.

### 2.7 Interval widths and fixed ranges

`δ_T1 = 0.15, δ_T2 = 0.05, δ_T3 = 0.03` are policy. Pilot (12 real queries): sweeping `δ_T1` over {0, 0.05, 0.10, 0.15, 0.25, 0.35} changes **no** winner. The reason is mechanical: all rated cells share one tier, so every interval is shifted by the same amount and `L` preserves order. The sweep says nothing about sensitivity when tiers differ. Synthetic test: with random mixes of T1 and T2 cells, the lower-bound and midpoint winners differ in 5% to 13% of random 8-model pools, so tier mixing matters once evidence is heterogeneous. Fixed reference ranges are set-independent (P1) but their endpoints are policy; their effect on rankings is **[NOT RUN]** (E5).

### 2.8 Missing metadata

| Observation | Source |
|---|---|
| Under maximin ranking, an unknown objective contributes 0 to the rank key, exactly like the legacy "missing = 0". Example: model X with unknown quality and perfect other values has `L = 0.50, U = 0.75, H = 1.00`; model Y with all values 0.55/0.50/0.50 has `L = 0.525`. Y outranks X by `L`, X outranks Y by `U`. | Executed example |
| Pilot (MCAR) on the real pool: remove each rated metric with probability `p` independently per model; fraction of query-draws in which Best Match is unchanged: `p = 0.1`: 0.68 (lower-bound) and 0.70 (midpoint); `p = 0.3`: 0.35 and 0.40; `p = 0.5`: 0.26 and 0.31 (2,400 draws per level) | Executed |
| Reading | Current winners are fragile because the within-category rating gaps are small (weight-space margins 0.012 to 0.125). The pilot cannot say whether the data would be better if complete, only that the rank leans on small differences | Executed |

The draft's claim that intervals "fix" missing data holds for **dominance and diagnostics** only. For ranking, the choice between pessimistic (maximin), neutral (midpoint) or in-between (Hurwicz) is a policy decision. It is not decided by the evidence available, which is why the revision keeps it explicit (section 8).

---

## 3. Hard constraints and estimated inputs

The draft treated budget, latency and privacy as hard constraints that cannot be bought back. That stays true. What changes is **what can honestly be guaranteed**.

### 3.1 Budget

| Quantity | Needs | Can AI Compass guarantee it? |
|---|---|---|
| Unit price compliance ("price ≤ $X per million tokens") | Documented per-token prices with source and date | Yes, as "compliant according to the cited price page on date D". It is a documentation fact, not a billing guarantee |
| Request cost | Input token count, output token count, plus billed extras (reasoning tokens, tool calls, caching, minimum charges, long-context tiers) | **No.** Input counts come from an estimator (`profile.tokens.method`) and are tokenizer-specific per model. Output length is unknown. Billed extras are not in the registry. Even an exact input count would not bound cost, because output and hidden tokens are not controlled by a recommendation-only product |
| Unknown pricing | no price | cannot be verified |

Proposed status vocabulary for the budget constraint (replaces a single pass/fail):

| Status | Meaning | Eligible? |
|---|---|---|
| `verified_unit_price_within_limit` | explicit unit-price limit, documented price within it | yes (the only hard-guarantee status) |
| `estimated_within_budget` | estimate with stated assumptions (n_in, n_out, margin) is below the limit | yes, labelled "estimated, not guaranteed", shown with its assumptions |
| `borderline` | estimate within the margin of the limit | yes with warning (policy band) |
| `estimated_over_budget` | estimate above the limit | no |
| `unverifiable` | price or token basis missing | no (cannot satisfy a verified requirement), reported separately from "over budget" |

The user may supply a hard cap on output tokens and a maximum input size; if they do, the status can be called `upper_bound_within_budget` **under those declared caps and the cited prices**, still not a billing guarantee. The product must never display "guaranteed within budget".

### 3.2 Privacy

`documented` means a vendor document states a handling commitment for a **named plan and region** on a **dated version**. It does not mean the commitment holds for the user's plan, or after a policy change. Strict privacy therefore requires `status = documented_for_scope`, scope matching the user's declared plan if given, and a date. Otherwise it is `undocumented` or `scope_unknown` and fails the strict constraint, with the reason shown. Currently all 37 approved products are `unknown`, so a strict request returns no candidates. That is correct and untested against real data.

### 3.3 Hard requirements versus inferred preferences

| Source | Role |
|---|---|
| Explicit structured field or unambiguous requirement phrase (rule-matched) | may be a hard constraint |
| Inferred by rule from wording | **never** a hard constraint. It becomes an objective weight or a named sensitivity scenario. The category gate is the one inferred item that gates eligibility today; it is covered by the ambiguity handling |
| Query-sensitivity inference (for example sensitive subject matter) | produces a **warning** and a one-click "treat as strict privacy" option, never silent exclusion or silent weight change |

---

## 4. Literature comparison

**Source status.** The project's literature survey and synopsis are not available as files. The project context lists the names, and states they "are not verified bibliographic records". The repository's `PHASE2B_RESEARCH_REPORT.md` has three matrix rows. The `CAPSTONE.zip` upload contains no survey. This section therefore verifies each named work against its primary page (arXiv, proceedings, publisher). I read abstracts and summary pages, not every full text, so statements about method are limited to what those pages state.

Two identifications need your confirmation against the survey: the work I matched to **FLARE** (the name also exists elsewhere in NLP) and the work I matched to **LENS** (the name is also used for other methods). I selected the routing papers below because they are routing frameworks; the survey may mean different papers.

### 4.1 Routing algorithms and methods

| Work | Authors, year, venue, link | Actual method | Problem addressed | Limitations relevant to AI Compass | Exact difference from the V2 proposal |
|---|---|---|---|---|---|
| **FrugalGPT** | L. Chen, M. Zaharia, J. Zou. TMLR 2024; arXiv:2305.05176 (May 2023). https://arxiv.org/abs/2305.05176 | Framework combining prompt adaptation, LLM approximation and an LLM cascade that learns which models to query for different queries; reports matching GPT-4 with up to 98% cost reduction in its experiments | Cost versus accuracy of paid LLM APIs with heterogeneous pricing | Learns from labelled outcomes and executes the models; optimizes accuracy and cost; no hard privacy eligibility, no evidence tiers | V2 executes nothing and learns nothing: it ranks documented metadata. It makes no accuracy or savings claim |
| **RouteLLM** | I. Ong, A. Almahairi, V. Wu, W.-L. Chiang, T. Wu, J. E. Gonzalez, M. W. Kadous, I. Stoica. ICLR 2025 (proceedings title "…from Preference Data"); arXiv:2406.18665 (Jun 2024, v4 Feb 2025). https://arxiv.org/abs/2406.18665 | Trains routers choosing between a stronger and a weaker LLM, from human preference data (Chatbot Arena) with data augmentation | Quality versus cost between two models | Two-model, trained; depends on preference data; no explicit uncertainty about registry values | V2 is multi-candidate, metadata-based and deterministic; no training data |
| **RouterDC** | S. Chen, W. Jiang, B. Lin, J. T. Kwok, Y. Zhang. NeurIPS 2024; arXiv:2409.19886; doi:10.52202/079017-2120 (as listed by the proceedings index). https://proceedings.neurips.cc/paper_files/paper/2024/hash/7a641b8ec86162fc875fb9f6456a542f-Abstract.html | Encoder plus per-LLM embeddings trained with two contrastive losses (sample-LLM, sample-sample) | Routing when several LLMs perform well on a query | Needs query-level performance data per LLM; accuracy-oriented | No overlap in method. V2 has no query-level performance data |
| **LLM Bandit** | Yang Li. arXiv:2502.02743 (Feb 2025); single author; I did not find a peer-reviewed venue. https://arxiv.org/abs/2502.02743 | Multi-armed-bandit formulation with preference-conditioned dynamic routing; model "identity vectors" built from evaluating models on benchmark prompts; the user sets a performance-cost trade-off at inference time | Cost-efficient selection with user preference and unseen models | Evaluating new models requires running them on prompts; focus on accuracy and cost | Closest to V2 in letting the user's trade-off weights steer selection. Differences: it learns a policy from evaluation runs, V2 does not run models |
| **CP-Router** | J. Su, F. Lin, Z. Feng, H. Zheng, T. Wang, Z. Xiao, X. Zhao, Z. Liu, L. Cheng, H. Wang. AAAI 2026 (vol. 40); arXiv:2505.19970 (May 2025); doi:10.1609/aaai.v40i39.40589 | Training-free routing between an LLM and a large reasoning model using the size of a conformal-prediction set, with Full-and-Binary-Entropy calibration of the error rate | Avoid over-spending reasoning tokens on easy multiple-choice prompts | Two models, multiple-choice QA, needs a calibration set and model confidence outputs | Its uncertainty concerns whether an answer is correct and carries a coverage guarantee. V2's intervals concern vendor-documentation quality and carry **no** statistical guarantee. These are different uncertainties and V2 must not borrow its language |
| **GraphRouter** | T. Feng, Y. Shen, J. You. ICLR 2025; arXiv:2410.03834 (v2 Mar 2025) | Heterogeneous graph of task, query and LLM nodes; edge prediction of response quality and cost; inductive for new LLMs; evaluated under three effect-cost weightings | Generalizable LLM selection with performance-cost trade-off | Learned from interaction data | Overlap: weighted effect-cost trade-offs. Difference: learned prediction versus deterministic scoring of declared metadata |
| **EmbedLLM** | R. Zhuang, T. Wu, Z. Wen, A. Li, J. Jiao, K. Ramchandran. ICLR 2025; arXiv:2410.02223 | Encoder-decoder learning compact vector representations of LLMs, usable for routing and for forecasting benchmark performance | Reusable model representations for many downstream tasks | Needs a corpus of model outputs/benchmark results; not a decision method by itself | A representation technique. V2 uses no embeddings |
| **PersonalizedRouter** | Z. Dai, T. Feng, J. You. TMLR (Nov 2025); arXiv:2511.16883 | Graph-based framework that models individual user profiles from interaction data (task, query, candidate LLMs, user decisions) to personalize LLM selection | Per-user preferences over performance, cost, response style | Needs user interaction history | V2 takes user preferences only as stated weights and constraints; no preference learning. Personalization via feedback is kept outside quality |
| **LENS** (identification to confirm) | J. Liu, L. Yu, K. Yue, Z. Tang. "LENS: Latent Precision Inference in Multi-LLM Routing", UAI 2026, PMLR 337:3933-3956. https://proceedings.mlr.press/v337/liu26b.html | Routing as posterior utility maximization under imprecise supervision; marginalizes over a latent precision; variational inference | Noisy supervision of model behaviour | Probabilistic, learned; needs supervision data | Closest in **motivation** (acting under imprecise evidence about models). V2 uses interval sets and tiers instead of a posterior. LENS gives a principled probabilistic treatment that V2 lacks and that needs data V2 does not have |
| **FLARE** (identification to confirm) | Y. Fu, H. Zhong, D. Huang, Y. Lu. "FLARE: Fine-Grained Length-Aware Routing for Resource-Efficient Heterogeneous LLM Serving", ACL 2026 (long), 2026.acl-long.1018. https://aclanthology.org/2026.acl-long.1018/ | Length-based models estimate per-query latency and cost; routing posed as a discrete multi-objective optimization; reports latency and cost reductions of up to 68% and 75% | Resource-efficient serving of heterogeneous LLMs | Needs trained length predictors and serving-side measurements | The one paper that directly addresses the token-estimate problem raised in section 3: it **predicts** output length. AI Compass has no such predictor, so V2 cannot offer budget guarantees. Its discrete multi-objective framing is the same family as V2's |

### 4.2 Benchmarks and evaluation frameworks (not routing algorithms)

| Work | Details | Relevance |
|---|---|---|
| **RouterBench** | Q. J. Hu, J. Bieker, X. Li, N. Jiang, B. Keigwin, G. Ranganath, K. Keutzer, S. K. Upadhyay. arXiv:2403.12031 (Mar 2024). Benchmark and framework with over 405k inference outcomes for evaluating multi-LLM routers. I found it presented as a poster at the ICML 2024 Agentic Markets Workshop and **could not confirm** an ICLR 2025 or other archival venue | The repository's `PHASE2B_RESEARCH_REPORT.md` says "ICLR 2025 / arXiv 2024". I could not support that and it should be corrected or sourced. A way to evaluate routers given outcome data; V2 has none |
| **LLMRouterBench** | arXiv:2601.07206. States that several routing methods, including a commercial router, do not outperform a best-single-model baseline on its benchmark. Authors not captured here | A caution: learned routers do not automatically beat a simple baseline, so V2 must report baselines honestly |
| **HELM** | P. Liang et al., "Holistic Evaluation of Language Models", TMLR 2023, arXiv:2211.09110 | Standardized conditions for comparing models (section 2.2) |

### 4.3 Robust, uncertainty-aware multi-criteria and optimization references

| Work | Contribution | Relevance |
|---|---|---|
| Greco, Mousseau, Słowiński, "Ordinal regression revisited: multiple criteria ranking using a set of additive value functions", EJOR 191(2), 2008 (pages shown as 415-435 and 416-436 by different indexes) | **Necessary** preference (holds for all compatible parameter sets) and **possible** preference (holds for at least one) | V2's certain dominance is a necessary-preference notion. Not new |
| Salo, Hämäläinen, "Preference ratios in multiattribute evaluation (PRIME)", IEEE Trans. SMC-A 31(6):533-545, 2001 | Dominance structures and decision rules under incomplete preference information | Same |
| Lahdelma, Hokkanen, Salminen, "SMAA: Stochastic multiobjective acceptability analysis", EJOR 106(1):137-143, 1998, doi:10.1016/S0377-2217(97)00163-X | Acceptability indices from exploring weight space; uncertain data as probability distributions | Weight-space diagnostic; needs distributions the registry lacks |
| Ide, Schöbel, "Robustness for uncertain multi-objective optimization: a survey and analysis of different concepts", OR Spectrum 38(1), 2016, doi:10.1007/s00291-015-0418-7; Ehrgott, Ide, Schöbel, "Minmax robustness for multi-objective optimization problems", EJOR 239(1):17-31, 2014; Schöbel, Zhou-Kangas, "The price of multiobjective robustness", EJOR 2021, doi:10.1016/j.ejor.2020.09.045 | Minmax robustness for vector-valued objectives under uncertainty sets | The framework in which interval worst-case optimization sits; more general than V2 needs |
| Mohajerin Esfahani, Kuhn, "Data-driven distributionally robust optimization using the Wasserstein metric: performance guarantees and tractable reformulations", arXiv:1505.05116 | Worst-case expected cost over a Wasserstein ball around the empirical distribution | Needs an empirical distribution (samples). The registry has point estimates with tiers, so not applicable now |
| Hurwicz (1951), Cowles Commission Discussion Paper, Statistics No. 356; Arrow & Hurwicz appendix in *Studies in Resource Allocation Processes* | Optimism-pessimism index `α·min + (1−α)·max` | Continuum between maximin and optimistic rules. Verified through secondary sources and the publisher record; the original note itself was not retrieved |
| García-Cascales, Lamata, "On rank reversal and TOPSIS method", Math. Comput. Modelling 56(5-6):123-132, 2012, doi:10.1016/j.mcm.2011.12.022 | Documents rank reversal in TOPSIS when alternatives are added | Supports rejecting TOPSIS |
| Brown, Cai, DasGupta (2001), above | Interval estimation for a binomial proportion | Used only to bound what Wilson can claim (2.4) |

### 4.4 What can and cannot be claimed

- None of the routing papers solves the problem V2 addresses, because each learns from outcome or interaction data. **This is a statement about the abstracts reviewed, not a systematic literature search**, and it must not be presented as an established research gap.
- Every ingredient of V2 (additive utility, interval values, necessary dominance, maximin, weight-space sensitivity, ordinal grading) exists in the MCDM and robust-optimization literature above. Combining them for a metadata-only catalogue recommender is an engineering application, not a new algorithm.
- No claim that V2 recommends better products than V1, than any router above, or than a baseline is supported by anything in this review.

---

## 5. Product-boundary check

| Draft element | Conflict with recommendation-only? | Action |
|---|---|---|
| Observed T3 reliability (Wilson) and observed p50 latency from execution history | **Yes**, no new executions occur; historical data are not refreshed | Remove from core (2.3, 2.4) |
| Query-level benchmark evidence | No, if it is published data | Allowed with comparison groups (2.2) |
| API keys influencing rank | Not present; test T-26 retained | Retain |
| Learning feedback into quality | Not a provider call, but contaminates a model property | Keep outside quality (retained from draft) |
| Escalation, answer evaluation | Not present | Confirmed absent |
| Draft section 5 live-registry columns | Database change; **no Neon or schema change is proposed or made** | Defer; needs separate approval |
| Neon / existing database configuration | Unchanged | Confirmed |

---

## 6. Alternative formulations

Setting: `n ≤ 50` candidates, `D = 6` objectives, interval values by tier, user weights with optional uncertainty.

### 6.1 Definitions

- **A. Interval Pareto plus maximin utility** (draft): per-model `L`; certain dominance as an order component.
- **A′. Maximin on a per-model score with dominance as annotation** (the draft with frontier-first removed).
- **B. Interval midpoint ranking with robustness indicators**: rank by `U` (or by the point estimate); intervals feed diagnostics only.
- **C. Minimax regret** over uncertain metrics (and optionally weights). For independent cell intervals and additive utility the worst case sets the candidate to `ℓ` and the rival to `h`, giving `regret(a) = max_{j≠a}(H_j − L_a)`. Choosing the minimum-regret model equals choosing the maximum `σ_a = L_a − max_{j≠a} H_j`. So minimax regret equals the lower-bound ranking with an adjustment for the single model that has the highest `H` (it is compared against the second-highest `H`). With uncertain weights in a polytope the maximization over weights is a linear program over the polytope's vertices.
- **D. Robust or distributionally robust multi-objective alternatives**: minmax robust efficiency (Ehrgott, Ide and Schöbel 2014; Ide and Schöbel 2016) for set-valued uncertainty; Wasserstein DRO (Mohajerin Esfahani and Kuhn) for sample-based ambiguity.
- **Hurwicz family**: `S_α = α L + (1 − α) H` (α = 1 is maximin, α = ½ is midpoint). Ranking is per-model.

### 6.2 Comparison

| Criterion | A (draft, frontier-first) | A′ (L, dominance annotated) | B (midpoint) | Hurwicz `S_α` | C (minimax regret) | D (robust / DRO) |
|---|---|---|---|---|---|---|
| Mathematical assumptions | Independent cell intervals, additive utility | same | same | same | same; weights polytope optional | Uncertainty set (robust) or a **sample-based distribution** (DRO) |
| Per-model score (IIA-safe) | **No** (tested) | **Yes** (tested) | **Yes** | **Yes** | **No** (tested: best changes after removal 66/4,000; known for Savage's rule) | Depends on formulation |
| Missing data in the rank | Worst case (0) | Worst case | Neutral (0.5) | Between, set by α | Worst case against best rival | Worst case in set |
| Conservatism | High | High | Low | Tunable | High, relative | High |
| Interpretability | Medium; frontier ordering is surprising (2.5.3 outcome D below C) | High | High | High | Low for end users | Low |
| Compute (n=50, D=6) | `O(n²D)` ≈ 15,000 | `O(n²D)` for annotation | `O(nD)` | `O(nD)` | `O(n²)` | LP/convex programs, orders of magnitude more |
| Weight sensitivity | Relative scaling (flawed) | Weight-space margin | Weight-space margin | Weight-space margin | Vertex enumeration | Set-based |
| Fit with this registry | Needs tiers | Needs tiers | Works with point estimates only | Needs tiers | Needs tiers | **Poor**: no samples, no empirical distribution, no uncertainty-set justification |
| Evidence it behaves differently from the simpler options on this data | n/a | Best Match equals A (by 1.1) | **Same Best Match as A′ in 12 of 12 real queries** (pilot) | not run | not run on real pool | not applicable |

On the real pool A′ and B choose the same Best Match for all 12 queries; they differ in 5% to 13% of random synthetic pools once tiers or clipping differ (section 2.7). So the data in hand cannot choose between maximin and midpoint; synthetic pools show they are not equivalent.

### 6.3 Recommendation

The evidence supports a **narrow** recommendation and does not support a single named algorithm yet:

1. **Rank by one per-model scalar** `S` (not frontier-first and not minimax regret as the primary key). This follows from a proof and from tests (independence of irrelevant alternatives, exact removal and insertion properties).
2. **Use interval structure for diagnostics, not for the rank order:** necessary dominance flags, separation `σ` against the best rival, weight-space margin, and evidence coverage `C`.
3. **Leave the conservatism of `S` an explicit, user-visible policy choice** (Hurwicz α) until E1 to E5 are run. The draft recommended maximin; this review does not find the evidence to keep or reject that recommendation.
4. **Defer** DRO and SMAA. SMAA can later serve as a weight-space diagnostic with an assumed uniform weight density; its acceptability indices would then be model-based, not data-based.

---

## 7. Corrected experiment plan

Algorithmic properties (what the method computes) and real-world recommendation quality (whether the output is the better product for a user) are separated. Only the second needs human or outcome data.

| ID | Experiment | Data | Measures | Human-labelled data needed? | Run in this review? |
|---|---|---|---|---|---|
| E1 | Missing metadata at 0, 10, 20, 30, 50%, MCAR and MNAR (drop low-evidence values preferentially), plus targeted removal from the winner | Registry (real) with synthetic deletion | Top-1 stability, Kendall τ, frontier size, grade distribution, per-objective sensitivity | No | Pilot MCAR only (2.8) |
| E2 | Noisy metadata: add noise or quantize ratings; check how often the true value lies inside the policy interval under the stated noise model | Synthetic noise model | Interval coverage under the assumed model, rank stability | No. Coverage holds only for the assumed noise, not for reality | Not run |
| E3 | Stale evidence: apply age-based and version-based downgrades | Historical registry snapshots (do not exist yet) or simulated release cadence | Rank change versus age | Real analysis needs dated snapshots | Not run |
| E4 | Different tier assignments: randomly reassign which cells are T1, T2, T3 | Synthetic on real pool | Disagreement between rank rules; winner stability | No | Synthetic pilot (disagreement 5% to 13%) |
| E5 | Interval-width policies and reference ranges: sweep `δ_T1, δ_T2, δ_T3` independently and by tier mix; sweep `[c_lo, c_hi]`, `[s_lo, s_hi]` | Real pool, synthetic pools | Winner and order stability | No | Uniform-tier sweep only: no change (2.7) |
| E6 | Candidate insertion and removal: exact property tests, then leave-one-out and one-in on the real pool | Synthetic and real | Violation counts per rule | No | Synthetic: 4,000 instances per rule (1.2). Real-pool replay not run |
| E7 | Weight perturbation: weight-space margin versus relative-scaling breakpoint; switching on a zero-weight objective; compare with SMAA weight sampling | Real and synthetic | Margin distribution; agreement between measures | No | Spec example and one real-pool margin set (0.012 to 0.125) |
| E8 | Ambiguous query classification: category ambiguity versus two-category runs | Independent queries labelled for ambiguity and category by at least two annotators, with agreement (Cohen's κ) | Category accuracy, ambiguity detection, run-agreement | **Yes** | Not run (the 27-case suite is self-authored and was tuned) |
| E9 | Explicit privacy and budget constraints with estimated tokens | Synthetic registry with known truth; real token counts from offline tokenizers on a text corpus to estimate the estimator's error | Zero verified-constraint violations; false-exclusion rate; distribution of estimator error | Real token counts need a text corpus; no human labels | Not run |
| E10 | Editorial-rating removal and replacement | Real pool; ratings from ≥ 2 independent raters with a written rubric | Winner change; inter-rater agreement (for example Krippendorff's α) | **Yes** for the replacement ratings | Removal run (2.5). Independent raters not available |
| E11 | Comparability failures: mix benchmark scores from incompatible protocols | Synthetic injections; real public scores for the same models under different protocols (each source verified) | Rank flips; rank correlation across protocols | No for synthetic; sources must be verified | Not run |
| E12 | Real-world quality: expert pairwise judgements of which product to use for a query; baselines strongest, cheapest, static, V1, V2 | Independent expert-labelled queries (pre-registered), ≥ 200 labelled outcomes for any calibration (the repository's own minimum, not a statistical derivation) | Top-k agreement with experts, calibration (Brier, expected calibration error) | **Yes** | Not run |

Synthetic experiments (E1, E2, E4, E5, E6, E7, E9, parts of E11) test **properties of the method**. They cannot show the method recommends better products.

---

## 8. Decision table

| Component (draft section) | Decision | Reason |
|---|---|---|
| Hard-constraint eligibility, unknown fails verified constraints (2.2) | **Retain**, revise vocabulary | Correct and testable. Add the status vocabulary of 3.1, 3.2 |
| Budget "hard guarantee" on estimated tokens (2.2) | **Revise** | Cannot be guaranteed (3.1) |
| Strict privacy (2.2) | **Revise** | `documented_for_scope` with date and plan (3.2) |
| Inferred requirements never hard (2.1, 2.2) | **Retain**, extend | Add warning plus "treat as strict" option |
| Fixed reference-range normalization (2.4) | **Retain** | Set-independent by proof; ranges themselves are policy, swept in E5 |
| Evidence tiers T0 to T3 (2.6) | **Revise** | Mechanical assignment rules, provenance fields, "unanchored" class (2.5) |
| Interval half-widths δ as ranking input (2.6) | **Defer** | Policy not measurement; uniform sweep uninformative (2.7). Use for diagnostics until E5 |
| Wilson interval on observed reliability (2.6) | **Remove** from core | Conflicts with recommendation-only; independence assumption fails (2.4) |
| Observed p50 latency (2.3) | **Remove** from core | No new executions (2.3) |
| Staleness flat 365 days (2.6) | **Revise** | Bind evidence to product version; calendar limit as fallback (2.6) |
| Editorial `RATINGS` in the rank | **Revise: gate** | Decide the winner in 8 of 12 queries; unanchored provenance. Needs your decision (O-A) |
| Frontier-first ranking key (2.5.3 to 2.5.4) | **Remove** | Breaks removal and insertion properties (1.2) |
| Certain (necessary) dominance | **Retain** as annotation and diagnostic | Sound (1.1); not a rank component |
| Maximin `L` as the rank key (2.5.4) | **Defer** | Choice among maximin, midpoint, Hurwicz is a policy decision (6.3); decide after E1, E4, E5 |
| Midpoint `U` with clipping | **Revise** | Clipping bias (1.4) |
| ε-tie ordering (2.7) | **Remove** from ordering | Non-transitive (1.5); keep as reported diagnostic |
| Weights: no query-inferred multipliers in ranking weights (2.5.5) | **Retain** | Consistent with the audit finding F8; scenarios stay |
| Quality-weight floor as warning (2.5.5) | **Retain** | |
| Learning bonus outside quality (2.5.5) | **Retain** | |
| Weight breakpoint by relative scaling and bisection (2.9, 7.2, 8.1) | **Replace** | Weight-space margin (1.3) |
| Pair perturbations as defined | **Replace** | Same |
| Separation `σ` | **Revise** | Use best rival (1.4) |
| Evidence precision `P` | **Replace** | Evidence coverage `C` (1.6) |
| Weakest-link grade | **Retain concept, rename, defer bands** | "Robustness grade"; bands from E7 |
| Numeric `confidence_value` kept as deprecated | **Retain** | Compatibility |
| Minimax regret as primary rule | **Remove** as primary | IIA failure (1.2). Its `σ` form stays as diagnostic |
| SMAA | **Defer** | Needs distributions; weight-space diagnostic possible later |
| Distributionally robust optimization | **Defer** | No sample data |
| TOPSIS | **Remove** | Rank reversal; cannot represent unknowns |
| Feature-flag migration, shadow mode, no DB change for approved pool | **Retain** | Sound |
| Live-registry column additions (5.1 to 5.3) | **Defer** | Separate approval; no Neon change here |
| Test specification (9) | **Revise** | Add tests T-40 to T-46 below; fix T-14 and T-19 (P3) |

### Tests to add or correct in the specification

| ID | Test |
|---|---|
| T-14 (corrected) | Under the new key, a certainly dominated model is never ranked above its dominator (follows from `L`), checked by property test |
| T-19 (corrected) | Removing the winner promotes the runner-up **for a per-model score**; the same test must fail for frontier-first (regression guard documenting why it was removed) |
| T-40 | Pairwise order of two existing models is unchanged by inserting any third model (property test, per-model score) |
| T-41 | `σ` equals `L_top − max_{j≠top} H_j`; example 3.3 gives −0.255 |
| T-42 | Weight-space margin equals 0.0778 on example 3.3 (against a brute-force check) and handles switching on a zero-weight objective |
| T-43 | Clipped intervals: midpoint of a clipped interval is not used for ranking; ranking by the point estimate is clip-invariant |
| T-44 | Unknown pricing returns `unverifiable`, not `estimated_over_budget` |
| T-45 | No status named "guaranteed" is emitted for an estimated request cost |
| T-46 | Comparison-group enforcement: values from different groups are never subtracted |

---

## 9. Implementation-readiness verdict

**Not ready to implement.** Do not start Algorithm V2 as drafted.

Blockers:

1. Replace the ranking key (frontier-first removed) and re-prove the properties for the new key. *Resolved on paper in this review; requires the revised specification.*
2. Fix `σ`, the weight margin and the grade bands; no band has a basis yet (E7).
3. Decide the treatment of unknowns in the rank (maximin, midpoint, Hurwicz α) and approve it.
4. Decide the status of the editorial ratings (gated, replaced after independent rating, or kept as labelled T1).
5. Define the evidence-record fields and mechanical tier rules, and the product-version binding for staleness.
6. Adopt the budget and privacy status vocabulary (section 3) and remove "guarantee" wording.
7. Remove observed latency and reliability from the core to respect the product boundary.
8. Run E1, E4, E5, E6 (real-pool replay), E7 before fixing parameter defaults.
9. Supply or point to the survey and synopsis so the literature comparison can be reconciled with the project's own entries, and confirm the FLARE and LENS identifications.

What could proceed independently once approved: nothing that changes behaviour. The per-metric evidence record (schema) does not depend on the algorithm choice, but it is a data-model change and needs separate approval, and it would be wasted if the evidence policy in blockers 4 and 5 changes.

A **revised `ALGORITHM_V2_SPEC.md` is not produced.** The corrections in sections 1 to 3 are well supported, but the central design choices (3 and 4 above) are decisions, not findings. A revised specification before those decisions would hide them. The draft now carries an errata banner pointing here.

### Open questions for you

| ID | Question |
|---|---|
| O-A | Should the editorial ratings stay in the ranking (labelled), be gated behind a flag, or be replaced after independent rating? |
| O-B | Conservatism of the score: maximin, midpoint, or a stated Hurwicz α? Decide after E1/E4/E5, or choose now? |
| O-C | May the registry record product-version identifiers and per-metric sources (schema work, separate approval)? |
| O-D | Where are the literature survey and synopsis? Are FLARE and LENS the routing papers identified in 4.1? |
| O-E | Is a "robustness grade" shown to users acceptable, given that on current data it cannot exceed "moderate"? |

### Assumptions and limitations of this review

- All real-pool numbers come from 12 labelled queries and the editorial ratings I wrote; they illustrate behaviour, not quality.
- The pilot's V2 variants did not apply the draft's rule that an explicit feature request raises the fit weight. The pilot disagreed with V1 on 4 of 12 queries (including a news query that explicitly asks for citations, where V1 picks Perplexity and the pilot picks ChatGPT), so those disagreements are partly artefacts of the pilot, not evidence about the proposal.
- Random property tests give evidence, not proofs; proofs are given where stated.
- Literature records were verified from primary or publisher pages and abstracts, not by reading every full text. Venue and page details marked as unconfirmed are unconfirmed. Hurwicz's original note and Savage's original paper were not retrieved; they are cited through secondary sources.
- No provider, API key, database or network call beyond web research was used.

---

## 10. Errata to earlier statements

| Where | Statement | Correction |
|---|---|---|
| `ALGORITHM_V2_SPEC.md` 2.5.3 / 2.5.4 | frontier-first key | Removed (1.2) |
| 8.4 P2 and P3 | "removing the winner promotes the runner-up exactly"; insertion changes "only if the new model outranks" | P3 false under frontier-first; order stability false under frontier-first. Holds for a per-model score |
| 3.3 | "Ranking by L: A > B > C > D" | A, B, D, C. The draft order is frontier-first |
| 2.8, 3.5 | `σ = L_top − H_next` | `σ = L_top − max_{j≠top} H_j`; −0.255 in example 3.3 |
| 3.4, 3.5 | ε* = 0.35 as stability | Overstates; pair 0.20; weight-mass margin 0.078 |
| 3.6 | ε* up to 2.0 from downward scaling | Invalid for ε > 1 |
| 2.6 | Wilson interval for observed reliability | Removed |
| 2.2 | "hard" budget on estimated tokens | Not a guarantee |
| 6 (complexity paragraph) | comparison to a UI timing | Removed; unsupported |
| `PHASE2B_RESEARCH_REPORT.md` (not modified here) | RouterBench "ICLR 2025 / arXiv 2024" | Not supported by sources found; see 4.2 |
| `ecosystem-routing-implementation-report.md` (project doc) | says metrics are unavailable | Outdated since the editorial ratings were added; update separately |

---

## Appendix: scripts (outside the repository; reproduce with `python3`)

`review_pool2.py` imports the repository (`app.services.routing_engine.pipeline`, `app.data.approved_ecosystem`) and therefore depends on the working-tree state of 2026-11-20.
