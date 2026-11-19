"""Plain-data model of the catalogue (JSON-serialisable; the engine is a pure function over it)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from typing import Any, Optional

# ── vocabularies (kept as strings so they serialise and index cleanly) ─────────
AUTH_OFFICIAL = "official_documentation"
AUTH_DEVELOPER = "developer_repository"
AUTH_PROVIDER = "provider_reported"
AUTH_AGGREGATOR = "aggregator_reported"
AUTH_RANK = {AUTH_OFFICIAL: 0, AUTH_DEVELOPER: 1, AUTH_PROVIDER: 2, AUTH_AGGREGATOR: 3}
OFFICIAL_AUTHORITIES = {AUTH_OFFICIAL, AUTH_DEVELOPER}

V_DETECTED, V_CORROBORATED, V_OFFICIAL = "detected", "corroborated", "officially_confirmed"
V_RANK = {V_DETECTED: 0, V_CORROBORATED: 1, V_OFFICIAL: 2}

# Retention (generation) status
R_RETAINED, R_SUPERSEDED, R_UNMANAGED, R_REVIEW, R_UNVERIFIED = "retained", "superseded", "unmanaged", "pending_review", "unverified"

# Lifecycle (model)
L_DISCOVERED, L_PENDING, L_ACTIVE, L_DEPRECATED, L_SUPERSEDED, L_UNAVAILABLE, L_REJECTED = (
    "discovered", "pending_verification", "active", "deprecated", "superseded", "unavailable", "rejected")


def iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.astimezone(timezone.utc).isoformat() if dt else None


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


@dataclass
class Observation:
    """One source's statement about one offering of one model. Untrusted until merged."""
    source_id: str
    authority: str
    offering_provider: str
    offering_model_id: str
    name: str
    developer: Optional[str] = None            # slug, when the source can say
    description: Optional[str] = None
    released_at: Optional[str] = None          # ISO; semantics given by released_at_kind
    released_at_kind: str = "unknown"          # official | repository_created | listed_on_aggregator | unknown
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    input_modalities: tuple = ()
    output_modalities: tuple = ()
    capabilities: tuple = ()
    pricing: Optional[dict] = None             # {input_per_million, output_per_million, cache_read_per_million, currency}
    open_weights: Optional[bool] = None
    license: Optional[str] = None
    parameter_count: Optional[int] = None
    urls: tuple = ()                           # ({kind, url, label}, ...)
    expires_at: Optional[str] = None
    deprecated: bool = False
    curated: Optional[dict] = None             # curated routing estimates + taxonomy (seed only)
    benchmarks: Optional[dict] = None          # independent benchmark evidence {source, scale, <metric>: value}; never invented
    taxonomy: Optional[dict] = None


@dataclass
class DeveloperRecord:
    slug: str
    name: str
    homepage: Optional[str] = None
    aliases: list = field(default_factory=list)
    openrouter_prefixes: list = field(default_factory=list)
    huggingface_orgs: list = field(default_factory=list)
    official_domains: list = field(default_factory=list)
    family_includes: list = field(default_factory=list)
    release_feeds: list = field(default_factory=list)      # official RSS announcement feeds (https, on official_domains); discovery signals only
    enabled: bool = True


@dataclass
class OfferingRecord:
    offering_key: str                           # canonical_key|provider|offering_model_id
    canonical_key: str
    provider: str
    offering_model_id: str
    source_id: str
    authority: str
    pricing: Optional[dict] = None
    urls: list = field(default_factory=list)
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    expires_at: Optional[str] = None
    deprecated: bool = False
    listed: bool = True
    consecutive_missing: int = 0
    first_seen_at: Optional[str] = None
    curated: Optional[dict] = None


@dataclass
class ModelRecord:
    canonical_key: str
    developer: Optional[str]
    name: str
    family: str
    track: str
    lineage_key: str
    generation_key: Optional[str] = None
    generation_kind: str = "none"
    generation_label: Optional[str] = None
    generation_sort: list = field(default_factory=list)
    variants: list = field(default_factory=list)
    size: Optional[str] = None
    stage: Optional[str] = None
    classification_confidence: str = "low"
    description: Optional[str] = None
    capabilities: list = field(default_factory=list)
    input_modalities: list = field(default_factory=list)
    output_modalities: list = field(default_factory=list)
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    open_weights: Optional[bool] = None
    license: Optional[str] = None
    parameter_count: Optional[int] = None
    benchmarks: Optional[dict] = None
    released_at: Optional[str] = None
    released_at_kind: str = "unknown"
    verification: str = V_DETECTED
    publication: str = "unpublished"            # unpublished | published
    retention: str = R_UNVERIFIED
    retention_reason: Optional[str] = None
    lifecycle: str = L_DISCOVERED
    availability: str = "unknown"               # public | preview | deprecated | discontinued | unknown
    sources: list = field(default_factory=list)
    provenance: dict = field(default_factory=dict)   # field -> {source, authority, value_hash?}
    conflicts: list = field(default_factory=list)
    taxonomy: Optional[dict] = None
    curated: Optional[dict] = None
    first_seen_at: Optional[str] = None
    last_changed_at: Optional[str] = None
    published_at: Optional[str] = None
    superseded_at: Optional[str] = None


@dataclass
class GenerationRecord:
    generation_key: str
    lineage_key: str
    kind: str
    label: str
    sort_key: list
    first_released_at: Optional[str] = None
    verification: str = V_DETECTED
    retention: str = R_UNVERIFIED
    retention_reason: Optional[str] = None
    model_count: int = 0


@dataclass
class LineageRecord:
    lineage_key: str
    developer: Optional[str]
    family: str
    track: str
    review_reason: Optional[str] = None


@dataclass
class SourceState:
    source_id: str
    kind: str = "public_catalog"
    enabled: bool = True
    refresh_interval_minutes: int = 360
    status: str = "never_run"                   # never_run | ok | partial | failed
    last_attempt_at: Optional[str] = None
    last_success_at: Optional[str] = None
    consecutive_failures: int = 0
    last_count: int = 0
    last_error: Optional[str] = None            # safe classified text only
    etag: Optional[str] = None
    cursor: Optional[str] = None


@dataclass
class Event:
    event_type: str
    entity_type: str                            # model | offering | generation | lineage | source | catalog
    entity_key: str
    occurred_at: str
    from_state: Optional[str] = None
    to_state: Optional[str] = None
    reason: Optional[str] = None
    run_id: Optional[str] = None


@dataclass
class CatalogState:
    version: int = 0
    developers: dict = field(default_factory=dict)      # slug -> DeveloperRecord
    lineages: dict = field(default_factory=dict)
    generations: dict = field(default_factory=dict)
    models: dict = field(default_factory=dict)
    offerings: dict = field(default_factory=dict)
    sources: dict = field(default_factory=dict)
    published_at: Optional[str] = None


_TABLES: dict[str, type] = {"developers": DeveloperRecord, "lineages": LineageRecord, "generations": GenerationRecord,
                            "models": ModelRecord, "offerings": OfferingRecord, "sources": SourceState}


def _build(cls, data: dict):
    names = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in names})


def state_to_dict(s: CatalogState) -> dict[str, Any]:
    out: dict[str, Any] = {"version": s.version, "published_at": s.published_at}
    for t in _TABLES:
        out[t] = {k: asdict(v) for k, v in getattr(s, t).items()}
    return out


def state_from_dict(d: dict) -> CatalogState:
    s = CatalogState(version=d.get("version", 0), published_at=d.get("published_at"))
    for t, cls in _TABLES.items():
        setattr(s, t, {k: _build(cls, v) for k, v in (d.get(t) or {}).items()})
    return s


def record_dict(obj) -> dict:
    return asdict(obj)
