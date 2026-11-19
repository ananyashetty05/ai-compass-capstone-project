"""Model registry facade.

API models come from the autonomous catalogue (services/catalog): discovered, verified and generation-managed, with no
static model list in code. Consumer AI applications are curated below and are always visible.
Only configured API providers enter the execution candidate pool.
AI applications (consumer tools) are always visible in the catalog
regardless of API key configuration — they are opened directly by the user.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Optional
from urllib.request import Request, urlopen
import json

from app.core.config import settings
from app.schemas.model import ModelMetadata

_ADAPTER_PROVIDERS = {"openai", "anthropic", "google", "groq", "openrouter"}

_VERIFIED = "2025-08-01T00:00:00+00:00"

def api_models() -> List[ModelMetadata]:
    """Active API models, derived from the single authoritative catalogue (never a static list)."""
    from app.services.catalog import registry
    return registry.published_models()


def _app(mid, name, provider, caps, tasks, modality, url, description, *,
         quality=0.8, cost=0.0, latency=0.3, free=True, modalities=None,
         entry_type="application_integration"):
    """AI consumer application — always visible, opened directly by the user."""
    return ModelMetadata(
        model_id=mid, model_name=name, provider=provider, model_family=name,
        capabilities=caps, supported_tasks=tasks, supported_domains=["general"],
        estimated_quality=quality, estimated_cost=cost, estimated_latency=latency,
        reliability=0.9, risk_level=0.1, context_window=0, cost_per_1k_tokens=0,
        avg_latency_seconds=0, fallback_priority=99, active=True,
        source="application_catalog", modality=modality,
        modalities=modalities or [modality],
        entry_type=entry_type, requires_key=not free,
        authentication_requirement="account" if free else "account_or_api_key",
        availability="consumer_app", data_provenance="provider_documentation_snapshot",
        metric_provenance={"capabilities": "provider_published", "quality": "estimated", "cost": "estimated", "latency": "estimated", "reliability": "estimated", "risk": "estimated"}, metadata_status="stale",
        last_verified_at=_VERIFIED, external_url=url, description=description,
    )


# AI Applications — consumer tools opened directly by the user.
# These are ALWAYS in the catalog regardless of API key configuration.
_AI_APPLICATIONS: List[ModelMetadata] = [
    # Text / Chat
    _app("app/chatgpt", "ChatGPT", "OpenAI",
         ["reasoning", "coding", "writing", "analysis", "research"],
         ["reasoning", "coding", "writing", "analysis", "summarization", "research", "qa"],
         "text", "https://chatgpt.com/",
         "OpenAI's consumer chat interface. Consumer chat interface from OpenAI; the model behind it is chosen by OpenAI.",
         quality=0.88, modalities=["text", "image"]),
    _app("app/claude", "Claude", "Anthropic",
         ["reasoning", "coding", "writing", "analysis"],
         ["reasoning", "coding", "writing", "analysis", "summarization", "qa"],
         "text", "https://claude.ai/",
         "Anthropic's consumer chat interface. Consumer chat interface from Anthropic; the model behind it is chosen by Anthropic.",
         quality=0.88, modalities=["text", "image"]),
    _app("app/gemini", "Gemini", "Google",
         ["reasoning", "coding", "writing", "analysis", "multimodal", "research"],
         ["reasoning", "coding", "writing", "analysis", "summarization", "research", "qa"],
         "text", "https://gemini.google.com/app",
         "Google's consumer AI interface. Consumer interface from Google with multimodal input; the model behind it is chosen by Google.",
         quality=0.87, modalities=["text", "image", "audio", "video"]),
    _app("app/perplexity", "Perplexity", "Perplexity AI",
         ["research", "reasoning", "analysis"],
         ["research", "summarization", "qa", "analysis"],
         "text", "https://www.perplexity.ai/",
         "AI-powered search and research assistant with real-time web access and citations.",
         quality=0.85),
    _app("app/deepseek", "DeepSeek Chat", "DeepSeek",
         ["reasoning", "coding", "math", "analysis"],
         ["reasoning", "coding", "math", "analysis", "qa"],
         "text", "https://chat.deepseek.com/",
         "DeepSeek's consumer chat interface. Excellent for reasoning and coding tasks.",
         quality=0.84),
    _app("app/grok", "Grok", "xAI",
         ["reasoning", "analysis", "writing", "research"],
         ["reasoning", "analysis", "writing", "research", "qa"],
         "text", "https://grok.com/",
         "xAI's consumer chat interface with real-time X/Twitter data access.",
         quality=0.82),
    _app("app/copilot", "Microsoft Copilot", "Microsoft",
         ["reasoning", "writing", "analysis", "coding"],
         ["reasoning", "writing", "analysis", "coding", "qa"],
         "text", "https://copilot.microsoft.com/",
         "Microsoft's AI assistant powered by OpenAI models. Integrated with Microsoft 365.",
         quality=0.83, modalities=["text", "image"]),
    _app("app/meta-ai", "Meta AI", "Meta",
         ["reasoning", "writing", "analysis"],
         ["reasoning", "writing", "analysis", "qa"],
         "text", "https://www.meta.ai/",
         "Meta's consumer AI assistant powered by Llama models.",
         quality=0.80),
    # Coding
    _app("app/cursor", "Cursor", "Anysphere",
         ["coding", "reasoning", "analysis"],
         ["coding", "debugging", "analysis"],
         "text", "https://www.cursor.com/",
         "AI-first code editor with deep codebase understanding and multi-file editing.",
         quality=0.90, free=False),
    _app("app/github-copilot", "GitHub Copilot", "GitHub",
         ["coding", "reasoning"],
         ["coding", "debugging"],
         "text", "https://github.com/features/copilot",
         "AI pair programmer integrated into VS Code, JetBrains, and other IDEs.",
         quality=0.87, free=False),
    _app("app/replit", "Replit AI", "Replit",
         ["coding", "reasoning"],
         ["coding", "debugging"],
         "text", "https://replit.com/",
         "Browser-based coding environment with AI assistance and instant deployment.",
         quality=0.80),
    # Image Generation
    _app("app/midjourney", "Midjourney", "Midjourney",
         ["image-generation"],
         ["image-generation"],
         "image", "https://www.midjourney.com/",
         "High-quality AI image generation. Best for artistic and creative images.",
         quality=0.93, free=False, entry_type="specialized_ai_tool"),
    _app("app/dalle", "DALL-E 3 (via ChatGPT)", "OpenAI",
         ["image-generation"],
         ["image-generation"],
         "image", "https://chatgpt.com/",
         "DALL-E 3 image generation accessible through ChatGPT. Excellent prompt adherence.",
         quality=0.88),
    _app("app/ideogram", "Ideogram", "Ideogram AI",
         ["image-generation"],
         ["image-generation"],
         "image", "https://ideogram.ai/",
         "AI image generation with excellent text rendering in images.",
         quality=0.87),
    _app("app/nano-banana", "Nano Banana (Gemini image generation)", "Google",
         ["image-generation", "image-editing"],
         ["image-generation", "image-editing"],
         "image", "https://gemini.google.com/app",
         "Google's Gemini image-generation experience, commonly referred to as Nano Banana. Availability and features can vary by account and region.",
         quality=0.82),
    _app("app/flux", "Flux (via Fal.ai)", "Black Forest Labs",
         ["image-generation"],
         ["image-generation"],
         "image", "https://fal.ai/models/fal-ai/flux/dev",
         "FLUX.1 open-source image generation model. High quality, fast inference.",
         quality=0.90),
    _app("app/canva-ai", "Canva AI", "Canva",
         ["image-generation", "image-editing", "presentation"],
         ["image-generation", "image-editing", "presentation"],
         "image", "https://www.canva.com/ai-image-generator/",
         "AI image generation and editing integrated into Canva's design platform.",
         quality=0.82, modalities=["image", "presentation"]),
    _app("app/adobe-firefly", "Adobe Firefly", "Adobe",
         ["image-generation", "image-editing"],
         ["image-generation", "image-editing"],
         "image", "https://firefly.adobe.com/",
         "Adobe's generative AI for images. Commercially safe, integrated with Creative Cloud.",
         quality=0.88, free=False),
    # Video Generation
    _app("app/sora", "Sora", "OpenAI",
         ["video-generation"],
         ["video-generation"],
         "video", "https://sora.com/",
         "OpenAI's video generation model. Creates realistic videos from text prompts.",
         quality=0.88, free=False),
    _app("app/runway", "Runway Gen-3", "Runway",
         ["video-generation", "image-editing"],
         ["video-generation", "image-editing"],
         "video", "https://runwayml.com/",
         "Professional AI video generation and editing. Used in film and media production.",
         quality=0.90, free=False),
    _app("app/kling", "Kling AI", "Kuaishou",
         ["video-generation"],
         ["video-generation"],
         "video", "https://klingai.com/",
         "High-quality AI video generation with realistic motion and long duration support.",
         quality=0.87),
    _app("app/hailuo", "Hailuo AI", "MiniMax",
         ["video-generation"],
         ["video-generation"],
         "video", "https://hailuoai.video/",
         "AI video generation with high visual quality and motion consistency.",
         quality=0.85),
    # Audio / Music
    _app("app/suno", "Suno", "Suno",
         ["music-generation", "audio-generation"],
         ["music-generation", "audio-generation"],
         "audio", "https://suno.com/",
         "AI music generation from text prompts. Creates full songs with vocals and instruments.",
         quality=0.88, entry_type="specialized_ai_tool"),
    _app("app/udio", "Udio", "Udio",
         ["music-generation", "audio-generation"],
         ["music-generation", "audio-generation"],
         "audio", "https://www.udio.com/",
         "AI music generation with high audio quality and style control.",
         quality=0.86),
    _app("app/elevenlabs", "ElevenLabs", "ElevenLabs",
         ["audio-generation", "voice-synthesis"],
         ["audio-generation"],
         "audio", "https://elevenlabs.io/",
         "AI voice synthesis and text-to-speech. Realistic voice cloning and generation.",
         quality=0.92, free=False),
    # Presentation
    _app("app/gamma", "Gamma", "Gamma",
         ["presentation"],
         ["presentation"],
         "presentation", "https://gamma.app/",
         "AI-powered presentation and document creation. Generates slides from text prompts.",
         quality=0.87, entry_type="specialized_ai_tool"),
    _app("app/beautiful-ai", "Beautiful.ai", "Beautiful.ai",
         ["presentation"],
         ["presentation"],
         "presentation", "https://www.beautiful.ai/",
         "AI presentation tool with smart slide design and automatic layout.",
         quality=0.82, free=False),
    _app("app/tome", "Tome", "Tome",
         ["presentation", "writing"],
         ["presentation", "writing"],
         "presentation", "https://tome.app/",
         "AI-powered storytelling and presentation tool.",
         quality=0.80),
    # Research / Document
    _app("app/notebooklm", "NotebookLM", "Google",
         ["research", "analysis", "summarization"],
         ["research", "analysis", "summarization", "qa"],
         "text", "https://notebooklm.google.com/",
         "Google's AI research assistant. Upload documents and ask questions about them.",
         quality=0.88),
    _app("app/consensus", "Consensus", "Consensus",
         ["research", "analysis"],
         ["research", "analysis", "summarization"],
         "text", "https://consensus.app/",
         "AI-powered academic research search. Finds and summarizes scientific papers.",
         quality=0.85),
    _app("app/elicit", "Elicit", "Ought",
         ["research", "analysis"],
         ["research", "analysis", "summarization"],
         "text", "https://elicit.com/",
         "AI research assistant for literature review and scientific paper analysis.",
         quality=0.84),
    # Data / Analysis
    _app("app/julius", "Julius AI", "Julius",
         ["data-analysis", "coding", "reasoning"],
         ["data-analysis", "coding", "analysis"],
         "text", "https://julius.ai/",
         "AI data analyst. Upload spreadsheets and get instant analysis, charts, and insights.",
         quality=0.86),
]


def _configured(provider: str) -> bool:
    return bool({"openai": settings.OPENAI_API_KEY, "anthropic": settings.ANTHROPIC_API_KEY, "google": settings.GEMINI_API_KEY, "groq": settings.GROQ_API_KEY, "openrouter": settings.OPENROUTER_API_KEY}.get(provider.lower()))


def _discovered_model(model_id: str, provider: str, *, source: str, now: str, context: int = 0,
                      input_price: float | None = None, output_price: float | None = None,
                      description: str | None = None) -> ModelMetadata:
    """Discovery records are informational until separately enriched/validated."""
    return ModelMetadata(
        model_id=model_id, model_name=model_id, provider=provider,
        model_family=model_id.split("/")[-1].split("-")[0].upper(), capabilities=["unknown"],
        supported_domains=[], supported_tasks=[], estimated_quality=None,
        estimated_cost=None, estimated_latency=None, reliability=None, risk_level=None,
        context_window=context, cost_per_1k_tokens=input_price / 1000 if input_price is not None else None,
        avg_latency_seconds=None, source="live_discovered", modality="text", modalities=["text"],
        entry_type="inference_model", active=False, availability="discovered_unvalidated",
        requires_key=True, provider_source=source, authentication_requirement="api_key",
        data_provenance="provider_model_list_api", last_verified_at=now,
        metric_provenance={"model_id": "provider_published", "pricing": "provider_published" if input_price is not None else "unavailable", "capabilities": "unavailable", "quality": "unavailable", "latency": "unavailable", "reliability": "unavailable", "risk": "unavailable"},
        metadata_status="incomplete", lifecycle_status="newly_discovered",
        adapter_compatible=provider.lower() in _ADAPTER_PROVIDERS,
        inference_access_status="unverified", routing_eligible=False,
        input_price_per_million=input_price, output_price_per_million=output_price,
        description=description or "Provider-discovered entry; metadata validation is required before routing eligibility.",
    )

def _status(entry: ModelMetadata) -> ModelMetadata:
    """Attach taxonomy and the *independent* access flags.

    Catalogue visibility, comparison eligibility and routing eligibility never depend on a
    credential. ``execution_available`` is the only flag that does.
    """
    from app.services import model_taxonomy
    item = model_taxonomy.classify(entry)
    configured = _configured(item.provider)
    item.user_access_configured = configured
    item.execution_available = bool(configured and item.adapter_compatible)
    item.availability = "api_configured" if configured else "configuration_required_for_inference"
    item.active = True
    item.comparison_eligible = True
    item.inference_access_status = "unverified"
    item.routing_eligible = item.lifecycle_status not in {"retired", "incompatible"}
    return item

def get_all_models() -> List[ModelMetadata]:
    """Models that can be *executed right now* (provider credential configured). Not the comparison pool."""
    disabled = {p.strip().lower() for p in settings.DISABLED_PROVIDERS.split(",") if p.strip()}
    return [_status(m) for m in api_models() if _configured(m.provider) and m.provider.lower() not in disabled]

def get_all_registry_entries() -> List[ModelMetadata]:
    """Full catalog: API models + AI applications. Applications are always active."""
    api = [_status(m) for m in api_models()]
    apps = [m.model_copy(update={"active": True, "availability": "consumer_app"}) for m in _AI_APPLICATIONS]
    for app in apps:
        app.inference_access_status = "not_applicable"
        app.routing_eligible = False
    try:
        from app.services.model_registry_store import get_current_snapshots
        live = get_current_snapshots()
    except Exception:
        # Persistence remains optional until its additive migration is applied.
        live = []
    merged = [*api, *apps]
    known = {(item.provider.lower(), item.model_id) for item in merged}
    merged.extend(item for item in live if (item.provider.lower(), item.model_id) not in known)
    return merged

def get_all_applications() -> List[ModelMetadata]:
    """AI consumer applications only — always available regardless of API keys."""
    return [m.model_copy(update={"active": True, "availability": "consumer_app"}) for m in _AI_APPLICATIONS]

def get_tool_recommendations(task_type: str, modality: str = "text") -> List[ModelMetadata]:
    """Return AI applications relevant to the given task type or modality."""
    apps = get_all_applications()
    matches = [a for a in apps if task_type in a.supported_tasks or modality in a.modalities]
    seen: set = set()
    result = []
    for a in matches:
        if a.model_id not in seen:
            seen.add(a.model_id)
            result.append(a)
    return result[:5]

def get_model_by_id(model_id: str) -> Optional[ModelMetadata]:
    return next((m for m in get_all_registry_entries() if m.model_id == model_id), None)

def get_models_sorted_by_fallback() -> List[ModelMetadata]:
    return sorted(get_all_models(), key=lambda m: m.fallback_priority)

def get_catalog_for_recommendation(task_type: str = "", modality: str = "text") -> List[ModelMetadata]:
    """Static, deterministic catalog (offline evaluation and research reproducibility)."""
    return get_catalog_with_exclusions(task_type, modality, live=False)[0]


def get_catalog_with_exclusions(task_type: str = "", modality: str = "text", live: bool = True):
    """Return (catalog, registry_exclusions).

    Catalog = ALL static API models (credentials are irrelevant to comparison) + consumer applications, adjusted by live
    registry evidence when LIVE_REGISTRY_ENABLED (never blocks on provider discovery;
    falls back to the static catalog if persistence is unavailable). ``registry_exclusions``
    explains each model the live registry removed, in the candidate filter's format.
    """
    disabled = {p.strip().lower() for p in settings.DISABLED_PROVIDERS.split(",") if p.strip()}
    # The comparison/recommendation pool is the whole catalogue. A missing credential only affects
    # execution_available (set by _status); it never removes a model from consideration.
    api = [_status(m) for m in api_models() if m.provider.lower() not in disabled]
    apps = get_all_applications()
    if task_type:
        apps = [a for a in apps if task_type in a.supported_tasks or task_type in a.capabilities]
    exclusions: list = []
    if live:
        from app.services import registry_service
        api, exclusions = registry_service.apply_live_registry(api)
    from app.services import model_taxonomy
    apps = [model_taxonomy.classify(a) for a in apps]
    return [*api, *apps], exclusions

def discover_openai_models() -> List[ModelMetadata]:
    """Fetch OpenAI's authenticated model-list API; no key means no discovery."""
    if not settings.OPENAI_API_KEY: return []
    req = Request("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"})
    with urlopen(req, timeout=10) as response: payload = json.load(response)  # nosec B310: fixed HTTPS provider endpoint
    now = datetime.now(timezone.utc).isoformat()
    return [_discovered_model(row["id"], "OpenAI", source="https://api.openai.com/v1/models", now=now) for row in payload.get("data", []) if row.get("id")]

def discover_openrouter_models() -> List[ModelMetadata]:
    """Fetch OpenRouter's catalog and retain only provider-supplied fields."""
    if not settings.OPENROUTER_API_KEY: return []
    req = Request("https://openrouter.ai/api/v1/models", headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}"})
    with urlopen(req, timeout=10) as response: payload = json.load(response)  # nosec B310: fixed HTTPS provider endpoint
    now = datetime.now(timezone.utc).isoformat()
    discovered = []
    for row in payload.get("data", []):
        pricing = row.get("pricing") or {}
        prompt_price = float(pricing.get("prompt") or 0) * 1_000_000
        completion_price = float(pricing.get("completion") or 0) * 1_000_000
        if row.get("id"):
            discovered.append(_discovered_model(row["id"], "OpenRouter", source="https://openrouter.ai/api/v1/models", now=now, context=int(row.get("context_length") or 4096), input_price=prompt_price, output_price=completion_price, description=row.get("description")))
    return discovered
