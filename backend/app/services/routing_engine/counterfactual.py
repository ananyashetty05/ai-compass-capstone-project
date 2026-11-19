"""Counterfactual explanations computed by *re-running the real routing functions*.

Nothing here is estimated or narrated: each scenario changes one input (an objective weight or one
hard constraint), calls ``filtering.filter_candidates`` + ``scoring.score_candidates`` + ``scoring.select``
again, and reports who wins. A scenario that cannot be computed is omitted rather than guessed.
"""
from typing import Any, Dict, List, Optional

from app.schemas.model import ModelMetadata
from app.services.routing_engine import filtering, scoring
from app.services.routing_engine.preferences import DIMENSIONS
from app.services.routing_engine.types import QueryProfileV2, ResolvedPreferences, ScoringConfig

_LABEL = {"quality": "quality", "cost": "cost", "latency": "speed", "reliability": "reliability", "risk": "risk control", "preference_alignment": "task fit"}
_RELAXABLE = {"max_cost_usd_per_request": "the cost limit", "max_latency_seconds": "the latency limit", "privacy_strict": "strict privacy", "require_capabilities": "the extra capability requirement"}
_BOOST = 2.0


def _winner(passing: List[ModelMetadata], profile, prefs, obs, learn, cfg) -> Optional[Dict[str, Any]]:
    if not passing:
        return None
    rows, _ = scoring.score_candidates(passing, profile, prefs, observed=obs, learning=learn, config=cfg)
    sel = scoring.select(rows, prefs, profile, cfg)
    top = rows[0]
    return {"model_id": top.model_id, "model_name": top.model_name, "provider": top.provider, "robust_score": top.robust_score,
            "candidates": len(rows), "confidence_level": sel.confidence_level}


def compute(pool: List[ModelMetadata], passing: List[ModelMetadata], profile: QueryProfileV2, prefs: ResolvedPreferences, *, base_id: Optional[str],
            mode: str, observed: Optional[dict], learning: Optional[dict], cfg: ScoringConfig, observed_latency: Optional[dict] = None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not passing or base_id is None:
        return out
    obs, learn = observed or {}, learning or {}

    # 1) emphasise one objective (weight x2, renormalised) over the same eligible set
    for dim in ("quality", "cost", "latency"):
        if prefs.weights.get(dim, 0) <= 0:
            continue
        w = {k: v * (_BOOST if k == dim else 1.0) for k, v in prefs.weights.items()}
        t = sum(w.values())
        p2 = prefs.model_copy(update={"weights": {k: v / t for k, v in w.items()}})
        win = _winner(passing, profile, p2, obs, learn, cfg)
        if win:
            out.append({"kind": "weight_shift", "scenario": f"If {_LABEL[dim]} mattered twice as much", "changed_input": f"weight.{dim} ×{_BOOST:g}",
                        "winner": win, "changed": win["model_id"] != base_id})

    # 2) relax each hard constraint that was actually applied, then refilter the whole pool
    present = {c.kind for c in prefs.hard_constraints}
    for kind, label in _RELAXABLE.items():
        if kind not in present:
            continue
        p2 = prefs.model_copy(update={"hard_constraints": [c for c in prefs.hard_constraints if c.kind != kind]})
        passing2, _ = filtering.filter_candidates(pool, profile, p2, mode=mode, observed_latency=observed_latency)
        win = _winner(passing2, profile, p2, obs, learn, cfg)
        if win:
            out.append({"kind": "constraint_relaxed", "scenario": f"If you removed {label}", "changed_input": f"constraint.{kind} removed",
                        "winner": win, "changed": win["model_id"] != base_id, "eligible_after": len(passing2), "eligible_before": len(passing)})
    return out
