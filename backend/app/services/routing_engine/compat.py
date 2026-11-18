"""Bridges between the legacy flat ``QueryProfile`` (still used by the offline evaluation study
and older API consumers) and the canonical ``QueryProfileV2``. There is one engine; these are projections."""
from app.schemas.query import QueryProfile
from app.services.routing_engine.types import ComplexityAssessment, Intent, QueryProfileV2, RiskAssessment, TokenEstimate
from app.services.routing_engine import understanding as U


def to_legacy_profile(p: QueryProfileV2) -> QueryProfile:
    cx = p.complexity.score
    kinds = {(r.kind, r.value) for r in p.explicit_requirements}
    return QueryProfile(
        task_type=p.task_type, domain=p.domain, complexity=round(cx, 3),
        context_requirement=round(min(1.0, p.tokens.input_tokens / 2000), 3),
        quality_requirement=round(min(1.0, 0.5 + cx * 0.3 + (0.2 if p.domain in {"medical", "legal"} else 0)), 3),
        risk_level=round(p.risk.score, 3), latency_requirement=0.8 if ("latency", "low") in kinds else 0.5,
        cost_sensitivity=0.8 if ("cost", "low") in kinds else 0.5, reliability_requirement=0.9 if ("accuracy", "high") in kinds else 0.75,
        estimated_tokens=p.tokens.input_tokens, analysis_method=p.analysis_method, required_modalities=list(p.required_modalities),
        required_capabilities=list(p.required_capabilities), classification_confidence=p.confidence.get("intent", 0.0), uncertainty_notes=list(p.notes))


def from_legacy_profile(q: QueryProfile) -> QueryProfileV2:
    intent = U.TASK_TYPE_TO_INTENT.get(q.task_type, "qa")
    tags = list(U.INTENT_TAGS.get(intent, ("qa",)))
    if q.task_type not in tags:
        tags.append(q.task_type)
    risk = float(q.risk_level)
    return QueryProfileV2(
        original_query="", primary_intent=intent, intents=[Intent(name=intent, score=1.0, registry_tags=tags)], task_type=q.task_type, task_tags=tags,
        domain=q.domain, domain_confidence=q.classification_confidence,
        complexity=ComplexityAssessment(score=q.complexity, category="moderate", methodology="converted from a legacy profile"),
        required_capabilities=list(q.required_capabilities), required_modalities=list(q.required_modalities or ["text"]),
        tokens=TokenEstimate(input_tokens=q.estimated_tokens, output_tokens=256, method="legacy_profile", exact=False, output_basis="legacy_default"),
        risk=RiskAssessment(sensitivity="none" if risk < 0.3 else "moderate", score=risk), analysis_method=q.analysis_method + "+v2_adapter")
