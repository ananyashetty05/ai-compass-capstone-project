"""Route Query pipeline orchestrator: one function, staged, every stage timed and reported honestly."""
import time
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.model import ModelMetadata
from app.services.routing_engine import access as access_mod, counterfactual, explain, filtering, observed as observed_mod, optimizer, preferences, scoring, understanding
from app.services.routing_engine import execution as execution_mod
from app.services.routing_engine.types import (
    CandidateScore, DecisionExplanation, ENGINE_VERSION, EvaluationOutcome, ExclusionRecord, ExecutionOutcome, ExecutionPolicy,
    NormalizationDetails, OptimizationResult, QueryProfileV2, ResolvedPreferences, SCORING_VERSION, ScoringConfig, Selection, StageRecord,
)

MODES = ("recommend", "execute")


class PipelineRequest(BaseModel):
    query: str
    task_type_hint: Optional[str] = None
    mode: str = "recommend"
    optimization_mode: str = "standard"
    optimization_options: Optional[Dict[str, bool]] = None
    optimized_prompt: Optional[str] = Field(default=None, description="User-reviewed/edited optimized prompt")
    submit_prompt: str = "optimized"
    max_cost: Optional[float] = None
    max_latency: Optional[float] = None
    require_capabilities: Optional[List[str]] = None
    privacy_requirement: Optional[str] = None
    model_ids: Optional[List[str]] = None
    preferred_providers: Optional[List[str]] = None
    excluded_providers: Optional[List[str]] = None
    excluded_model_ids: Optional[List[str]] = None
    weight_overrides: Optional[Dict[str, float]] = None
    budget_usd: Optional[float] = None
    evaluate_response: bool = True


class PipelineResult(BaseModel):
    version: str = ENGINE_VERSION
    scoring_version: str = SCORING_VERSION
    mode: str
    status: str
    profile: QueryProfileV2
    optimization: OptimizationResult
    preferences: ResolvedPreferences
    candidates: List[CandidateScore] = []
    exclusions: List[ExclusionRecord] = []
    normalization: Optional[NormalizationDetails] = None
    selection: Selection
    explanation: DecisionExplanation
    execution: ExecutionOutcome
    evaluation: EvaluationOutcome
    stages: List[StageRecord] = []
    candidate_pool: str = "api_models"
    no_candidate_guidance: Dict[str, Any] = {}
    access: Dict[str, Any] = Field(default={}, description="Execution access of the recommended model; independent of its suitability")
    counterfactuals: List[Dict[str, Any]] = Field(default=[], description="Scenarios computed by re-running filtering+scoring with one input changed")
    catalogue_summary: Dict[str, Any] = {}
    prompt_used: str = ""
    prompt_used_source: str = "original"
    scoring_config: Optional[ScoringConfig] = None
    routing_latency_ms: float = 0.0
    model_lookup: Dict[str, Any] = Field(default={}, exclude=True)


class _Timer:
    def __init__(self, stages: List[StageRecord]):
        self.stages = stages

    def run(self, name: str, label: str, fn: Callable[[], Any], detail: Callable[[Any], str] = lambda _r: ""):
        t0 = time.perf_counter()
        try:
            out = fn()
        except Exception:
            self.stages.append(StageRecord(name=name, label=label, status="failed", duration_ms=round((time.perf_counter() - t0) * 1000, 2)))
            raise
        self.stages.append(StageRecord(name=name, label=label, status="completed", duration_ms=round((time.perf_counter() - t0) * 1000, 2), detail=detail(out)))
        return out

    def skip(self, name: str, label: str, why: str):
        self.stages.append(StageRecord(name=name, label=label, status="skipped", detail=why))


def _registry_exclusions(items: List[Dict[str, str]]) -> List[ExclusionRecord]:
    return [ExclusionRecord(model_id=i["model_id"], code="registry_ineligible", requirement="routing eligibility from the live model registry", reason=i["reason"],
                            permanence="temporary", stage="registry_eligibility") for i in items]


def run(req: PipelineRequest, *, saved_weights: Optional[Dict[str, float]], user_id: Optional[str],
        catalog_loader: Optional[Callable[[str, str], Any]] = None, learning_loader: Optional[Callable[[str, List[str]], Dict[str, float]]] = None,
        observed_loader: Optional[Callable[[List[str]], Dict[str, Any]]] = None, adapter_factory: Optional[Callable] = None,
        sleep: Optional[Callable[[float], None]] = None) -> PipelineResult:
    t_start = time.perf_counter()
    stages: List[StageRecord] = []
    tm = _Timer(stages)

    def validate():
        if req.mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        if req.submit_prompt not in ("original", "optimized"):
            raise ValueError("submit_prompt must be 'original' or 'optimized'")
        if req.optimization_mode not in optimizer.MODES:
            raise ValueError(f"optimization_mode must be one of {optimizer.MODES}")
        return True
    tm.run("input_validation", "Input validation", validate)

    profile = tm.run("query_understanding", "Query understanding", lambda: understanding.analyze(req.query, req.task_type_hint),
                     lambda p: f"{p.primary_intent} · {p.complexity.category} · {p.domain}")
    prefs = tm.run("preference_resolution", "Preference resolution", lambda: preferences.resolve(
        profile, saved_weights=saved_weights, weight_overrides=req.weight_overrides, max_cost=req.max_cost, max_latency=req.max_latency,
        require_capabilities=req.require_capabilities, privacy_requirement=req.privacy_requirement, model_ids=req.model_ids,
        preferred_providers=req.preferred_providers, excluded_providers=req.excluded_providers, excluded_model_ids=req.excluded_model_ids),
        lambda p: f"weights from {p.weight_source.replace('_', ' ')}; {len(p.hard_constraints)} hard constraint(s)")

    if req.optimization_mode == "disabled" and not req.optimized_prompt:
        tm.skip("prompt_optimization", "Prompt optimization", "Disabled; the original prompt is used")
    optimization = optimizer.optimize(req.query, profile, req.optimization_mode, req.optimization_options)
    if req.optimization_mode != "disabled" or req.optimized_prompt:
        stages.append(StageRecord(name="prompt_optimization", label="Prompt optimization", status="completed",
                                  detail=("user-edited prompt supplied" if req.optimized_prompt else f"{req.optimization_mode} mode; intent preserved: {optimization.intent_preserved}")))

    loader = catalog_loader
    if loader is None:
        from app.services.model_registry import get_catalog_with_exclusions
        loader = get_catalog_with_exclusions
    catalog, reg_excl = tm.run("candidate_discovery", "Candidate discovery", lambda: loader(profile.task_type, profile.required_modalities[0]),
                               lambda r: f"{len(r[0])} registry entries considered")
    exclusions: List[ExclusionRecord] = _registry_exclusions(reg_excl)
    if req.model_ids:
        known = {m.model_id for m in catalog} | {e["model_id"] for e in reg_excl}
        unknown = sorted(set(req.model_ids) - known)
        if unknown:
            raise ValueError(f"Unknown model pool selection: {', '.join(unknown)}")
        blocked = [e for e in reg_excl if e["model_id"] in set(req.model_ids)]
        if blocked:
            raise ValueError("; ".join(f"{e['model_id']} is excluded from routing: {e.get('reason', 'excluded by the live registry')}" for e in blocked))
    api_pool = [m for m in catalog if m.entry_type == "inference_model"]
    app_pool = [m for m in catalog if m.entry_type != "inference_model"]
    models_by_id = {m.model_id: m for m in catalog}
    obs = (observed_loader or observed_mod.load_observed)([m.model_id for m in catalog])

    pool_name = "api_models"
    obs_latency = {k: v.latency_p50_seconds for k, v in obs.items() if v.latency_p50_seconds}

    def do_filter():
        nonlocal pool_name
        passing, excl = filtering.filter_candidates(api_pool, profile, prefs, mode=req.mode, observed_latency=obs_latency)
        if not passing and req.mode == "recommend" and app_pool:
            p2, e2 = filtering.filter_candidates(app_pool, profile, prefs, mode="recommend")
            if p2:
                pool_name = "applications"
                return p2, excl + e2
            return passing, excl + e2
        return passing, excl
    passing, excl = tm.run("hard_constraint_filtering", "Hard-constraint filtering", do_filter, lambda r: f"{len(r[0])} eligible, {len(r[1])} excluded")
    exclusions += excl

    cfg = ScoringConfig()
    rows: List[CandidateScore] = []
    learn: Dict[str, float] = {}
    norm: Optional[NormalizationDetails] = None
    selection = Selection(status="no_eligible_candidates", caveats=["No candidate satisfied the hard constraints."])
    guidance: Dict[str, Any] = {}
    if passing:
        if user_id:
            try:
                ll = learning_loader
                if ll is None:
                    from app.services.feedback_store import get_learning_bonuses as ll
                learn = ll(user_id, [m.model_id for m in passing])
            except Exception:
                learn = {}
        rows, norm = tm.run("multi_objective_scoring", "Multi-objective scoring", lambda: scoring.score_candidates(passing, profile, prefs, observed=obs, learning=learn, config=cfg),
                            lambda r: f"{len(r[0])} candidates scored")
        selection = tm.run("model_selection", "Model selection", lambda: scoring.select(rows, prefs, profile, cfg),
                           lambda s: f"{s.confidence_level} confidence")
        import re as _re
        if "image-generation" in (profile.required_capabilities or []) and _re.search(r"\banimat\w*|\bgif\b|\bmotion\b", req.query, _re.I):
            selection.caveats.append("The request mentions animation. Image models produce still images, not motion; "
                                     "for moving output, ask for a video clip instead.")
    else:
        tm.skip("multi_objective_scoring", "Multi-objective scoring", "No eligible candidates")
        tm.skip("model_selection", "Model selection", "No eligible candidates")
        guidance = filtering.no_candidate_guidance(exclusions)

    # final prompt text
    selected_model = models_by_id.get(selection.selected_model_id) if selection.selected_model_id else None
    if not req.optimized_prompt and req.optimization_mode != "disabled" and selected_model is not None:
        optimization = optimizer.optimize(req.query, profile, req.optimization_mode, req.optimization_options, model=selected_model)
    if req.submit_prompt == "original" or req.optimization_mode == "disabled" and not req.optimized_prompt:
        prompt, source = req.query, "original"
    else:
        prompt, source = (req.optimized_prompt or optimization.optimized_prompt), "optimized"

    execution = ExecutionOutcome(status="not_requested", mode=req.mode)
    evaluation = EvaluationOutcome(status="not_requested", notes=["Recommendation mode: no model was run, so no response exists to evaluate."])
    if req.mode == "execute":
        if profile.risk.execution_blocked:
            execution = ExecutionOutcome(status="blocked", mode="execute", blocked_reason=profile.risk.execution_block_reason)
            evaluation = EvaluationOutcome(status="skipped", notes=["Execution was blocked."])
            tm.skip("execution", "Execution", profile.risk.execution_block_reason or "blocked")
        elif profile.needs_clarification:
            execution = ExecutionOutcome(status="blocked", mode="execute", blocked_reason="The query needs clarification before a model is run.")
            evaluation = EvaluationOutcome(status="skipped", notes=["Execution was blocked."])
            tm.skip("execution", "Execution", "Clarification required")
        elif not rows:
            execution = ExecutionOutcome(status="blocked", mode="execute", blocked_reason="No eligible executable candidate.")
            evaluation = EvaluationOutcome(status="skipped", notes=["Nothing was executed."])
            tm.skip("execution", "Execution", "No eligible candidate")
        else:
            policy = ExecutionPolicy(budget_usd=req.budget_usd)
            kwargs = {}
            if adapter_factory:
                kwargs["adapter_factory"] = adapter_factory
            else:
                # Production path: a recommended model without server credentials stays recommended but is skipped for execution.
                kwargs["access_blocked"] = {mid: access_mod.describe(m)["next_step"] for mid, m in models_by_id.items() if not access_mod.describe(m)["execution_available"]}
            if sleep:
                kwargs["sleep"] = sleep
            t0 = time.perf_counter()
            execution, evaluation = execution_mod.execute(ranked=rows, models=models_by_id, prompt=prompt, query=req.query, profile=profile, policy=policy,
                                                          prompt_source=source, evaluate=req.evaluate_response, **kwargs)
            stages.append(StageRecord(name="execution", label="Execution", status="completed" if execution.status == "succeeded" else "failed",
                                      duration_ms=round((time.perf_counter() - t0) * 1000, 2), detail=f"{len(execution.attempts)} attempt(s); {execution.status}"))
            stages.append(StageRecord(name="response_evaluation", label="Response evaluation", status="completed" if evaluation.status == "completed" else "skipped", detail=evaluation.status))
    else:
        tm.skip("execution", "Execution", "Recommendation mode")

    explanation = tm.run("explanation", "Explanation", lambda: explain.build(profile, prefs, rows, exclusions, selection))
    access = access_mod.describe(selected_model) if selected_model is not None else {}
    cfs: List[Dict[str, Any]] = []
    if rows and pool_name == "api_models":
        try:
            cfs = tm.run("counterfactuals", "Counterfactual analysis", lambda: counterfactual.compute(
                api_pool, passing, profile, prefs, base_id=selection.selected_model_id, mode=req.mode, observed=obs, learning=learn, cfg=cfg, observed_latency=obs_latency),
                lambda r: f"{len(r)} scenario(s) recomputed")
        except Exception:
            cfs = []
    catalogue = {"catalogue_total": len(catalog) + len(reg_excl), "considered": len(catalog), "excluded_by_registry": len(reg_excl), "eligible": len(passing) if pool_name == "api_models" or passing else 0,
                 "excluded_by_constraints": len(excl), "scored": len(rows), "selected": 1 if selection.selected_model_id else 0,
                 "credentials_used_for_comparison": False, "audience": profile.audience.kind}
    status = "needs_clarification" if profile.needs_clarification and rows else ("no_eligible_candidates" if not rows else "ok")
    return PipelineResult(
        mode=req.mode, status=status, profile=profile, optimization=optimization, preferences=prefs, candidates=rows, exclusions=exclusions, normalization=norm,
        selection=selection, explanation=explanation, execution=execution, evaluation=evaluation, stages=stages, candidate_pool=pool_name,
        no_candidate_guidance=guidance, access=access, counterfactuals=cfs, catalogue_summary=catalogue, prompt_used=prompt, prompt_used_source=source, scoring_config=cfg,
        routing_latency_ms=round((time.perf_counter() - t_start) * 1000, 2), model_lookup=models_by_id)
