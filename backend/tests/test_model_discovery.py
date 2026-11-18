import os
os.environ.setdefault("JWT_SECRET", "unit-test-only-secret-do-not-use-in-production")

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
    candidates, filtered = filter_candidates([entry], analyze("Explain recursion"))
    assert candidates == []
    assert filtered[0]["reason"] == "Model is inactive"


def test_openai_discovery_without_credentials_is_empty():
    with patch.object(model_registry.settings, "OPENAI_API_KEY", ""):
        assert model_registry.discover_openai_models() == []


def test_unconfigured_provider_is_not_routable():
    with patch.object(model_registry.settings, "OPENAI_API_KEY", ""):
        assert all(item.provider != "OpenAI" for item in model_registry.get_all_models())
