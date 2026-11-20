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


MIN_QUALITY_WEIGHT = 0.18


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
            excluded_model_ids: Optional[List[str]] = None, max_input_price_per_million: Optional[float] = None,
            max_output_price_per_million: Optional[float] = None) -> ResolvedPreferences:
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

    # Two budgets: inferred adjustments are small and capped at 1.5x; explicit user wishes may go up to 2.5x. Both are reported.
    caps = {"explicit": 2.5, "inferred": 1.5}
    spent = {"explicit": {d: 1.0 for d in DIMENSIONS}, "inferred": {d: 1.0 for d in DIMENSIONS}}

    def bump(dim: str, factor: float, reason: str, origin: str = "explicit") -> None:
        lo, hi = 1 / caps[origin], caps[origin]
        new = min(hi, max(lo, spent[origin][dim] * factor))
        applied = new / spent[origin][dim]
        spent[origin][dim] = new
        factors[dim] = spent["explicit"][dim] * spent["inferred"][dim]
        if abs(applied - 1.0) > 1e-9:
            adjustments.append(WeightAdjustment(dimension=dim, factor=round(applied, 3), reason=reason, origin=origin))

    # --- inferred from the query (never from invented user wishes) ---
    if profile.risk.sensitivity == "high":
        bump("risk", 1.5, "The query contains high-sensitivity content", "inferred")
    elif profile.risk.sensitivity == "moderate":
        bump("risk", 1.3, "The query contains moderately sensitive content", "inferred")
    cx = profile.complexity.category
    if cx == "highly_complex":
        bump("quality", 1.4, "Highly complex task: answer quality matters most", "inferred")
        bump("reliability", 1.15, "Highly complex task: a failure is costly", "inferred")
        bump("cost", 0.8, "Highly complex task: cost is secondary to getting it right", "inferred")
        bump("latency", 0.85, "Highly complex task: latency is secondary", "inferred")
    elif cx == "complex":
        bump("quality", 1.25, "Complex task: answer quality matters more", "inferred")
        bump("cost", 0.9, "Complex task: cost is secondary to quality", "inferred")
    elif cx == "simple" and profile.reasoning_requirement in {"none", "light"}:
        bump("cost", 1.2, "Simple task: a capable cheaper model is enough", "inferred")
        bump("latency", 1.2, "Simple task: fast answers are valuable", "inferred")
        bump("quality", 0.9, "Simple task: marginal quality gains matter less", "inferred")
    if profile.risk.sensitivity in {"moderate", "high"} or profile.domain in {"medical", "legal", "finance"}:
        bump("reliability", 1.15, f"High-consequence content ({profile.domain if profile.domain != 'general' else 'sensitive'}): consistency matters", "inferred")

    # --- stated by the user ---
    kinds = {(r.kind, r.value) for r in profile.explicit_requirements}
    if ("latency", "lowest") in kinds:
        bump("latency", 2.0, "You asked for the fastest answer possible")
    elif ("latency", "low") in kinds:
        bump("latency", 1.4, "You asked for a fast answer")
    if ("accuracy", "highest") in kinds:
        bump("quality", 2.0, "You asked for the most accurate / highest-quality model")
        bump("reliability", 1.3, "You asked for the most accurate / highest-quality model")
    elif ("accuracy", "high") in kinds:
        bump("quality", 1.4, "You stressed accuracy")
        bump("reliability", 1.15, "You stressed accuracy")
    if ("cost", "lowest") in kinds:
        bump("cost", 2.0, "You asked for the cheapest suitable model")
    elif ("cost", "low") in kinds:
        bump("cost", 1.4, "You asked for low cost")
    adjusted = {d: base[d] * factors[d] for d in DIMENSIONS}
    total = sum(adjusted.values())
    weights = {d: adjusted[d] / total for d in DIMENSIONS}
    if weights["quality"] < MIN_QUALITY_WEIGHT:
        deficit = MIN_QUALITY_WEIGHT - weights["quality"]
        others = sum(v for d, v in weights.items() if d != "quality")
        weights = {d: (MIN_QUALITY_WEIGHT if d == "quality" else v * (1 - deficit / others)) for d, v in weights.items()}
        adjustments.append(WeightAdjustment(dimension="quality", factor=1.0, origin="inferred",
                                            reason=f"Quality keeps at least a {MIN_QUALITY_WEIGHT:.0%} share so a cost/speed wish cannot select an unsuitable model"))

    hard: List[HardConstraint] = []
    if profile.risk.execution_blocked:
        hard.append(HardConstraint(kind="execution_blocked", value=profile.risk.execution_block_reason, source="application"))
    if max_cost is not None:
        hard.append(HardConstraint(kind="max_cost_usd_per_request", value=max_cost, source="request"))
    if max_input_price_per_million is not None:
        hard.append(HardConstraint(kind="max_input_price_per_million", value=max_input_price_per_million, source="request"))
    if max_output_price_per_million is not None:
        hard.append(HardConstraint(kind="max_output_price_per_million", value=max_output_price_per_million, source="request"))
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
