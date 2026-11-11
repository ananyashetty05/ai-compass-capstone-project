"""Verified catalog snapshots plus explicit provider discovery.

Static rows are documentation snapshots, not claims of live availability.
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

_VERIFIED = "2025-08-01T00:00:00+00:00"

def _model(mid, name, provider, family, caps, tasks, modalities=("text",), *, context=128000,
           quality=.75, cost=.5, latency=.5, input_price=None, output_price=None, description="", source=""):
    return ModelMetadata(
        model_id=mid, model_name=name, provider=provider, model_family=family,
        capabilities=["general", *caps], supported_domains=["general", "computer_science", "mathematics", "science", "creative"],
        supported_tasks=[*tasks, "qa"], modality=modalities[0], modalities=list(modalities),
        estimated_quality=quality, estimated_cost=cost, estimated_latency=latency, reliability=.85, risk_level=.15,
        context_window=context, cost_per_1k_tokens=(input_price or 0) / 1000, avg_latency_seconds=2.5, fallback_priority=5,
        active=True, source="static_verified_catalog", entry_type="inference_model", requires_key=True,
        availability="unknown", provider_source=source, authentication_requirement="api_key",
        data_provenance="provider_documentation_snapshot", last_verified_at=_VERIFIED,
        input_price_per_million=input_price, output_price_per_million=output_price,
        external_url=source or None, description=description,
    )

_API_MODELS: List[ModelMetadata] = [
    _model("gpt-4.1", "GPT-4.1", "OpenAI", "GPT-4.1", ["reasoning", "coding", "analysis", "writing"], ["reasoning", "coding", "analysis", "summarization", "writing", "math"], context=1_000_000, quality=.86, cost=.72, latency=.58, input_price=2, output_price=8, description="Long-context text and vision API model.", source="https://platform.openai.com/docs/models"),
    _model("gpt-4.1-mini", "GPT-4.1 mini", "OpenAI", "GPT-4.1", ["coding", "analysis", "writing"], ["coding", "analysis", "summarization", "writing"], context=1_000_000, quality=.74, cost=.2, latency=.2, input_price=.4, output_price=1.6, description="Lower-cost GPT-4.1 API variant.", source="https://platform.openai.com/docs/models"),
    _model("o3", "o3", "OpenAI", "o-series", ["reasoning", "coding", "math"], ["reasoning", "coding", "math", "analysis"], quality=.9, cost=.88, latency=.75, input_price=2, output_price=8, description="Reasoning-focused API model.", source="https://platform.openai.com/docs/models"),
    _model("gpt-image-1", "GPT Image 1", "OpenAI", "GPT Image", ["image-generation", "image-editing"], ["image-generation"], ("image",), context=0, quality=.82, cost=.7, latency=.65, description="Image generation and editing API model.", source="https://platform.openai.com/docs/guides/image-generation"),
    _model("claude-opus-4-20250514", "Claude Opus 4", "Anthropic", "Claude 4", ["reasoning", "coding", "analysis", "writing"], ["reasoning", "coding", "analysis", "summarization", "writing"], context=200000, quality=.9, cost=.9, latency=.75, input_price=15, output_price=75, description="High-capability Claude API model.", source="https://docs.anthropic.com/en/docs/about-claude/models"),
    _model("claude-sonnet-4-20250514", "Claude Sonnet 4", "Anthropic", "Claude 4", ["reasoning", "coding", "analysis", "writing"], ["reasoning", "coding", "analysis", "summarization", "writing"], context=200000, quality=.84, cost=.55, latency=.55, input_price=3, output_price=15, description="Balanced Claude API model.", source="https://docs.anthropic.com/en/docs/about-claude/models"),
    _model("claude-3-5-haiku-20241022", "Claude 3.5 Haiku", "Anthropic", "Claude 3.5", ["analysis", "writing"], ["analysis", "summarization", "writing"], context=200000, quality=.7, cost=.15, latency=.18, input_price=.8, output_price=4, description="Fast Claude API model.", source="https://docs.anthropic.com/en/docs/about-claude/models"),
    _model("gemini-2.5-pro", "Gemini 2.5 Pro", "Google", "Gemini 2.5", ["reasoning", "coding", "analysis", "multimodal"], ["reasoning", "coding", "analysis", "summarization", "math"], ("text", "image", "audio", "video"), context=1_000_000, quality=.87, cost=.7, latency=.6, description="Multimodal Gemini API model.", source="https://ai.google.dev/gemini-api/docs/models"),
    _model("gemini-2.5-flash", "Gemini 2.5 Flash", "Google", "Gemini 2.5", ["coding", "analysis", "multimodal"], ["coding", "analysis", "summarization"], ("text", "image", "audio", "video"), context=1_000_000, quality=.78, cost=.25, latency=.2, description="Fast multimodal Gemini API model.", source="https://ai.google.dev/gemini-api/docs/models"),
    _model("gemini-2.5-flash-lite", "Gemini 2.5 Flash-Lite", "Google", "Gemini 2.5", ["analysis", "multimodal"], ["analysis", "summarization"], ("text", "image"), context=1_000_000, quality=.66, cost=.1, latency=.12, description="Low-cost Gemini API model.", source="https://ai.google.dev/gemini-api/docs/models"),
    _model("llama-3.3-70b-versatile", "Llama 3.3 70B Versatile", "Groq", "Llama 3.3", ["reasoning", "coding", "analysis"], ["reasoning", "coding", "analysis", "summarization"], quality=.76, cost=.2, latency=.1, description="Llama hosted by Groq.", source="https://console.groq.com/docs/models"),
    _model("deepseek-r1-distill-llama-70b", "DeepSeek R1 Distill Llama 70B", "Groq", "DeepSeek R1", ["reasoning", "math", "coding"], ["reasoning", "math", "coding"], quality=.78, cost=.25, latency=.18, description="Reasoning model hosted by Groq.", source="https://console.groq.com/docs/models"),
    _model("mistral-large-latest", "Mistral Large", "Mistral", "Mistral Large", ["reasoning", "coding", "analysis"], ["reasoning", "coding", "analysis", "summarization"], quality=.8, cost=.55, latency=.45, description="Mistral API model.", source="https://docs.mistral.ai/getting-started/models/"),
    _model("deepseek-chat", "DeepSeek-V3", "DeepSeek", "DeepSeek V3", ["reasoning", "coding", "analysis"], ["reasoning", "coding", "analysis", "summarization"], context=64000, quality=.78, cost=.25, latency=.4, description="DeepSeek API chat model.", source="https://api-docs.deepseek.com/"),
    _model("deepseek-reasoner", "DeepSeek-R1", "DeepSeek", "DeepSeek R1", ["reasoning", "math", "coding"], ["reasoning", "math", "coding", "analysis"], context=64000, quality=.82, cost=.5, latency=.6, description="DeepSeek API reasoning model.", source="https://api-docs.deepseek.com/"),
    _model("meta-llama/llama-3.3-70b-instruct", "Llama 3.3 70B Instruct", "Together AI", "Llama 3.3", ["reasoning", "coding", "analysis"], ["reasoning", "coding", "analysis", "summarization"], quality=.76, cost=.28, latency=.35, description="Meta Llama hosted inference endpoint.", source="https://docs.together.ai/docs/inference-models"),
    _model("Qwen/Qwen2.5-72B-Instruct", "Qwen2.5 72B Instruct", "Together AI", "Qwen 2.5", ["reasoning", "coding", "math"], ["reasoning", "coding", "math", "analysis"], quality=.76, cost=.27, latency=.35, description="Qwen hosted inference endpoint.", source="https://docs.together.ai/docs/inference-models"),
    _model("microsoft/phi-4", "Phi-4", "Hugging Face", "Phi", ["reasoning", "math", "analysis"], ["reasoning", "math", "analysis"], quality=.7, cost=.25, latency=.35, description="Microsoft Phi family via hosted inference.", source="https://huggingface.co/microsoft/phi-4"),
    _model("command-a-03-2025", "Command A", "Cohere", "Command", ["reasoning", "coding", "retrieval"], ["reasoning", "coding", "analysis", "summarization"], quality=.76, cost=.4, latency=.4, description="Cohere enterprise API model.", source="https://docs.cohere.com/docs/models"),
    _model("amazon.nova-pro-v1:0", "Amazon Nova Pro", "Amazon Bedrock", "Nova", ["reasoning", "analysis", "multimodal"], ["reasoning", "analysis", "summarization"], ("text", "image", "video"), quality=.77, cost=.45, latency=.45, description="Amazon Bedrock Nova API model.", source="https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html"),
    _model("jamba-1.5-large", "Jamba 1.5 Large", "AI21", "Jamba", ["reasoning", "analysis", "long-context"], ["reasoning", "analysis", "summarization"], context=256000, quality=.73, cost=.45, latency=.45, description="AI21 API model.", source="https://docs.ai21.com/"),
    _model("accounts/fireworks/models/llama-v3p3-70b-instruct", "Llama 3.3 70B Instruct", "Fireworks AI", "Llama 3.3", ["reasoning", "coding", "analysis"], ["reasoning", "coding", "analysis"], quality=.76, cost=.25, latency=.25, description="Fireworks hosted inference model.", source="https://fireworks.ai/models"),
    _model("deepseek/deepseek-r1", "DeepSeek R1", "OpenRouter", "DeepSeek R1", ["reasoning", "math", "coding"], ["reasoning", "math", "coding", "analysis"], quality=.82, cost=.5, latency=.55, description="Gateway-hosted DeepSeek reasoning model.", source="https://openrouter.ai/docs/models"),
]


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
         "OpenAI's consumer chat interface. Supports GPT-4o and o-series models.",
         quality=0.88, modalities=["text", "image"]),
    _app("app/claude", "Claude", "Anthropic",
         ["reasoning", "coding", "writing", "analysis"],
         ["reasoning", "coding", "writing", "analysis", "summarization", "qa"],
         "text", "https://claude.ai/",
         "Anthropic's consumer chat interface. Supports Claude 3.5 and Claude 4 models.",
         quality=0.88, modalities=["text", "image"]),
    _app("app/gemini", "Gemini", "Google",
         ["reasoning", "coding", "writing", "analysis", "multimodal", "research"],
         ["reasoning", "coding", "writing", "analysis", "summarization", "research", "qa"],
         "text", "https://gemini.google.com/app",
         "Google's consumer AI interface. Supports Gemini 2.5 Pro with multimodal input.",
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
         "Microsoft's AI assistant powered by GPT-4. Integrated with Microsoft 365.",
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

def _status(entry: ModelMetadata) -> ModelMetadata:
    item = entry.model_copy(deep=True)
    # Registry presence means the entry can be evaluated and recommended.
    # API configuration is deliberately separate: no key must never hide a
    # valid recommendation candidate or make it appear unavailable.
    item.availability = "api_configured" if _configured(item.provider) else "configuration_required_for_inference"
    item.active = True
    return item

def get_all_models() -> List[ModelMetadata]:
    """API-callable models only (requires configured provider keys)."""
    disabled = {p.strip().lower() for p in settings.DISABLED_PROVIDERS.split(",") if p.strip()}
    return [_status(m) for m in _API_MODELS if _configured(m.provider) and m.provider.lower() not in disabled]

def get_all_registry_entries() -> List[ModelMetadata]:
    """Full catalog: API models + AI applications. Applications are always active."""
    api = [_status(m) for m in _API_MODELS]
    apps = [m.model_copy(update={"active": True, "availability": "consumer_app"}) for m in _AI_APPLICATIONS]
    return [*api, *apps]

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
    """Return all catalog entries suitable for recommendation display.
    Includes both API models (with availability status) and AI applications.
    """
    # A catalog recommendation is independent of execution credentials. The
    # separate availability field tells the UI whether this deployment can
    # invoke the API; it must not suppress a documented candidate.
    api = [m.model_copy(update={"active": True, "availability": "configured" if _configured(m.provider) else "unknown"}) for m in _API_MODELS]
    apps = get_all_applications()
    if task_type:
        apps = [a for a in apps if task_type in a.supported_tasks or task_type in a.capabilities]
    return [*api, *apps]

def discover_openai_models() -> List[ModelMetadata]:
    """Fetch OpenAI's authenticated model-list API; no key means no discovery."""
    if not settings.OPENAI_API_KEY: return []
    req = Request("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"})
    with urlopen(req, timeout=10) as response: payload = json.load(response)  # nosec B310: fixed HTTPS provider endpoint
    now = datetime.now(timezone.utc).isoformat()
    return [ModelMetadata(model_id=row["id"], model_name=row["id"], provider="OpenAI", model_family=row["id"].split("-")[0].upper(), capabilities=["unknown"], supported_domains=["general"], supported_tasks=["qa"], estimated_quality=.5, estimated_cost=.5, estimated_latency=.5, reliability=.5, risk_level=.5, source="live_discovered", modality="text", modalities=["text"], entry_type="model", active=True, availability="configured", requires_key=True, provider_source="https://api.openai.com/v1/models", authentication_requirement="api_key", data_provenance="provider_model_list_api", last_verified_at=now, description="Live catalog entry; capability and price metadata await enrichment.") for row in payload.get("data", [])]

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
        discovered.append(ModelMetadata(model_id=row["id"], model_name=row.get("name") or row["id"], provider="OpenRouter", model_family=(row.get("id") or "unknown").split("/")[0], capabilities=["unknown"], supported_domains=["general"], supported_tasks=["qa"], estimated_quality=.5, estimated_cost=.5, estimated_latency=.5, reliability=.5, risk_level=.5, context_window=int(row.get("context_length") or 4096), cost_per_1k_tokens=prompt_price / 1000, avg_latency_seconds=0, source="live_discovered", modality="text", modalities=["text"], entry_type="model", active=True, availability="configured", requires_key=True, provider_source="https://openrouter.ai/api/v1/models", authentication_requirement="api_key", data_provenance="provider_model_list_api", last_verified_at=now, input_price_per_million=prompt_price, output_price_per_million=completion_price, description=row.get("description")))
    return discovered
