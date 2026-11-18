"""Model lifecycle states and the transitions the live registry may make.

A transition always carries a *reason*. Nothing here decides routing eligibility;
see registry_eligibility.py. A higher version number never retires an older model:
only provider-reported lifecycle data or repeated absence from a successful
provider list moves a model out of service.
"""
from __future__ import annotations

NEWLY_DISCOVERED = "newly_discovered"
PENDING_VALIDATION = "pending_validation"
ACTIVE = "active"
DEPRECATED = "deprecated"
UNAVAILABLE = "unavailable"
RETIRED = "retired"
INCOMPATIBLE = "incompatible"
DISCOVERY_FAILED = "discovery_failed"  # kept for schema compatibility; set on provider-level failure displays only

STATES = (NEWLY_DISCOVERED, PENDING_VALIDATION, ACTIVE, DEPRECATED, UNAVAILABLE, RETIRED, INCOMPATIBLE, DISCOVERY_FAILED)

# (from_state or None for first sighting) -> allowed next states
_ALLOWED: dict[str | None, set[str]] = {
    None: {NEWLY_DISCOVERED, PENDING_VALIDATION, INCOMPATIBLE, ACTIVE, DEPRECATED, RETIRED},
    NEWLY_DISCOVERED: {PENDING_VALIDATION, INCOMPATIBLE, DEPRECATED, UNAVAILABLE, RETIRED, ACTIVE},
    PENDING_VALIDATION: {ACTIVE, INCOMPATIBLE, DEPRECATED, UNAVAILABLE, RETIRED},
    ACTIVE: {DEPRECATED, UNAVAILABLE, RETIRED, INCOMPATIBLE, PENDING_VALIDATION},
    DEPRECATED: {ACTIVE, UNAVAILABLE, RETIRED, PENDING_VALIDATION},
    UNAVAILABLE: {PENDING_VALIDATION, ACTIVE, RETIRED, DEPRECATED},
    RETIRED: {PENDING_VALIDATION, ACTIVE},  # only if the provider lists it again as live
    INCOMPATIBLE: {PENDING_VALIDATION, NEWLY_DISCOVERED},  # an adapter was added later
    DISCOVERY_FAILED: set(STATES) - {DISCOVERY_FAILED},
}


def can_transition(previous: str | None, new: str) -> bool:
    return previous == new or new in _ALLOWED.get(previous, set())


def initial_status(*, adapter_compatible: bool, provider_lifecycle: str | None) -> tuple[str, str]:
    """Status and reason for a model seen for the first time."""
    if provider_lifecycle == "retired":
        return RETIRED, "Provider lists this model as retired."
    if provider_lifecycle == "deprecated":
        return DEPRECATED, "Provider lists this model as deprecated."
    if not adapter_compatible:
        return INCOMPATIBLE, "No inference adapter exists for this provider."
    return NEWLY_DISCOVERED, "First seen in a successful provider model list."


def next_status(previous: str, *, adapter_compatible: bool, provider_lifecycle: str | None,
                inference_validated: bool) -> tuple[str, str]:
    """Status for a model that the latest successful provider list still contains."""
    if provider_lifecycle == "retired":
        return RETIRED, "Provider lists this model as retired."
    if provider_lifecycle == "deprecated":
        return DEPRECATED, "Provider lists this model as deprecated."
    if not adapter_compatible:
        return INCOMPATIBLE, "No inference adapter exists for this provider."
    if previous in {UNAVAILABLE, RETIRED, INCOMPATIBLE, DEPRECATED}:
        # Returned to the provider list (or an adapter now exists); re-validate rather than trust.
        return (ACTIVE, "Listed again by the provider and inference was previously validated.") if (
            previous in {UNAVAILABLE, DEPRECATED} and inference_validated
        ) else (PENDING_VALIDATION, "Listed again by the provider; validation is required.")
    if previous == NEWLY_DISCOVERED:
        return PENDING_VALIDATION, "Adapter-compatible model awaiting metadata and inference validation."
    if previous == PENDING_VALIDATION and inference_validated:
        return ACTIVE, "Inference access verified."
    return previous, ""


def after_missing(previous: str, missing_count: int, threshold: int) -> tuple[str, str]:
    """Status after a successful provider list omitted the model."""
    if previous in {UNAVAILABLE, RETIRED}:
        return previous, ""
    if missing_count >= threshold:
        return UNAVAILABLE, f"Absent from {missing_count} consecutive successful provider lists."
    return previous, ""
