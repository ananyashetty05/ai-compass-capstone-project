"""Preference and objective resolution.

Precedence (highest first):
 1. application security/safety constraints (e.g. credentials block execution)
 2. request-level hard constraints (cost/latency/privacy/capabilities/pool/exclusions)
 3. user-level hard restrictions (none are stored today; the slot exists)
 4. objective weights: request override, else saved profile weights, else defaults
 5. system defaults

Saved preferences are never modified here. Query-derived adjustments are bounded
(1.0-1.5x), reported individually, and applied after the base weights are chosen.
"""
import math
from typing import Any, Dict, List, Optional

from app.services.routing_engine.types import HardConstraint, QueryProfileV2, ResolvedPreferences, WeightAdjustment

DIMENSIONS = ("quality", "cost", "latency", "reliability", "risk", "preference_alignment")
DEFAULT_WEIGHTS: Dict[str, float] = {"quality": 0.30, "cost": 0.15, "latency": 0.15, "reliability": 0.20, "risk": 0.10, "preference_alignment": 0.10}


def normalize_weights(supplied: Optional[Dict[str, Any]]) -> Dict[str, float]:
    """Validate and normalise to sum 1. Negative/non-finite -> ValueError; unparsable legacy value -> default;
    no positive supplied weight -> documented defaults."""
    supplied = supplied or {}
    values: Dict[str, float] = {}
    for dim in DIMENSIONS:
        raw = supplied.get(dim, DEFAULT_WEIGHTS[dim])
        try:
            v = float(raw)
        except (TypeError, ValueError):
            v = DEFAULT_WEIGHTS[dim]
        if not math.isfinite(v) or v < 0:
            raise ValueError(f"Routing weight '{dim}' must be a finite non-negative number")
        values[dim] = v
    known = [values[d] for d in DIMENSIONS if d in supplied]
    total = sum(values.values())
    if not known or sum(known) <= 0 or total <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {d: values[d] / total for d in DIMENSIONS}


def resolve(profile: QueryProfileV2, *, saved_weights: Optional[Dict[str, Any]] = None, weight_overrides: Optional[Dict[str, Any]] = None,
            max_cost: Optional[float] = None, max_latency: Optional[float] = None, require_capabilities: Optional[List[str]] = None,
            privacy_requirement: Optional[str] = None, model_ids: Optional[List[str]] = None,
            preferred_providers: Optional[List[str]] = None, excluded_providers: Optional[List[str]] = None,
            excluded_model_ids: Optional[List[str]] = None) -> ResolvedPreferences:
    defaults_applied: List[str] = []
    warnings: List[str] = []
    if weight_overrides:
        base_src, base = "request_override", normalize_weights(weight_overrides)
    elif saved_weights:
        base_src, base = "saved_profile", normalize_weights(saved_weights)
        missing = [d for d in DIMENSIONS if d not in saved_weights]
        if missing:
            defaults_applied.append("default weight used for: " + ", ".join(missing))
    else:
        base_src, base = "system_default", dict(DEFAULT_WEIGHTS)
        defaults_applied.append("no saved or request weights; documented defaults applied")

    adjustments: List[WeightAdjustment] = []
    factors = {d: 1.0 for d in DIMENSIONS}

    def bump(dim: str, factor: float, reason: str) -> None:
        factors[dim] = min(1.5, factors[dim] * factor)
        adjustments.append(WeightAdjustment(dimension=dim, factor=factor, reason=reason))

    if profile.risk.sensitivity == "high":
        bump("risk", 1.5, "The query contains high-sensitivity content")
    elif profile.risk.sensitivity == "moderate":
        bump("risk", 1.3, "The query contains moderately sensitive content")
    kinds = {(r.kind, r.value) for r in profile.explicit_requirements}
    if ("latency", "low") in kinds:
        bump("latency", 1.25, "You asked for a fast answer")
    if ("accuracy", "high") in kinds:
        bump("quality", 1.25, "You stressed accuracy")
        bump("reliability", 1.1, "You stressed accuracy")
    if ("cost", "low") in kinds:
        bump("cost", 1.25, "You asked for low cost")
    adjusted = {d: base[d] * factors[d] for d in DIMENSIONS}
    total = sum(adjusted.values())
    weights = {d: adjusted[d] / total for d in DIMENSIONS}

    hard: List[HardConstraint] = []
    if profile.risk.execution_blocked:
        hard.append(HardConstraint(kind="execution_blocked", value=profile.risk.execution_block_reason, source="application"))
    if max_cost is not None:
        hard.append(HardConstraint(kind="max_cost_usd_per_request", value=max_cost, source="request"))
    if max_latency is not None:
        hard.append(HardConstraint(kind="max_latency_seconds", value=max_latency, source="request"))
    if require_capabilities:
        hard.append(HardConstraint(kind="require_capabilities", value=list(require_capabilities), source="request"))
    if privacy_requirement == "strict":
        hard.append(HardConstraint(kind="privacy_strict", value=True, source="request"))
    elif profile.risk.recommends_strict_privacy:
        warnings.append("The query looks sensitive. Strict privacy is recommended but not required; enable it to exclude models without documented data handling.")
    if model_ids:
        hard.append(HardConstraint(kind="model_pool", value=list(model_ids), source="request"))
    if excluded_providers:
        hard.append(HardConstraint(kind="excluded_providers", value=list(excluded_providers), source="request"))
    if excluded_model_ids:
        hard.append(HardConstraint(kind="excluded_models", value=list(excluded_model_ids), source="request"))
    if max_cost is not None and max_cost <= 0:
        raise ValueError("max_cost must be positive")
    overlap = set(p.lower() for p in (preferred_providers or [])) & set(p.lower() for p in (excluded_providers or []))
    if overlap:
        raise ValueError("A provider cannot be both preferred and excluded: " + ", ".join(sorted(overlap)))
    return ResolvedPreferences(
        weights={d: weights[d] for d in DIMENSIONS}, base_weights={d: base[d] for d in DIMENSIONS}, weight_source=base_src,
        adjustments=adjustments, hard_constraints=hard, preferred_providers=[p.lower() for p in (preferred_providers or [])],
        excluded_providers=[p.lower() for p in (excluded_providers or [])], excluded_model_ids=list(excluded_model_ids or []),
        defaults_applied=defaults_applied, warnings=warnings)
