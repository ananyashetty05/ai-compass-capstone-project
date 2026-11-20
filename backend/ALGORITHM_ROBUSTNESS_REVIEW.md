# AI Compass: Algorithm Robustness Review

Date: 2026-11-20. Status: **review and specification only. Nothing here was implemented.**
Companions: `EXPERIMENTAL_DESIGN_V2.md` (experiments and metrics), `BASELINE_DEFINITIONS.md` (E1 to E10).
Builds on: `ALGORITHM_V2_SPEC.md` (draft, carries an errata banner) and `ALGORITHM_V2_REVIEW.md` (first review). This document does not repeat that review's derivations; it cites them and adds new audit findings, new counterexamples, the baseline-fairness analysis and the verdict.

## 0. Verdict, naming, and evidence status

**Verdict: REQUIRES MATHEMATICAL REVISION.** Not ready for implementation. The revision is specified in section 6; two further items need data or decisions before parameters can be fixed (section 8).

**Naming.** The string "ER-PCR" does not appear in the repository, the project documents or the earlier specification. This review treats it as your name for the proposed V2 algorithm (the draft in `ALGORITHM_V2_SPEC.md`, called EIPMU there: certain-dominance frontier, interval utilities, maximin). If ER-PCR is a different design, tell me and sections 2 and 6 need re-checking against it.

**Status labels.**

| Label | Meaning |
|---|---|
| **[PROVED]** | argument given here; where a random test also exists it is named, and is evidence only |
| **[EXECUTED]** | a script was run in this session or the previous review; script and result are stated |
| **[COUNTEREXAMPLE]** | concrete input where the property fails; hand-checkable, and executed where stated |
| **[BY INSPECTION]** | read from the source, not executed |
| **[OPEN]** | not established |
| **[NOT RUN]** | designed only |

**What was executed in this review** (scripts in `/tmp/v3/`, outside the repository): the V1 Pareto-marking counterexample (imports the real `_mark_pareto`), the V1 log min-max set-dependence check (imports the real `_log_minmax_utility`), the fixed-range flip, the tie-rule removal counterexample, the disclosure-incentive check, and confidence-interval widths for small samples. Everything else quoted from earlier work was executed in the previous review (`/tmp/v2/*.py`) and is cited as such, not re-run. **No benchmark result, no model-quality result and no comparison between algorithms on real recommendation quality exists, and none is claimed.**

---

## 1. Audit of the current algorithm (V1) and the V2 draft

### 1.1 What V1 actually does (approved-ecosystem path)

[BY INSPECTION] `routing_engine/scoring.py::score_ecosystem` and `select`:

```
align_m  = Σ_k part_k · fit_k                      (feature 0.5, intent 0.3, category 0.2; intent only for some categories)
used     = {alignment} ∪ {quality, latency, reliability, risk} ∪ {cost if a cost preference was stated}
weights  = alignment 0.55 ; others 0.45 · normalized user weights
U_m      = Σ_d w_d · u_d          (unknown → 0)
R_m      = Σ_d w_d · max(0, u_d − (1 − conf_d) · ρ)        ρ = 0.25
order    = sort by (−R, tie key); candidates within ε = 0.005 of the top are re-ordered by the tie key
confidence = 0.35·category_conf + 0.35·min(1, margin/0.10) + 0.30·feature_support, with caps 0.45 / 0.60
```

### 1.2 Audit findings

Severity: **H** can change a recommendation or a claim, **M** weakens a claim, **L** documentation.

| # | Area | Finding | Evidence | Sev |
|---|---|---|---|---|
| A1 | Arbitrary constants | `ALIGN_SHARE = 0.55`, `ALIGNMENT_WEIGHTS` (0.5/0.3/0.2), `SECONDARY_ROLE_FIT = 0.85`, `EDITORIAL_CONFIDENCE = 0.5`, `ρ = 0.25`, `ε = 0.005`, `MARGIN_FULL = 0.10`, confidence weights 0.35/0.35/0.30, level cut-offs 0.75/0.5, caps 0.45/0.60, access-class utilities (1.0/0.75/0.5/0.3). None has a derivation or a sensitivity study in the repository | source | H |
| A2 | Fixed share vs user weights | Fit carries 55% of the score regardless of what the user asked for. A user who sets quality weight to 0.9 still cannot move more than 45% of the score | source | H |
| A3 | Uncertainty penalty is nearly inert | Every editorial cell has confidence 0.5, so R subtracts the same constant 0.125 from every editorial utility; the alignment term subtracts a query-dependent constant that is the same for all candidates. R therefore ranks like U except where the clip at 0 bites (utilities below the constant). On the approved pool the "robust score" adds no information beyond the clip. | derived from source; the clip claim is [BY INSPECTION] | M |
| A4 | Missing = 0 | Unknown utility and confidence are 0 (`missing_policy = "pessimistic"`), so an undocumented product is scored as if it were worst on that objective | source | H |
| A5 | Pareto marking | A candidate with an unknown objective can never be marked dominated, even when strictly worse than another on every known objective | **[EXECUTED][COUNTEREXAMPLE]** A=(0.9,0.9,0.9,0.9,0.9); B=(0.2, *unknown*, 0.2, 0.2, 0.2). Real `_mark_pareto`: B is Pareto-optimal. A control model C with all five values 0.2 is dominated by A | H |
| A6 | Set-dependent normalization (live path) | `_log_minmax_utility` normalizes cost across the candidate set. Inserting a cheaper model changes everyone else's cost utility | **[EXECUTED][COUNTEREXAMPLE]** costs {1e-4,1e-3,1e-2} → utilities (1.0, 0.5, 0.0); add a model at 1e-6 → (0.5, 0.25, 0.0, 1.0). The same three models, the same weights, different utilities | H |
| A7 | Weight sensitivity | The live path perturbs each weight by ±20% *relative*. A zero weight cannot be perturbed, so "the user adds a cost preference" is invisible; on the approved pool `weight_stability` is not computed at all (`None`) | source | M |
| A8 | ε-tie rule | The tie window is anchored at the leader, which makes Best Match depend on candidates that are not winners | **[EXECUTED][COUNTEREXAMPLE]** scores T=0.508, m=0.504, c=0.500, ε=0.005, tie key prefers c over m over T. All three present: winner m. Remove T (a non-winner): winner c | H |
| A9 | "Confidence" is not a probability | The value is a weighted sum of a classifier confidence, a saturating margin and a coverage fraction. It has never been compared with labelled outcomes; calling it "confidence" invites a probabilistic reading it does not support | source; the repository's own labelled-outcome minimum (200) is not met | H |
| A10 | Editorial ratings carry the result | Quality, speed, reliability and risk for the 37 products are hand-set values with no source and no rubric. Removing them (set unknown) changes Best Match in 8 of 12 labelled queries | **[EXECUTED]** previous review, `review_pool2.py` | H |
| A11 | Privacy and budget | Strict privacy excludes unknown data handling (tested). Budget uses `estimated_tokens × price`; the token count is an estimate and output tokens are not controlled | source + test list | H |
| A12 | Self-authored evaluation set | The 27-case suite and the 12 queries used above were written by the project author and used to tune the rules. They cannot support generalization claims | project history | H |

### 1.3 Findings about the V2 draft

Carried from `ALGORITHM_V2_REVIEW.md` (derivations there); restated with their status so this document stands alone.

| # | Finding | Status |
|---|---|---|
| B1 | Frontier-first ordering breaks the removal and insertion properties the draft claimed: removing the winner fails to promote the runner-up (559 of 4,000), inserting a model reorders existing models (249 of 4,000) | **[EXECUTED]** previous review, hand counterexamples in 2.6 below |
| B2 | σ must use the best rival's upper bound: example 3.3 gives −0.255, not −0.175; the lower-bound order there is A, B, D, C | **[PROVED]** by recomputation |
| B3 | Relative-scaling breakpoint ε* overstates stability; the exact minimum weight shift in example 3.4 is 0.0778 against the draft's 0.35 | **[EXECUTED]** (200,000-draw brute force gave 0.078) |
| B4 | The 0.20/0.40 and 0.70/0.90 bands have no derivation | [BY INSPECTION] |
| B5 | Maximin treats an unknown as 0 in the rank, reproducing V1's "missing = 0" | **[PROVED]** (2.7) |
| B6 | Midpoints of clipped intervals are biased; lower-bound and midpoint winners differ in 5.1% of random same-tier pools because of clipping | **[EXECUTED]** previous review |
| B7 | Interval widths and reference ranges are policy values presented as evidence intervals | [BY INSPECTION] |
| B8 | Observed T3 reliability and latency with a Wilson interval contradict the recommendation-only boundary and the independence assumption | [BY INSPECTION] |
| B9 | A guaranteed budget cannot rest on an estimated token count | **[PROVED]** (section 4) |

### 1.4 Contradictions between stages

| # | Stage A | Stage B | Contradiction |
|---|---|---|---|
| C1 | Eligibility ("hard constraints are never traded") | Category gate from query classification | The classifier is an inference but it removes candidates like a hard constraint. An inferred requirement acts as a hard one |
| C2 | Weights ("only explicit wishes count") | V1 alignment share 0.55 | A fixed system weight dominates the user's explicit weights |
| C3 | Ranking key (exact lexicographic) | Tie window ε (draft 2.7) | Two incompatible orders; the second is intransitive and removal-unstable (A8) |
| C4 | "Intervals fix missing data" | Maximin rank | Unknown contributes its lower bound 0, the old rule |
| C5 | Frontier-first | "Winner = argmax L" | Same winner, different second place; the explanation shows one order and the score another |
| C6 | Recommendation-only | Observed T3 evidence | Observation requires executions the product no longer performs |
| C7 | Evidence tiers (T1 ±0.15) | V1 `EDITORIAL_CONFIDENCE = 0.5` | Two different, unrelated uncertainty models for the same value |
| C8 | Strict privacy | All 37 approved products have unknown data handling | Strict privacy returns no recommendation for every query. Correct but untested on real data and it makes the feature vacuous on the approved pool |

---

## 2. Mathematical properties

Notation: candidate m has per-objective interval [ℓ_d, h_d] ⊆ [0,1]; weights w ≥ 0, Σw = 1; L = Σ w ℓ, U = Σ w (ℓ+h)/2, H = Σ w h. a ≻ b (certain dominance) iff ℓ_d(a) ≥ h_d(b) for every d with w_d > 0 and strictly for one.

### 2.1 Hard-constraint invariance

Claim: **eligibility of a candidate depends only on that candidate and the stated constraints, never on weights, other candidates, or scoring.**

- **[PROVED] by construction**, provided the eligibility predicate is a function E(m, constraints, evidence(m)) and no set-level quantity (rank, normalization, pool cap) enters it. Consequences: (i) changing weights never changes the eligible set; (ii) tightening a constraint can only shrink the set; (iii) with a per-model ranking score, if the previous winner is still eligible after tightening, it is still the winner (removal of non-winners, section 2.6).
- Caveats that break the premise on the approved pool and must be tested, not assumed: the pool cap of 50, the category gate (an inferred, not stated, constraint, C1), and `observed_latency` entering `check_model` (eligibility would then change over time).
- **Status of the guarantee for budget:** none (section 4).

### 2.2 Fixed normalization and candidate-set dependence

- Set-dependent min-max (V1 live path): **[EXECUTED][COUNTEREXAMPLE]** A6. Property fails.
- Fixed reference ranges (V2): utility of a cell is a function of that cell alone → score of a model is independent of the other candidates **[PROVED]**.
- Fixed ranges are not neutral. They are policy, and the endpoints can decide a winner. **[EXECUTED][COUNTEREXAMPLE]** weights quality 0.5, cost 0.5; A: quality 0.50, cost 1e-4; B: quality 0.90, cost 1e-2; cost utility `1 − log10(c/lo)/log10(hi/lo)`.

| Cost range | S_A | S_B | Winner |
|---|---|---|---|
| [1e-5, 1e-1] | 0.625 | 0.575 | A |
| [1e-6, 1e0] | 0.583 | 0.617 | B |

- Clamping to the range loses information: all costs at or below `lo` get utility 1, so a 10× price difference below `lo` is invisible. Whether the range covers the real catalogue is [OPEN] (needs the live registry's price distribution).

### 2.3 Interval dominance

| Property | Status | Basis |
|---|---|---|
| a ≻ b ⇒ L_a > L_b | **[PROVED]** | L_a − L_b ≥ Σ w(ℓ_a − h_b) ≥ 0, strict where the strict dimension has weight > 0. 17,234 random dominating pairs, 0 violations (previous review) |
| ≻ is transitive | **[PROVED]** | ℓ_a ≥ h_b ≥ ℓ_b ≥ h_c |
| ≻ is irreflexive and asymmetric | **[PROVED]** | strictness on one dimension |
| Converse (L_a > L_b ⇒ a ≻ b) | **[COUNTEREXAMPLE]** | draft example 3.3: L_D = 0.55 > L_C = 0.395 but neither dominates |
| Dominance is weight-free | **[COUNTEREXAMPLE]** | it is evaluated over weighted objectives only. A model that is worse only on a zero-weight objective is dominated; raise that weight and it is not |
| "Not dominated" means "good" | **[COUNTEREXAMPLE]** | **[EXECUTED]**: B has one unknown cell [0,1] and is worse than A by 0.7 on the other; A does not certainly dominate B. One unknown cell is enough to stay on the frontier, the same defect as A5 |

Therefore the frontier is a set of **not certainly dominated** models, not a set of good models, and its size grows with missing data. Use the term "undominated", report its size, and never use it as a ranking component.

### 2.4 Pareto frontier correctness

- V1 `_mark_pareto`: **[EXECUTED][COUNTEREXAMPLE]** A5. Correct only among candidates with identical known-objective signatures.
- Complexity: O(n²D) worst case for n ≤ 50, D ≤ 6, about 15,000 comparisons: not a concern.
- Correctness of a frontier requires a stated order relation. For intervals there are two natural ones: certain (ℓ_a ≥ h_b, used here) and possible (h_a ≥ ℓ_b). They give different frontiers: the possible-dominance frontier is smaller and the certain-dominance frontier is larger. **[OPEN]**: which one the product wants is a policy question.

### 2.5 Maximin ranking

- argmax L lies on the undominated set **[PROVED]** (a dominator has strictly larger L; 20,000 random pools, 0 violations).
- Maximin is one point of the Hurwicz family S_α = αL + (1−α)H (α = 1 maximin, α = ½ midpoint) **[PROVED]**. Choosing α is a decision about attitude to ambiguity. No evidence available selects it.
- **Disclosure incentive [EXECUTED]:** one cell, unknown [0,1] versus revealed 0.2 ± 0.15. Maximin: L goes from 0 to 0.05 (revealing helps). Midpoint: 0.5 to 0.2 (revealing a mediocre value hurts). So maximin rewards publishing evidence even when it is poor; midpoint rewards silence. For a registry that wants complete records this favours maximin, but that is a governance argument, not an accuracy argument.
- Maximin penalizes the unknown exactly as hard as a known worst-case value: unknown = 0 in L. It does not distinguish "no data" from "bad data". Report both L and H.

### 2.6 Weight perturbation and breakpoints

Full derivation in `ALGORITHM_V2_REVIEW.md` 1.3. Summary of what must hold in any revision:

| Item | Status |
|---|---|
| For one rival j the sign of L_top − L_j after renormalized relative scaling flips at most once, so bisection is valid per rival; a closed form exists | **[PROVED]** |
| Downward scaling is defined only for ε ≤ 1; at ε = 1 the weighted objective set changes; upward scaling can saturate (ε* = ∞) | **[PROVED]** |
| Relative scaling cannot activate a zero-weight objective | **[PROVED]** |
| Axis ε* = 0.35 vs pair 0.20 vs exact minimum mass shift 0.0778 (example 3.4) | **[EXECUTED]** |
| Weight-space margin δ_j* (smallest total-variation shift making rival j tie the leader; fractional-knapsack greedy over g_d = ℓ_d(top) − ℓ_d(j)) | defined and checked against brute force |

The metric (total variation = half the L1 distance) is a policy choice: it reads as "the fraction of weight mass the user would have to reallocate". An L∞ or per-axis limit gives different numbers. The margin must be reported with its metric.

**Counterexamples to the removal and insertion invariants of the draft (frontier-first)**, weights x = y = 0.5, point values (hand-checkable; executed in the previous review):

| Case | Models (x,y) | Before | After | Property violated |
|---|---|---|---|---|
| Removal | T(0.90,0.90), c(0.70,0.70), m(0.10,0.95) | T, m, c | remove T → c, m (runner-up m not promoted) | runner-up promotion |
| Insertion | T(0.90,0.50), A(0.60,0.70), B(0.30,0.85); insert N(0.80,0.75) dominating A | T, A, B | N, T, B, A | pair order of A, B changes |

### 2.7 Candidate insertion and removal

| Ranking rule | Best Match under non-winner removal | Runner-up promotion | Pair order under insertion |
|---|---|---|---|
| Per-model scalar (L, U, S_α) with exact key | **[PROVED]** invariant | **[PROVED]** | **[PROVED]** (IIA) |
| Frontier-first | invariant [PROVED via 2.3] | **[COUNTEREXAMPLE]** 559/4,000 | **[COUNTEREXAMPLE]** 249/4,000 |
| Minimax regret | **[COUNTEREXAMPLE]** 66/4,000 | **[COUNTEREXAMPLE]** 436/4,000 | **[COUNTEREXAMPLE]** 232/4,000 |
| V1 ε-tie anchored at leader | **[EXECUTED][COUNTEREXAMPLE]** A8 | not tested | not tested |
| V1 live path (min-max normalization) | fails through A6 | not tested | fails through A6 |

(Counts from the previous review's random tests, 4,000 instances; the proof column does not depend on them.)

### 2.8 Missing-evidence treatment

| Rule | Unknown cell contributes | Effect |
|---|---|---|
| V1 pessimistic | 0 | unknown ≡ worst |
| Maximin L | ℓ = 0 | same, with H kept as diagnostic |
| Midpoint U | 0.5 | unknown ≡ average; hides disclosure |
| Hurwicz S_α | (1−α)·1 | in between |
| Marginalization / imputation | needs a distribution | not available |

**[EXECUTED]** pilot (previous review, MCAR, 2,400 draws per level, real approved pool): Best Match unchanged in 68%, 35%, 26% of draws at p = 0.1, 0.3, 0.5 (lower-bound) and 70%, 40%, 31% (midpoint). This measures fragility of the current *data*, because within-category rating gaps are small (weight-space margins 0.012 to 0.125). It says nothing about which rule is right. MNAR (low values missing more often) was not run.

### 2.9 Confidence interpretation

- A probability statement ("the recommendation is correct with probability p") requires a calibration set: labelled queries, a defined correctness event, and a calibration metric (Brier score, expected calibration error). None exists. **[PROVED]** that without one the number cannot be called a probability.
- What the project can honestly report is a **robustness grade**: how far the recommendation moves under stated perturbations (weight-space margin δ*, separation σ against the best rival, evidence coverage C = share of the weight resting on documented or measured cells). Thresholds are policy and must be chosen from the experiment distributions (EXP-3 in the design), not by hand.
- Separate **measurement uncertainty** (a quantity with a method and a sample) from **policy uncertainty** (interval widths, ranges, α, thresholds). Today every registry interval is policy.

### 2.10 Deterministic tie-breaking

- A ranking is deterministic iff the key is a total order on the candidate set. The exact key (score rounded to a fixed precision, then fixed fields, then `model_id`) is total **[PROVED]** because `model_id` is unique.
- A tolerance window is not a total order (a~b, b~c, a≁c: 0.500, 0.504, 0.508 at ε = 0.005) and, anchored at the leader, breaks removal invariance (A8). **Recommendation:** order by exact rounded score; report "within ε of the leader" as a diagnostic.
- Rounding precision is itself a parameter: scores that differ by float noise must tie. Fix the precision (for example 12 decimals) and test it.
- Seeded randomness (baseline E7) must not enter the product ranking.

---

## 3. Evidence and comparability (summary)

Derivations in `ALGORITHM_V2_REVIEW.md` sections 2 and 3. Requirements carried into the design:

1. A quality value is comparable only within one `comparison_group = (benchmark id, version, protocol, evaluation window)`. HELM reports that before its standardization models were on average evaluated on 17.9% of its core scenarios (Liang et al., TMLR 2023, arXiv:2211.09110).
2. Tier assignment is mechanical and auditable: T3 measured (method, n, date, group), T2 documented (source URL, value, date, plan scope), T1 rated against a written rubric by a named rater, T1u unanchored (treated as unknown for ranking), T0 unknown. The 37 current ratings are T1u.
3. Stale evidence is downgraded when it cannot be tied to the current product version; the calendar limit is a fallback and is swept, not asserted.
4. Observed latency and reliability from execution logs are not available in a recommendation-only product.

---

## 4. Hard constraints on estimated inputs

| Term | Definition (proposed) |
|---|---|
| **Verified unit-price compliance** | A documented unit price (source, date) satisfies a stated unit-price limit. The only hard-guarantee budget status, and it is a documentation fact, not a billing guarantee |
| **Estimated request cost** | f(estimated input tokens, assumed output tokens, price, extras). Never a guarantee |
| **Upper-bound compliance** | Holds only if the user supplies hard caps on input and output tokens and the price page is cited; still excludes reasoning tokens, tool calls, caching, minimum charges unless documented |
| **Unknown pricing** | Cannot satisfy a verified requirement; reported as `unverifiable`, not "over budget" |
| **Documented privacy** | A vendor document states a handling commitment for a named plan, region and dated version that matches the user's declared plan |
| **Undocumented / scope unknown** | No such document, or the scope does not match; fails strict privacy with the reason shown |
| **Hard requirement** | Explicit structured field or an unambiguous rule-matched phrase |
| **Inferred preference** | Anything produced by classification or keyword inference. Becomes a weight or a scenario, a warning, or a "treat as strict" option; never an exclusion |

**[PROVED]** that no guarantee on request cost follows from an estimated token count: the true cost is c(n_in, n_out) with n_in and n_out not controlled by the recommender, so a bound requires a bound on n_in and n_out that the recommender does not have. The word "guaranteed" must not appear for estimated cost.

---

## 5. Literature comparison

### 5.1 Sources and verification status

The project's literature survey and synopsis are **not available as files**; the project context lists the names and says they are unverified. Each entry below was checked against a primary or publisher page. **Re-fetched in this session:** FrugalGPT (arXiv page and TMLR PDF header), RouterBench (arXiv listing), RouteLLM router list (framework documentation and a third-party analysis of its code), CP-Router (arXiv page), LLM Bandit (arXiv page), LIME and SHAP (publisher records). **Carried from the previous review without re-fetching:** RouterDC, GraphRouter, EmbedLLM, PersonalizedRouter, LENS, FLARE, and the MCDM and robust-optimization references. I read abstracts and landing pages, not every full text.

### 5.2 Published routing algorithms

| Work | Reference | Method (as verified) | Limitations for AI Compass | Difference from the proposal |
|---|---|---|---|---|
| **FrugalGPT** | L. Chen, M. Zaharia, J. Zou. *FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance.* **TMLR, Dec 2024**, OpenReview `cSimKw5p6R`; arXiv:2305.05176 (May 2023). https://arxiv.org/abs/2305.05176 | Framework for choosing LLM APIs adaptively. The arXiv version names three strategy families (prompt adaptation, LLM approximation, LLM cascade); the cascade calls models in turn and stops when a learned judger scores the answer above a threshold. Reports matching the best single model at up to 98% lower cost on its tasks | Needs executed answers and a trained judger; optimizes accuracy and cost | V2 runs nothing, learns nothing, and makes no cost-saving claim |
| **RouteLLM** | I. Ong, A. Almahairi, V. Wu, W.-L. Chiang, T. Wu, J. E. Gonzalez, M. W. Kadous, I. Stoica. *RouteLLM: Learning to Route LLMs with Preference Data.* ICLR 2025; arXiv:2406.18665. https://arxiv.org/abs/2406.18665 | Trains routers that predict whether a stronger or a weaker model should answer, from human preference data (Chatbot Arena) plus augmentation. Four router types: similarity-weighted ranking (Bradley-Terry style), matrix factorization, BERT classifier, causal-LLM classifier; a threshold sets the share of calls to the strong model | Two models; trained on preference data | V2 is multi-candidate and metadata-only |
| **RouterDC** | S. Chen, W. Jiang, B. Lin, J. T. Kwok, Y. Zhang. NeurIPS 2024; arXiv:2409.19886. https://proceedings.neurips.cc/paper_files/paper/2024/hash/7a641b8ec86162fc875fb9f6456a542f-Abstract.html | Query encoder plus learnable per-LLM embeddings trained with two contrastive losses | Needs per-query performance of every LLM | No query-level performance data in AI Compass |
| **LLM Bandit** | Yang Li. *LLM Bandit: Cost-Efficient LLM Generation via Preference-Conditioned Dynamic Routing.* **arXiv preprint** 2502.02743 (Feb 2025); single author; the arXiv page lists no peer-reviewed venue. https://arxiv.org/abs/2502.02743 | Per the abstract: LLM selection formulated as a multi-armed bandit, user sets a performance-cost preference at inference time, policy meant to generalize to unseen LLMs. Arms, rewards, context and update rule are **not stated on the page I read** | Details beyond the abstract unverified here | Shares "user preference steers selection"; V2 does not learn |
| **CP-Router** | J. Su, F. Lin, Z. Feng, H. Zheng, T. Wang, Z. Xiao, X. Zhao, Z. Liu, L. Cheng, H. Wang. arXiv:2505.19970 (May 2025). The arXiv page names no venue; a publisher record found in the previous review gave AAAI 2026 (vol. 40), doi:10.1609/aaai.v40i39.40589 | Training-free routing between an LLM and a large reasoning model for multiple-choice questions: nonconformity score 1 − softmax probability, threshold from a calibration set at error rate α, prediction-set size decides the route (small set → LLM); α chosen by an entropy criterion (FBE) | Needs model probabilities over answer options, a calibration set, and multiple-choice format | Its uncertainty is about *answer correctness* with a coverage guarantee under exchangeability. V2's intervals are policy bands with no statistical guarantee. The language must not be borrowed |
| **GraphRouter** | T. Feng, Y. Shen, J. You. ICLR 2025; arXiv:2410.03834 | Heterogeneous graph of task, query and LLM nodes; edge prediction of quality and cost; inductive for new LLMs | Learned from interaction data | Learned prediction vs scoring declared metadata |
| **PersonalizedRouter** | Z. Dai, T. Feng, J. You. TMLR (Nov 2025); arXiv:2511.16883 | Graph model of individual user profiles from interaction data to personalize LLM choice | Needs per-user interaction history | V2 takes preference only as stated weights and constraints |
| **LENS** (identification unconfirmed) | J. Liu, L. Yu, K. Yue, Z. Tang. *LENS: Latent Precision Inference in Multi-LLM Routing.* UAI 2026, PMLR 337:3933-3956 | Routing as posterior utility maximization under imprecise supervision; marginalizes a latent precision | Probabilistic and learned | Closest in motivation (acting under imprecise evidence); V2 uses interval sets and tiers, not a posterior |
| **FLARE** (identification unconfirmed) | Y. Fu, H. Zhong, D. Huang, Y. Lu. *FLARE: Fine-Grained Length-Aware Routing for Resource-Efficient Heterogeneous LLM Serving.* ACL 2026, 2026.acl-long.1018 | Length-based predictors of per-query latency and cost; routing as a discrete multi-objective optimization; serving-side | Needs trained length predictors and serving measurements | The one entry that addresses the token-estimation problem of section 4; AI Compass has no predictor |

### 5.3 Representation technique, benchmarks and evaluation frameworks

| Work | Reference | Role | Relevance |
|---|---|---|---|
| **EmbedLLM** | R. Zhuang, T. Wu, Z. Wen, A. Li, J. Jiao, K. Ramchandran. ICLR 2025; arXiv:2410.02223 | **Representation learning** of LLMs from model outputs, usable for routing and performance forecasting. Not a router by itself | No outcome corpus in AI Compass |
| **RouterBench** | Q. J. Hu, J. Bieker, X. Li, N. Jiang, B. Keigwin, G. Ranganath, K. Keutzer, S. K. Upadhyay. *RouterBench: A Benchmark for Multi-LLM Routing System.* **arXiv preprint** 2403.12031 (Mar 2024, v2 28 Mar 2024). The arXiv listing marks it "Preprint"; I found no archival venue. https://arxiv.org/abs/2403.12031 | **Benchmark and evaluation framework**: a dataset of over 405,000 inference outcomes and a theoretical framework for comparing routers; not a routing algorithm | The repository's `PHASE2B_RESEARCH_REPORT.md` says "ICLR 2025"; not supported by anything found. Needs correcting there (not edited here) |
| **LLMRouterBench** | arXiv:2601.07206 (authors not captured) | Benchmark reporting that several routers, including a commercial one, do not beat a best-single-model baseline | Caution that sophisticated routers can fail simple baselines; V2 must include strongest, cheapest and static baselines |
| **HELM** | P. Liang et al. TMLR 2023, arXiv:2211.09110 | Evaluation framework with standardized scenarios | Comparability rule (section 3) |

### 5.4 Explanation methods

None of the eleven works is an explanation method. The explanation techniques that matter for this project's "why this recommendation" feature are separate:

| Work | Reference | Note |
|---|---|---|
| **LIME** | M. T. Ribeiro, S. Singh, C. Guestrin. *"Why Should I Trust You?": Explaining the Predictions of Any Classifier.* KDD 2016, pp. 1135-1144, doi:10.1145/2939672.2939778; arXiv:1602.04938 | Local surrogate-model explanation of a classifier's prediction |
| **SHAP** | S. M. Lundberg, S.-I. Lee. *A Unified Approach to Interpreting Model Predictions.* NIPS (NeurIPS) 2017; arXiv:1705.07874 | Shapley-value feature attribution |

AI Compass's decision trace is a deterministic report of its own additive score; it is **not** LIME or SHAP, and a score that is additive in known weights is its own exact explanation. Using either method here would add nothing to that and should not be claimed.

### 5.5 Robust and multi-criteria decision references

Greco, Mousseau, Słowiński, EJOR 191(2), 2008 (necessary/possible preference); Salo and Hämäläinen, IEEE Trans. SMC-A 31(6), 2001 (PRIME); Lahdelma, Hokkanen, Salminen, EJOR 106(1), 1998, doi:10.1016/S0377-2217(97)00163-X (SMAA); Ehrgott, Ide, Schöbel, EJOR 239(1), 2014 and Ide and Schöbel, OR Spectrum 38(1), 2016, doi:10.1007/s00291-015-0418-7 (minmax robustness for multi-objective problems); Mohajerin Esfahani and Kuhn, arXiv:1505.05116 (Wasserstein distributionally robust optimization, needs a sample distribution); Hurwicz (1951), Cowles Commission Statistics No. 356 (optimism-pessimism index; original note not retrieved, cited through secondary sources); Brown, Cai, DasGupta, Statistical Science 16(2), 2001, doi:10.1214/ss/1009213286 (binomial intervals).

### 5.6 What is published, what is ours, what is the contribution

| Category | Items |
|---|---|
| Published routing algorithms | FrugalGPT, RouteLLM, RouterDC, LLM Bandit (preprint), CP-Router, GraphRouter, PersonalizedRouter, LENS (identification unconfirmed), FLARE (identification unconfirmed) |
| Published representation technique | EmbedLLM |
| Published benchmarks / evaluation frameworks | RouterBench (preprint), LLMRouterBench, HELM |
| Published explanation methods | LIME, SHAP (neither used) |
| Published decision-theory components used by the proposal | additive utility; interval values; necessary dominance (ROR/PRIME vocabulary); maximin and Hurwicz criteria; weight-space analysis (SMAA); Wilson interval (removed from the core) |
| **Our simplified experimental adaptations** | E2 to E7 in `BASELINE_DEFINITIONS.md`. They keep one structural idea of each paper and discard the learning. None reproduces the paper |
| **The actual proposed contribution (what can be defended)** | A deterministic, documented-metadata **recommender for an AI-product catalogue** that (i) separates hard constraints from preferences, (ii) records evidence provenance and tier per metric, (iii) ranks by a per-model score with stated attitude to missing data, and (iv) reports exact weight-space and evidence diagnostics. This is an engineering application of existing MCDM and robust-decision techniques to a setting the surveyed routers do not address (no executions, no training data). **No algorithmic novelty and no research gap is claimed**: the abstracts reviewed are not a systematic search, and every ingredient exists above |

---

## 6. Decision table: alternative designs

"Defensible" means: provable properties, no unsupported claim, runs on the data that exists. It does **not** mean "recommends better products", which is not established for any option.

| # | Design | Per-model score (IIA) | Missing data | Needs data not in registry | Properties proved | Weaknesses | Decision |
|---|---|---|---|---|---|---|---|
| D0 | V1 as in repository | Partly (A6, A8 fail) | worst case | no | few | A1 to A12 | **Baseline E1**, not recommended |
| D1 | Draft EIPMU (frontier-first + maximin + ε-tie + ε*) | **No** | worst case | observed T3 | dominance, argmax L | B1 to B9 | **Remove** |
| D2 | Per-model maximin L, dominance annotated, weight-space margin | Yes | worst case, disclosure rewarded | no | IIA, insertion/removal, determinism | conservatism is a policy; ratings still decisive | **Candidate** |
| D3 | Per-model midpoint U, intervals as diagnostics | Yes | neutral, disclosure penalized | no | IIA | hides missing data; clipping bias (fix by ranking on point estimates) | **Candidate** |
| D4 | Per-model Hurwicz S_α with α reported | Yes | tunable | no | IIA; spans D2 and D3 | α must be chosen | **Recommended form**, α open |
| D5 | Minimax regret | **No** | worst vs best rival | no | none for IIA | removal/insertion failures (66, 436, 232 of 4,000) | **Reject as primary**; σ stays as a diagnostic |
| D6 | Weight-robust maximin on point values (E9) | Yes | not addressed | no | IIA | ignores data uncertainty | **Baseline E9** |
| D7 | Pareto-only (E8) | n/a (set) | incomparable | no | frontier | does not choose; weights ignored | **Baseline E8** |
| D8 | SMAA acceptability indices | n/a | needs distributions | weight and value distributions | none needed | assumes a prior over weights | **Defer** (weight-space diagnostic later) |
| D9 | Distributionally robust (Wasserstein) | depends | needs samples | empirical distribution | published guarantees need the sample | no samples | **Defer** |
| D10 | Learned routers (E2 to E7 families) | n/a | n/a | execution outcomes or preference data | none here | contradict recommendation-only | **Out of scope**; used only as labelled simplified baselines |

**Most defensible approach: D4**, with these parts:

1. Eligibility by hard constraints with the status vocabulary of section 4; unknown never silently passes a verified requirement.
2. Fixed reference ranges (policy, swept) and a per-metric evidence record with mechanical tiers; unanchored values are treated as unknown.
3. One per-model score S_α with α **reported and user-visible**; both L and H shown.
4. Diagnostics, not ranking components: undominated flag, σ against the best rival, exact weight-space margin δ*, evidence coverage C.
5. Exact lexicographic tie-break ending in `model_id`; no ε window in the order.
6. Robustness grade with thresholds taken from experiment distributions, never called confidence until calibrated.

D4 is "most defensible" only in that it is the design whose stated properties have proofs and whose weaknesses are explicit. Whether it beats D0 on real recommendation quality is **[OPEN]** and needs the expert-labelled experiment (EXP-6 in the design).

---

## 7. Product-boundary check

Recommendation only. No provider inference, no answer generation, no answer-quality evaluation, no automatic escalation, no fabricated provider measurements, no API-key-dependent ranking, no database or Neon change. The learning baseline (E7) uses recommendation-acceptance feedback only, and is evaluated offline on synthetic users; it is not a proposal to add provider calls. Observed T3 evidence is removed from the core for the reason in C6.

---

## 8. Remaining decisions, risks and verdict

### 8.1 Blocking items before implementation

| # | Item | Type |
|---|---|---|
| K1 | Replace the draft's ranking key by the per-model score and re-state the properties | mathematical revision (specified here) |
| K2 | Choose α (or ship maximin and midpoint side by side) | decision, informed by EXP-1, EXP-2, ADV-9 |
| K3 | Decide the status of the 37 editorial ratings (labelled T1u as an explicit ranking input, gated, or replaced by rubric-based independent ratings) | decision |
| K4 | Evidence record and tier rules; product-version binding | data-model design (schema change needs separate approval) |
| K5 | Budget and privacy status vocabulary; remove "guarantee" | specification edit |
| K6 | Grade thresholds | derived from EXP-3 |
| K7 | Expert-labelled query set (≥ the size in EXP-6) | data collection |
| K8 | Survey and synopsis, and confirmation of the FLARE and LENS identifications | input from you |

### 8.2 Residual risks

Ratings may stay decisive whatever the algorithm (A10); real-pool results rest on 12 to 27 self-authored queries and cannot generalize; ranges and widths remain policy; the literature check is abstract-level.

### 8.3 Verdict

**REQUIRES MATHEMATICAL REVISION.** The revision is concrete and small (K1, K5, and the diagnostics in section 6 point 4), and I could write it as a revised specification on request. The design is **not** ready for implementation, and it is also not ready to be called validated: K2, K3, K6 and K7 are open and no experiment on recommendation quality has been run.

### 8.4 Assumptions and limitations

- "ER-PCR" is read as the V2 proposal (section 0).
- Literature statements are abstract-level; FLARE and LENS identifications and LLM Bandit's details are unconfirmed; CP-Router's venue comes from a publisher record found earlier and the arXiv page does not state it.
- Random tests are evidence only; proofs are given where stated.
- Numbers from the 12-query pool illustrate behaviour of the editorial ratings, not recommendation quality.
- Nothing in the application, schema, database, credentials, deployment or GitHub was changed. The working tree's earlier uncommitted changes were left as they were.
