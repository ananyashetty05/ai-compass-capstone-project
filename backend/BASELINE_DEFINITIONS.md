# AI Compass: Baseline Definitions (E1 to E10)

Date: 2026-11-20. Status: **specification only. No baseline has been implemented or run.**
Companions: `ALGORITHM_ROBUSTNESS_REVIEW.md`, `EXPERIMENTAL_DESIGN_V2.md`.

## 0. The honesty rule

Published routers (FrugalGPT, RouteLLM, RouterDC, LLM Bandit, CP-Router, FLARE) learn from **outcome data** (answers, correctness, human preferences, serving measurements) or require **executing** models. AI Compass is recommendation-only and has **metadata only**: editorial ratings, documented features, pricing class or price, privacy status. So E2 to E7 below are **metadata-only adaptations that keep one structural idea of each paper and discard its learning**. They are named "X-inspired". **None reproduces the published method, none may be described as a reproduction, and no result from them says anything about the published method's performance.** Each entry states what is kept, what is dropped, and what the baseline can and cannot fairly show.

Two further rules:

1. **Same eligible set.** Every baseline receives exactly the candidates that pass the hard-constraint filter (so differences are differences in ranking, not in filtering). Constraint compliance is tested separately with the filter off (EXP-5 in the design).
2. **No tuning on test data.** Hyperparameters are fixed on a development split before the test split is touched (design 5.2). Defaults below are declared starting values, not tuned values.

## 1. Common formal setting

- Candidate set M, |M| = n ≤ 50, after eligibility.
- Objectives d ∈ D = {fit, quality, speed, reliability, risk, cost}. Value of m on d: point estimate v_{m,d} ∈ [0,1] or *unknown*; for V2 variants also an interval [ℓ,h] and a tier.
- User weights w (simplex). Query profile q: category, requested features, estimated input tokens, constraints.
- A **ranker** maps (M, w, q) to a total order on M; its top element is the *recommendation*. A **set selector** (E8) returns a subset.
- Tie-break for every baseline: score rounded to 12 decimals, then the approved-list order, then `model_id`. Deterministic, and it is **not** part of any published method.
- Seeds: stochastic baselines (E7) use a fixed seed list recorded in the experiment manifest.

### 1.1 Capability matrix

| Baseline | Needs training data | Needs executing models | Runs on approved pool (37, editorial) | Runs on live registry (prices) | Runnable today |
|---|---|---|---|---|---|
| R0 to R3 reference | no | no | yes | yes | yes |
| E1 V1 | no | no | yes | yes | yes |
| E2 | no (adaptation) | no | partly: pricing is an access class, not a price, so ties are heavy | yes | yes, with caveat |
| E3 | no (adaptation) | no | yes | yes | yes |
| E4 | no (adaptation) | no | yes | partly: depends on descriptive text | yes |
| E5 | no (adaptation) | no | no: no per-token prices for products | yes | live registry only |
| E6 | **yes** (labelled queries for calibration) | no | n/a | n/a | **no, until labelled queries exist** |
| E7 | simulated feedback only | no | yes (synthetic users) | yes | yes, synthetic only |
| E8 | no | no | yes | yes | yes |
| E9 | no | no | yes | yes | yes |
| E10a draft | no | no | yes | yes | yes |
| E10b corrected | no | no | yes | yes | yes |

### 1.2 Reference baselines (not in the ten, required for context)

The repository's offline evaluation already defines `strongest`, `cheapest` and `static` (`offline_evaluation.py`). Add a seeded random choice. The LLMRouterBench result that sophisticated routers can fail to beat a best-single-model baseline is the reason these must always be reported.

| ID | Rule |
|---|---|
| R0 | Uniform random among eligible (seeded; report the mean over 1,000 draws, not one draw) |
| R1 | Strongest: highest `quality` value; unknown last |
| R2 | Cheapest: lowest price (or access-class rank); unknown last |
| R3 | Static: first eligible in the approved-list order |

---

## 2. E1: Existing AI Compass scoring baseline

**Source:** this repository (not a published method).

**Procedure (approved-ecosystem path).** Exactly `routing_engine/scoring.py::score_ecosystem` then `select`, with the working-tree constants:

```
align = Σ_k part_k · fit_k            (feature 0.5, intent 0.3, category 0.2; intent only for intent categories)
obj   = {quality, latency, reliability, risk} ∪ {cost if a cost preference was stated}
w     = {alignment: 0.55} ∪ {d: 0.45 · normalized user weight}
U     = Σ w_d · u_d  (unknown → 0)
R     = Σ w_d · max(0, u_d − (1 − conf_d) · 0.25)        conf = 0.5 editorial, 0.85/0.6 alignment
order = by (−R, tie key); candidates within 0.005 of the top re-ordered by the tie key
```

Live-registry path: `score_candidates` (log min-max across the candidate set, observed statistics, Wilson reliability when ≥ 5 samples). Run both and report them separately.

**Inputs:** the same metadata as the current product. **Objective:** maximize R. **Assumptions:** editorial values are comparable; the 0.55 fit share is right; ρ and ε are as set.

**Freezing.** The working tree contains uncommitted changes. Before any run, record the SHA-256 of every file under `backend/app/services/routing_engine/`, `backend/app/data/approved_ecosystem.py` and the constants above in the experiment manifest, so E1 means one specific code state. No git tag or push is needed.

**Simplified:** nothing; it is the system. **Can show:** how often the new algorithms change the current system's output and why; the cost of the audit defects A1 to A12. **Cannot show:** that V1 is right or wrong about which product is better.

---

## 3. E2: FrugalGPT-inspired cost-quality selection

**Published method.** FrugalGPT (Chen, Zaharia, Zou; TMLR 2024): an LLM *cascade*. Models are ordered (learned, roughly cheap to expensive); the query goes to the first; a learned *judger* scores the answer; if the score is above a threshold the answer is returned, otherwise the next model is called. The ordering and thresholds are learned from labelled data per task. Cost saving comes from stopping early.

**Kept:** a cost-ordered scan with a quality threshold as the stopping rule. **Dropped:** execution, the judger, learning, per-query adaptation, the cascade itself (no second call exists in a recommendation).

**Procedure (E2a, threshold-first-adequate).**
```
sort eligible by price ascending (unknown price last)
τ ← quality threshold (default: 0.70 of the [0,1] editorial scale)
return the first m with quality(m) ≥ τ and quality known
if none: return argmax quality
```
**E2b (budget form).** Maximize quality subject to estimated request cost ≤ B, B the user's stated budget; if none is stated, B = median eligible cost.

**Inputs:** price (per-token or access class), quality estimate, optional budget. **Objective:** E2a minimize cost s.t. quality ≥ τ; E2b maximize quality s.t. cost ≤ B. **Assumptions:** the quality metadata is an adequate proxy for the judger's score; cost order is meaningful.

**Data caveat.** The approved pool has no prices, only an access class (free / free tier / pay-as-you-go / paid), so E2a produces large ties there and its output is mostly set by the tie-break. Report E2 on the approved pool as "access-class cost-quality" and on the live registry as price-based.

**Can show:** whether a one-sided threshold rule picks different products than a weighted score, and how sensitive that is to τ (sweep τ ∈ {0.5, 0.6, 0.7, 0.8, 0.9}). **Cannot show:** any FrugalGPT cost-reduction figure, whether a cascade would help, or anything about the learned judger.

---

## 4. E3: RouteLLM-inspired preference routing

**Published method.** RouteLLM (Ong et al., ICLR 2025): for a pair (strong model, weak model), learn P(strong is preferred | query) from human preference data (Chatbot Arena) with data augmentation. Four router families: similarity-weighted ranking (a Bradley-Terry style weighted Elo using query-embedding similarity), matrix factorization, a BERT classifier, and a causal-LLM classifier. A threshold on the predicted probability sets what share of calls go to the strong model; the threshold is calibrated on data.

**Kept:** a strong/weak binary decision controlled by a threshold. **Dropped:** every learned component, the preference data, the pair of fixed models.

**Procedure (difficulty-threshold two-tier router).**
```
strong ← eligible models in the top tercile of quality (known only)
weak   ← eligible models in the cheapest tercile (price or access class)
difficulty(q) ← rule-based score in [0,1] from the query profile: reasoning/code/multi-step features, estimated length, number of requested features
if difficulty(q) ≥ θ (default 0.5): pick argmax weighted score within strong
else: pick argmax weighted score within weak
if a tier is empty: fall back to all eligible
```
The difficulty rule is **ours**, not RouteLLM's, and is the weakest part of this baseline. Fix it before looking at any outcome, and sweep θ ∈ {0.3, 0.5, 0.7}.

**Inputs:** quality, price/access class, query profile, weights. **Objective:** implicit; strong tier favours quality, weak tier favours cost. **Assumptions:** the rule-based difficulty correlates with the need for a stronger product; terciles of editorial quality are meaningful.

**Can show:** whether a coarse two-tier policy loses relative to multi-objective scoring on the metadata. **Cannot show:** anything about learned routers, preference data, or RouteLLM's reported cost savings.

---

## 5. E4: RouterDC-inspired query-model matching

**Published method.** RouterDC (Chen et al., NeurIPS 2024): a query encoder and one learnable embedding per LLM, trained with two contrastive losses: a sample-LLM loss (pull the query toward the embeddings of LLMs that did well on it, push away from the others) and a sample-sample loss (pull together queries with similar LLM outcomes). Routing = the LLM whose embedding is most similar to the query embedding.

**Kept:** route by similarity between a query representation and a model representation. **Dropped:** the encoder training, the learnable model embeddings, all contrastive losses, all outcome data.

**Procedure (description-retrieval).**
```
doc(m) ← concatenation of the product's documented strengths, features and category text
build TF-IDF (unigram+bigram, fit on the eligible docs only) ; vector x(q) for the query text, x(m) for each doc
score(m) = cosine(x(q), x(m))
return argmax score ; ties by the common tie-break
```
A sentence-embedding variant needs a downloadable encoder; the workspace network is restricted, so TF-IDF is the default and an embedding variant is optional if an encoder is supplied.

**Inputs:** query text, product description text. **Objective:** maximize cosine similarity. **Assumptions:** the documented text describes what the product is good at; lexical overlap reflects task fit.

**Overlap warning.** V1's `feature_fit` already matches requested features against documented features, so E4 is correlated with the alignment term of E1 by design. Report E4's agreement with E1's alignment term alone before interpreting differences.

**Can show:** how far pure description matching goes without any quality, cost or risk metadata. **Cannot show:** anything about RouterDC's trained embeddings or contrastive objectives.

---

## 6. E5: FLARE-inspired length/resource-aware routing

**Identification caveat.** The survey is unavailable and the FLARE entry is a best match: *FLARE: Fine-Grained Length-Aware Routing for Resource-Efficient Heterogeneous LLM Serving* (Fu, Zhong, Huang, Lu; ACL 2026, 2026.acl-long.1018). **Do not run E5 under this name until you confirm that is the intended paper.**

**Published method (as verified from the abstract level).** Length-based models estimate per-query latency and cost; routing is posed as a discrete multi-objective optimization over heterogeneous LLM deployments, with reported latency and cost reductions in a serving setting.

**Kept:** estimating a per-request resource figure from length and choosing under a resource objective. **Dropped:** trained length and latency predictors, serving-side measurements, the deployment setting.

**Procedure (length-aware cost routing).**
```
n_in  ← profile.estimated_tokens (tokenizer-agnostic estimator, documented error)
n_out ← rule: category-based multiple of n_in, with a stated lower and upper multiple (default 0.5×, 1×, 2× as three scenarios)
cost(m) = price_in(m)·n_in + price_out(m)·n_out        # only where both prices are documented
filter: n_in ≤ context(m)
return argmin cost over eligible (E5a) ; or argmax weighted score with cost term from cost(m) (E5b)
report the winner under each n_out scenario
```
**Inputs:** documented input and output prices per model, context window, estimated tokens. **Objective:** E5a minimize estimated request cost; E5b the weighted score with request cost as the cost objective. **Assumptions:** the output-length rule is representative.

**Data caveat.** The approved pool has **no per-token prices** for products, so E5 cannot run there; it runs on the live registry only.

**Can show:** how sensitive the winner is to output-length assumptions, and how often a budget status flips with the assumption (links to the "no guarantee on estimated cost" finding). **Cannot show:** that FLARE's predictors work, any latency result (no throughput data exist in the registry), or anything about serving.

---

## 7. E6: CP-Router-inspired uncertainty handling

**Published method.** CP-Router (Su et al., arXiv 2505.19970): training-free routing between an LLM and a large reasoning model for multiple-choice questions. From the LLM's softmax probabilities over the options, nonconformity = 1 − probability; a threshold set from a calibration set at error rate α gives a *prediction set*; a small set (size 1 in the text; threshold τ in the pseudocode) means low uncertainty → answer with the LLM, a large set → send to the reasoning model. α is chosen by an entropy criterion (FBE).

**Kept:** the split-conformal prediction-set construction and using the set's size as the uncertainty signal. **Dropped:** LLM probabilities, multiple-choice questions, the model pair, FBE.

**Procedure (conformal recommendation set).** Requires a **calibration set of labelled queries**: for query i an expert marks the set A_i of acceptable products.
```
s(q,m) = normalized score of m under the ranker being wrapped, in [0,1]
calibration:  e_i = 1 − max_{m ∈ A_i} s(q_i,m)               (nonconformity of the best acceptable product)
q̂ = the ⌈(n_cal+1)(1−α)⌉ / n_cal empirical quantile of {e_i}
for a new query: C(q) = { m : 1 − s(q,m) ≤ q̂ }
if |C(q)| ≤ τ: recommend argmax s ; else: "ambiguous, show C(q)"
```
**Guarantee, stated precisely.** If calibration and test queries are exchangeable, P(C(q) contains at least one acceptable product) ≥ 1 − α. It says nothing about which product is best. It does **not** transfer to queries drawn from a different distribution than the labelled set.

**Status: specified, not runnable.** There is no labelled calibration set. With the 12 to 27 self-authored queries, n_cal is too small and the queries are not independent of the rules, so exchangeability fails. Minimum calibration size: for α = 0.1 at least ⌈1/α⌉ − 1 = 9 labels gives a non-trivial quantile, and a stable empirical coverage estimate needs on the order of hundreds (design 4, EXP-6).

**Can show:** whether a coverage-controlled set abstains sensibly, once labels exist. **Cannot show:** anything about CP-Router's LLM-versus-reasoning-model routing.

---

## 8. E7: LLM Bandit-inspired feedback adaptation

**Published method (limited).** LLM Bandit (Yang Li, arXiv 2502.02743, preprint): per the abstract, LLM selection is formulated as a multi-armed bandit, users set performance-cost preferences at inference time, and the policy is meant to generalize to unseen LLMs. **The arms, rewards, context and update rule are not given on the page I read**, so this baseline cannot claim to follow them. It is a generic bandit adaptation inspired by the abstract only.

**Kept:** treating selection as sequential choice with feedback. **Dropped:** everything not in the abstract.

**Procedure (Beta-Bernoulli Thompson sampling over products, per category).**
```
state: (a_m, b_m) per (category, product), prior from the metadata score: a_m = 1 + κ·s_m, b_m = 1 + κ·(1 − s_m), κ = 4
each round: eligible set M_t ; sample θ_m ~ Beta(a_m, b_m) ; recommend argmax θ_m
feedback r ∈ {0,1}: the simulated user accepts the recommendation
update: a ← a + r, b ← b + (1 − r)
evaluation policy for the product (deterministic): recommend argmax posterior mean a/(a+b)
```
Feedback means **acceptance of the recommendation** (a click or a thumbs-up), not answer quality: the product never sees answers. It is also kept out of the *quality* metric, as the audit requires, and enters only as a personalization term.

**Inputs:** a metadata score as prior, simulated users. **Objective:** minimize cumulative regret against the simulated users' true preferences. **Assumptions:** acceptance probability is a function of a latent user utility; feedback is independent across rounds.

**Can show (synthetic only):** how fast a feedback-adapted ranking converges, how much a wrong prior costs, and whether adaptation can break the deterministic-recommendation requirement. **Cannot show:** that real users give consistent feedback, any real-world gain, or anything about LLM Bandit's method.

---

## 9. E8: Pareto-only selection

**Source:** classical multi-objective optimization; not a router.

**Procedure.**
```
E8a (point): frontier F = {m : no m' with v_{m',d} ≥ v_{m,d} ∀d and > for some d}, over objectives with known values for both; weights ignored
E8b (interval): F = {m : no m' certainly dominates m (ℓ_{m'} ≥ h_m on every weighted objective, strict on one)}
output: the set F (set selector).  Single recommendation for winner-level metrics: the first element of F under the common tie-break
```
Unknown handling for E8a: a pair with different known-objective sets is **incomparable** (this reproduces V1's `_mark_pareto`, including its defect A5); an E8a′ variant treats unknown as 0.

**Inputs:** objective values. **Objective:** efficiency without weights. **Assumptions:** all objectives are comparable on [0,1].

**Can show:** frontier size, how often the oracle-best product is on the frontier, how fast the frontier grows with missing data (A5), and how much a weighted scalar adds. **Cannot show:** which frontier member to pick; a single-winner score for E8 depends only on the tie-break and must not be reported as E8's recommendation quality. Report set-level metrics.

---

## 10. E9: Robust selection without uncertainty intervals

**Source:** decision theory (minimax over a weight uncertainty set); no single paper.

**Definition (our choice, because "without intervals" is not unique).** Point utilities, no tiers, no intervals; robustness only to the user's *weights*.

```
W_δ = { w' in the simplex : TV(w', w) ≤ δ }          TV = ½‖w' − w‖₁
score(m) = min_{w' ∈ W_δ} Σ_d w'_d · v_{m,d}          (unknown → 0)
return argmax score
```
The inner minimum has a closed form: move up to δ of weight mass from the objectives where v is largest to the one where v is smallest (fractional knapsack). δ default 0.10, sweep {0.05, 0.10, 0.20}. δ = 0 reduces to the plain weighted sum.

**Assumptions:** the user's weights are the main uncertainty; values are exact. **Per-model score:** yes, so it keeps the insertion and removal properties.

**Can show:** whether tiered intervals add anything beyond weight robustness; the effect of ignoring data uncertainty. **Cannot show:** robustness to missing or noisy values, by construction.

---

## 11. E10: Full proposed algorithm

Two registered variants, because the draft and the corrected form behave differently and the difference is itself a result.

**E10a: draft EIPMU** exactly as `ALGORITHM_V2_SPEC.md` (frontier-first key, exact lexicographic order, ε-tie in 2.7, relative-scaling ε*, σ with the runner-up, P with δ_T1 = 0.15, δ_T2 = 0.05, δ_T3 = 0.03). Run it **as written**, to quantify the defects in `ALGORITHM_ROBUSTNESS_REVIEW.md` (insertion, removal, ε-tie, σ).

**E10b: corrected form (recommended design D4).**
```
eligibility(m, constraints, evidence)                       # section 4 status vocabulary; hard only if explicit
cell interval from tier: T0 [0,1]; T1u treated as T0; T1 v ± δ1; T2 v ± δ2; T3 documented interval
S_α(m) = Σ_d w_d · (α ℓ_d + (1−α) h_d)                     # α reported; run α = 1 and α = 0.5
order = exact S_α rounded to 12 decimals, then fixed fields, then model_id
diagnostics: undominated flag, σ = L_top − max_{j≠top} H_j, weight-space margin δ* (total variation), evidence coverage C
```
All parameters (α, δ_T1, δ_T2, δ_T3, ranges) are **pre-registered before the test split is run**. Intervals are clipped for display only; ranking uses the unclipped point-and-width values so clipping cannot bias the order.

**Can show:** whether D4 satisfies the proven properties in practice, how its output differs from E1 and E8/E9 and by how much, how it degrades under the stress experiments. **Cannot show:** that its recommendations are better, until expert-labelled data exist. No outcome of E10 may be reported as "the algorithm is superior".

---

## 12. Reporting rules for all baselines

1. Name: "X-inspired (metadata-only adaptation)". Never "X reproduction".
2. For every table row: the baseline's parameters, seeds, the code-state hashes, the data snapshot id.
3. Report effect sizes with 95% intervals and paired comparisons on identical instances (design 5).
4. Never report a baseline's result without R0 to R3 beside it.
5. Where a baseline is unrunnable (E5 without prices, E6 without labels), report "not run" with the reason, not a substituted number.
6. Disclose every place a baseline is stronger or weaker than the published method because of the adaptation (the "simplified" paragraphs above) in the same table as the result.
