# AI Compass — One Unified Recommendation Algorithm

**Status:** implemented, tested, no flag, no second version. `ALGORITHM_VERSION`, the V2 package, the interval scoring variants and the `v2` response field are gone. Nothing was pushed, deployed or migrated.

## What the algorithm is now

The original foundation is unchanged: category-first routing over the approved ecosystem → hard constraints before scoring → multi-objective weighted score (fit share 0.55, then quality/speed/reliability/risk, cost only on a stated cost preference) → deterministic selection → explanation, counterfactuals, confidence. Recommendation only; credentials never affect rank; the API and every field the UI reads are still populated.

Five changes, each chosen because it fixed something measurable:

| # | Change | Why (evidence) |
|---|---|---|
| 1 | **Exact ordering.** The ±0.005 tolerance window anchored at the leader is removed. Tie rules apply only to exactly equal scores. | In V1 a product scoring *higher* could lose to an earlier-listed one. Example: "cinematic rainy street video" — Gemini Omni scored 0.8283, Runway 0.8261, Runway won by list order. 7 of the 27 approved-pool winners were decided this way; now 0. A tolerance window also makes a ranking depend on who else is in the pool; exact ordering cannot. |
| 2 | **Unknown metric = neutral prior at zero confidence** (0.5, then the standard uncertainty penalty ρ=0.25 → 0.25), replacing "unknown = 0". | V1 treated "no data" as "worst possible". Chosen on dev seeds only, then confirmed on 2,000 untouched test seeds: regret 0.1073 → 0.0932 (−13%), top-1 hit rate 39.9% → 43.3%. A fixed prior (not a pool average) keeps removal invariance. |
| 3 | **Feature matching fixed.** "video clip from this image" now means image-to-video; "speech/narration" means text-to-speech; "Instagram poster" no longer matches *social video*; a requested feature that **no** product in the category documents (e.g. multimodal input for image generators) is disclosed and left out instead of lowering everyone's coverage equally. | These were the reasons many queries could not separate products. vd2 and mv2 confidence 0.23→0.45 and 0.53→0.68; dd4 0.76→0.91. |
| 4 | **Exact weight margin.** `weight_stability` is now the share of a 10% re-weighting (worst direction) the winner survives; `weight_margin` + `weight_margin_rival` report the exact smallest shift that flips the winner. | The old ±20% single-weight trials said "stable 100%" for a winner an exact search flips with a 7% shift. The exact value is deterministic, cheaper, and brute-force verified in tests. |
| 5 | **Constraints.** New hard limits `max_input_price_per_million` / `max_output_price_per_million` (unpublished price → excluded as unverifiable); cost-limit wording always says "estimated … not a guaranteed or billed amount"; strict privacy still passes on the registry's documented status but now says when that documentation is undated or older than a year. | Small, real capability gaps. The V2 "privacy scope" idea was **dropped**: the registry has no scope field, so enforcing it would have excluded everything. |

Deliberately **not** carried over from V2: interval/maximin scoring (it ignored the editorial ratings and lost accuracy in simulation), evidence tiers and certain-dominance diagnostics (no data to feed them), the empty evidence-records file.

## Evidence (and its limits)

**Synthetic study** (`research/unified_experiments/run.py`, test seeds 1000–2999, 2,000 instances per setting; prior chosen on dev seeds 0–199 only). Regret = share of the best-to-worst gap lost (lower is better):

| Setting | V1 original | Exact order only | Prior only | **Unified** | Paired reduction (95% CI) |
|---|---|---|---|---|---|
| editorial unbiased | 0.1073 | 0.1086 | 0.0939 | **0.0932** | 0.0141 [0.0104, 0.0180] |
| editorial inflated | 0.1335 | 0.1347 | 0.1164 | **0.1170** | 0.0164 [0.0122, 0.0206] |
| editorial noisy | 0.1509 | 0.1500 | 0.1419 | **0.1426** | 0.0083 [0.0041, 0.0125] |
| unknown data truly worse | 0.0612 | 0.0622 | 0.0625 | **0.0620** | −0.0008 [−0.0042, 0.0026] (no difference) |

Reading it honestly: the accuracy gain comes from change 2; change 1 is accuracy-neutral and is about correctness and determinism. The gain is real but modest (a 6–13% regret reduction in three settings, nothing when unknown data is genuinely worse); it holds across all three editorial-quality settings, and the unified rule is worse than V1 on about 5% of instances while better on about 10%.

**Real approved pool, 27 queries, same machine, original V1 code vs unified:** category accuracy/purity/determinism/credential independence stay 1.0; winners decided by list order 7 → 0; mean confidence 0.658 → 0.680 (8 high / 14 medium / 5 low before and after); winners changed on vd1, vd3 (Runway → Gemini Omni / Veo, which already had the higher score); confidence rose on im4, vd2, mv2, dd4. Removal invariance on these 27 queries: removing any non-winner never changed the winner, before or after (114 removals), and removing the winner always promoted the runner-up under the unified algorithm (checked on all 27 queries), so no improvement is claimed from this sample. The earlier V2 study did measure the tolerance-window flaw on its own generator: the V1 formula failed "runner-up is promoted when the winner is removed" in 40 of 1,000 trials; exact ordering makes that property hold by construction. Live catalogue, 9 curated queries: 4 winners had been decided by the tolerance window; q01/q09 now show an exact weight margin of 0.56%, i.e. a fragile pick that the confidence now reflects (confidence 0.33, low).

**What this cannot show.** No independent labels say which product is truly best for a real query, so product-level correctness is *not* proven and no such claim is made. The synthetic generator is ours. The editorial ratings behind quality/speed/reliability/risk remain hand-set estimates; the system still says so on every result. Sanity checks that did hold: "cite sources" → Perplexity, "clone my voice" → ElevenLabs, "one API for many models" → OpenRouter, AWS Lambda → Amazon Q Developer, "lowest-latency inference API" → Groq, UI wireframe → Figma. (A landing-page query also returns Figma rather than a site builder such as Lovable; that is a within-category judgement the available ratings do not settle, and it is left as is.)

## Verification

Backend: 427 passed, 1 failed — the one failure (`test_catalog_api::test_offline_defaults_are_honest`, 503 vs 403) fails identically on the code before any of this work. Frontend: type-check, lint (existing warnings only) and build pass. 28 new tests (`tests/test_unified_algorithm.py`, `tests/test_approved_unified.py`) cover exact ordering, removal invariance across all 27 queries (114 removals), missing-prior behaviour, brute-force verification of the weight margin, unit-price limits, privacy notes, feature matching, and the absence of any version switch. Two existing assertions were updated on purpose (scoring version 3.0.0; missing policy name).

## Files

Changed: `routing_engine/{scoring,filtering,preferences,ecosystem,pipeline,types,explain}.py`, `core/config.py`; new `routing_engine/robustness.py`; frontend wording/types only (stability labels, tie note, scoring-config type). Results: `research/results/unified_experiments.json`, `unified_real_pool.json` (the earlier `v2_experiments.json` is kept as the historical V2 study). The V2 spec/review documents describe the abandoned design and are kept for history only.
