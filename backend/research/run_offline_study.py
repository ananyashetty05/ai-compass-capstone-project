"""Run deterministic, metadata-only Phase 2 routing studies; no provider calls."""
import json
from pathlib import Path
from app.services import candidate_filter, offline_evaluation, query_analyzer
from app.services.model_registry import get_catalog_for_recommendation

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "datasets" / "phase2_curated_v1.json"
OUT = ROOT / "results" / "phase2_offline_v1.json"
PROFILES = {
    "balanced": {"quality": .30, "cost": .15, "latency": .15, "reliability": .20, "risk": .10, "preference_alignment": .10},
    "quality": {"quality": 1, "cost": 0, "latency": 0, "reliability": 0, "risk": 0, "preference_alignment": 0},
    "cost": {"quality": 0, "cost": 1, "latency": 0, "reliability": 0, "risk": 0, "preference_alignment": 0},
    "reliability": {"quality": 0, "cost": 0, "latency": 0, "reliability": 1, "risk": 0, "preference_alignment": 0},
}

def main():
    dataset = json.loads(DATASET.read_text())
    rows = []
    for sample in dataset["samples"]:
        profile = query_analyzer.apply_task_type_hint(query_analyzer.analyze(sample["query"]), sample["task_type"])
        catalog = get_catalog_for_recommendation(profile.task_type, profile.required_modalities[0])
        for profile_name, weights in PROFILES.items():
            candidates, filtered = candidate_filter.filter_candidates(catalog, profile)
            results = offline_evaluation.evaluate(candidates, profile, weights, filtered)
            rows.append({"query_id": sample["id"], "risk_label": sample["risk"], "profile": profile_name, "candidate_count": len(candidates), "filtered_count": len(filtered), "strategies": [r.model_dump() for r in results]})
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"dataset": dataset["dataset_id"], "method": "deterministic_metadata_only", "provider_calls": 0, "rows": rows}, indent=2))
    print(f"Wrote {len(rows)} deterministic study rows to {OUT}")

if __name__ == "__main__":
    main()
