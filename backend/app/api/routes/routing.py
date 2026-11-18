"""
Route Query API (engine 2.0).

* POST /analyze-query     understand a query (no routing)
* POST /optimize-prompt   Prompt Optimizer 2.0 preview (modes, preserved constraints, quality indicators)
* POST /route-and-generate  full pipeline; mode=recommend (default, runs nothing) or mode=execute
* GET  /routing-history[/id]  persisted decisions (404 until the optional migration is applied)

The response keeps every legacy field and adds ``engine`` with the complete structured decision.
"""
import threading
import time
import uuid
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.logging import get_logger
from app.schemas.query import OptimizePromptRequest, OptimizePromptResponse, QueryRequest
from app.schemas.response import RouteAndGenerateResponse
from app.services import feedback_store, routing_log_store, user_store
from app.services.model_registry import get_catalog_with_exclusions, get_model_by_id, get_tool_recommendations
from app.services.routing_engine import optimizer, pipeline, understanding
from app.services.routing_engine.compat import to_legacy_profile

router = APIRouter()
logger = get_logger(__name__)
bearer = HTTPBearer(auto_error=False)

_RANKED_ALTERNATIVES_COUNT = 4
_IDEMPOTENCY_TTL = 600.0
_IDEMPOTENCY_MAX = 200
_idem_lock = threading.Lock()
_idem_cache: Dict[Tuple[str, str], Tuple[float, RouteAndGenerateResponse]] = {}


def _get_uid(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> Optional[str]:
    return user_store.decode_token(creds.credentials) if creds else None


def _require_user(uid: Optional[str]):
    user = user_store.get_by_id(uid) if uid else None
    if not user:
        raise HTTPException(401, "Authentication required. Please log in.")
    return user


@router.post("/analyze-query")
def analyze_query(body: dict):
    q = body.get("query", "")
    if not q or not isinstance(q, str):
        raise HTTPException(422, "query is required")
    try:
        profile = understanding.analyze(q, body.get("task_type_hint"))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {**to_legacy_profile(profile).model_dump(), "profile": profile.model_dump()}


@router.post("/optimize-prompt", response_model=OptimizePromptResponse)
def optimize_prompt(req: OptimizePromptRequest):
    try:
        profile = understanding.analyze(req.query, req.task_type_hint)
        model = get_model_by_id(req.model_id) if req.model_id else None
        result = optimizer.optimize(req.query, profile, req.mode, req.options, model=model)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    dump = result.model_dump()
    return OptimizePromptResponse(
        optimized_prompt=result.optimized_prompt, task_type=profile.task_type, domain=profile.domain, method=result.method, original_prompt=result.original_prompt,
        mode=result.mode, applied=result.applied, changes=dump["changes"], preserved_constraints=result.preserved_constraints, ambiguities=dump["ambiguities"],
        warnings=result.warnings, intent_preserved=result.intent_preserved, preservation_checks=result.preservation_checks, quality_before=dump["quality_before"],
        quality_after=dump["quality_after"], model_adaptation=result.model_adaptation, isolated_untrusted_blocks=result.isolated_untrusted_blocks,
        needs_clarification=profile.needs_clarification,
        analysis={"primary_intent": profile.primary_intent, "secondary_intents": [i.name for i in profile.secondary_intents], "complexity": profile.complexity.category,
                  "domain": profile.domain, "sensitivity": profile.risk.sensitivity, "tokens_estimate": profile.tokens.input_tokens})


def _filtered_legacy(excl):
    return [{"model_id": e.model_id, "reason": e.reason, "code": e.code, "requirement": e.requirement, "permanence": e.permanence, "stage": e.stage} for e in excl]


def _build_response(req: QueryRequest, user, res: "pipeline.PipelineResult", routing_id: str, total_ms: float) -> RouteAndGenerateResponse:
    by_model = res.model_lookup
    rows = res.candidates
    top = rows[0]
    selected = by_model[top.model_id]
    ex = res.execution
    final_id = ex.final_model_id or top.model_id
    final_model = by_model.get(final_id, selected)
    legacy_scores = []
    for r in rows:
        u = {k: (v if v is not None else 0.0) for k, v in r.utilities.items()}
        legacy_scores.append({
            "model_id": r.model_id, "quality_score": r.utilities.get("quality"), "cost_score": u["cost"], "latency_score": u["latency"], "reliability_score": u["reliability"],
            "risk_score": u["risk"], "preference_alignment": u["preference_alignment"], "overall_score": round(r.robust_score, 4),
            "score_breakdown": {**{k: r.utilities.get(k) for k in u}, "utility": r.utility, "robust_score": r.robust_score, "confidence": r.confidence, "learning_bonus": r.learning_adjustment}})
    alternatives = []
    for r in rows[1:_RANKED_ALTERNATIVES_COUNT + 1]:
        m = by_model[r.model_id]
        s = next(x for x in legacy_scores if x["model_id"] == r.model_id)
        alternatives.append({"model_id": r.model_id, "model_name": m.model_name, "provider": m.provider, "overall_score": s["overall_score"], "quality_score": s["quality_score"],
                             "cost_score": s["cost_score"], "latency_score": s["latency_score"], "reliability_score": s["reliability_score"], "risk_score": s["risk_score"],
                             "score_breakdown": s["score_breakdown"], "description": m.description, "modality": m.modality})
    tools = [{"model_id": t.model_id, "model_name": t.model_name, "provider": t.provider, "modality": t.modality, "entry_type": t.entry_type, "description": t.description,
              "external_url": t.external_url, "requires_key": t.requires_key, "capabilities": t.capabilities}
             for t in get_tool_recommendations(res.profile.task_type, res.profile.domain)[:3]]
    exp = res.explanation
    routing_explanation = {
        "routing_system": {"name": "AI Compass", "type": "adaptive_llm_router"}, "selected_model": top.model_id, "selected_model_name": selected.model_name,
        "fallback_model_id": rows[1].model_id if len(rows) > 1 else None, "routing_reason": exp.why_selected, "applied_weights": res.preferences.weights,
        "applied_constraints": {c.kind: c.value for c in res.preferences.hard_constraints if c.kind != "execution_blocked"},
        "user_context": {"user_group": user.user_group, "user_name": user.name, "routing_preferences": user.routing_preferences.model_dump(), "preferences_customized": user.preferences_customized},
        "query_characteristics": {"task_type": res.profile.task_type, "domain": res.profile.domain, "complexity": res.profile.complexity.score, "quality_requirement": None, "risk_level": res.profile.risk.score},
        "score_breakdown": next(s["score_breakdown"] for s in legacy_scores if s["model_id"] == top.model_id), "metadata_provenance": selected.metric_provenance, "metadata_status": selected.metadata_status,
        "overall_score": round(top.robust_score, 4), "filtered_out": _filtered_legacy(res.exclusions), "candidate_count": len(rows), "routing_latency_ms": res.routing_latency_ms,
        "narrative": exp.summary + " " + " ".join(exp.why_selected[:2]) + " " + exp.confidence_statement}
    if ex.status == "succeeded":
        generated = ex.response_text or ""
    elif ex.status == "not_requested":
        generated = "Recommendation ready. No model inference was run by AI Compass; use the recommended model with the prompt shown."
    else:
        generated = ex.blocked_reason or "No response was produced."
    ev = res.evaluation
    hs = ev.heuristic_scores
    if ev.status == "completed":
        response_eval = {"quality_score": hs.get("heuristic_quality", 0.0), "relevance_score": hs.get("relevance", 0.0), "completeness_score": hs.get("completeness", 0.0), "risk_score": 0.0,
                         "accepted": bool(ev.accepted), "evaluation_reasons": [f"{c.name}: {'pass' if c.passed else 'fail'} — {c.detail}" for c in ev.checks], "evaluation_method": ev.method}
    else:
        response_eval = {"quality_score": 0.0, "relevance_score": 0.0, "completeness_score": 0.0, "risk_score": 0.0, "accepted": False, "evaluation_reasons": ev.notes,
                         "evaluation_method": "not_applicable_recommendation_only" if ev.status == "not_requested" else f"evaluation_{ev.status}"}
    escalation = {"escalated": ex.escalated, "escalation_trigger": ex.escalation_reason, "original_model_id": top.model_id if ex.escalated else None,
                  "fallback_model_id": final_id if ex.escalated else None, "escalation_reason": ex.escalation_reason, "attempts": len(ex.attempts),
                  "final_status": "recommendation_ready" if ex.status == "not_requested" else ex.status}
    usage = [{"model_id": a.model_id, "latency_ms": a.latency_ms, "estimated_cost": a.cost_usd, "input_tokens": a.input_tokens, "output_tokens": a.output_tokens,
              "total_tokens": (a.input_tokens or 0) + (a.output_tokens or 0) if a.input_tokens is not None else None} for a in ex.attempts if a.outcome == "success"]
    engine = res.model_dump()
    engine["profile"]["original_query"] = ""  # the query is already returned as `query`; do not duplicate it in the engine payload
    engine["optimization"]["original_prompt"] = ""
    return RouteAndGenerateResponse(
        routing_system={"name": "AI Compass", "type": "adaptive_llm_router"}, routing_id=routing_id, query=req.query, profile=user.user_group,
        query_analysis=to_legacy_profile(res.profile).model_dump(), candidate_models=[r.model_id for r in rows], filtered_models=_filtered_legacy(res.exclusions), model_scores=legacy_scores,
        selected_model_id=top.model_id, selected_model_name=selected.model_name, routing_explanation=routing_explanation, generated_response=generated,
        response_evaluation=response_eval, escalation_info=escalation, final_model_id=final_id, final_model_name=final_model.model_name,
        performance_metrics={"total_latency_ms": round(total_ms, 1), "routing_latency_ms": res.routing_latency_ms, "candidates_evaluated": len(rows), "models_filtered": len(res.exclusions),
                             "escalated": ex.escalated, "user_group": user.user_group, "total_estimated_cost": ex.total_cost_usd if ex.total_cost_usd is not None else 0.0},
        request_usage=usage, optimized_prompt=res.prompt_used, learning_active=any(r.learning_adjustment != 0 for r in rows), ranked_alternatives=alternatives,
        tool_recommendations=tools,
        recommended_destination={"provider": final_model.provider, "entry_type": final_model.entry_type, "official_url": final_model.external_url, "availability": final_model.availability,
                                 "data_provenance": final_model.data_provenance, "last_verified_at": final_model.last_verified_at}, engine=engine)


@router.post("/route-and-generate", response_model=RouteAndGenerateResponse)
def route_and_generate(req: QueryRequest, uid: Optional[str] = Depends(_get_uid)):
    t0 = time.time()
    user = _require_user(uid)
    cache_key = (uid, req.idempotency_key) if req.idempotency_key and req.mode == "execute" else None
    if cache_key:
        with _idem_lock:
            hit = _idem_cache.get(cache_key)
            if hit and time.time() - hit[0] < _IDEMPOTENCY_TTL:
                return hit[1]
    try:
        preq = pipeline.PipelineRequest(**{k: v for k, v in req.model_dump().items() if k not in {"user_id", "idempotency_key"}})
        res = pipeline.run(preq, saved_weights=user.get_routing_weights(), user_id=uid)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not res.candidates:
        parts = "; ".join(f"{e.model_id}: {e.reason}" for e in res.exclusions[:8])
        hint = " ".join(res.no_candidate_guidance.get("suggestions", []))
        raise HTTPException(422, f"No model satisfies this query's constraints. {parts}. {hint}".strip())
    routing_id = str(uuid.uuid4())
    try:
        feedback_store.record_routing_decision(routing_id, uid, res.selection.selected_model_id)
    except Exception:
        logger.exception("Could not persist routing decision for feedback validation")
    try:
        routing_log_store.record(routing_id, uid, res)
    except Exception:
        logger.exception("Could not persist routing log")
    response = _build_response(req, user, res, routing_id, (time.time() - t0) * 1000)
    logger.info(f"Routed: {user.user_group} | {res.selection.selected_model_id} | mode={res.mode} | {response.performance_metrics['total_latency_ms']}ms")
    if cache_key:
        with _idem_lock:
            if len(_idem_cache) >= _IDEMPOTENCY_MAX:
                oldest = min(_idem_cache, key=lambda k: _idem_cache[k][0])
                _idem_cache.pop(oldest, None)
            _idem_cache[cache_key] = (time.time(), response)
    return response


@router.get("/routing-history")
def routing_history(limit: int = 50, uid: Optional[str] = Depends(_get_uid)):
    _require_user(uid)
    if not routing_log_store.table_available():
        raise HTTPException(404, "Routing history storage has not been provisioned (migration 20261119_route_query_engine.sql).")
    return routing_log_store.history(uid, min(max(limit, 1), 200))


@router.get("/routing-history/{routing_id}")
def routing_decision(routing_id: str, uid: Optional[str] = Depends(_get_uid)):
    _require_user(uid)
    if not routing_log_store.table_available():
        raise HTTPException(404, "Routing history storage has not been provisioned.")
    row = routing_log_store.get_decision(uid, routing_id)
    if not row:
        raise HTTPException(404, "Routing decision not found.")
    return row
