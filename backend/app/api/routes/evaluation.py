"""API-free evaluation of routing strategies using registry metadata only."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.schemas.evaluation import OfflineEvaluationRequest, OfflineEvaluationResponse
from app.services import candidate_filter, category_evaluation, offline_evaluation, query_analyzer, user_store
from app.services.routing_engine import audience as audience_mod
from app.services.model_registry import approved_pool_enabled, get_catalog_for_recommendation

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
    if approved_pool_enabled():
        return _approved_offline(req, user, profile)

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


def _approved_offline(req: OfflineEvaluationRequest, user, profile) -> OfflineEvaluationResponse:
    """Approved pool: no product has measured cost, latency or quality, so classic strategy benchmarking has nothing to compare.
    Instead the category-first ranking is compared with the plain approved-list order for the same category, and both are shown."""
    from app.schemas.evaluation import CatalogCoverage, OfflineStrategyResult
    from app.services.routing_engine import pipeline
    try:
        preq = pipeline.PipelineRequest(query=req.query, task_type_hint=req.task_type_hint, optimization_mode="disabled", max_cost=req.max_cost, max_latency=req.max_latency,
                                        require_capabilities=req.require_capabilities, privacy_requirement=req.privacy_requirement, model_ids=req.model_ids)
        res = pipeline.run(preq, saved_weights=user.get_routing_weights(), user_id=None)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    filtered = [{"model_id": e.model_id, "reason": e.reason} for e in res.exclusions]
    rows = res.candidates
    cat = res.profile.category
    results = []
    est_note = "Quality, reliability and risk are editorial estimates (relative judgements, not measurements); latency in seconds and prices are not available."
    def _disp(row, dim):
        """Value to show for a baseline: the rankable utility, else the displayed (editorial, never ranked) value."""
        v = row.utilities.get(dim)
        if v is None:
            e = row.evidence.get(dim)
            v = e.raw_value if e is not None and isinstance(e.raw_value, (int, float)) else None
        return v

    def _row(name, row, why):
        u = {d: _disp(row, d) for d in ("quality", "reliability", "risk", "cost")}
        return OfflineStrategyResult(
            strategy=name, status="selected", selected_model_id=row.model_id, selected_model=row.model_name, provider=row.provider, selection_rationale=why,
            routing_score=row.robust_score, quality_score=u.get("quality"), reliability_score=u.get("reliability"),
            risk_score=None if u.get("risk") is None else round(1.0 - u["risk"], 4), capabilities=list(row.strengths[:6]), availability="open_at_destination",
            constraint_satisfied=True, quality_source="editorial_estimate", missing_data=["latency in seconds", "price", est_note], data_sources={"fit": "vendor_published_strengths", "ratings": "editorial_estimate"})
    if rows:
        ordered = sorted(rows, key=lambda r: r.editorial_order)
        results.append(_row("aicompass", rows[0], "Highest fit score inside the resolved category. " + (cat.reason if cat else "")))
        strongest = max(rows, key=lambda r: ((_disp(r, "quality") or 0.0), -r.editorial_order))
        results.append(_row("strongest", strongest, "Highest editorial quality estimate in the resolved category, ignoring what the query asks for."))
        priced = [r for r in rows if r.utilities.get("cost") is not None]
        if priced:
            cheapest = max(priced, key=lambda r: (r.utilities["cost"], -r.editorial_order))
            results.append(_row("cheapest", cheapest, "Most open access class (free, free tier, pay-as-you-go, paid) in the resolved category. Classes are documented, not prices."))
        else:
            results.append(OfflineStrategyResult(strategy="cheapest", status="unavailable", selection_rationale="No product in this category has a documented pricing class.", constraint_satisfied=False))
        results.append(_row("static", ordered[0], "Baseline: the first product in the approved list that serves the category, ignoring what the query asks for."))
    else:
        results.append(OfflineStrategyResult(strategy="aicompass", status="unavailable", selection_rationale="No product satisfied the constraints.", constraint_satisfied=False))
    return OfflineEvaluationResponse(
        evaluation_method="offline_category_routing", data_disclosure=offline_evaluation.APPROVED_DATA_DISCLOSURE, query_analysis=profile, candidate_count=len(rows),
        filtered_models=filtered, strategy_results=results,
        catalog_coverage=CatalogCoverage(evaluated_models=len(rows), providers=len({r.provider for r in rows}), recommendation_only_models=len(rows), execution_ready_models=0,
                                         recommendation_only_share=1.0 if rows else None, models_with_missing_metadata=sum(1 for r in rows if r.utilities.get("cost") is None), missing_metadata_share=None,
                                         selection_by_strategy=[{"strategy": r.strategy, "selected_model": r.selected_model} for r in results],
                                         note="Approved pool: every product is recommendation-only. Quality, reliability and risk are editorial estimates; no measured data or prices exist."))


@router.get("/evaluate/ecosystem")
def evaluate_ecosystem(uid: Optional[str] = Depends(_get_uid)) -> dict:
    """Category-first routing suite over a fixed labelled query set. Metadata only: no product is called."""
    user = user_store.get_by_id(uid) if uid else None
    if not user:
        raise HTTPException(401, "Authentication required. Please log in.")
    from app.services import ecosystem_evaluation
    return ecosystem_evaluation.run()


@router.get("/evaluate/categories")
def evaluate_categories(uid: Optional[str] = Depends(_get_uid)) -> dict:
    """Category-aware offline evaluation over a fixed labelled query set. Metadata only: no model is called."""
    user = user_store.get_by_id(uid) if uid else None
    if not user:
        raise HTTPException(401, "Authentication required. Please log in.")
    return category_evaluation.run()
