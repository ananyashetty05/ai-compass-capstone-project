# AI Compass Phase 2B: Offline Experimental Analysis

## Scope and research framing

This study evaluates deterministic **metadata-based routing decisions**, not model response quality, factuality, provider latency, availability, or billing. The candidate contribution is an explainable, configurable weighted router that applies hard eligibility constraints (including strict privacy metadata requirements) before ranking candidates. It is a systems-integration framing, not a claim of algorithmic novelty.

## Questions

- RQ1: Do valid weight profiles change selections over a fixed eligible pool?
- RQ2: Which weighted dimensions affect selection in this curated sample?
- RQ3: Do Pareto frontiers add trade-off insight beyond one weighted winner?

## Dataset and fairness

`phase2_curated_v1` has ten author-curated prompts. Labels are study inputs, not expert annotation. Every profile and baseline uses the same analyzer output, catalog snapshot, hard-filter result, and metadata. AI Compass, strongest, cheapest, and static ranking therefore share eligibility; unavoidable differences are their selection objectives. Unknown price is excluded from cheapest ranking; unavailable quality prevents strongest ranking.

## Literature matrix (verified primary sources)

| Work | Venue/year | Method and relevance | Limitation for comparison |
|---|---|---|---|
| Chen, Zaharia, Zou, *FrugalGPT* | TMLR, 2024 (arXiv 2023) | Cost-aware cascades/approximation; establishes cost-quality routing precedent. | Focuses on cascade cost/accuracy, not this system's hard privacy eligibility. |
| Ong et al., *RouteLLM* | arXiv 2024 | Preference-data router between stronger and weaker models. | Learned preference router; AI Compass is not trained. |
| Hu et al., *RouterBench* | ICLR 2025 / arXiv 2024 | Benchmark/framework with inference outcomes for multi-LLM routing. | Requires outcome data absent from this study. |

Named methods such as RouterDC, EmbedLLM, MODEL-SAT, GraphRouter, Hybrid LLM, LLM Bandit, and FLARE require further source-by-source bibliographic verification before inclusion; this report does not make claims about them.

## Reproduction

Run `PYTHONPATH=. .venv/bin/python research/run_offline_study.py`, then `PYTHONPATH=. .venv/bin/python research/analyze_phase2b.py` from `backend`. The latter creates a separate artifact and does not alter Phase 2 output.

## Validity and limits

Results are deterministic; repeated identical runs do not provide variance or statistical evidence. Registry quality/reliability/risk/latency are estimates, so selection changes are analytical consequences of configured metadata only. Live-inference experiments require fixed providers, prompts, repeated samples, defensible response judging, observed latency/cost, and an isolated persistence environment for feedback studies.
