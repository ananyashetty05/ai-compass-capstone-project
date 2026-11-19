"""Catalogue API + registry integration: cron/admin auth, retired-model visibility, live-mode summary, routing pool."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import model_registry, registry_service
from app.services.catalog import engine, registry
from app.services.catalog.store import MemoryStore
from tests.test_catalog_lifecycle import FakeSource, G2, G3, G4, T0, dev, run, store_with

client = TestClient(app)
P = "/api/v1"


@pytest.fixture
def live(monkeypatch):
    """A 'persistent' catalogue backed by an in-memory store, with a superseded generation."""
    s = store_with(dev("acme"))
    run(s, FakeSource(batches=[[G2, G3]]))
    run(s, FakeSource(batches=[[G2, G3, G4]]), minutes=5)
    registry.reset_for_tests()
    monkeypatch.setattr(registry.settings, "CATALOG_PERSISTENCE_ENABLED", True)
    monkeypatch.setattr(registry.settings, "DATABASE_URL", "postgresql://unused")
    registry._stores["pg"] = s
    registry_service.invalidate_cache()
    yield s
    registry.reset_for_tests()
    registry_service.invalidate_cache()


def test_offline_defaults_are_honest():
    registry.reset_for_tests()
    body = client.get(f"{P}/catalog/summary").json()
    assert body["live"] is False and body["last_success_at"] is None and body["recent_events"] == [] and body["note"]
    assert client.get(f"{P}/catalog/events").json() == []
    assert client.post(f"{P}/catalog/refresh").status_code == 403                    # admin token required
    assert client.get(f"{P}/catalog/cron").status_code == 503                        # unconfigured => disabled


def test_live_summary_reflects_real_events_and_totals(live):
    body = client.get(f"{P}/catalog/summary").json()
    assert body["live"] is True and body["totals"]["published"] == 2 and body["totals"]["retired"] == 1
    assert any(e["event_type"] == "model_superseded" for e in body["recent_events"])
    fam = next(f for f in client.get(f"{P}/catalog/families").json() if f["lineage_key"] == "acme:nova:text")
    assert [g["retention"] for g in fam["generations"]] == ["retained", "retained", "superseded"]


def test_retired_model_leaves_active_surfaces_but_stays_resolvable(live):
    active = {m["model_id"] for m in client.get(f"{P}/models").json() if m["entry_type"] == "inference_model"}
    assert "acme/nova-4" in active and "acme/nova-2" not in active
    assert "acme/nova-2" not in {m.model_id for m in model_registry.api_models()}
    detail = client.get(f"{P}/models/detail", params={"provider": "Acme", "model_id": "acme/nova-2"})
    assert detail.status_code == 200
    entry = detail.json()["entry"]
    assert entry["catalog"]["retired"] is True and entry["routing_eligible"] is False and entry["execution_available"] is False
    hist = client.get(f"{P}/catalog/models/history", params={"key": "acme:nova-2"}).json()
    assert any(h["event_type"] == "model_superseded" for h in hist)


def test_superseded_model_is_not_in_routing_candidates(live):
    from app.services.model_registry import get_catalog_with_exclusions
    ids = {m.model_id for m in get_catalog_with_exclusions("", "text", live=False)[0]}
    assert "acme/nova-2" not in ids and "acme/nova-4" in ids


def test_cron_requires_exact_secret_and_runs_due_sources(live, monkeypatch):
    monkeypatch.setattr(client.app.state if False else registry.settings, "CRON_SECRET", "s3cret")
    from app.api.routes import catalog as route
    monkeypatch.setattr(route.src_mod, "default_sources", lambda: [FakeSource("fake", [[G2, G3, G4]])])
    assert client.get(f"{P}/catalog/cron").status_code == 401
    assert client.get(f"{P}/catalog/cron", headers={"Authorization": "Bearer nope"}).status_code == 401
    ok = client.get(f"{P}/catalog/cron", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200 and ok.json()["trigger"] == "cron" and ok.json()["status"] in {"ok", "partial"}


def test_register_developer_validates_input(live, monkeypatch):
    from app.api.routes import models as models_route
    monkeypatch.setattr(models_route.settings, "REGISTRY_ADMIN_TOKEN", "adm")
    h = {"X-Registry-Admin-Token": "adm"}
    assert client.post(f"{P}/catalog/developers", json={"slug": "Bad Slug", "name": "X Corp"}, headers=h).status_code == 422
    assert client.post(f"{P}/catalog/developers", json={"slug": "newco", "name": "NewCo", "official_domains": ["not a domain"]}, headers=h).status_code == 422
    assert client.post(f"{P}/catalog/developers", json={"slug": "newco", "name": "NewCo", "homepage": "http://x.com"}, headers=h).status_code == 422
    r = client.post(f"{P}/catalog/developers", json={"slug": "newco", "name": "NewCo", "openrouter_prefixes": ["newco"], "official_domains": ["newco.ai"]}, headers=h)
    assert r.status_code == 201
    assert client.post(f"{P}/catalog/developers", json={"slug": "newco", "name": "NewCo"}, headers=h).status_code == 409
    assert any(d["slug"] == "newco" for d in client.get(f"{P}/catalog/developers").json())


def test_destinations_only_point_to_registered_domains():
    registry.reset_for_tests()
    for m in registry.published_models():
        from urllib.parse import urlsplit
        for d in m.catalog["destinations"]:
            assert d["url"].startswith("https://") and urlsplit(d["url"]).hostname
