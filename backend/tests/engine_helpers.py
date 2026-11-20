"""Shared fixtures for Route Query engine tests (deterministic, no network, no database)."""
import os
os.environ.setdefault("JWT_SECRET", "unit-test-only-secret-do-not-use-in-production")

from typing import Dict, List, Optional

from app.schemas.model import ModelMetadata
from app.services.routing_engine import preferences, understanding
from app.services.routing_engine.types import ResolvedPreferences


def mk(model_id: str, *, q: Optional[float] = 0.8, cost: Optional[float] = 0.5, latency: Optional[float] = 0.5, rel: Optional[float] = 0.85, risk: Optional[float] = 0.15,
       inp: Optional[float] = 1.0, out: Optional[float] = 4.0, provider: str = "Test", ctx: int = 128000, caps: Optional[List[str]] = None,
       tasks: Optional[List[str]] = None, modalities: Optional[List[str]] = None, privacy: str = "unknown", entry_type: str = "inference_model",
       prov: Optional[Dict[str, str]] = None, avg_latency: float = 2.5) -> ModelMetadata:
    return ModelMetadata(
        model_id=model_id, model_name=model_id.upper(), provider=provider, capabilities=caps if caps is not None else ["general", "coding", "reasoning"],
        supported_domains=["general"], supported_tasks=tasks if tasks is not None else ["coding", "reasoning", "qa", "analysis"],
        estimated_quality=q, estimated_cost=cost, estimated_latency=latency, reliability=rel, risk_level=risk, context_window=ctx,
        cost_per_1k_tokens=(inp or 0) / 1000, avg_latency_seconds=avg_latency, active=True, source="test", entry_type=entry_type, adapter_compatible=entry_type == "inference_model",
        modalities=modalities or ["text"], modality=(modalities or ["text"])[0], input_price_per_million=inp, output_price_per_million=out, data_handling_status=privacy,
        metric_provenance=prov or {"quality": "estimated", "cost": "estimated", "latency": "estimated", "reliability": "estimated", "risk": "estimated", "pricing": "provider_published"})


def profile(query: str = "Write a Python function that sorts a list of records.", hint: Optional[str] = None):
    return understanding.analyze(query, hint)


def prefs(p, **kw) -> ResolvedPreferences:
    return preferences.resolve(p, **kw)


# Provenance under which a registry value may take part in ranking (ER-PCR: only documented/measured evidence ranks).
MEASURED_PROV = {"quality": "benchmark", "cost": "estimated", "latency": "measured", "reliability": "measured", "risk": "estimated", "pricing": "provider_published"}
