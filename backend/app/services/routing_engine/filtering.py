"""Hard-constraint filtering. Runs strictly before scoring; a constraint can never be bought back by a high score.

Every removed candidate yields an ``ExclusionRecord``. Constraints that cannot be verified
because metadata is missing exclude the candidate (unknown is not treated as compliant).
"""
from typing import Dict, List, Optional, Tuple

from app.schemas.model import ModelMetadata
from app.services.routing_engine.types import ExclusionRecord, QueryProfileV2, ResolvedPreferences

_PERMANENT_LIFECYCLE = {"retired", "incompatible"}
_ALLOWED_PRIVACY = {"provider_documented_restricted", "customer_controlled"}
MEASURED_LATENCY_PROVENANCE = {"measured", "observed", "provider_reported"}


def is_executable(model: ModelMetadata) -> bool:
    return model.entry_type == "inference_model" and bool(model.adapter_compatible)


def estimate_request_cost(model: ModelMetadata, input_tokens: int, output_tokens: int) -> Optional[float]:
    """USD for one request from published per-million prices; None when either price is unknown."""
    if model.input_price_per_million is None or model.output_price_per_million is None:
        return None
    return (input_tokens * model.input_price_per_million + output_tokens * model.output_price_per_million) / 1_000_000


def declared_latency_seconds(model: ModelMetadata, observed_p50: Optional[float] = None) -> Tuple[Optional[float], str]:
    if observed_p50 is not None:
        return observed_p50, "observed_p50"
    if model.avg_latency_seconds is not None and model.avg_latency_seconds > 0:
        prov = (model.metric_provenance or {}).get("latency", "estimated")
        return model.avg_latency_seconds, "registry_measured" if prov in MEASURED_LATENCY_PROVENANCE else "registry_estimate"
    return None, "unavailable"


def _tags(model: ModelMetadata) -> set:
    return {t.lower() for t in [*model.capabilities, *model.supported_tasks]}


def check_model(model: ModelMetadata, profile: QueryProfileV2, prefs: ResolvedPreferences, *, mode: str = "recommend",
                observed_latency: Optional[Dict[str, float]] = None) -> List[ExclusionRecord]:
    fails: List[ExclusionRecord] = []

    def fail(code: str, requirement: str, reason: str, permanence: str, **evidence) -> None:
        fails.append(ExclusionRecord(model_id=model.model_id, model_name=model.model_name, provider=model.provider, code=code,
                                     requirement=requirement, reason=reason, evidence=evidence, permanence=permanence))

    if not model.active:
        fail("model_inactive", "model must be active", "Model is inactive", "temporary", lifecycle=model.lifecycle_status)
    elif model.lifecycle_status in _PERMANENT_LIFECYCLE:
        fail("lifecycle_excluded", "lifecycle must allow routing", f"Model lifecycle is '{model.lifecycle_status}'", "permanent", lifecycle=model.lifecycle_status)
    if model.provider.lower() in prefs.excluded_providers:
        fail("provider_excluded_by_user", "provider not excluded", f"Provider {model.provider} is excluded by request", "temporary", provider=model.provider)
    if model.model_id in prefs.excluded_model_ids:
        fail("model_excluded_by_user", "model not excluded", "Model is excluded by request", "temporary")
    pool = next((c.value for c in prefs.hard_constraints if c.kind == "model_pool"), None)
    if pool and model.model_id not in pool:
        fail("not_in_selected_pool", "model must be in the selected pool", "Not in the model pool you selected", "temporary")
    if mode == "execute" and not is_executable(model):
        fail("not_executable", "execution needs an API model with a compatible adapter",
             "Consumer applications and entries without a compatible adapter cannot be executed by AI Compass", "permanent",
             entry_type=model.entry_type, adapter_compatible=model.adapter_compatible)

    have_mod = set(model.modalities or [model.modality])
    need_mod = set(profile.required_modalities or ["text"])
    if not need_mod <= have_mod:
        fail("modality_unsupported", "required modalities: " + ", ".join(sorted(need_mod)),
             "Missing required modality: " + ", ".join(sorted(need_mod - have_mod)), "permanent", model_modalities=sorted(have_mod))

    req_caps = list(profile.required_capabilities)
    extra = next((c.value for c in prefs.hard_constraints if c.kind == "require_capabilities"), None) or []
    req_caps += [c for c in extra if c not in req_caps]
    caps = {c.lower() for c in model.capabilities}
    missing = [c for c in req_caps if c.lower() not in caps]
    if missing:
        fail("capability_missing", "required capabilities: " + ", ".join(req_caps), f"Missing required capabilities: {missing}", "permanent",
             model_capabilities=sorted(caps))

    need = profile.tokens.total
    if model.context_window and model.context_window > 0:
        if need > model.context_window:
            fail("context_insufficient", f"context ≥ {need} tokens (estimate)", f"Context window too small ({model.context_window} < {need})", "permanent",
                 context_window=model.context_window, required_tokens=need, estimate_method=profile.tokens.method)
    elif need > 16000:
        fail("context_unverifiable", f"context ≥ {need} tokens (estimate)", "The context window is not published and this request is long, so it cannot be verified", "unknown",
             required_tokens=need)

    max_cost = next((c.value for c in prefs.hard_constraints if c.kind == "max_cost_usd_per_request"), None)
    if max_cost is not None:
        cost = estimate_request_cost(model, profile.tokens.input_tokens, profile.tokens.output_tokens)
        if cost is None:
            fail("cost_unverifiable", f"estimated cost ≤ ${max_cost}", "Cannot verify the cost constraint because pricing is unavailable", "unknown")
        elif cost > max_cost:
            fail("cost_exceeds_limit", f"estimated cost ≤ ${max_cost}", f"Estimated cost ${cost:.6f} exceeds the limit ${max_cost:.6f}", "temporary",
                 estimated_cost_usd=cost, input_tokens=profile.tokens.input_tokens, output_tokens=profile.tokens.output_tokens)

    max_lat = next((c.value for c in prefs.hard_constraints if c.kind == "max_latency_seconds"), None)
    if max_lat is not None:
        lat, basis = declared_latency_seconds(model, (observed_latency or {}).get(model.model_id))
        if lat is None:
            fail("latency_unverifiable", f"latency ≤ {max_lat}s", "Cannot verify the latency constraint because latency metadata is unavailable", "unknown")
        elif lat > max_lat:
            fail("latency_exceeds_limit", f"latency ≤ {max_lat}s", f"Latency {lat:.1f}s exceeds the limit {max_lat:.1f}s ({basis.replace('_', ' ')})", "temporary", latency_seconds=lat, basis=basis)

    if any(c.kind == "privacy_strict" for c in prefs.hard_constraints) and model.data_handling_status not in _ALLOWED_PRIVACY:
        fail("privacy_unverified", "documented restricted data handling (strict privacy)",
             "Does not have documented data-handling metadata required for strict privacy", "permanent", data_handling_status=model.data_handling_status)
    return fails


def filter_candidates(models: List[ModelMetadata], profile: QueryProfileV2, prefs: ResolvedPreferences, *, mode: str = "recommend",
                      observed_latency: Optional[Dict[str, float]] = None) -> Tuple[List[ModelMetadata], List[ExclusionRecord]]:
    passing: List[ModelMetadata] = []
    excluded: List[ExclusionRecord] = []
    for m in models:
        fails = check_model(m, profile, prefs, mode=mode, observed_latency=observed_latency)
        if fails:
            first = fails[0]
            if len(fails) > 1:
                first.evidence = {**first.evidence, "also_failed": [f.code for f in fails[1:]]}
            excluded.append(first)
        else:
            passing.append(m)
    return passing, excluded


def no_candidate_guidance(excluded: List[ExclusionRecord]) -> Dict[str, object]:
    """Explain an empty candidate set and suggest constraint changes (derived from the actual exclusions)."""
    by_code: Dict[str, int] = {}
    for e in excluded:
        by_code[e.code] = by_code.get(e.code, 0) + 1
    suggestions = {
        "cost_exceeds_limit": "Raise the maximum cost.", "cost_unverifiable": "Remove the cost limit or select models with published pricing.",
        "latency_exceeds_limit": "Raise the latency limit.", "latency_unverifiable": "Remove the latency limit; no candidate publishes latency.",
        "privacy_unverified": "Turn off strict privacy, or add models with documented data handling.",
        "capability_missing": "Remove a required capability or add a model that declares it.", "modality_unsupported": "Choose a task a configured model supports, or configure a provider that does.",
        "context_insufficient": "Shorten the input or use a larger-context model.", "not_executable": "Run in recommendation mode, or configure an API provider for this task.",
        "not_in_selected_pool": "Widen the selected model pool.", "provider_excluded_by_user": "Remove a provider exclusion.", "model_excluded_by_user": "Remove a model exclusion.",
    }
    return {"unsatisfied": by_code, "suggestions": sorted({suggestions[c] for c in by_code if c in suggestions})}
