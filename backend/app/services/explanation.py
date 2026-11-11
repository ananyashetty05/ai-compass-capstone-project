"""
AI Compass - Explanation Service

Generates transparent, human-readable explanations for every routing decision.
Explanations are derived from actual routing data — not fabricated.
Includes user profile context (user_group + saved preferences).
"""
from typing import Dict, Any, Optional
from app.schemas.routing import RoutingDecision
from app.schemas.query import QueryProfile
from app.schemas.model import ModelMetadata
from app.schemas.profile import PersistentUserProfile


def build_explanation(
    routing_decision: RoutingDecision,
    query_profile: QueryProfile,
    all_models: list,
    user_profile: Optional[PersistentUserProfile] = None,
) -> Dict[str, Any]:
    model_map: Dict[str, ModelMetadata] = {m.model_id: m for m in all_models}
    selected = model_map.get(routing_decision.selected_model_id)

    selected_score = next(
        (s for s in routing_decision.model_scores if s.model_id == routing_decision.selected_model_id), None
    )

    user_context = {}
    if user_profile:
        user_context = {
            "user_group": user_profile.user_group,
            "user_name": user_profile.name,
            "routing_preferences": user_profile.routing_preferences.model_dump(),
            "preferences_customized": user_profile.preferences_customized,
        }

    return {
        "routing_system": {"name": "AI Compass", "type": "adaptive_llm_router"},
        "selected_model": routing_decision.selected_model_id,
        "selected_model_name": selected.model_name if selected else routing_decision.selected_model_id,
        "fallback_model_id": routing_decision.fallback_model_id,
        "routing_reason": routing_decision.routing_reason,
        "applied_weights": routing_decision.applied_weights,
        "applied_constraints": routing_decision.applied_constraints,
        "user_context": user_context,
        "query_characteristics": {
            "task_type": query_profile.task_type,
            "domain": query_profile.domain,
            "complexity": query_profile.complexity,
            "quality_requirement": query_profile.quality_requirement,
            "risk_level": query_profile.risk_level,
        },
        "score_breakdown": selected_score.score_breakdown if selected_score else {},
        "overall_score": selected_score.overall_score if selected_score else 0,
        "filtered_out": routing_decision.filtered_out_models,
        "candidate_count": len(routing_decision.candidate_models),
        "routing_latency_ms": routing_decision.routing_latency_ms,
        "narrative": _narrative(routing_decision, query_profile, selected, selected_score, user_profile),
    }


def _narrative(routing_decision, query_profile, selected, selected_score, user_profile) -> str:
    if not selected or not selected_score:
        return "Model selected based on multi-objective scoring."

    w = routing_decision.applied_weights
    top_dim = max(w, key=w.get)

    group_str = f"The user's {user_profile.user_group.capitalize()} profile" if user_profile else "The routing profile"
    cost_note = ""
    if user_profile and user_profile.user_group == "student":
        cost_note = " placing a high priority on cost while requiring adequate quality and reliability."
    elif user_profile and user_profile.user_group == "researcher":
        cost_note = " prioritizing maximum quality and reliability above cost."
    elif user_profile and user_profile.user_group == "organization":
        cost_note = " emphasizing reliability and privacy/risk control."
    else:
        cost_note = f" weighting {top_dim} most heavily ({w.get(top_dim, 0):.0%})."

    quality_note = (
        "satisfied the required quality threshold"
        if selected.estimated_quality >= query_profile.quality_requirement
        else "was the closest available match to the quality requirement"
    )

    return (
        f"AI Compass evaluated the query using the saved user preferences, query complexity, "
        f"quality requirement, cost and latency considerations, reliability requirement, and risk level. "
        f"The query was identified as a {query_profile.task_type} task in the "
        f"{query_profile.domain.replace('_', ' ')} domain "
        f"(complexity: {query_profile.complexity:.0%}). "
        f"{group_str}{cost_note} "
        f"Among the eligible models, {selected.model_name} {quality_note} "
        f"and achieved an overall routing score of {selected_score.overall_score:.3f}."
    )
