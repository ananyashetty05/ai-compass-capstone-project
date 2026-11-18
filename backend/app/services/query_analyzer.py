"""Compatibility facade over the Route Query engine's query understanding.

The keyword analyzer that lived here was replaced by ``routing_engine.understanding``. ``analyze``
still returns the legacy flat ``QueryProfile`` (used by the offline evaluation study and older
clients) as a projection of the canonical ``QueryProfileV2``.
"""
from typing import Optional

from app.schemas.query import QueryProfile
from app.services.query_hints import TASK_TYPE_HINTS  # noqa: F401  (re-exported)
from app.services.routing_engine import understanding
from app.services.routing_engine.compat import to_legacy_profile

_HINT_REQUIREMENTS = {
    "coding": (["text"], ["coding"]), "research": (["text"], ["research"]), "math": (["text"], ["math"]),
    "image-generation": (["image"], ["image-generation"]), "video-generation": (["video"], ["video-generation"]),
    "presentation": (["presentation"], ["presentation"]), "audio-generation": (["audio"], ["audio-generation"]),
    "design": (["image"], ["image-generation"]), "reasoning": (["text"], ["reasoning"]),
}


def analyze(query: str) -> QueryProfile:
    return to_legacy_profile(understanding.analyze(query))


def apply_task_type_hint(profile: QueryProfile, task_type_hint: Optional[str]) -> QueryProfile:
    if not task_type_hint:
        return profile
    hint = task_type_hint.strip().lower()
    if hint not in TASK_TYPE_HINTS:
        raise ValueError(f"Unsupported task category: {task_type_hint}")
    modalities, capabilities = _HINT_REQUIREMENTS.get(hint, (["text"], []))
    return profile.model_copy(update={"task_type": hint, "required_modalities": modalities, "required_capabilities": capabilities})
