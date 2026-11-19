"""API-free evaluation of routing strategies using registry metadata only."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.schemas.evaluation import OfflineEvaluationRequest, OfflineEvaluationResponse
from app.services import candidate_filter, category_evaluation, offline_evaluation, query_analyzer, user_store
from app.services.routing_engine import audience as audience_mod
from app.services.model_registry import get_catalog_for_recommendation

router = APIRouter()
bearer = HTTPBearer(auto_error=False)


def inference_models_only(catalog):
    """Offline evaluation compares routing strategies over API models AI Compass can actually run.

    Consumer applications (ChatGPT, Cursor, ...) are destinations the user opens themselves: they have no
    adapter and no published per-token price, so they would win cost- and latency-weighted strategies on
    missing data. They remain visible in the Model Pool and Route Query tool suggestions.
    """
    return [model for model in catalog if model.entry_type == "inference_model"]


def _get_uid(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> Optional[str]:
    return user_store.decode_token(creds.credentials) if creds else None


@router.post("/evaluate/offline", response_model=OfflineEvaluationResponse)
def evaluate_offline(
    req: OfflineEvaluationRequest,
    uid: Optional[str] = Depends(_get_uid),
) -> OfflineEvaluationResponse:
    user = user_store.get_by_id(uid) if uid else None
    if not user:
        raise HTTPException(401, "Authentication required. Please log in.")

    profile = query_analyzer.analyze(req.query)
    try:
        profile = query_analyzer.apply_task_type_hint(profile, req.task_type_hint)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    catalog = get_catalog_for_recommendation(
        profile.task_type,
        profile.required_modalities[0],
    )
    catalog = inference_models_only(catalog)
    if req.model_ids:
        available_ids = {model.model_id for model in catalog}
        unknown_ids = sorted(set(req.model_ids) - available_ids)
        if unknown_ids:
            raise HTTPException(422, f"Unknown model pool selection: {', '.join(unknown_ids)}")
        requested_ids = set(req.model_ids)
        catalog = [model for model in catalog if model.model_id in requested_ids]

    candidates, filtered = candidate_filter.filter_candidates(
        catalog,
        profile,
        max_cost=req.max_cost,
        max_latency=req.max_latency,
        require_capabilities=req.require_capabilities,
        privacy_requirement=getattr(req, "privacy_requirement", None),
        audience_kind=audience_mod.assess(req.query).kind,
    )
    if req.max_cost is not None:
        unknown_pricing = [
            model for model in candidates
            if model.input_price_per_million is None and model.cost_per_1k_tokens <= 0
        ]
        if unknown_pricing:
            unknown_ids = {model.model_id for model in unknown_pricing}
            candidates = [model for model in candidates if model.model_id not in unknown_ids]
            filtered.extend({
                "model_id": model.model_id,
                "reason": "Cannot verify the maximum input-price constraint because pricing is unavailable.",
            } for model in unknown_pricing)

    strategy_results = offline_evaluation.evaluate(
        models=candidates,
        query_profile=profile,
        weights=user.get_routing_weights(),
        filtered_out=filtered,
    )
    return OfflineEvaluationResponse(
        data_disclosure=offline_evaluation.DATA_DISCLOSURE,
        query_analysis=profile,
        candidate_count=len(candidates),
        filtered_models=filtered,
        strategy_results=strategy_results,
        catalog_coverage=offline_evaluation.catalog_coverage(candidates, strategy_results),
    )


@router.get("/evaluate/categories")
def evaluate_categories(uid: Optional[str] = Depends(_get_uid)) -> dict:
    """Category-aware offline evaluation over a fixed labelled query set. Metadata only: no model is called."""
    user = user_store.get_by_id(uid) if uid else None
    if not user:
        raise HTTPException(401, "Authentication required. Please log in.")
    return category_evaluation.run()
