"""
AI Compass - Multi-Objective Router (CORE RESEARCH MODULE)

Implements configurable weighted multi-objective scoring for model selection.

Research context:
  This module investigates an integrated adaptive and risk-aware multi-objective
  routing framework. The weighting system is configurable and transparent.
  Weights are NOT hard-coded — they come from user profiles and can be overridden via API.

Scoring dimensions:
  - quality_score:        how well the model's capability matches the query requirement
  - cost_score:           inverse of cost (higher = cheaper)
  - latency_score:        inverse of latency (higher = faster)
  - reliability_score:    model reliability
  - risk_score:           inverse of risk (higher = safer)
  - preference_alignment: how well the model aligns with user profile preferences

All scores are normalized to [0, 1].
"""
import math
from typing import Any, List, Dict, Optional, Tuple
from app.schemas.model import ModelMetadata
from app.schemas.query import QueryProfile
from app.schemas.routing import RoutingDecision, ModelScore
from app.core.logging import get_logger

logger = get_logger(__name__)

DEFAULT_WEIGHTS = {
    "quality": 0.30,
    "cost": 0.15,
    "latency": 0.15,
    "reliability": 0.20,
    "risk": 0.10,
    "preference_alignment": 0.10,
}


def _describe_constraints(
    constraints: Optional[Dict[str, Any]],
    candidate_count: int,
    eliminated_count: int,
) -> Dict[str, Any]:
    """
    Echo the hard constraints that were actually applied, plus what they did.

    Callers that apply no constraints (the evaluation baselines, which
    score every configured model) get {} so the client can say so plainly
    instead of implying a filter ran.

    Values are flat scalars on purpose: the client renders this dict as
    generic key/value chips, so a nested value would reach the user as
    the string "[object Object]".
    """
    if not constraints:
        return {}

    described: Dict[str, Any] = {}
    for key in ("max_cost", "max_latency"):
        value = constraints.get(key)
        if value is not None:
            described[key] = value
    capabilities = constraints.get("require_capabilities")
    if capabilities:
        described["require_capabilities"] = ", ".join(capabilities)

    # Only meaningful alongside a real constraint, so an all-None payload
    # still reports "no constraints were applied" rather than a bare count.
    if not described:
        return {}

    described["models_eliminated"] = eliminated_count
    described["models_considered"] = candidate_count
    return described


def route(
    models: List[ModelMetadata],
    query_profile: QueryProfile,
    weights: Dict[str, float],
    filtered_out: List[Dict[str, str]],
    constraints: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
) -> RoutingDecision:
    """
    Score all candidate models and select the best one.
    Returns a RoutingDecision with full transparency.

    `constraints` is the set of hard limits the caller passed to the
    candidate filter. It is reported back verbatim in the decision so the
    decision explains itself; omitting it reports that none were applied.

    `user_id` enables personalised learning bonuses from feedback history.
    """
    if not models:
        raise ValueError("route() requires at least one candidate model")

    import time
    start = time.time()

    # Load per-model learning bonuses (empty dict during cold start)
    learning_bonuses: Dict[str, float] = {}
    if user_id:
        try:
            from app.services.feedback_store import get_learning_bonus
            learning_bonuses = {
                m.model_id: get_learning_bonus(user_id, m.model_id) for m in models
            }
        except Exception as exc:
            logger.warning(f"Learning bonus lookup failed: {exc}")

    # Merge configured profile weights with defaults so every score dimension
    # has an explicit contribution. Older persisted profiles may not contain
    # newer dimensions; those dimensions receive the documented default.
    # Reject negative/non-finite weights rather than silently producing scores
    # that are difficult to interpret in an experiment.
    import math

    dimension_weights = {}
    supplied = weights or {}
    for dimension, default_value in DEFAULT_WEIGHTS.items():
        value = supplied.get(dimension, default_value)
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = default_value
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"Routing weight '{dimension}' must be a finite non-negative number")
        dimension_weights[dimension] = value
    quality_missing = any(
        model.estimated_quality is None
        or not math.isfinite(model.estimated_quality)
        for model in models
    )
    if quality_missing:
        dimension_weights["quality"] = 0.0
        logger.info("Quality dimension excluded because one or more candidates lack quality metadata")

    # If a caller explicitly sets every supplied weight to zero, use the
    # documented defaults rather than accidentally giving all weight to the
    # one dimension that may have been absent from an older profile.
    supplied_known = [float(supplied[k]) for k in DEFAULT_WEIGHTS if k in supplied]
    total = sum(dimension_weights.values())
    if not supplied_known or sum(supplied_known) <= 0 or total <= 0:
        fallback_weights = dict(DEFAULT_WEIGHTS)
        if quality_missing:
            fallback_weights["quality"] = 0.0
        fallback_total = sum(fallback_weights.values())
        norm_weights = {
            key: value / fallback_total
            for key, value in fallback_weights.items()
        }
    else:
        norm_weights = {key: value / total for key, value in dimension_weights.items()}

    # Score each model
    scored: List[ModelScore] = []
    for model in models:
        ms = _score_model(model, query_profile, norm_weights, learning_bonuses.get(model.model_id, 0.0))
        scored.append(ms)

    # Sort by overall score descending
    scored.sort(key=lambda s: s.overall_score, reverse=True)

    selected = scored[0]
    fallback = scored[1] if len(scored) > 1 else None

    routing_reasons = _generate_reasons(selected, scored, query_profile, norm_weights, models)

    elapsed_ms = (time.time() - start) * 1000

    learning_active = bool(learning_bonuses and any(v != 0.0 for v in learning_bonuses.values()))

    return RoutingDecision(
        selected_model_id=selected.model_id,
        fallback_model_id=fallback.model_id if fallback else None,
        candidate_models=[m.model_id for m in models],
        filtered_out_models=filtered_out,
        model_scores=scored,
        routing_reason=routing_reasons,
        applied_weights=norm_weights,
        applied_constraints=_describe_constraints(constraints, len(models), len(filtered_out)),
        routing_latency_ms=round(elapsed_ms, 2),
        learning_active=learning_active,
    )


def _score_model(
    model: ModelMetadata,
    query_profile: QueryProfile,
    weights: Dict[str, float],
    learning_bonus: float = 0.0,
) -> ModelScore:
    """Compute per-dimension scores and weighted overall score."""

    quality_score = _quality_score(model, query_profile)
    cost_score = 1.0 - model.estimated_cost
    latency_score = 1.0 - model.estimated_latency
    reliability_score = model.reliability
    risk_score = 1.0 - model.risk_level
    preference_alignment = _preference_alignment(model, query_profile)

    breakdown = {
        "quality": quality_score,
        "cost": cost_score,
        "latency": latency_score,
        "reliability": reliability_score,
        "risk": risk_score,
        "preference_alignment": preference_alignment,
    }

    overall = sum((breakdown[k] or 0) * weights.get(k, 0) for k in breakdown)
    # Apply learning bonus after weighted sum — bounded, additive, transparent
    overall_with_learning = max(0.0, min(1.0, overall + learning_bonus))

    return ModelScore(
        model_id=model.model_id,
        quality_score=round(quality_score, 4) if quality_score is not None else None,
        cost_score=round(cost_score, 4),
        latency_score=round(latency_score, 4),
        reliability_score=round(reliability_score, 4),
        risk_score=round(risk_score, 4),
        preference_alignment=round(preference_alignment, 4),
        overall_score=round(overall_with_learning, 4),
        score_breakdown={
            **breakdown,
            "learning_bonus": round(learning_bonus, 4),
        },
    )


def _quality_score(model: ModelMetadata, query_profile: QueryProfile) -> Optional[float]:
    """
    Quality score: penalize if model quality is below the query's requirement.
    Reward if model quality exceeds requirement.
    """
    if model.estimated_quality is None or not math.isfinite(model.estimated_quality):
        return None
    gap = model.estimated_quality - query_profile.quality_requirement
    if gap >= 0:
        return min(1.0, model.estimated_quality + gap * 0.1)
    else:
        # Penalize proportionally to the gap
        return max(0.0, model.estimated_quality + gap * 0.5)


def _preference_alignment(model: ModelMetadata, query_profile: QueryProfile) -> float:
    """
    Proxy for query-to-model capability fit based on task/domain/capability metadata.
    This is not a direct measurement of an individual user's personal preferences;
    that distinction should be preserved when interpreting experimental results.
    """
    score = 0.5  # baseline
    if query_profile.task_type in model.supported_tasks:
        score += 0.25
    if query_profile.domain in model.supported_domains:
        score += 0.15
    if "general" in model.supported_domains:
        score += 0.05
    # Bonus for specialized models on specialized tasks
    if query_profile.task_type == "coding" and "coding" in model.capabilities:
        score += 0.10
    return min(1.0, score)


def _generate_reasons(
    selected: ModelScore,
    all_scores: List[ModelScore],
    query_profile: QueryProfile,
    weights: Dict[str, float],
    models: List[ModelMetadata],
) -> List[str]:
    """Generate human-readable routing reasons from actual score data."""
    model_map = {m.model_id: m for m in models}
    sel_model = model_map.get(selected.model_id)
    reasons = []

    if sel_model:
        reasons.append(
            f"{sel_model.model_name} selected with overall score {selected.overall_score:.3f}"
        )

    # Explain top contributing dimensions
    top_dims = [
        item for item in sorted(weights.items(), key=lambda x: x[1], reverse=True)
        if item[1] > 0
    ][:3]
    for dim, w in top_dims:
        score_val = getattr(selected, f"{dim}_score", selected.score_breakdown.get(dim, 0))
        reasons.append(
            f"Strong {dim} score ({score_val:.2f}) — weight {w:.0%} in current profile"
        )

    # Quality vs requirement
    if sel_model:
        if sel_model.estimated_quality is None or not math.isfinite(sel_model.estimated_quality):
            reasons.append("Quality metadata unavailable; quality was excluded from the routing comparison")
        elif sel_model.estimated_quality >= query_profile.quality_requirement:
            reasons.append(
                f"Quality ({sel_model.estimated_quality:.2f}) meets requirement ({query_profile.quality_requirement:.2f})"
            )
        else:
            reasons.append(
                f"Quality ({sel_model.estimated_quality:.2f}) is below ideal requirement ({query_profile.quality_requirement:.2f}) but best available"
            )

    # Compare with runner-up
    if len(all_scores) > 1:
        runner_up = all_scores[1]
        diff = selected.overall_score - runner_up.overall_score
        reasons.append(
            f"Outscored next candidate ({runner_up.model_id}) by {diff:.3f} points"
        )

    return reasons
