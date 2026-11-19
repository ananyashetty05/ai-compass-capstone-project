"""Recommendation category, access route and pricing class of a catalogue entry.

Two audiences, two pools:

* ``conversational`` - models the user talks to directly (an AI assistant: ChatGPT-, Claude- or
  Gemini-style models, and the consumer applications themselves).
* ``developer_api`` - models and providers you build with: inference providers (Groq), aggregators
  (OpenRouter), model hubs (Hugging Face), and specialised model types (embeddings, rerankers,
  image/speech models) from any provider.

Rules (nothing is guessed; an entry that cannot be placed is ``unclassified`` and is kept out of both
pools until it is classified):

* Category comes from the *role the provider plays* (curated in ``model_taxonomy.PROVIDER_ROLES``)
  and from the entry's own declared model type, never from a provider name appearing in a query.
* A provider API of a model developer (OpenAI, Anthropic, Google, ...) serving a chat model is
  ``conversational`` and *also* has a documented integration route, so a developer query may still
  consider it.
* Pricing class is evidence-based. Unknown stays ``unknown``; it is never presented as free.

This module is pure: it reads fields already on the entry and returns a new value object. It does not
touch scoring, so category selection happens before ranking and cannot change a score.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

CONVERSATIONAL = "conversational"
DEVELOPER = "developer"            # legacy routing tag in ``use_categories``
DEVELOPER_API = "developer_api"
UNCLASSIFIED = "unclassified"

# Providers whose role is to host, route or catalogue models made by others.
HOSTING_ROLES = {"inference_provider", "model_aggregator", "model_hub", "cloud_platform"}

ACCESS_TYPES = ("consumer_chat", "provider_api", "hosted_inference", "aggregator_api", "self_hosted", "unknown")
PRICING_CATEGORIES = ("completely_free", "free_tier_limited", "pay_as_you_go", "paid_subscription", "self_hosted_open_weight", "unknown")

PRICING_LABELS: Dict[str, str] = {
    "completely_free": "Free",
    "free_tier_limited": "Free tier with limits",
    "pay_as_you_go": "Pay-as-you-go",
    "paid_subscription": "Paid subscription",
    "self_hosted_open_weight": "Self-hosted (open weights)",
    "unknown": "Pricing not verified",
}
CATEGORY_LABELS: Dict[str, str] = {
    CONVERSATIONAL: "Conversational AI",
    DEVELOPER_API: "Developer & API",
    UNCLASSIFIED: "Unclassified",
}

_SPECIALISED_TYPES = {"embedding", "reranker", "image_generation", "video_generation", "speech", "vision", "vision_language", "base_model"}
_ROLE_ACCESS = {
    "model_developer": "provider_api", "cloud_platform": "provider_api", "inference_provider": "hosted_inference",
    "model_hub": "hosted_inference", "model_aggregator": "aggregator_api",
}


@dataclass(frozen=True)
class OfferingProfile:
    model_category: str
    access_type: str
    intended_use: List[str] = field(default_factory=list)
    integration_supported: Optional[bool] = None
    pricing_category: str = "unknown"
    free_tier_available: Optional[bool] = None
    category_basis: str = ""

    def as_dict(self) -> dict:
        return {
            "model_category": self.model_category, "access_type": self.access_type, "intended_use": list(self.intended_use),
            "integration_supported": self.integration_supported, "pricing_category": self.pricing_category,
            "free_tier_available": self.free_tier_available, "category_basis": self.category_basis,
        }


def _is_api_model(m) -> bool:
    return getattr(m, "entry_type", "inference_model") in {"inference_model", "model"}


def provider_role_of(m) -> str:
    role = getattr(m, "provider_role", None) or "unknown"
    if role != "unknown":
        return role
    from app.services.model_taxonomy import PROVIDER_ROLES  # local import: avoids a cycle with the taxonomy module
    return PROVIDER_ROLES.get((getattr(m, "provider", "") or "").lower(), "unknown")


def pricing_category_of(m) -> tuple:
    """(pricing_category, free_tier_available). Only documented facts count; None/unknown never becomes free."""
    if not _is_api_model(m):
        return "unknown", None
    fa = getattr(m, "free_access", "unknown") or "unknown"
    inp, out = getattr(m, "input_price_per_million", None), getattr(m, "output_price_per_million", None)
    if fa == "free" or (inp == 0 and out == 0):
        return "completely_free", True
    if fa == "limited_free":
        return "free_tier_limited", True
    if getattr(m, "free_download", None) is True and getattr(m, "api_available", None) is not True:
        return "self_hosted_open_weight", True
    if fa == "paid" or (inp is not None and inp > 0) or (out is not None and out > 0):
        return "pay_as_you_go", False
    return "unknown", None


def _intended_use(m, category: str) -> List[str]:
    if not _is_api_model(m):
        return ["general_assistant"]
    mt = getattr(m, "model_type", "") or ""
    caps = {c.lower() for c in [*(getattr(m, "capabilities", None) or []), *(getattr(m, "capability_tags", None) or [])]}
    use: List[str] = ["general_assistant"] if category == CONVERSATIONAL else ["project_integration"]
    if mt == "embedding":
        use += ["embedding", "rag"]
    elif mt == "reranker":
        use += ["rag", "specialized"]
    elif mt in _SPECIALISED_TYPES:
        use += ["specialized"]
    if mt == "code_chat" or {"coding", "code"} & caps:
        use.append("coding")
    if mt == "reasoning_chat" or "reasoning" in caps:
        use.append("reasoning")
    if {"image_understanding", "vision_input", "audio_input"} & caps or mt in {"vision", "vision_language"}:
        use.append("multimodal")
    if "tool_calling" in caps or "tool-calling" in caps:
        use.append("agent_development")
    seen: List[str] = []
    for u in use:
        if u not in seen:
            seen.append(u)
    return seen


def profile_of(m) -> OfferingProfile:
    """Derive the offering profile of one catalogue entry (pure; no I/O)."""
    pricing, free_tier = pricing_category_of(m)
    if not _is_api_model(m):
        return OfferingProfile(CONVERSATIONAL, "consumer_chat", ["general_assistant"], False, pricing, free_tier,
                               "AI application the user opens; it exposes no API of its own")
    role = provider_role_of(m)
    cats = set(getattr(m, "use_categories", None) or [])
    primary = getattr(m, "primary_category", "unclassified")
    mt = getattr(m, "model_type", "") or ""
    access = _ROLE_ACCESS.get(role, "unknown")
    if getattr(m, "free_download", None) is True and role == "model_hub" and getattr(m, "api_available", None) is not True:
        access = "self_hosted"

    if role in HOSTING_ROLES:
        cat, basis, integ = DEVELOPER_API, f"served through {role.replace('_', ' ')} (an API/infrastructure route, not a consumer assistant)", True
    elif primary == "developer" or mt in _SPECIALISED_TYPES or (cats and CONVERSATIONAL not in cats):
        cat, basis, integ = DEVELOPER_API, "specialised model type or developer-only use", True
    elif role == "model_developer" and (CONVERSATIONAL in cats or primary == CONVERSATIONAL):
        cat, basis = CONVERSATIONAL, "chat model offered by its developer"
        integ = True if (DEVELOPER in cats or getattr(m, "api_available", None) is True) else None
    else:
        cat, basis, integ = UNCLASSIFIED, "provider role or model type not verified; kept out of both pools until classified", None
    return OfferingProfile(cat, access, _intended_use(m, cat), integ, pricing, free_tier, basis)
