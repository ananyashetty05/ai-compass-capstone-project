"""Primary-category classification for catalogue entries.

One decision per entry, taken from structured evidence only (declared output/input modalities, the
serving route, curated taxonomy, name tokens that the developer itself uses). It never uses the
hosting provider's name as evidence.

* ``primary_category`` is MUTUALLY EXCLUSIVE: conversational | developer | application | unclassified.
  Category totals are therefore additive and reconcile with the active total.
* ``capability_tags`` OVERLAP (a chat model can also code and see images). They are counted
  separately and must never be summed into a total.
* ``use_categories`` (routing audience tags, overlapping) are derived from the primary category so the
  Model Pool, Model Inspect and the router read one decision.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

CONVERSATIONAL, DEVELOPER, APPLICATION, UNCLASSIFIED = "conversational", "developer", "application", "unclassified"
PRIMARY_CATEGORIES = (CONVERSATIONAL, DEVELOPER, APPLICATION, UNCLASSIFIED)

# kind -> routing model_type (kept compatible with the router's existing values)
KIND_TO_MODEL_TYPE = {
    "chat": "chat", "reasoning_chat": "reasoning_chat", "multimodal_chat": "chat", "code_chat": "code_chat",
    "embedding": "embedding", "reranker": "reranker", "image_generation": "image_generation", "video_generation": "video_generation",
    "speech": "speech", "vision": "vision", "vision_language": "vision_language", "code": "code_chat", "base_model": "base_model",
    "consumer_app": "consumer_app", "unclassified": "unclassified",
}
KIND_LABELS = {
    "chat": "Chat", "reasoning_chat": "Reasoning chat", "multimodal_chat": "Multimodal chat", "code_chat": "Code chat",
    "embedding": "Embedding", "reranker": "Reranker", "image_generation": "Image generation", "video_generation": "Video generation",
    "speech": "Speech & audio", "vision": "Vision", "vision_language": "Vision-language", "code": "Code",
    "base_model": "Base model", "consumer_app": "Application", "unclassified": "Unclassified",
}

_CHAT_KINDS = {"chat", "reasoning_chat", "multimodal_chat", "code_chat"}
_TOK = lambda s: re.split(r"[^a-z0-9]+", s.lower())                                              # noqa: E731
_RERANK = re.compile(r"rerank", re.I)
_EMBED = re.compile(r"(?:^|[^a-z])(embed|embedding|embeddings|bge|gte|e5|clip|siglip|minilm)(?:[^a-z]|$)", re.I)
_CODE = re.compile(r"(?:^|[^a-z])(coder|codex|code|codellama|codestral|devstral|starcoder)(?:[^a-z]|$)", re.I)
_SPEECH = re.compile(r"(?:^|[^a-z])(whisper|asr|tts|speech|voice|wav2vec)(?:[^a-z]|$)", re.I)
_INSTRUCT = re.compile(r"(?:^|[^a-z])(instruct|chat|it|sft|dpo|rlhf|assistant|command|r1)(?:[^a-z]|$)", re.I)


@dataclass
class Classification:
    primary_category: str
    kind: str
    basis: str                      # curated | derived | unverified
    reason: str
    use_categories: list = field(default_factory=list)
    capability_tags: list = field(default_factory=list)

    @property
    def model_type(self) -> str:
        return KIND_TO_MODEL_TYPE.get(self.kind, "unclassified")


def capability_tags(caps: Iterable[str], in_m: Iterable[str], out_m: Iterable[str], name: str, open_weights: Optional[bool], kind: str) -> list:
    caps, in_m, out_m = set(caps or ()), set(in_m or ()), set(out_m or ())
    tags = set()
    if kind in _CHAT_KINDS:
        tags.add("chat")
    if "reasoning" in caps or kind == "reasoning_chat":
        tags.add("reasoning")
    if kind in {"code", "code_chat"} or _CODE.search(name) or "code" in caps or "coding" in caps:
        tags.add("coding")
    if "image" in in_m or "image_understanding" in caps:
        tags.add("vision_input")
    if "audio" in in_m or "audio_input" in caps:
        tags.add("audio_input")
    if "video" in in_m:
        tags.add("video_input")
    if "image" in out_m:
        tags.add("image_generation")
    if "video" in out_m:
        tags.add("video_generation")
    if "audio" in out_m or kind == "speech":
        tags.add("speech")
    if "embeddings" in out_m or kind == "embedding":
        tags.add("embedding")
    if "tool_calling" in caps:
        tags.add("tool_calling")
    if "structured_output" in caps:
        tags.add("structured_output")
    if open_weights is True:
        tags.add("open_weights")
    return sorted(tags)


def _finish(primary: str, kind: str, basis: str, reason: str, *, integrable: bool, caps, in_m, out_m, name: str, open_weights) -> Classification:
    # Routing audience tags overlap by design: an integrable chat model serves both audiences, a specialised model only developers.
    if primary == CONVERSATIONAL:
        uc = [CONVERSATIONAL] + ([DEVELOPER] if integrable else [])
    elif primary == DEVELOPER:
        uc = [DEVELOPER]
    elif primary == APPLICATION:
        uc = [CONVERSATIONAL] if kind == "consumer_app" and "text" in set(in_m or ("text",)) else []
    else:
        uc = []
    return Classification(primary, kind, basis, reason, uc, capability_tags(caps, in_m, out_m, name, open_weights, kind))


def classify(*, name: str, offering_ids: Iterable[str], in_m: Iterable[str], out_m: Iterable[str], caps: Iterable[str], sources: Iterable[str],
             open_weights: Optional[bool], entry_type: str = "inference_model", curated_type: Optional[str] = None,
             curated_categories: Optional[Iterable[str]] = None) -> Classification:
    in_m, out_m, caps, sources = tuple(in_m or ()), tuple(out_m or ()), tuple(caps or ()), set(sources or ())
    ids = " ".join(offering_ids or ())
    label = f"{name} {ids}"
    args = dict(caps=caps, in_m=in_m, out_m=out_m, name=label, open_weights=open_weights)

    if entry_type != "inference_model":
        return _finish(APPLICATION, "consumer_app", "derived", "AI application opened by the user; not an API model", integrable=False, **args)

    cats = set(curated_categories or ())
    if curated_type and curated_type != "unclassified" and cats:
        kind = {"chat": "chat", "reasoning_chat": "reasoning_chat", "code_chat": "code_chat"}.get(curated_type, curated_type)
        kind = kind if kind in KIND_LABELS else "unclassified"
        if kind in _CHAT_KINDS and "conversational" in cats:
            return _finish(CONVERSATIONAL, kind, "curated", "curated from provider documentation", integrable="developer" in cats, **args)
        return _finish(DEVELOPER, kind, "curated", "curated from provider documentation", integrable=True, **args)

    # ── specialised model types, decided by declared modalities first ──
    if _RERANK.search(label):
        return _finish(DEVELOPER, "reranker", "derived", "name identifies a reranker", integrable=True, **args)
    if "embeddings" in out_m:
        return _finish(DEVELOPER, "embedding", "derived", "declared output is embeddings", integrable=True, **args)
    if "image" in out_m:
        return _finish(DEVELOPER, "image_generation", "derived", "declared output includes images", integrable=True, **args)
    if "video" in out_m:
        return _finish(DEVELOPER, "video_generation", "derived", "declared output includes video", integrable=True, **args)
    if "audio" in out_m or (set(in_m) == {"audio"}) or _SPEECH.search(label):
        return _finish(DEVELOPER, "speech", "derived", "speech or audio model (declared modalities)", integrable=True, **args)
    if _EMBED.search(label) and "text" not in out_m:
        return _finish(DEVELOPER, "embedding", "derived", "name identifies an embedding model", integrable=True, **args)
    if set(in_m) == {"image"} and "text" in out_m:
        return _finish(DEVELOPER, "vision", "derived", "image-to-text model (declared modalities)", integrable=True, **args)
    if _CODE.search(label):
        return _finish(DEVELOPER, "code", "derived", "coding-specialised model (named by its developer)", integrable=True, **args)

    if "text" in out_m:
        multimodal = bool({"image", "audio", "video", "file"} & set(in_m))
        kind = "reasoning_chat" if "reasoning" in caps else ("multimodal_chat" if multimodal else "chat")
        if "openrouter" in sources:
            return _finish(CONVERSATIONAL, kind, "derived", "served as a chat-completions model (tools/parameters declared by the aggregator)", integrable=True, **args)
        if _INSTRUCT.search(name):
            return _finish(CONVERSATIONAL, kind, "derived", "instruction-tuned release (named instruct/chat/it by its developer)", integrable=bool(open_weights), **args)
        if multimodal:
            return _finish(DEVELOPER, "vision_language", "derived", "vision-language weights without chat tuning in the name", integrable=True, **args)
        return _finish(DEVELOPER, "base_model", "derived", "text weights without instruction tuning in the name: base model for fine-tuning or integration", integrable=True, **args)

    return _finish(UNCLASSIFIED, "unclassified", "unverified", "no verified output modality or task for this entry", integrable=False, **args)
