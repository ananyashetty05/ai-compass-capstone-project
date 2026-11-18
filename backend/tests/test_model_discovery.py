import os
os.environ.setdefault("JWT_SECRET", "unit-test-only-secret-do-not-use-in-production")

import io
import json
from unittest.mock import patch

from app.services import model_registry
from app.services.candidate_filter import filter_candidates
from app.services.query_analyzer import analyze


def test_discovered_record_is_inactive_until_metadata_validation():
    entry = model_registry._discovered_model(
        "provider/new-model", "OpenRouter", source="https://example.invalid/models", now="2026-01-01T00:00:00+00:00"
    )
    assert entry.lifecycle_status == "newly_discovered"
    assert entry.metadata_status == "incomplete"
    assert entry.adapter_compatible is True
    assert entry.active is False
    assert entry.routing_eligible is False
    assert entry.inference_access_status == "unverified"
    assert entry.estimated_quality is None
    assert entry.reliability is None
    candidates, filtered = filter_candidates([entry], analyze("Explain recursion"))
    assert candidates == []
    assert filtered[0]["reason"] == "Model is inactive"


def test_openai_discovery_without_credentials_is_empty():
    with patch.object(model_registry.settings, "OPENAI_API_KEY", ""):
        assert model_registry.discover_openai_models() == []


def test_openrouter_discovery_normalizes_only_provider_reported_metadata():
    payload = {"data": [{
        "id": "provider/model", "name": "Provider model", "context_length": 8192,
        "description": "provider description",
        "pricing": {"prompt": "0.000002", "completion": "0.000004"},
    }]}

    class Response(io.StringIO):
        def __enter__(self):
            return self
        def __exit__(self, *_):
            self.close()

    with (
        patch.object(model_registry.settings, "OPENROUTER_API_KEY", "test-key"),
        patch.object(model_registry, "urlopen", return_value=Response(json.dumps(payload))),
    ):
        entries = model_registry.discover_openrouter_models()

    assert len(entries) == 1
    entry = entries[0]
    assert entry.model_id == "provider/model"
    assert entry.input_price_per_million == 2.0
    assert entry.output_price_per_million == 4.0
    assert entry.context_window == 8192
    assert entry.estimated_quality is None
    assert entry.inference_access_status == "unverified"


def test_unconfigured_provider_is_not_routable():
    with patch.object(model_registry.settings, "OPENAI_API_KEY", ""):
        assert all(item.provider != "OpenAI" for item in model_registry.get_all_models())


def test_discovered_entry_with_unknown_latency_cannot_meet_latency_constraint():
    entry = model_registry._discovered_model(
        "provider/new-model", "OpenRouter", source="https://example.invalid/models", now="2026-01-01T00:00:00+00:00"
    ).model_copy(update={"active": True, "capabilities": ["general", "coding"]})
    candidates, filtered = filter_candidates([entry], analyze("Explain recursion"), max_latency=1.0)
    assert candidates == []
    assert "latency metadata is unavailable" in filtered[0]["reason"]
