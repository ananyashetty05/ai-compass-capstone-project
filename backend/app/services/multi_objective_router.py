"""Compatibility facade over ``routing_engine.scoring``.

There is a single scoring implementation. ``route`` keeps the legacy signature/return type used by
the offline evaluation study and returns a ``RoutingDecision`` built from the new engine's output.
"""
import time
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger
from app.schemas.model import ModelMetadata
from app.schemas.query import QueryProfile
from app.schemas.routing import ModelScore, RoutingDecision
from app.services.routing_engine import preferences, scoring
from app.services.routing_engine.compat import from_legacy_profile
from app.services.routing_engine.preferences import DEFAULT_WEIGHTS  # noqa: F401  (re-exported)

logger = get_logger(__name__)


def _describe_constraints(constraints: Optional[Dict[str, Any]], candidate_count: int, eliminated_count: int) -> Dict[str, Any]:
    if not constraints:
        return {}
    described: Dict[str, Any] = {k: constraints[k] for k in ("max_cost", "max_latency", "privacy_requirement") if constraints.get(k) is not None}
    if constraints.get("require_capabilities"):
        described["require_capabilities"] = ", ".join(constraints["require_capabilities"])
    if not described:
        return {}
    described["models_eliminated"], described["models_considered"] = eliminated_count, candidate_count
    return described


def route(models: List[ModelMetadata], query_profile: QueryProfile, weights: Dict[str, float], filtered_out: List[Dict[str, str]],
          constraints: Optional[Dict[str, Any]] = None, user_id: Optional[str] = None) -> RoutingDecision:
    if not models:
        raise ValueError("route() requires at least one candidate model")
    start = time.time()
    profile = from_legacy_profile(query_profile)
    prefs = preferences.resolve(profile, saved_weights=weights if weights else None)
    learning: Dict[str, float] = {}
    if user_id:
        try:
            from app.services.feedback_store import get_learning_bonuses
            learning = get_learning_bonuses(user_id, [m.model_id for m in models])
        except Exception as exc:
            logger.warning(f"Learning bonus lookup failed: {exc}")
    rows, _norm = scoring.score_candidates(models, profile, prefs, learning=learning)
    sel = scoring.select(rows, prefs, profile)
    scores = []
    for r in rows:
        u = {k: (v if v is not None else 0.0) for k, v in r.utilities.items()}
        scores.append(ModelScore(model_id=r.model_id, quality_score=r.utilities.get("quality"), cost_score=u["cost"], latency_score=u["latency"], reliability_score=u["reliability"],
                                 risk_score=u["risk"], preference_alignment=u["preference_alignment"], overall_score=round(r.robust_score, 4),
                                 score_breakdown={**{k: r.utilities.get(k) for k in u}, "utility": r.utility, "robust_score": r.robust_score, "learning_bonus": r.learning_adjustment}))
    by_id = {m.model_id: m for m in models}
    reasons = [f"{by_id[rows[0].model_id].model_name} selected with robust score {rows[0].robust_score:.3f}"]
    if len(rows) > 1:
        reasons.append(f"Outscored next candidate ({rows[1].model_id}) by {rows[0].robust_score - rows[1].robust_score:.3f} points")
    return RoutingDecision(selected_model_id=rows[0].model_id, fallback_model_id=rows[1].model_id if len(rows) > 1 else None, candidate_models=[m.model_id for m in models],
                           filtered_out_models=filtered_out, model_scores=scores, routing_reason=reasons, applied_weights=prefs.weights,
                           applied_constraints=_describe_constraints(constraints, len(models), len(filtered_out)), routing_latency_ms=round((time.time() - start) * 1000, 2),
                           learning_active=any(v != 0.0 for v in learning.values()))
