"""Compatibility facade over ``routing_engine.filtering`` (hard constraints before scoring).

Returns the legacy ``(passing, [{"model_id", "reason"}])`` shape. ``max_cost`` is USD per request
(estimated from published prices and estimated tokens), matching the UI label.
"""
from typing import Dict, List, Optional, Tuple

from app.schemas.model import ModelMetadata
from app.schemas.query import QueryProfile
from app.services.routing_engine import filtering, preferences
from app.services.routing_engine.compat import from_legacy_profile


def filter_candidates(models: List[ModelMetadata], query_profile: QueryProfile, max_cost: Optional[float] = None, max_latency: Optional[float] = None,
                      require_capabilities: Optional[List[str]] = None, privacy_requirement: Optional[str] = None,
                      audience_kind: str = "conversational") -> Tuple[List[ModelMetadata], List[Dict[str, str]]]:
    profile = from_legacy_profile(query_profile)
    profile.audience.kind = audience_kind
    profile.audience.category = "developer_api" if audience_kind == "developer" else "conversational"
    prefs = preferences.resolve(profile, max_cost=max_cost, max_latency=max_latency, require_capabilities=require_capabilities, privacy_requirement=privacy_requirement)
    passing, excluded = filtering.filter_candidates(models, profile, prefs)
    return passing, [{"model_id": e.model_id, "reason": e.reason, "code": e.code} for e in excluded]
