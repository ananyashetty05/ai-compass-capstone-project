# AI Compass: Experimental Design V2

Date: 2026-11-20. Status: **design only. No experiment in this document has been run.** Numbers below are either sample-size arithmetic (reproducible with the stated formulas) or are labelled as results of earlier pilots.
Companions: `ALGORITHM_ROBUSTNESS_REVIEW.md` (audit, properties, verdict), `BASELINE_DEFINITIONS.md` (E1 to E10 and reference baselines R0 to R3).

## 1. Principles and scope

1. **Two questions, kept apart.**
   - *Algorithmic properties:* does the method do what its specification says (invariances, bounded error under stated degradation, determinism, constraint compliance given its inputs)? These can be tested on synthetic data with known truth.
   - *Recommendation quality:* is the recommended product the one a competent human would pick? This needs independent expert labels. **No synthetic experiment can answer it**, and none may be reported as if it did.
2. **No superiority claims before data.** Every hypothesis below is either a deterministic property (expected exact result) or a two-sided comparison. The design commits to reporting all baselines' results, including those where the proposed algorithm does worse.
3. **Pre-registration.** Before the test split is run: algorithms and parameters, metrics, hypotheses, sample sizes, exclusion rules and analysis code are written to the experiment manifest and hashed. Anything done after seeing test results is labelled exploratory.
4. **Boundaries.** Recommendation only. No provider call, no answer generation, no answer-quality evaluation, no API-key-dependent ranking, no database writes (the harness reads a file snapshot of the registry, never Neon), no change to application code.
5. **Honest naming.** Baselines E2 to E7 are metadata-only adaptations (`BASELINE_DEFINITIONS.md`). Their results are never reported as results of the published methods.

## 2. Data tiers and oracles

| Tier | Content | Truth available | Supports |
|---|---|---|---|
| **D1 synthetic universe** | Generated candidate pools with latent true values and generated observation processes | Yes, by construction | properties, degradation, noise, constraints, stress |
| **D2 real registry snapshot** | The 37 approved products with their editorial values, features, categories; later the live registry; plus the existing self-authored queries (12 labelled, 27 in the test suite) | No | behaviour on real metadata; margins; agreement between algorithms. **Not** correctness |
| **D3 expert-labelled queries** | Independent queries with expert judgements (EXP-6) | Expert judgement | recommendation quality, grade calibration |

### 2.1 D1 generator (specification)

```
pool:     n ∈ {10, 25, 50}; D = 6 objectives (fit, quality, speed, reliability, risk, cost)
truth:    u*_{m,d} ~ Beta(a,b); correlation structure ρ_obj ∈ {-0.5, 0, +0.5} between quality and cost utility; mean μ ∈ {0.3, 0.5, 0.7}
weights:  w ~ Dirichlet(1,…,1), plus structured cases (one-hot, two-hot, a zero weight on cost)
attributes: privacy ∈ {compliant, non-compliant}; capability flags; context window; price; independent of u*
observation process: tier_{m,d} ∈ {T0, T1, T2, T3} with probabilities p_T; observed v = clip(u* + ε_tier), ε ~ N(0, σ_tier²),
             σ_T1 = 0.10, σ_T2 = 0.04, σ_T3 = 0.02 (generator parameters, deliberately different from the algorithms' policy widths)
oracle O1: argmax over truth-eligible m of Σ_d w_d u*_{m,d}
```
Every generator parameter is an independent variable in at least one experiment (so conclusions are not specific to one setting), and all generator seeds are recorded. The generator's assumptions are the main threat to D1 conclusions (section 8).

### 2.2 Oracles

| Oracle | Definition | Used for |
|---|---|---|
| O1 (synthetic) | argmax of true weighted utility over truth-eligible candidates | regret, Pareto efficiency, winner-change against truth |
| O2 (constraint) | truth-eligibility of each candidate under the stated constraints | violation rate, false exclusion |
| O3 (expert) | acceptable set A_i and, where collected, graded or pairwise preferences from ≥ 3 independent experts | recommendation quality (EXP-6) |

## 3. Metrics

Instances i = 1..N. rec_i = the algorithm's recommendation (or none), R_i^ref and R_i^pert = reference and perturbed rankings, E*_i = truth-eligible set, u* = true utilities under the instance's weights.

| ID | Metric | Definition | Notes |
|---|---|---|---|
| M1 | **Recommendation coverage** | `#{i: rec_i exists} / #{i: E*_i ≠ ∅}` ; also `empty-correct` = share of instances with E*_i = ∅ where the algorithm returns none | an algorithm that always returns something has coverage 1 and fails `empty-correct` |
| M2 | **Hard-constraint violation rate** | `#{i: rec_i ∉ E*_i} / #{i: rec_i exists}`. Variant M2v: violation of a requirement the algorithm marked *verified*. False-exclusion rate `#{m ∈ E*_i excluded} / #{m ∈ E*_i}` | M2v must be 0 if the documentation is correct; non-zero only through documentation error (EXP-5) |
| M3 | **Preference alignment** | (a) Kendall τ_b between the algorithm's order and the order of true utility under w; (b) *responsiveness violation rate*: raise w_d by Δ (renormalize), count instances where the winner's value on d decreases | (b) is [PROVED] zero for any linear score; a non-zero count for any method signals non-linearity |
| M4 | **Ranking correlation** | Kendall τ_b between two rankings over the common candidates (reference vs perturbed; algorithm vs oracle) | |
| M5 | **Winner-change rate** | `#{i: top(R^pert_i) ≠ top(R^ref_i)} / N` | reference = same algorithm on full, unperturbed data; or O1 where stated |
| M6 | **Rank displacement** | `(1/n) Σ_m |rank_ref(m) − rank_pert(m)|` normalized by its maximum `n/2`; plus the displacement of the reference winner | |
| M7 | **Regret** | `r_i = (Σ w u*(O1 best) − Σ w u*(rec_i)) / (Σ w u*(O1 best) − Σ w u*(worst eligible))`, in [0,1]; 0–1 regret `1[rec_i ∉ A_i]` for expert labels | the oracle is always stated; with O3 only the 0–1 form is used unless graded labels exist |
| M8 | **Pareto efficiency** | share of recommendations not dominated under true values among truth-eligible; for set selectors: frontier precision and recall against the true frontier | |
| M9 | **Evidence coverage and precision** | coverage C = Σ_d w_d · 1[tier_d ≥ T2] of the recommended model; precision P = 1 − Σ w (h − ℓ) (policy-dependent, reported with its widths); *interval coverage* = share of true values inside the algorithm's intervals | interval coverage is meaningful only under the generator's noise model |
| M10 | **Robustness under missing/noisy metadata** | area under the degradation curve of (1 − M5) over p ∈ {0, .1, .2, .3, .5} (AUDC), and retention `metric(p)/metric(0)` | |
| M11 | **Selection stability** | share of K = 200 weights drawn uniformly from the total-variation ball of radius δ around w that keep the winner; and the exact margin δ* (smallest total-variation shift that changes the winner) | δ* from the greedy fractional-knapsack computation, checked against brute force |
| M12 | **Runtime and overhead** | wall-clock per decision (median, p95) over 30 warm repetitions after 3 discarded warm-ups, n = 50, D = 6, on a stated machine; algorithm-only and pipeline-inclusive; operation counts | no "fast" claim without a stated requirement |
| M13 | **Grade calibration** | for each robustness grade, the observed rate of agreement with O1 or O3; Brier score and expected calibration error over the grades | needs labels; grade is not called confidence until calibrated |

## 4. Experiments

Common to all (unless overridden): baselines R0 to R3, E1, E8, E9, E10a, E10b, plus E2, E3, E4 where their data exist (E5 live registry only, E6 only after labels exist, E7 in EXP-3 and EXP-6 only). Same eligible set for every algorithm unless the experiment tests eligibility. Paired comparison on identical instances. Seeds recorded.

### EXP-1 Metadata degradation (10%, 20%, 30%, 50%)

- **Research question.** How do winner stability, ranking agreement and regret degrade as registry cells go missing, and does the treatment of unknowns (worst case, neutral, tunable) change the curve?
- **Hypotheses.** H1.1 (check): agreement with the full-data result declines monotonically in p for every algorithm. H1.2 (two-sided): the algorithms differ in AUDC. H1.3: which unknown-treatment gives the lower regret depends on the truth distribution mean μ (the worst-case rule loses when true values are high, the neutral rule when they are low); the experiment measures how strongly. No direction is asserted for H1.2.
- **Independent variables.** Deletion level p ∈ {0, 10, 20, 30, 50}%; mechanism {MCAR; MAR by provider documentation habit; MNAR with low values deleted first; targeted deletion of the full-data winner's cells}; truth mean μ ∈ {0.3, 0.5, 0.7}; n ∈ {10, 25, 50}.
- **Controlled.** Weights, eligible set (eligibility cells are *not* deleted here; ADV-3 does that), tie-break, seeds across algorithms.
- **Data and sample.** D1: N = 10,000 instances per (p, mechanism, μ, n) cell (half-width ≤ 0.01 at proportion 0.5, section 5.1). D2: each of the 12 labelled queries × 1,000 deletion draws; the draws are not independent queries, so intervals describe deletion randomness only and the result does not generalize to queries.
- **Metrics.** M5, M6, M4, M7 (D1), M10, M1, M9.
- **Expected interpretation.** A curve per algorithm with intervals. A difference in AUDC supports "treats missing data differently", nothing more. Previous pilot (MCAR, real pool, 2,400 draws per level, **different code, not a result of this design**): winner unchanged in 68%, 35%, 26% (lower-bound) at p = 0.1, 0.3, 0.5.
- **Threats.** MCAR is unrealistic; real missingness is structural (providers do not publish risk). Generator realism. The real pool's small rating gaps make it fragile whatever the algorithm.

### EXP-2 Metadata noise and estimation error

- **Research question.** How do noise, bias and estimation errors in the values affect the recommendation, and are the algorithms' stated intervals consistent with the error they are meant to cover?
- **Hypotheses.** H2.1: regret increases with noise level for every algorithm. H2.2: interval coverage reaches the nominal level only when the algorithm's width policy is at least the generator's noise scale; below it, coverage falls (expected, quantifies policy mismatch). H2.3: a per-provider systematic bias (a lenient rater) produces larger winner changes than independent noise of the same variance.
- **Independent variables.** Noise type {additive Gaussian σ ∈ {0.05, 0.10, 0.15, 0.25}; rating quantization to steps 0.25; per-provider bias ±0.10 on a random 30% of providers; multiplicative log-normal error on prices σ ∈ {0.1, 0.3, 0.5}; tier mislabelling with probability {0.1, 0.3}}; width policy {matched, narrower ×0.5, wider ×2}.
- **Controlled.** True values, weights, eligible set, n.
- **Data and sample.** D1, N = 10,000 per cell; D2 for the quantization and bias cases only (they are applied to the real editorial values).
- **Metrics.** M7, M5, M4, M9 (interval coverage), M13 proxy (does a "high" grade imply fewer winner changes?).
- **Expected interpretation.** Interval coverage results hold only for the stated noise model; they say nothing about the real registry's error, which is unknown. Report matched and mismatched policies side by side.
- **Threats.** The noise model is chosen by us. Real errors are likely correlated with provider and category.

### EXP-3 User preference changes

- **Research question.** How sensitive is the recommendation to the user's weights, does the exact margin predict flips, and do the algorithms respond in the direction the user asks?
- **Hypotheses.** H3.1 (deterministic): for linear-score algorithms raising w_d never lowers the winner's value on d (expected 0 violations in N). H3.2 (deterministic): no flip for any weight within total-variation distance δ* of w, and a flip at δ* plus an arbitrarily small amount; expected 0 mismatches against brute-force search on D1. H3.3 (quantitative): the draft's relative-scaling ε* and the exact δ* disagree; the experiment reports the distribution of the disagreement. H3.4: V1's ±20% axis perturbation never reports a flip caused by switching on a zero weight.
- **Independent variables.** Perturbation type {TV-ball sampling δ ∈ {0.02, 0.05, 0.10, 0.20, 0.30}; axis scaling ±20%; pair moves; switching on a zero weight; one-hot extremes}; base weight family {Dirichlet, structured, saved profile}.
- **Controlled.** Candidate values and eligibility.
- **Data and sample.** D1 N = 10,000 per cell; D2: 12 queries × the weight families (a margin per query; descriptive only).
- **Metrics.** M11 (stability and δ*), M5, M6, M3 (responsiveness violation), M12 for the margin computation. E7 is included here with simulated users whose true weights differ from the stated ones (regret over rounds).
- **Expected interpretation.** The distribution of δ* over representative queries is the **only** legitimate basis for robustness-grade thresholds; thresholds are set by a pre-registered rule (for example the terciles of δ* on the development split) and then frozen. They remain policy, and are labelled so.
- **Threats.** The weight prior (Dirichlet) is not the real user distribution. Real saved weights may cluster. The metric (total variation) is a choice.

### EXP-4 Candidate insertion and removal

- **Research question.** Do the algorithms keep the winner and the order stable when candidates are added or removed, as their specifications claim?
- **Hypotheses.** H4.1 (deterministic, PROVED): per-model scalar scores (E9, E10b, E1 on the approved pool except for its ε-tie rule) show 0 violations of: Best Match invariance under non-winner removal, runner-up promotion under winner removal, pair-order preservation under insertion. H4.2 (counterexample-based expectation): frontier-first (E10a), minimax regret and V1's ε-tie window show violations. H4.3: V1's live path shows violations through set-dependent normalization. H4.4: inserting an exact clone with a larger `model_id` never changes the winner except to the clone itself, and only through the tie-break.
- **Independent variables.** Operation {insert random; insert dominating the winner; insert dominated; insert a clone; insert a near-clone (values ± 1e-6); remove a non-winner; remove the winner; leave-one-out over all candidates}; n.
- **Controlled.** Weights, all other candidates, tie-break.
- **Data and sample.** D1 N = 10,000 per (operation, algorithm). D2: complete leave-one-out and one-in over the 37 products × 12 queries (exhaustive, so no sampling error, but queries are not a sample of anything).
- **Metrics.** Violation counts per property with exact Clopper-Pearson upper bounds (zero violations in 10,000 trials gives an upper bound of about 0.0003, the rule of three); M5, M6.
- **Expected interpretation.** Zero violations for the proved properties confirms the implementation matches the proof; it does **not** extend the proof. Any violation of a proved property is an implementation defect, not a finding about the method.
- **Threats.** Random pools may not contain the adversarial configurations; the constructed counterexamples (review 2.6, 2.7) must be included as fixed regression cases.

### EXP-5 Mandatory privacy (and budget) constraint compliance

- **Research question.** Under explicit mandatory constraints, are hard requirements never violated *given the documentation*, and how large is the residual violation caused by documentation error and by estimated inputs?
- **Hypotheses.** H5.1 (deterministic): with eligibility first, M2v = 0 for every algorithm when the documentation is correct. H5.2: with the filter off, baselines that do not model constraints violate them at the rate predicted by the share of non-compliant candidates (quantifies why the filter exists). H5.3: with documentation error probability ρ_doc, the true-violation rate M2 is positive and increases with ρ_doc; the algorithm cannot remove it. H5.4: with estimated tokens, the request-cost budget is violated at a positive rate that grows with the token and output-length error, so "guaranteed" is not supportable.
- **Independent variables.** Documentation status {documented for scope; documented for another plan; undocumented; unknown; stale; contradictory}; ρ_doc ∈ {0, 0.02, 0.05, 0.10}; strictness {strict, preferred}; filter {on, off}; budget limit as quantile of candidate costs; token-estimate error σ_tok ∈ {0.1, 0.25, 0.5} (log-normal) and output-length scenario {0.5×, 1×, 2×}.
- **Controlled.** True attributes, weights, eligible-by-truth set.
- **Data and sample.** D1, N = 10,000 per cell. Real tokenizer error needs a text corpus and offline tokenizers; the workspace network is restricted, so this step needs a supplied corpus or tokenizers (**open**), otherwise σ_tok stays a swept parameter and no real error figure is claimed.
- **Metrics.** M1 (including `empty-correct`), M2, M2v, false-exclusion rate, M7.
- **Expected interpretation.** Report the status distribution (`verified`, `estimated`, `borderline`, `unverifiable`) next to violations. No claim about real provider documentation accuracy.
- **Threats.** ρ_doc is invented. Real documentation errors correlate with provider and age. Privacy has more dimensions than one flag.

### ADV-1 Overlapping utility intervals

- **RQ.** Does the algorithm report indistinguishability honestly when intervals overlap heavily?
- **Hypothesis.** When all candidates have equal midpoints and widths ≥ their gaps, σ < 0 for every instance and the robustness grade is never "high" (deterministic given the grade rule); the winner then follows the tie-break alone and the output says so.
- **Independent.** Overlap fraction ∈ {0, 25, 50, 75, 100%}; width policy; tier mix.
- **Controlled.** Midpoints, weights. **Data.** D1 N = 10,000 per overlap level; D2 pool replay (every query's σ). **Baselines.** E1 (its confidence value), E10a, E10b.
- **Metrics.** σ distribution, M11, M13 (grade vs winner change), M5 under a width-policy change.
- **Interpretation.** A pass is "indistinguishable cases are labelled as such", not "the winner is right".
- **Threats.** Equal midpoints are an extreme construction.

### ADV-2 Conflicting objectives

- **RQ.** What happens when every candidate is on the Pareto front (quality trades off against cost, speed against risk)?
- **Hypothesis.** The frontier equals the full set; the choice is determined by weights only; margins are small; a Pareto-only selector returns everything and so cannot recommend (E8 reports frontier size = n).
- **Independent.** Front curvature (concave, linear, convex), correlation ρ_obj ∈ {−0.9, −0.5}, n.
- **Data.** D1 N = 5,000 per setting. **Baselines.** E8, E9, E10b, E1, R1 to R3.
- **Metrics.** Frontier size, M11, M3, M7.
- **Interpretation.** Shows the value of weights over frontier membership; says nothing about which weights users hold.
- **Threats.** Synthetic fronts.

### ADV-3 Unknown mandatory metadata

- **RQ.** Is an unknown mandatory cell (privacy, price, capability, context) ever silently treated as passing?
- **Hypothesis (deterministic).** An unknown mandatory cell never satisfies a verified requirement; the model appears in an `unverifiable` list with a reason; coverage reflects this; no crash.
- **Independent.** Fraction of candidates with unknown mandatory cells {0, 25, 50, 100%}; which cell.
- **Data.** D1 N = 5,000 per cell; D2: the 37 products, all with unknown privacy (strict privacy must return none, with the reason).
- **Baselines.** All, filter on.
- **Metrics.** M1, M2v, a transparency check (every exclusion carries a reason code: share must be 100%).
- **Interpretation.** Pass/fail on invariants, not a performance measure.
- **Threats.** The real pool's privacy status being all-unknown makes strict privacy vacuous (finding C8).

### ADV-4 Extreme candidate values

- **RQ.** Do extreme or invalid values produce NaN, crashes, non-determinism or silently wrong utilities?
- **Hypothesis (deterministic).** Invalid cells (NaN, ±inf, negative price, quality outside [0,1], zero latency, duplicate ids) become unknown with a reason code and never reach the score; no NaN or inf in any output; two runs on identical input are byte-identical.
- **Independent.** Value classes {0, 1e-12, 1e6, −1, NaN, inf, 1+1e-9}; n ∈ {1, 2, 50}; weights {all zero, one-hot, NaN}.
- **Data.** Fixed adversarial fixtures plus fuzzing, N = 10,000 random invalid injections per algorithm.
- **Baselines.** E1 and E10b mainly; others as feasible.
- **Metrics.** crash rate, NaN/inf rate in outputs, determinism rate, M12 scaling, behaviour at the range clamp (utility saturation).
- **Interpretation.** Robustness of the implementation. The specification must first define each invalid class (it is silent today).
- **Threats.** Fuzzing coverage.

### ADV-5 All candidates ineligible

- **RQ.** When nothing passes the hard constraints, does the system say so, explain, and avoid silent relaxation?
- **Hypothesis (deterministic).** Output is `no_eligible_candidates`; no recommendation; the guidance names a constraint whose relaxation admits at least one candidate in 100% of cases where such a relaxation exists; no constraint is relaxed automatically.
- **Independent.** Which constraint(s) empty the set; number of binding constraints.
- **Data.** D1 N = 5,000 per setting; D2: strict privacy on the approved pool.
- **Baselines.** All with filter on.
- **Metrics.** M1 (`empty-correct`), false-recommendation rate (must be 0), relaxation-advice validity.
- **Interpretation.** Invariant check.
- **Threats.** Relaxation advice depends on the policy of what may be relaxed.

### ADV-6 Zero-weight objectives

- **RQ.** Do zero-weight objectives influence the result, and can sensitivity analysis see them?
- **Hypotheses.** H-6.1 (PROVED for linear scores): changing values on a zero-weight objective leaves the order unchanged (0 violations). H-6.2: the exact margin δ* is finite when a zero-weight objective differs across candidates (switching it on can change the winner); the relative-scaling ε* is infinite in the same instances. H-6.3: dominance annotation changes when a zero-weight objective is switched on (documented, not a defect).
- **Independent.** Number of zero weights (1 to 5); whether the zero-weight objective separates the top candidates.
- **Data.** D1 N = 10,000 per setting. **Baselines.** E1, E9, E10a, E10b.
- **Metrics.** invariance violations, δ* vs ε*, dominance flips.
- **Interpretation.** Confirms the move from relative scaling to the weight-space margin.
- **Threats.** none beyond the generator.

### ADV-7 Stale and contradictory evidence

- **RQ.** How much does the resolution policy for old or conflicting evidence change the recommendation?
- **Hypothesis.** No policy dominates; the experiment reports the spread. H-7.1: a flat calendar downgrade changes more winners than a version-bound rule when release cadence is fast.
- **Independent.** Staleness rule {none; 180, 365, 730 days; version-bound}; contradiction rule {newest; most authoritative tier; hull of intervals with tier downgrade; drop both}; fraction of cells with two sources {10, 30%}; release cadence {monthly, quarterly, yearly}.
- **Data.** D1 only. **Real dated records do not exist yet**; this experiment cannot use D2 until the evidence record (K4) stores dates and versions.
- **Baselines.** E10b under each rule; E1 for reference.
- **Metrics.** M5 between rule pairs, M7, M9.
- **Interpretation.** A sensitivity statement ("the winner changed in x% of instances depending on policy"), used to decide whether the policy needs a user-visible setting.
- **Threats.** Simulated cadence and conflict structure.

### ADV-8 Benchmark comparability

- **RQ.** What error do incomparable benchmark scores introduce, and does a within-comparison-group rule remove it?
- **Hypothesis.** When protocol offsets between groups are large compared with true gaps, raw cross-group comparison increases regret; a within-group-only rule reduces that error at a cost in coverage (cells outside the group become unknown). The break-even offset is reported, not assumed.
- **Independent.** Number of groups {2, 3, 5}; offset size b ∈ {0, 0.05, 0.10, 0.20}; share of models with scores in more than one group {0, 25, 50%}.
- **Data.** D1 N = 10,000 per cell. A real-data variant (public scores of the same models under different protocols) is optional and each source must be verified before use.
- **Baselines.** E1 (compares raw), E10b with and without the comparison-group rule, R1.
- **Metrics.** M7, M4, M1 (coverage lost), M9.
- **Interpretation.** Justifies or rejects the comparison-group requirement quantitatively.
- **Threats.** Offsets are additive in the generator; real protocol differences are not.

### ADV-9 Sensitivity to uncertainty-interval policies

- **RQ.** How much of the result is decided by policy parameters rather than data?
- **Hypotheses.** H-9.1: on pools where all rated cells share one tier, the winner is invariant to the tier width (mechanical: a common shift preserves order; **already observed** on the 12 real queries with a one-parameter sweep, not a result of this design). H-9.2: on mixed-tier pools the winner varies with width policy. H-9.3: lower-bound and midpoint winners differ in a non-trivial share of mixed-tier pools (earlier pilot: 5% to 13%).
- **Independent.** δ_T1 ∈ {0, 0.05, 0.10, 0.15, 0.25, 0.35}; δ_T2 ∈ {0, 0.02, 0.05, 0.10}; δ_T3 ∈ {0, 0.03, 0.06}; reference ranges (cost, latency) at three settings each; α ∈ {1, 0.75, 0.5}; ε-tie on/off; tier-assignment rule; coarse full-factorial grid plus one-at-a-time sweeps.
- **Data.** D1 N = 5,000 per tier-mix condition; D2 replay.
- **Baselines.** E10a, E10b, E9.
- **Metrics.** M5 relative to the pre-registered default, share of instances whose winner is invariant over the whole grid ("policy-robust"), first-order variance shares of regret per parameter.
- **Interpretation.** Identifies which parameters must be user-visible or empirically set, and which do not matter.
- **Threats.** The grid bounds define the answer; report the bounds.

### EXP-6 Expert-labelled recommendation quality (the only experiment that addresses real quality)

- **RQ.** Do experts accept the algorithm's recommendation, and is the robustness grade informative about agreement?
- **Hypotheses.** H6.1 (two-sided, paired): E10b and E1 differ in the share of top-1 recommendations that fall in the experts' acceptable set. H6.2: E1, E10b, R1 (strongest), R2 (cheapest) and R0 differ from one another; R0 sets the floor. H6.3: higher robustness grades are associated with higher agreement (monotone), tested with a trend test; if not monotone the grade is uninformative and must not be shown as a confidence. **No direction is claimed for H6.1.**
- **Design.** Queries from a source independent of the author and of the development set. Stratify by category. Each query is judged blind (algorithm names and rankings hidden, product order randomized) by ≥ 3 independent experts who mark the acceptable set and, for a subsample, rank the top 3. Pre-registered rubric. Annotators must not see the editorial ratings. Inter-annotator agreement is reported (Krippendorff's α, with the conventional 0.667 and 0.8 reference points treated as conventions, not guarantees); if agreement is low the labels are reported as unreliable and no algorithm comparison is made.
- **Sample size.** Normal-approximation formulas (section 5.1): about **323** queries to estimate an acceptable-rate near 0.7 to ±0.05; about **234** queries to detect a 10-point difference between two algorithms at 5% significance and 80% power if 30% of queries are discordant (more if fewer are discordant; 940 for a 5-point difference). Treat these as planning figures; recompute with the observed discordance from a pilot of ~50 queries.
- **Baselines.** R0 to R3, E1, E8 (set hit), E9, E10a, E10b, plus E2 to E4 where runnable; E6 becomes runnable on this data.
- **Metrics.** M7 (0–1 regret and graded), M1, M13, M4 with expert ranks, M8 (set hit for E8).
- **Expected interpretation.** Whatever the result, it is reported: if E10b does not beat E1 or R1, that is the finding.
- **Threats.** Expert disagreement; product drift between labelling and use; construct validity of "acceptable"; annotator familiarity with some products; small categories; the editorial ratings were authored by the same person who wrote the rules (circularity; the experts break it only if they are independent and blind).

## 5. Statistical plan

### 5.1 Sample sizes (reproducible arithmetic)

- Proportion with half-width h at 95%: `n = z² p(1−p)/h²`, z = 1.96. For p = 0.5: h = 0.10 → 97; 0.05 → 385; 0.02 → 2,401; **0.01 → 9,604**. For p = 0.7, h = 0.05 → 323.
- Paired difference in proportions (McNemar, normal approximation): `n ≈ (z_{α/2}√d + z_β√(d − Δ²))² / Δ²`, d = discordant share, Δ = difference, z_β = 0.8416. Examples: Δ = 0.10, d = 0.2 / 0.3 / 0.4 → 155 / 234 / 312; Δ = 0.05, d = 0.3 → 940.
- Zero violations in N independent trials: one-sided 95% upper bound `1 − 0.05^{1/N}`, about 3/N (N = 10,000 → 0.0003; N = 2,000 → 0.0015).
- **What the real pool can support.** The Wilson 95% half-width at an observed proportion of 0.5 is ±0.246 for 12 queries, ±0.176 for 27, ±0.153 for 37, ±0.069 for 200, ±0.054 for 323 (computed). The existing 12 and 27 self-authored queries therefore cannot distinguish algorithms whose true rates differ by less than about 0.2 to 0.3, apart from being non-independent of the development.

### 5.2 Splits and freezing

D1: generator seeds 0 to 999 are the development set (parameter exploration allowed); seeds 1000 to 1999 and higher are the test set, touched once after the manifest is hashed. D2/D3: the existing 27 test-suite queries are development only; test queries are new and independently labelled. Post-hoc analyses are labelled exploratory.

### 5.3 Tests and reporting

Paired design on identical instances. Binary outcomes: exact McNemar. Continuous (regret, displacement): Wilcoxon signed-rank with Hodges-Lehmann estimate. All intervals: percentile bootstrap, 10,000 resamples, or exact binomial where applicable. Multiplicity: Holm correction across the family of algorithm comparisons within an experiment. Effect sizes and intervals are reported before p-values. Invariant checks (proved properties) are reported as counts, not p-values.

## 6. Harness (design; not created)

Location proposed: `backend/experiments/` (does not exist; creating it needs your approval). Components: generator; degraders (missingness, noise); algorithm adapters (E1 calls the existing code read-only; E2 to E10 are re-implementations from `BASELINE_DEFINITIONS.md`); metric library; runner (CLI, seeded, resumable); output as JSON and CSV with a manifest (code-state SHA-256, parameters, seeds, data snapshot id, environment). Inputs are file snapshots of the registry (an export of the approved pool and, later, of the live registry); **no network, no database writes, no Neon access**. Every algorithm adapter must pass the unit tests derived from the proved properties and the review's counterexamples before any experiment uses it (so a defect in an adapter is not read as a finding).

## 7. Execution status

| Experiment | Status | Prior related evidence (different code, not results of this design) |
|---|---|---|
| EXP-1 | Not run | MCAR pilot on the real pool (2,400 draws per level) |
| EXP-2 | Not run | none |
| EXP-3 | Not run | one example of exact margin vs relative scaling; real-pool margins 0.012 to 0.125 |
| EXP-4 | Not run | 4,000-instance property tests; hand counterexamples; two V1 counterexamples executed |
| EXP-5 | Not run | existing unit tests for strict privacy on unknown handling |
| ADV-1 to ADV-9 | Not run | ADV-9: one-parameter width sweep on the 12 queries (no change) |
| EXP-6 | Not run; needs data | none |
| Baselines E2 to E10 | Not implemented | E10a/b logic prototyped earlier only as scratch code |

## 8. Cross-cutting threats to validity

| Threat | Mitigation in the design | Residual |
|---|---|---|
| **Circularity:** one author wrote the ratings, the rules and the test queries | independent expert labels (EXP-6); development/test split; blind annotation | until EXP-6 runs, no result supports a quality claim |
| **Synthetic-to-real gap** | vary generator parameters; fixed regression cases from real counterexamples | conclusions limited to the generator's family |
| **Small real pool** | report intervals (5.1); exhaustive enumeration where possible | cannot generalize |
| **Baseline weakness:** adaptations are weaker than published methods | state what was dropped (`BASELINE_DEFINITIONS.md`); report R0 to R3 | a win over an adaptation is not a win over the method |
| **Researcher degrees of freedom** | pre-registration, frozen test, Holm correction, exploratory label | some choices (metrics, ranges) remain policy |
| **Metric validity** | define the oracle in every table; separate property metrics from quality metrics | "acceptable" is an expert construct |
| **Product drift** | date-stamp labels and snapshots | labels age |
| **Implementation defects read as findings** | adapter unit tests from the proofs | residual bugs |
| **Multiple comparisons** | Holm; limited hypothesis list | exploratory results stay exploratory |
| **Leakage** (development queries or ratings influencing test) | separate sources; annotators blind to ratings | monitor |
