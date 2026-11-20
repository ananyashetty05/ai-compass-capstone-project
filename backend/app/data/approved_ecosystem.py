"""The approved Model Pool ("ecosystem").

This is the ONLY list the recommendation engine compares when ``POOL_SOURCE == "approved"`` (the default).
It was supplied by the project owner (7 categories, hard cap of 50 entries) and is curated by hand:

* ``category``   one primary category; ``secondary`` lists other approved categories the same product is
                 documented to serve. A product is stored once and is compared inside every category it serves.
* ``strengths``  feature tags taken from each vendor's published positioning. They are matched against features
                 the query asks for. They are NOT benchmark results and carry no numeric quality claim.
* Nothing here is generated from a provider name. Quality, speed, reliability and risk are hand-set EDITORIAL ESTIMATES
  (``RATINGS``): relative judgements, not measurements, labelled as such everywhere they are shown.

Entries describe where a product can be reached; AI Compass recommends and never calls them.
"""
from __future__ import annotations

from typing import Dict, List, NamedTuple, Optional, Tuple

from app.schemas.model import ModelMetadata

MAX_POOL_SIZE = 50

CATEGORIES: Tuple[str, ...] = ("conversational", "image", "video", "music_voice", "document_design", "api_models", "coding")
CATEGORY_LABELS: Dict[str, str] = {
    "conversational": "Conversational AI", "image": "Image generation", "video": "Video generation",
    "music_voice": "Music & voice", "document_design": "Documents, slides & design",
    "api_models": "API models & inference", "coding": "Coding",
}
# Tie-break order between categories when two score equally (specific artefact categories first, generic chat last).
CATEGORY_PRIORITY: Tuple[str, ...] = ("video", "image", "music_voice", "document_design", "coding", "api_models", "conversational")

_KIND_TO_ENTRY_TYPE = {
    "assistant": "application_integration", "coding_assistant": "application_integration", "design_tool": "application_integration",
    "app_builder": "application_integration", "image_model": "specialized_ai_tool", "video_model": "specialized_ai_tool",
    "audio_model": "specialized_ai_tool", "inference_platform": "inference_model", "model_hub": "inference_model",
}
_CATEGORY_MODALITY = {"conversational": "text", "image": "image", "video": "video", "music_voice": "audio", "document_design": "presentation", "api_models": "text", "coding": "code"}


class _E(NamedTuple):
    slug: str
    name: str
    provider: str
    category: str
    kind: str
    url: str
    description: str
    strengths: Tuple[str, ...]
    secondary: Tuple[str, ...] = ()
    caps: Tuple[str, ...] = ()
    pricing: str = "unknown"          # only set where the vendor documents a free tier / pricing model
    weights: str = "proprietary"
    api: Optional[bool] = None


_CHAT = ("reasoning", "writing", "analysis", "qa", "summarization", "coding", "education", "math", "research", "creative", "translation")

POOL: Tuple[_E, ...] = (
    # ── Conversational AI ───────────────────────────────────────────────────────────────────────────────────────
    _E("claude", "Claude", "Anthropic", "conversational", "assistant", "https://claude.ai/",
       "Anthropic's assistant: long documents, careful writing and analysis, coding help.",
       ("long-context", "writing", "analysis", "reasoning", "coding", "summarization", "document-upload"), caps=_CHAT, pricing="free_tier_limited", api=True),
    _E("chatgpt", "ChatGPT", "OpenAI", "conversational", "assistant", "https://chatgpt.com/",
       "OpenAI's general-purpose assistant: chat, reasoning, coding, files, voice and image input.",
       ("general-purpose", "reasoning", "coding", "writing", "analysis", "multimodal", "voice", "file-analysis"), caps=_CHAT + ("multimodal",), pricing="free_tier_limited", api=True),
    _E("gemini", "Gemini", "Google", "conversational", "assistant", "https://gemini.google.com/",
       "Google's assistant: multimodal input, Google Workspace integration, long context, coding help.",
       ("multimodal", "long-context", "google-workspace", "reasoning", "coding", "research", "slides", "document-generation"),
       secondary=("document_design", "coding"), caps=_CHAT + ("multimodal", "presentation", "document-generation"), pricing="free_tier_limited", api=True),
    _E("perplexity", "Perplexity", "Perplexity AI", "conversational", "assistant", "https://www.perplexity.ai/",
       "Answer engine with live web search and cited sources.",
       ("web-search", "citations", "research", "current-events", "fact-finding", "summarization"), caps=("research", "qa", "analysis", "summarization", "reasoning"), pricing="free_tier_limited", api=True),
    _E("deepseek", "DeepSeek", "DeepSeek", "conversational", "assistant", "https://chat.deepseek.com/",
       "DeepSeek's assistant: strong reasoning, maths and coding; open-weight model family.",
       ("reasoning", "math", "coding", "open-weights", "analysis"), caps=("reasoning", "math", "coding", "analysis", "qa", "writing", "research"), pricing="free_tier_limited", weights="open_weights", api=True),
    _E("grok", "Grok", "xAI", "conversational", "assistant", "https://grok.com/",
       "xAI's assistant with real-time access to posts on X.",
       ("real-time", "social-media", "current-events", "reasoning", "humor"), caps=_CHAT, pricing="free_tier_limited", api=True),
    # ── Image generation ────────────────────────────────────────────────────────────────────────────────────────
    _E("nano-banana", "Nano Banana", "Google", "image", "image_model", "https://gemini.google.com/",
       "Google's Gemini image model: prompt-based image creation and conversational image editing.",
       ("image-editing", "photorealism", "consistent-subjects", "text-prompt", "multi-image-blend"), caps=("image-generation",)),
    _E("firefly", "Adobe Firefly", "Adobe", "image", "image_model", "https://firefly.adobe.com/",
       "Adobe's generative image tool, designed for commercial use and integrated with Creative Cloud.",
       ("commercially-safe", "creative-cloud", "design-workflow", "vector", "image-editing", "text-effects"), caps=("image-generation",), pricing="free_tier_limited"),
    _E("gpt-image-1", "GPT Image 1", "OpenAI", "image", "image_model", "https://platform.openai.com/docs/models/gpt-image-1",
       "OpenAI's image model: accurate text rendering, instruction following and image editing; available by API.",
       ("text-rendering", "instruction-following", "image-editing", "api-access", "photorealism"), caps=("image-generation",), api=True),
    _E("midjourney", "Midjourney", "Midjourney", "image", "image_model", "https://www.midjourney.com/",
       "Image generator known for stylised, artistic output.",
       ("artistic", "stylised", "illustration", "concept-art", "aesthetic"), caps=("image-generation",), pricing="paid_subscription"),
    _E("dall-e-3", "DALL·E 3", "OpenAI", "image", "image_model", "https://openai.com/index/dall-e-3/",
       "OpenAI's earlier image model with strong prompt adherence.",
       ("prompt-adherence", "illustration", "text-prompt"), caps=("image-generation",), api=True),
    _E("flux", "FLUX", "Black Forest Labs", "image", "image_model", "https://bfl.ai/",
       "Black Forest Labs' image models; open-weight variants exist.",
       ("photorealism", "prompt-adherence", "open-weights", "api-access", "image-editing"), caps=("image-generation",), weights="open_weights", api=True),
    # ── Video generation ────────────────────────────────────────────────────────────────────────────────────────
    _E("sora", "Sora", "OpenAI", "video", "video_model", "https://sora.com/",
       "OpenAI's text-to-video model.",
       ("text-to-video", "cinematic", "realism", "storyboard"), caps=("video-generation",)),
    _E("runway-gen-3", "Runway Gen-3", "Runway", "video", "video_model", "https://runwayml.com/",
       "Runway's video model with creative controls for filmmakers.",
       ("text-to-video", "image-to-video", "creative-controls", "film-production", "motion-control"), caps=("video-generation",), pricing="free_tier_limited"),
    _E("kling", "Kling AI", "Kuaishou", "video", "video_model", "https://klingai.com/",
       "Kuaishou's video generator: text-to-video and image-to-video.",
       ("text-to-video", "image-to-video", "realism", "motion"), caps=("video-generation",), pricing="free_tier_limited"),
    _E("gemini-omni", "Gemini Omni / Veo", "Google", "video", "video_model", "https://deepmind.google/models/veo/",
       "Google's video generation with native audio.",
       ("text-to-video", "native-audio", "cinematic", "realism"), caps=("video-generation",)),
    _E("higgsfield", "Higgsfield AI", "Higgsfield", "video", "video_model", "https://higgsfield.ai/",
       "Video generation app focused on cinematic camera movement and social content.",
       ("camera-control", "cinematic", "social-video", "image-to-video"), caps=("video-generation",)),
    # ── Music & voice ───────────────────────────────────────────────────────────────────────────────────────────
    _E("suno", "Suno", "Suno", "music_voice", "audio_model", "https://suno.com/",
       "Generates complete songs, with vocals, from a text prompt.",
       ("music", "song", "vocals", "lyrics-to-song"), caps=("music-generation", "audio-generation"), pricing="free_tier_limited"),
    _E("elevenlabs", "ElevenLabs", "ElevenLabs", "music_voice", "audio_model", "https://elevenlabs.io/",
       "Text-to-speech, voice cloning, dubbing and speech-to-text.",
       ("voice", "text-to-speech", "voice-cloning", "multilingual", "dubbing", "narration", "transcription"), caps=("audio-generation",), pricing="free_tier_limited", api=True),
    _E("lyria", "Lyria", "Google", "music_voice", "audio_model", "https://deepmind.google/models/lyria/",
       "Google DeepMind's music generation model.",
       ("music", "instrumental", "soundtrack"), caps=("music-generation", "audio-generation"), api=True),
    _E("mureka", "Mureka.ai", "Mureka", "music_voice", "audio_model", "https://www.mureka.ai/",
       "AI music creation: songs, lyrics and instrumentals.",
       ("music", "song", "vocals", "instrumental", "lyrics-to-song"), caps=("music-generation", "audio-generation"), pricing="free_tier_limited"),
    _E("sarvam", "Sarvam AI", "Sarvam AI", "music_voice", "audio_model", "https://www.sarvam.ai/",
       "Indian-language speech and language models: text-to-speech, speech recognition and translation.",
       ("voice", "text-to-speech", "indian-languages", "multilingual", "transcription", "translation"), caps=("audio-generation",), api=True),
    _E("cartesia", "Cartesia", "Cartesia", "music_voice", "audio_model", "https://cartesia.ai/",
       "Low-latency text-to-speech for real-time voice agents.",
       ("voice", "text-to-speech", "low-latency", "voice-agents", "voice-cloning"), caps=("audio-generation",), api=True),
    _E("gpt-live", "GPT Live", "OpenAI", "music_voice", "audio_model", "https://openai.com/",
       "OpenAI's real-time voice conversation.",
       ("voice", "real-time", "conversational-voice", "voice-agents"), caps=("audio-generation",)),
    # ── Documents, slides & design ──────────────────────────────────────────────────────────────────────────────
    _E("gamma", "Gamma", "Gamma", "document_design", "design_tool", "https://gamma.app/",
       "Generates presentations, documents and simple web pages from a prompt.",
       ("slides", "presentation", "pitch-deck", "documents", "web-pages"), caps=("presentation", "document-generation"), pricing="free_tier_limited"),
    _E("lovable", "Lovable", "Lovable", "document_design", "app_builder", "https://lovable.dev/",
       "Builds web apps and landing pages from a prompt.",
       ("web-app", "landing-page", "prototype", "no-code", "website"), caps=("web-app-generation",), pricing="free_tier_limited"),
    _E("figma", "Figma", "Figma", "document_design", "design_tool", "https://www.figma.com/",
       "Collaborative interface design with AI-assisted generation.",
       ("ui-design", "prototype", "wireframe", "design-system", "collaboration", "mockup"), caps=("design",), pricing="free_tier_limited"),
    _E("canva", "Canva", "Canva", "document_design", "design_tool", "https://www.canva.com/",
       "Design suite with AI tools: presentations, social posts, documents and image generation.",
       ("slides", "presentation", "poster", "social-media", "templates", "brand-kit", "image-generation", "flyer", "document-generation"),
       secondary=("image",), caps=("presentation", "design", "document-generation", "image-generation"), pricing="free_tier_limited"),
    # ── API models & inference ──────────────────────────────────────────────────────────────────────────────────
    _E("huggingface", "Hugging Face", "Hugging Face", "api_models", "model_hub", "https://huggingface.co/models",
       "Model hub and inference providers; the largest open-model catalogue.",
       ("open-weights", "model-hub", "self-host", "fine-tuning", "embeddings", "inference-api", "datasets"), caps=("embedding", "inference-api"), pricing="free_tier_limited", weights="open_weights", api=True),
    _E("ai21", "AI21", "AI21 Labs", "api_models", "inference_platform", "https://www.ai21.com/",
       "AI21's Jamba models, served by API.",
       ("long-context", "enterprise", "inference-api", "private-deployment"), caps=("inference-api",), api=True),
    _E("openrouter", "OpenRouter", "OpenRouter", "api_models", "inference_platform", "https://openrouter.ai/",
       "One API across many providers' models, with unified billing.",
       ("multi-provider", "unified-api", "model-switching", "inference-api", "fallback-routing"), caps=("inference-api",), pricing="pay_as_you_go", api=True),
    _E("groq", "Groq", "Groq", "api_models", "inference_platform", "https://groq.com/",
       "Very fast hosted inference for open models.",
       ("low-latency", "fast-inference", "open-weights", "inference-api", "speech-to-text"), caps=("inference-api",), pricing="free_tier_limited", api=True),
    # ── Coding ──────────────────────────────────────────────────────────────────────────────────────────────────
    _E("github-copilot", "GitHub Copilot", "GitHub", "coding", "coding_assistant", "https://github.com/features/copilot",
       "Coding assistant inside editors and on GitHub: completion, chat, agents and pull-request help.",
       ("ide", "autocomplete", "pull-requests", "github", "code-review", "agent"), caps=("coding",), pricing="free_tier_limited"),
    _E("cursor", "Cursor", "Anysphere", "coding", "coding_assistant", "https://cursor.com/",
       "AI-first code editor with codebase-aware chat and agent edits.",
       ("ide", "codebase-aware", "multi-file-edit", "agent", "autocomplete", "refactor"), caps=("coding",), pricing="free_tier_limited"),
    _E("amazon-q", "Amazon Q Developer", "Amazon Web Services", "coding", "coding_assistant", "https://aws.amazon.com/q/developer/",
       "AWS's coding assistant: code generation, security scanning, and help with AWS services.",
       ("aws", "cloud", "security-scanning", "ide", "code-transformation", "autocomplete"), caps=("coding",), pricing="free_tier_limited"),
    _E("codex", "Codex", "OpenAI", "coding", "coding_assistant", "https://openai.com/codex/",
       "OpenAI's coding agent for writing, fixing and reviewing code.",
       ("agent", "autonomous-tasks", "code-review", "refactor", "debugging"), caps=("coding",), api=True),
    _E("claude-code", "Claude Code", "Anthropic", "coding", "coding_assistant", "https://www.anthropic.com/claude-code",
       "Anthropic's agentic coding tool for the terminal and IDEs.",
       ("agent", "terminal", "codebase-aware", "multi-file-edit", "refactor", "debugging", "ide"), caps=("coding",)),
)

# Editorial estimates (0-1) of how each product is generally regarded on four objectives: (quality, speed, reliability, risk).
# Risk is "lower is better" (data-handling / content / maturity exposure). These are the project's qualitative judgements from
# public positioning and general reputation. They are NOT benchmarks or measurements, are labelled "editorial estimate" wherever
# shown, carry low confidence, and are meant to be reviewed or replaced when measured data is available.
RATINGS: Dict[str, Tuple[float, float, float, float]] = {
    "claude": (.92, .75, .90, .15), "chatgpt": (.92, .80, .92, .18), "gemini": (.90, .82, .90, .18), "perplexity": (.82, .80, .85, .22),
    "deepseek": (.86, .78, .75, .35), "grok": (.80, .80, .78, .30),
    "nano-banana": (.88, .85, .85, .20), "firefly": (.82, .80, .92, .10), "gpt-image-1": (.90, .65, .88, .20),
    "midjourney": (.92, .70, .85, .25), "dall-e-3": (.80, .75, .88, .20), "flux": (.88, .80, .78, .28),
    "sora": (.90, .45, .80, .25), "runway-gen-3": (.86, .60, .85, .22), "kling": (.86, .55, .78, .30),
    "gemini-omni": (.90, .55, .85, .20), "higgsfield": (.78, .60, .72, .30),
    "suno": (.88, .70, .82, .30), "elevenlabs": (.92, .85, .92, .25), "lyria": (.82, .75, .85, .20), "mureka": (.75, .70, .72, .30),
    "sarvam": (.80, .80, .80, .22), "cartesia": (.84, .95, .85, .20), "gpt-live": (.85, .90, .85, .20),
    "gamma": (.82, .80, .85, .15), "lovable": (.80, .70, .78, .22), "figma": (.88, .85, .92, .12), "canva": (.85, .88, .92, .12),
    "huggingface": (.80, .70, .85, .20), "ai21": (.78, .75, .82, .18), "openrouter": (.82, .80, .85, .22), "groq": (.84, .97, .88, .18),
    "github-copilot": (.86, .88, .92, .15), "cursor": (.90, .85, .85, .20), "amazon-q": (.78, .80, .88, .15),
    "codex": (.88, .65, .85, .20), "claude-code": (.92, .65, .88, .18),
}

_ID_PREFIX = "eco/"


def _build(e: _E) -> ModelMetadata:
    modalities = sorted({"text", _CATEGORY_MODALITY[e.category]} | ({"image"} if "multimodal" in e.caps else set()) | ({"presentation"} if "presentation" in e.caps else set())
                        | ({"image"} if "image-generation" in e.caps else set()))
    return ModelMetadata(
        model_id=_ID_PREFIX + e.slug, model_name=e.name, provider=e.provider, developer=e.provider, model_family=e.name,
        capabilities=list(e.caps), supported_tasks=sorted({*e.caps, *e.strengths}), supported_domains=["general"],
        modality=_CATEGORY_MODALITY[e.category], modalities=modalities, entry_type=_KIND_TO_ENTRY_TYPE[e.kind],
        requires_key=False, authentication_requirement="account", availability="open_at_destination", active=True,
        source="approved_ecosystem", data_provenance="project_owner_approved_list", metadata_status="curated",
        lifecycle_status="active", routing_eligible=True, comparison_eligible=True, execution_available=False,
        inference_access_status="not_applicable", external_url=e.url, description=e.description,
        context_window=0, fallback_priority=50, weights_status=e.weights, api_available=e.api,
        pricing_category=e.pricing, free_tier_available=True if e.pricing in {"completely_free", "free_tier_limited"} else None,
        taxonomy_status="curated", classification_basis="curated", classification_reason="Approved ecosystem list (project owner); features from vendor positioning",
        estimated_quality=RATINGS[e.slug][0], estimated_latency=RATINGS[e.slug][1], reliability=RATINGS[e.slug][2], risk_level=RATINGS[e.slug][3],
        metric_provenance={"capabilities": "vendor_published", "quality": "editorial_estimate", "cost": "curated_pricing_category" if e.pricing != "unknown" else "unavailable",
                           "latency": "editorial_estimate", "reliability": "editorial_estimate", "risk": "editorial_estimate"},
        ecosystem_category=e.category, secondary_categories=list(e.secondary), product_kind=e.kind, strengths=list(e.strengths), ecosystem_approved=True,
        use_categories=[], primary_category="application" if _KIND_TO_ENTRY_TYPE[e.kind] != "inference_model" else "developer",
    )


def approved_models() -> List[ModelMetadata]:
    """Fresh copies of the approved pool (callers may mutate them)."""
    models = [_build(e) for e in POOL]
    assert len(models) <= MAX_POOL_SIZE, f"approved pool exceeds {MAX_POOL_SIZE}"
    return models


def category_counts() -> Dict[str, int]:
    """Entries per primary category (sums to the pool size) and per serving category (a product can serve several)."""
    primary: Dict[str, int] = {c: 0 for c in CATEGORIES}
    serving: Dict[str, int] = {c: 0 for c in CATEGORIES}
    for e in POOL:
        primary[e.category] += 1
        for c in {e.category, *e.secondary}:
            serving[c] += 1
    return {"primary": primary, "serving": serving, "total": len(POOL)}  # type: ignore[dict-item]


def serves(model: ModelMetadata, category: str) -> bool:
    return model.ecosystem_category == category or category in (model.secondary_categories or [])
