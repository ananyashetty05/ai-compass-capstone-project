"""Capability and intended-use taxonomy for the model catalogue.

Principles
----------
* Classification is by *what a model is and can do*, never by provider name alone. Providers
  such as Groq, OpenRouter, Together AI or Hugging Face host or route models; they are not
  model developers. ``developer`` and ``provider`` are therefore separate fields.
* A model can belong to several use categories. ``conversational`` = can answer ordinary
  questions directly. ``developer`` = can be integrated into an application or project through
  an API, a local download, or another documented route.
* Only curated facts are written. Anything not curated stays ``unknown`` / empty so that the
  UI and the router can say "not verified" instead of guessing. Curated values come from the
  developer's or provider's public documentation as of ``TAXONOMY_SNAPSHOT``; they should be
  re-verified before being relied on for licensing or cost decisions.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from app.schemas.model import ModelMetadata

TAXONOMY_SNAPSHOT = "2025-08-01"

CONVERSATIONAL = "conversational"
DEVELOPER = "developer"

# Provider *roles*. A provider can be several things; the dominant documented role is recorded.
PROVIDER_ROLES: Dict[str, str] = {
    "openai": "model_developer", "anthropic": "model_developer", "google": "model_developer", "mistral": "model_developer",
    "deepseek": "model_developer", "cohere": "model_developer", "ai21": "model_developer",
    "groq": "inference_provider", "together ai": "inference_provider", "fireworks ai": "inference_provider",
    "openrouter": "model_aggregator", "hugging face": "model_hub", "amazon bedrock": "cloud_platform",
}

# Hosted-inference access policy per *provider*. Per-model overrides below take precedence.
# "limited_free" = a free tier with usage limits is documented; it is not a statement that every
# model on the provider is free, and limits can change.
PROVIDER_FREE_ACCESS: Dict[str, tuple] = {
    "groq": ("limited_free", "Groq documents a rate-limited free tier; limits vary per model and change over time."),
    "google": ("limited_free", "The Gemini API documents a free tier with rate limits; availability varies by model."),
    "openai": ("paid", "OpenAI API usage is billed per token."),
    "anthropic": ("paid", "Anthropic API usage is billed per token."),
    "hugging face": ("limited_free", "Hugging Face documents a free serverless inference quota; heavier use needs a paid plan or a dedicated endpoint."),
    "openrouter": ("unknown", "OpenRouter lists some models at no charge and others per token; check the specific model page."),
}

# Consumer applications are conversational products opened by the user; they expose no API of their own.
_APP_CATS = (CONVERSATIONAL,)


def classify(model: ModelMetadata) -> ModelMetadata:
    """Return a copy of ``model`` with taxonomy fields populated. Unknown stays unknown."""
    prov = model.provider.lower()
    out = model.model_copy(deep=True)
    out.provider_role = "application" if model.entry_type != "inference_model" else PROVIDER_ROLES.get(prov, "unknown")
    if model.entry_type != "inference_model":
        out.developer = out.developer or model.provider
        out.model_type = "consumer_app"
        out.use_categories = list(_APP_CATS) if model.modality == "text" else []
        out.deployment_options = ["consumer_app"]
        out.api_available = False
        out.free_access = "unknown"
        out.taxonomy_status = "derived"
        out.primary_category, out.category_kind = "application", "consumer_app"
        out.classification_basis, out.classification_reason = "derived", "AI application opened by the user; not an API model"
        return out
    if model.taxonomy_status == "curated":
        # Facts come from the catalogue pipeline (curated documentation snapshot / verified sources), not from code.
        out.provider_role = PROVIDER_ROLES.get(prov, "unknown")
        if out.free_access == "unknown" and prov in PROVIDER_FREE_ACCESS:
            out.free_access, out.free_access_note = PROVIDER_FREE_ACCESS[prov]
        return out
    # Discovered / unknown entries: never guess. Remain unclassified until verified facts exist.
    out.taxonomy_status = "unclassified"
    out.use_categories = []
    out.model_type = "unclassified"
    out.api_available = True if model.adapter_compatible else None
    return out


def serves(model: ModelMetadata, category: str) -> bool:
    return category in (model.use_categories or [])
