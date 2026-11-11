"""
Main routing endpoint — capability-aware, returns ranked alternatives + tool recommendations.
"""
import time
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.schemas.query import OptimizePromptRequest, OptimizePromptResponse, QueryRequest
from app.schemas.response import RouteAndGenerateResponse
from app.services import query_analyzer, candidate_filter, multi_objective_router
from app.services import explanation, user_store, prompt_adapter
from app.services import prompt_optimizer
from app.services.model_registry import get_catalog_for_recommendation, get_tool_recommendations
from app.schemas.response import ResponseEvaluation, EscalationInfo
from app.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)
bearer = HTTPBearer(auto_error=False)

_RANKED_ALTERNATIVES_COUNT = 4


def _get_uid(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> Optional[str]:
    if not creds:
        return None
    return user_store.decode_token(creds.credentials)


@router.post("/analyze-query")
def analyze_query(body: dict):
    q = body.get("query", "")
    if not q:
        raise HTTPException(422, "query is required")
    return query_analyzer.analyze(q).model_dump()


@router.post("/optimize-prompt", response_model=OptimizePromptResponse)
def optimize_prompt(req: OptimizePromptRequest):
    query_profile = query_analyzer.analyze(req.query)
    try:
        query_profile = query_analyzer.apply_task_type_hint(query_profile, req.task_type_hint)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    optimized = prompt_optimizer.optimize(req.query, query_profile)
    return OptimizePromptResponse(
        optimized_prompt=optimized.prompt,
        task_type=optimized.task_type,
        domain=optimized.domain,
        method=optimized.method,
    )


@router.post("/route-and-generate", response_model=RouteAndGenerateResponse)
def route_and_generate(req: QueryRequest, uid: Optional[str] = Depends(_get_uid)):
    t0 = time.time()

    user_profile = user_store.get_by_id(uid) if uid else None
    if not user_profile:
        raise HTTPException(401, "Authentication required. Please log in.")

    query_profile = query_analyzer.analyze(req.query)
    try:
        query_profile = query_analyzer.apply_task_type_hint(query_profile, req.task_type_hint)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    weights = user_profile.get_routing_weights()

    all_models = get_catalog_for_recommendation(query_profile.task_type, query_profile.required_modalities[0])
    if not all_models:
        raise HTTPException(
            503,
            "The recommendation catalog is empty.",
        )
    if req.model_ids:
        catalog_ids = {model.model_id for model in all_models}
        unknown_ids = sorted(set(req.model_ids) - catalog_ids)
        if unknown_ids:
            raise HTTPException(422, f"Unknown model pool selection: {', '.join(unknown_ids)}")
        selected_ids = set(req.model_ids)
        all_models = [model for model in all_models if model.model_id in selected_ids]
        if not all_models:
            raise HTTPException(422, "The selected model pool contains no eligible catalog models.")

    candidates, filtered_out = candidate_filter.filter_candidates(
        all_models, query_profile,
        max_cost=req.max_cost,
        max_latency=req.max_latency,
        require_capabilities=req.require_capabilities,
    )
    if not candidates:
        reasons = "; ".join(f"{item['model_id']}: {item['reason']}" for item in filtered_out)
        raise HTTPException(422, f"No catalog entry satisfies this query's constraints. {reasons}")

    routing_decision = multi_objective_router.route(
        candidates, query_profile, weights, filtered_out,
        constraints={
            "max_cost": req.max_cost,
            "max_latency": req.max_latency,
            "require_capabilities": req.require_capabilities,
        },
        user_id=uid,
    )

    selected_model = next((m for m in all_models if m.model_id == routing_decision.selected_model_id), None)
    if not selected_model:
        raise HTTPException(500, "Selected model not found")

    optimized_prompt = prompt_adapter.adapt(req.query, query_profile)

    # AI Compass is a recommender, not an inference proxy.  Invoking an API
    # provider here made a successful routing decision fail whenever the
    # deployment did not hold that provider's key.  Keep the complete real
    # analyzer → filter → rank pipeline, then return an actionable routing
    # decision without making an external model call.
    generated_response = (
        "Recommendation ready. No model inference was run by AI Compass; "
        "open the official destination and use the optimized prompt."
    )
    final_eval = ResponseEvaluation(
        quality_score=1.0,
        relevance_score=1.0,
        completeness_score=1.0,
        risk_score=0.0,
        accepted=True,
        evaluation_reasons=["Recommendation-only workflow; no provider response was evaluated."],
        evaluation_method="not_applicable_recommendation_only",
    )
    escalation_info = EscalationInfo(
        escalated=False,
        attempts=0,
        final_status="recommendation_ready",
    )
    request_usage = [{"model_id": selected_model.model_id, "estimated_cost": 0.0}]
    final_response = generated_response
    final_optimized_prompt = optimized_prompt

    exp = explanation.build_explanation(routing_decision, query_profile, all_models, user_profile)

    final_model_id = routing_decision.selected_model_id
    final_model = selected_model

    # Build ranked alternatives (top N scored models excluding the winner)
    model_map = {m.model_id: m for m in all_models}
    ranked_alternatives = []
    for score in routing_decision.model_scores[1: _RANKED_ALTERNATIVES_COUNT + 1]:
        alt_model = model_map.get(score.model_id)
        if alt_model:
            ranked_alternatives.append({
                "model_id": score.model_id,
                "model_name": alt_model.model_name,
                "provider": alt_model.provider,
                "overall_score": score.overall_score,
                "quality_score": score.quality_score,
                "cost_score": score.cost_score,
                "latency_score": score.latency_score,
                "reliability_score": score.reliability_score,
                "risk_score": score.risk_score,
                "score_breakdown": score.score_breakdown,
                "description": alt_model.description,
                "modality": alt_model.modality,
            })

    # Tool recommendations for specialized tasks
    tool_recs = get_tool_recommendations(query_profile.task_type, query_profile.domain)
    tool_recommendations = [
        {
            "model_id": t.model_id,
            "model_name": t.model_name,
            "provider": t.provider,
            "modality": t.modality,
            "entry_type": t.entry_type,
            "description": t.description,
            "external_url": t.external_url,
            "requires_key": t.requires_key,
            "capabilities": t.capabilities,
        }
        for t in tool_recs[:3]
    ]

    total_ms = (time.time() - t0) * 1000
    total_cost = sum(item["estimated_cost"] or 0 for item in request_usage)
    routing_id = str(uuid.uuid4())

    logger.info(f"Routed: {user_profile.user_group} | {routing_decision.selected_model_id} | {total_ms:.0f}ms")

    return RouteAndGenerateResponse(
        routing_system={"name": "AI Compass", "type": "adaptive_llm_router"},
        routing_id=routing_id,
        query=req.query,
        profile=user_profile.user_group,
        query_analysis=query_profile.model_dump(),
        candidate_models=[m.model_id for m in candidates],
        filtered_models=filtered_out,
        model_scores=[s.model_dump() for s in routing_decision.model_scores],
        selected_model_id=routing_decision.selected_model_id,
        selected_model_name=selected_model.model_name,
        routing_explanation=exp,
        generated_response=final_response,
        response_evaluation=final_eval.model_dump(),
        escalation_info=escalation_info.model_dump(),
        final_model_id=final_model_id,
        final_model_name=final_model.model_name,
        performance_metrics={
            "total_latency_ms": round(total_ms, 1),
            "routing_latency_ms": routing_decision.routing_latency_ms,
            "candidates_evaluated": len(candidates),
            "models_filtered": len(filtered_out),
            "escalated": escalation_info.escalated,
            "user_group": user_profile.user_group,
            "total_estimated_cost": round(total_cost, 8),
        },
        request_usage=request_usage,
        optimized_prompt=final_optimized_prompt,
        learning_active=routing_decision.learning_active,
        ranked_alternatives=ranked_alternatives,
        tool_recommendations=tool_recommendations,
        recommended_destination={
            "provider": final_model.provider,
            "entry_type": final_model.entry_type,
            "official_url": final_model.external_url,
            "availability": final_model.availability,
            "data_provenance": final_model.data_provenance,
            "last_verified_at": final_model.last_verified_at,
        },
    )
