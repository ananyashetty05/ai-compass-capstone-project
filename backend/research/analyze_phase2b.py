"""Separate deterministic Phase 2B analysis; never rewrites Phase 2 results."""
import json
from pathlib import Path
from app.services import candidate_filter, multi_objective_router, query_analyzer
from app.services.model_registry import get_catalog_for_recommendation
from run_offline_study import DATASET, PROFILES

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results" / "phase2b_analysis_v1.json"
DIMS = ("quality", "cost", "latency", "reliability", "risk", "preference_alignment")

def pareto(models, profile):
    """Return IDs non-dominated on higher-is-better normalized metadata proxies."""
    def vector(m):
        q = m.estimated_quality
        if q is None: return None
        return (q, 1 - m.estimated_cost, 1 - m.estimated_latency, m.reliability, 1 - m.risk_level)
    valid = [(m, vector(m)) for m in models if vector(m) is not None]
    return sorted(m.model_id for m, v in valid if not any(
        other is not m and all(a >= b for a, b in zip(ov, v)) and any(a > b for a, b in zip(ov, v))
        for other, ov in valid
    ))

def main():
    dataset = json.loads(DATASET.read_text())
    sensitivity, ablations, frontiers = [], [], []
    for sample in dataset["samples"]:
        profile = query_analyzer.apply_task_type_hint(query_analyzer.analyze(sample["query"]), sample["task_type"])
        candidates, filtered = candidate_filter.filter_candidates(get_catalog_for_recommendation(profile.task_type, profile.required_modalities[0]), profile)
        winners = {name: multi_objective_router.route(candidates, profile, weights, filtered).selected_model_id for name, weights in PROFILES.items()}
        sensitivity.append({"query_id": sample["id"], "winners": winners, "unique_winners": len(set(winners.values()))})
        balanced = PROFILES["balanced"]
        base = winners["balanced"]
        for dimension in DIMS:
            weights = dict(balanced); weights[dimension] = 0
            decision = multi_objective_router.route(candidates, profile, weights, filtered)
            ablations.append({"query_id": sample["id"], "removed_dimension": dimension, "baseline_winner": base, "ablated_winner": decision.selected_model_id, "changed": base != decision.selected_model_id, "eligible_candidates": len(candidates)})
        frontiers.append({"query_id": sample["id"], "eligible_candidates": len(candidates), "pareto_frontier": pareto(candidates, profile)})
    OUT.write_text(json.dumps({"method":"deterministic_metadata_only", "dataset":dataset["dataset_id"], "sensitivity":sensitivity, "ablations":ablations, "pareto":frontiers}, indent=2))
    print(f"Wrote {OUT}")
if __name__ == "__main__": main()
