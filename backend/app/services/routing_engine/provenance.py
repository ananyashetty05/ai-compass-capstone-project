"""Decision provenance and reproducibility.

A routing decision is a pure function of: the query, the resolved preferences/constraints, the candidate catalogue
snapshot, the observed-evidence inputs, and the algorithm versions. ``fingerprint`` hashes exactly those inputs, so two
decisions with equal fingerprints must have identical filtering, ranking and selection (tested), and a changed
fingerprint explains *why* a repeat request may route differently (catalogue, pricing, weights or algorithm changed).

The raw query is never stored: only its SHA-256 participates in the fingerprint.
"""
import hashlib
import json
from typing import Any, Dict, Iterable, Optional

from app.schemas.model import ModelMetadata
from app.services.routing_engine.types import ENGINE_VERSION, SCORING_VERSION

_MODEL_FIELDS = (
    "model_id", "provider", "entry_type", "active", "lifecycle_status", "adapter_compatible", "capabilities", "supported_tasks", "modalities",
    "context_window", "input_price_per_million", "output_price_per_million", "avg_latency_seconds", "estimated_quality", "estimated_cost",
    "estimated_latency", "reliability", "risk_level", "data_handling_status", "model_type", "use_categories", "weights_status", "free_access",
)


def _digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")).hexdigest()


def catalogue_hash(models: Iterable[ModelMetadata]) -> str:
    """Content hash of the routing-relevant fields of every candidate (order independent)."""
    rows = sorted((m.model_dump(include=set(_MODEL_FIELDS)) for m in models), key=lambda r: (str(r.get("provider")), str(r.get("model_id"))))
    return _digest(rows)


def catalogue_info() -> Dict[str, Any]:
    """Version of the live catalogue state if one is loaded; never raises (routing must not depend on it)."""
    try:
        from app.services.catalog import registry
        st = registry.state()
        return {"version": st.version, "origin": registry.origin(), "published_at": st.published_at}
    except Exception:
        return {"version": None, "origin": "unavailable", "published_at": None}


def build(*, query: str, mode: str, task_hint: Optional[str], prefs: Any, models: Iterable[ModelMetadata], observed_latency: Dict[str, float],
          learning: Dict[str, float], pool: str) -> Dict[str, Any]:
    models = list(models)
    chash = catalogue_hash(models)
    inputs = {
        "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(), "mode": mode, "task_hint": task_hint, "pool": pool,
        "weights": prefs.weights, "constraints": [c.model_dump() for c in prefs.hard_constraints],
        "excluded_providers": sorted(prefs.excluded_providers), "excluded_model_ids": sorted(prefs.excluded_model_ids),
        "preferred_providers": sorted(getattr(prefs, "preferred_providers", []) or []),
        "catalogue_sha256": chash, "observed_latency": observed_latency, "learning": learning,
        "engine_version": ENGINE_VERSION, "scoring_version": SCORING_VERSION,
    }
    info = catalogue_info()
    return {
        "fingerprint": _digest(inputs), "engine_version": ENGINE_VERSION, "scoring_version": SCORING_VERSION,
        "catalogue": {"candidates": len(models), "content_sha256": chash, **info},
        "inputs_hashed": sorted(k for k in inputs if k != "query_sha256") + ["query_sha256"],
        "reproducibility": ("Identical fingerprint implies identical filtering, ranking and selection. A different fingerprint means the query, "
                            "constraints, weights, catalogue content, observed evidence or algorithm version differs."),
    }
