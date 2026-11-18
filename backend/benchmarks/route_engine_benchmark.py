"""Route Query Engine benchmark harness.

What this measures — and what it does not
-----------------------------------------
Everything here is computed from the *registry's published or estimated metadata* for a fixed scenario set.
The numbers are therefore **decision-quality proxies**, not measurements of real response quality, latency or
spend. Real execution quality is reported as "not measured" because no model is called and no judge model or
human label is available. Do not quote these figures as model performance.

Strategies compared
* always_strongest  - highest registry quality estimate, ignores the request
* always_cheapest   - lowest estimated USD for the request (requires both prices), ignores the request
* static_default    - fixed default weights over raw registry estimates; no task fit, no filtering
* engine_v2         - the Route Query Engine 2.0 pipeline (recommend mode)
* engine_v1         - not run: the previous engine is retained only as a backup under backend/_to_delete/pre_engine_v2

Per scenario and strategy we report whether the pick satisfies the scenario's hard constraints (checked with the
same filter the engine uses), plus the estimated cost and the registry quality of the pick.

Usage:  python -m benchmarks.route_engine_benchmark [--json out.json]     (from the backend directory)
"""
import argparse
import json
import statistics
import sys
from typing import Any, Dict, List, Optional

from app.services.model_registry import get_all_registry_entries
from app.services.routing_engine import filtering, pipeline, preferences, understanding
from app.services.routing_engine.preferences import DEFAULT_WEIGHTS

SCENARIOS: List[Dict[str, Any]] = [
    {"id": "qa-simple", "query": "What is the capital of France?"},
    {"id": "code-gen", "query": "Write a Python function that parses CSV files and returns JSON."},
    {"id": "code-budget", "query": "Write a Python function that debounces another function.", "max_cost": 0.002},
    {"id": "debug", "query": "My script crashes with a TypeError:\n```python\nprint(1 + 'a')\n```\nPlease debug it."},
    {"id": "math-proof", "query": "Prove that the sum of two even numbers is even, step by step."},
    {"id": "reasoning-hard", "query": "Design a distributed payment system, compare consensus protocols, justify the trade-offs and provide a migration plan. Output as a table."},
    {"id": "summarise-long", "query": "Summarize this report:\n" + "Energy storage costs fell across several markets this year. " * 120},
    {"id": "writing", "query": "Write a short blog post about remote work productivity, under 300 words."},
    {"id": "research", "query": "Research and compare the main approaches to retrieval-augmented generation, with limitations."},
    {"id": "data-analysis", "query": "Analyse this dataset and identify anomalies:\n" + "\n".join(f"row{i},{i * 3},{i % 4}" for i in range(30))},
    {"id": "image", "query": "Generate an image of a lighthouse at dawn."},
    {"id": "sensitive", "query": "What dosage of ibuprofen is typical for an adult with a fever?", "privacy_requirement": "high"},
    {"id": "latency-cap", "query": "Explain what a hash map is in a few sentences.", "max_latency": 3.0},
    {"id": "ambiguous", "query": "fix this"},
]


def _catalog():
    return [m for m in get_all_registry_entries() if m.entry_type == "inference_model" and m.active]


def _satisfies(model, scenario, profile, prefs) -> bool:
    return not filtering.check_model(model, profile, prefs, mode="recommend")


def _cost(model, profile) -> Optional[float]:
    return filtering.estimate_request_cost(model, profile.tokens.input_tokens, profile.tokens.output_tokens)


def _pick_strongest(models, profile):
    ranked = [m for m in models if m.estimated_quality is not None]
    return max(ranked, key=lambda m: (m.estimated_quality, m.model_id)) if ranked else None


def _pick_cheapest(models, profile):
    priced = [(c, m) for m in models if (c := _cost(m, profile)) is not None]
    return min(priced, key=lambda t: (t[0], t[1].model_id))[1] if priced else None


def _pick_static(models, profile):
    def s(m):
        q, c, l, r, k = (m.estimated_quality, m.estimated_cost, m.estimated_latency, m.reliability, m.risk_level)
        if None in (q, c, l, r, k):
            return None
        w = DEFAULT_WEIGHTS
        return w["quality"] * q + w["cost"] * (1 - c) + w["latency"] * (1 - l) + w["reliability"] * r + w["risk"] * (1 - k) + w["preference_alignment"] * 0.5
    scored = [(s(m), m) for m in models if s(m) is not None]
    return max(scored, key=lambda t: (t[0], t[1].model_id))[1] if scored else None


def run(catalog=None) -> Dict[str, Any]:
    catalog = catalog if catalog is not None else _catalog()
    by_id = {m.model_id: m for m in catalog}
    out: Dict[str, Any] = {"catalog_size": len(catalog), "scenarios": [], "summary": {}, "not_measured": [
        "real response quality", "real latency", "real spend", "user satisfaction",
        "engine_v1 comparison (previous engine retained only as a backup, not executed here)"]}
    strategies = ("always_strongest", "always_cheapest", "static_default", "engine_v2")
    tallies = {s: {"picked": 0, "satisfied": 0, "no_pick": 0, "quality": [], "cost": []} for s in strategies}
    for sc in SCENARIOS:
        profile = understanding.analyze(sc["query"])
        prefs = preferences.resolve(profile, max_cost=sc.get("max_cost"), max_latency=sc.get("max_latency"), privacy_requirement=sc.get("privacy_requirement"))
        picks: Dict[str, Optional[Any]] = {
            "always_strongest": _pick_strongest(catalog, profile), "always_cheapest": _pick_cheapest(catalog, profile), "static_default": _pick_static(catalog, profile)}
        try:
            res = pipeline.run(pipeline.PipelineRequest(query=sc["query"], max_cost=sc.get("max_cost"), max_latency=sc.get("max_latency"), privacy_requirement=sc.get("privacy_requirement")),
                               saved_weights=None, user_id=None, catalog_loader=lambda t, m: (list(catalog), []), learning_loader=lambda u, i: {}, observed_loader=lambda i: {})
            picks["engine_v2"] = by_id.get(res.selection.selected_model_id) if res.candidates else None
            engine_note = {"confidence": res.selection.confidence_level, "needs_clarification": res.profile.needs_clarification, "eligible": len(res.candidates)}
        except Exception as exc:  # report, never hide
            picks["engine_v2"], engine_note = None, {"error": str(exc)[:120]}
        row = {"id": sc["id"], "intent": profile.primary_intent, "engine": engine_note, "strategies": {}}
        for name in strategies:
            m = picks[name]
            t = tallies[name]
            if m is None:
                t["no_pick"] += 1
                row["strategies"][name] = {"pick": None}
                continue
            ok = _satisfies(m, sc, profile, prefs)
            c = _cost(m, profile)
            t["picked"] += 1
            t["satisfied"] += int(ok)
            if m.estimated_quality is not None:
                t["quality"].append(m.estimated_quality)
            if c is not None:
                t["cost"].append(c)
            row["strategies"][name] = {"pick": m.model_id, "satisfies_hard_constraints": ok, "registry_quality_estimate": m.estimated_quality, "estimated_cost_usd": c}
        out["scenarios"].append(row)
    n = len(SCENARIOS)
    for name, t in tallies.items():
        out["summary"][name] = {
            "scenarios": n, "picked": t["picked"], "no_pick": t["no_pick"],
            "hard_constraint_satisfaction_rate": round(t["satisfied"] / t["picked"], 3) if t["picked"] else None,
            "mean_registry_quality_estimate": round(statistics.mean(t["quality"]), 3) if t["quality"] else None,
            "mean_estimated_cost_usd": round(statistics.mean(t["cost"]), 6) if t["cost"] else None,
            "response_quality": "not measured"}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", help="write the full result to this path")
    args = ap.parse_args(argv)
    result = run()
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
    print(f"Catalog: {result['catalog_size']} inference models (registry estimates; nothing was executed)\n")
    print(f"{'strategy':<18}{'picked':>7}{'no pick':>8}{'constraint ok':>15}{'mean q (est.)':>15}{'mean $ (est.)':>15}")
    for name, s in result["summary"].items():
        print(f"{name:<18}{s['picked']:>7}{s['no_pick']:>8}{str(s['hard_constraint_satisfaction_rate']):>15}{str(s['mean_registry_quality_estimate']):>15}{str(s['mean_estimated_cost_usd']):>15}")
    print("\nNot measured: " + "; ".join(result["not_measured"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
