"""Routing eligibility, decided independently of discovery.

Eligibility is the conjunction of explicit, individually reportable checks. A
catalog entry that is merely *listed* by a provider is never eligible on that
basis alone. Static curated entries keep their existing behaviour (configured +
adapter-compatible) unless live evidence excludes them; live-discovered entries
additionally need a fresh successful inference verification and complete
provider-published scoring metadata (no placeholder scores are ever invented).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.config import settings
from app.schemas.model import ModelMetadata

# Machine-readable exclusion codes -> human explanation shown in the API and UI.
REASONS = {
    "not_inference_model": "Consumer applications and tools are opened directly; they are not API routing candidates.",
    "provider_disabled": "The provider is disabled by deployment configuration.",
    "provider_not_configured": "No credentials are configured for this provider.",
    "adapter_incompatible": "No inference adapter supports this provider.",
    "lifecycle_excluded": "The model's lifecycle status excludes it from routing.",
    "inference_not_verified": "Inference access has not been verified for this discovered model.",
    "inference_verification_stale": "The last successful inference verification is too old.",
    "inference_verification_failed": "The latest inference verification failed.",
    "metadata_incomplete": "Provider-published scoring metadata (quality, latency, reliability, risk, pricing) is unavailable; no placeholders are used.",
}
WARNINGS = {
    "deprecated": "Provider reports this model as deprecated; it still works until retirement.",
    "stale_catalog": "The provider catalog has not been refreshed within the configured TTL.",
}

_LIFECYCLE_BLOCKED = {"newly_discovered", "pending_validation", "unavailable", "retired", "incompatible", "discovery_failed"}
_SCORING_FIELDS = ("estimated_quality", "estimated_cost", "estimated_latency", "reliability", "risk_level", "cost_per_1k_tokens")


@dataclass
class Verification:
    status: str  # validated | failed
    verified_at: datetime
    error_code: Optional[str] = None


@dataclass
class Eligibility:
    eligible: bool
    reasons: list[str] = field(default_factory=list)   # exclusion codes
    warnings: list[str] = field(default_factory=list)

    def explain(self) -> list[dict]:
        return [{"code": c, "message": REASONS.get(c, c)} for c in self.reasons]


def provider_configured(provider: str) -> bool:
    from app.services.model_registry import _configured
    return _configured(provider)


def provider_disabled(provider: str) -> bool:
    return provider.lower() in {p.strip().lower() for p in settings.DISABLED_PROVIDERS.split(",") if p.strip()}


def is_live_only(model: ModelMetadata) -> bool:
    return model.source == "live_discovered"


def evaluate(model: ModelMetadata, *, verification: Optional[Verification] = None,
             catalog_stale: bool = False, now: Optional[datetime] = None) -> Eligibility:
    now = now or datetime.now(timezone.utc)
    reasons: list[str] = []
    warnings: list[str] = []
    if model.entry_type != "inference_model":
        return Eligibility(False, ["not_inference_model"])
    if provider_disabled(model.provider):
        reasons.append("provider_disabled")
    if not provider_configured(model.provider):
        reasons.append("provider_not_configured")
    if not model.adapter_compatible:
        reasons.append("adapter_incompatible")
    if model.lifecycle_status in _LIFECYCLE_BLOCKED:
        # Static curated rows are "active"; live rows must have progressed to "active" themselves.
        reasons.append("lifecycle_excluded")
    if model.lifecycle_status == "deprecated":
        warnings.append("deprecated")
    if verification is not None and verification.status == "failed" and verification.error_code in {"invalid_model", "authentication"}:
        reasons.append("inference_verification_failed")
    if is_live_only(model):
        if verification is None or verification.status != "validated":
            if "inference_verification_failed" not in reasons:
                reasons.append("inference_not_verified")
        elif now - verification.verified_at > timedelta(days=settings.REGISTRY_VERIFICATION_MAX_AGE_DAYS):
            reasons.append("inference_verification_stale")
        if any(getattr(model, name) is None for name in _SCORING_FIELDS):
            reasons.append("metadata_incomplete")
    if model.source == "catalog" and model.taxonomy_status == "unclassified" and (model.cost_per_1k_tokens is None or not model.context_window):
        # Catalogue-discovered models may lack benchmark scores (the router treats unknown pessimistically), but they need
        # at least a published price and context window to be compared fairly.
        reasons.append("metadata_incomplete")
    if catalog_stale:
        warnings.append("stale_catalog")
    return Eligibility(not reasons, reasons, warnings)
