"""Live Model Pool: lifecycle, discovery normalisation, eligibility, routing overlay, admin API.

Database-backed tests (class TestPersistence) run only against TEST_DATABASE_URL.
"""
import os
os.environ.setdefault("JWT_SECRET", "unit-test-only-secret-do-not-use-in-production")

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.schemas.model import ModelMetadata
from app.services import (inference_verification, model_registry, provider_discovery as pd,
                          registry_eligibility as elig, registry_lifecycle as lc, registry_service)
from app.services.candidate_filter import filter_candidates
from app.services.query_analyzer import analyze
from tests.conftest import HAS_ISOLATED_TEST_DATABASE

client = TestClient(app)
NOW = datetime(2026, 11, 18, tzinfo=timezone.utc)


def live(provider="OpenRouter", mid="acme/new", **kw) -> ModelMetadata:
    base = model_registry._discovered_model(mid, provider, source="https://example.invalid", now=NOW.isoformat())
    return base.model_copy(update={"canonical_key": f"{provider.lower()}:{mid}", **kw})


def complete(entry: ModelMetadata) -> ModelMetadata:
    return entry.model_copy(update={"estimated_quality": .7, "estimated_cost": .3, "estimated_latency": .3, "reliability": .8,
                                    "risk_level": .2, "cost_per_1k_tokens": .001, "lifecycle_status": "active"})


# ── lifecycle ────────────────────────────────────────────────────────────────
class TestLifecycle:
    def test_first_sighting(self):
        assert lc.initial_status(adapter_compatible=True, provider_lifecycle=None)[0] == "newly_discovered"
        assert lc.initial_status(adapter_compatible=False, provider_lifecycle=None)[0] == "incompatible"
        assert lc.initial_status(adapter_compatible=True, provider_lifecycle="deprecated")[0] == "deprecated"
        assert lc.initial_status(adapter_compatible=True, provider_lifecycle="retired")[0] == "retired"

    def test_progression_requires_validation_not_version_numbers(self):
        assert lc.next_status("newly_discovered", adapter_compatible=True, provider_lifecycle=None, inference_validated=False)[0] == "pending_validation"
        assert lc.next_status("pending_validation", adapter_compatible=True, provider_lifecycle=None, inference_validated=False)[0] == "pending_validation"
        assert lc.next_status("pending_validation", adapter_compatible=True, provider_lifecycle=None, inference_validated=True)[0] == "active"

    def test_reappearance_revalidates(self):
        assert lc.next_status("unavailable", adapter_compatible=True, provider_lifecycle=None, inference_validated=False)[0] == "pending_validation"
        assert lc.next_status("retired", adapter_compatible=True, provider_lifecycle=None, inference_validated=True)[0] == "pending_validation"

    def test_absence_needs_threshold(self):
        assert lc.after_missing("active", 1, 2)[0] == "active"
        assert lc.after_missing("active", 2, 2)[0] == "unavailable"
        assert lc.after_missing("retired", 5, 2)[0] == "retired"

    def test_transition_table(self):
        assert lc.can_transition(None, "newly_discovered")
        assert not lc.can_transition("retired", "unavailable")


# ── discovery normalisation ──────────────────────────────────────────────────
class TestDiscovery:
    def test_openrouter_normalises_and_rejects_bad_rows(self):
        payload = {"data": [
            {"id": "a/b", "name": "A B", "context_length": 8192, "pricing": {"prompt": "0.000001", "completion": "-1"},
             "architecture": {"input_modalities": ["text", "image"]}},
            {"id": "bad id with spaces"}, {"id": 12}, {"id": "a/b"},  # invalid, non-string, duplicate
        ]}
        with patch.object(settings, "OPENROUTER_API_KEY", "k"), patch.object(pd, "_get_json", return_value=payload):
            result = pd.discover_openrouter()
        assert [e.model_id for e in result.entries] == ["a/b"] and result.rejected == 3
        e = result.entries[0]
        assert e.input_price_per_million == 1.0 and e.output_price_per_million is None   # negative = unknown, never 0
        assert e.modalities == ["text", "image"] and e.canonical_key == "openrouter:a/b"
        assert e.estimated_quality is None and e.reliability is None and e.lifecycle_status == "newly_discovered"

    def test_anthropic_lifecycle_is_provider_reported(self):
        rows = [{"id": "claude-x", "display_name": "Claude X", "lifecycle": "active", "max_input_tokens": 200000},
                {"id": "claude-old", "display_name": "Old", "lifecycle": "deprecated", "deprecated_at": "2026-01-01T00:00:00Z", "retires_at": "2027-01-01T00:00:00Z"},
                {"id": "claude-gone", "lifecycle": "retired"}]
        with patch.object(settings, "ANTHROPIC_API_KEY", "k"), patch.object(pd, "_anthropic_list_raw", return_value=rows):
            result = pd.discover_anthropic()
        by_id = {e.model_id: e for e in result.entries}
        assert by_id["claude-x"].lifecycle_status == "newly_discovered" and by_id["claude-x"].context_window == 200000
        assert by_id["claude-old"].lifecycle_status == "deprecated" and by_id["claude-old"].retires_at == "2027-01-01T00:00:00Z"
        assert by_id["claude-gone"].lifecycle_status == "retired"

    def test_gemini_strips_resource_prefix_to_match_static_ids(self):
        rows = [{"name": "models/gemini-2.5-pro", "display_name": "Gemini 2.5 Pro", "input_token_limit": 1048576}]
        with patch.object(settings, "GEMINI_API_KEY", "k"), patch.object(pd, "_gemini_list_raw", return_value=rows):
            entry = pd.discover_google().entries[0]
        assert entry.model_id == "gemini-2.5-pro" and entry.canonical_key == "google:gemini-2.5-pro"

    def test_groq_active_flag_is_not_interpreted(self):
        payload = {"data": [{"id": "llama-x", "active": False, "context_window": 8192}]}
        with patch.object(settings, "GROQ_API_KEY", "k"), patch.object(pd, "_get_json", return_value=payload):
            assert pd.discover_groq().entries[0].lifecycle_status == "newly_discovered"

    def test_missing_credentials(self):
        with patch.object(settings, "OPENAI_API_KEY", ""):
            with pytest.raises(pd.DiscoveryError) as exc:
                pd.discover("openai")
        assert exc.value.kind == "not_configured"

    @pytest.mark.parametrize("status,kind", [(401, "authentication"), (403, "authentication"), (429, "rate_limited")])
    def test_http_errors_are_classified_without_leaking_details(self, status, kind):
        from urllib.error import HTTPError
        err = HTTPError("https://api.openai.com/v1/models", status, "secret-body sk-123", {}, None)
        with patch.object(settings, "OPENAI_API_KEY", "sk-123"), patch.object(pd, "_get_json", side_effect=err):
            with pytest.raises(pd.DiscoveryError) as exc:
                pd.discover("openai")
        assert exc.value.kind == kind and "sk-123" not in exc.value.safe_message and "secret-body" not in exc.value.safe_message

    def test_timeout_and_malformed(self):
        with patch.object(settings, "GROQ_API_KEY", "k"):
            with patch.object(pd, "_get_json", side_effect=TimeoutError()):
                with pytest.raises(pd.DiscoveryError) as exc:
                    pd.discover("groq")
            assert exc.value.kind == "timeout"
            with patch.object(pd, "_get_json", return_value={"data": "nope"}):
                with pytest.raises(pd.DiscoveryError) as exc:
                    pd.discover("groq")
            assert exc.value.kind == "malformed_response"
            with patch.object(pd, "_get_json", return_value={"data": [{"id": "bad id"}]}):  # nothing usable is not an authoritative empty list
                with pytest.raises(pd.DiscoveryError):
                    pd.discover("groq")

    def test_empty_list_is_valid(self):
        with patch.object(settings, "GROQ_API_KEY", "k"), patch.object(pd, "_get_json", return_value={"data": []}):
            assert pd.discover("groq").entries == []


# ── eligibility ──────────────────────────────────────────────────────────────
class TestEligibility:
    def test_listed_is_not_eligible(self):
        with patch.object(settings, "OPENROUTER_API_KEY", "k"):
            result = elig.evaluate(live())
        assert not result.eligible
        assert {"lifecycle_excluded", "inference_not_verified", "metadata_incomplete"} <= set(result.reasons)

    def test_live_only_needs_fresh_verification_and_complete_metadata(self):
        entry = complete(live())
        ok = elig.Verification("validated", NOW - timedelta(days=1))
        with patch.object(settings, "OPENROUTER_API_KEY", "k"):
            assert elig.evaluate(entry, verification=ok, now=NOW).eligible
            assert "inference_not_verified" in elig.evaluate(entry, now=NOW).reasons
            assert "inference_verification_stale" in elig.evaluate(entry, verification=elig.Verification("validated", NOW - timedelta(days=30)), now=NOW).reasons
            assert "metadata_incomplete" in elig.evaluate(entry.model_copy(update={"estimated_quality": None}), verification=ok, now=NOW).reasons

    def test_incompatible_provider_and_disabled(self):
        entry = complete(live("Mistral", "mistral-x"))
        assert "adapter_incompatible" in elig.evaluate(entry).reasons
        with patch.object(settings, "OPENROUTER_API_KEY", "k"), patch.object(settings, "DISABLED_PROVIDERS", "openrouter"):
            assert "provider_disabled" in elig.evaluate(complete(live())).reasons

    def test_applications_never_route(self):
        app_entry = model_registry.get_all_applications()[0]
        assert elig.evaluate(app_entry).reasons == ["not_inference_model"]

    def test_static_entries_keep_existing_behaviour(self):
        static = model_registry._status(next(m for m in model_registry.api_models() if m.model_id == "gpt-4.1"))
        assert static.adapter_compatible is True
        with patch.object(settings, "OPENAI_API_KEY", "k"):
            assert elig.evaluate(static).eligible
        with patch.object(settings, "OPENAI_API_KEY", ""):
            assert elig.evaluate(static).reasons == ["provider_not_configured"]

    def test_static_entry_excluded_by_failed_verification_or_live_unavailability(self):
        static = model_registry._status(next(m for m in model_registry.api_models() if m.model_id == "gpt-4.1"))
        with patch.object(settings, "OPENAI_API_KEY", "k"):
            assert "inference_verification_failed" in elig.evaluate(static, verification=elig.Verification("failed", NOW, "invalid_model")).reasons
            assert elig.evaluate(static, verification=elig.Verification("failed", NOW, "timeout")).eligible  # transient errors do not exclude
            assert "lifecycle_excluded" in elig.evaluate(static.model_copy(update={"lifecycle_status": "unavailable"})).reasons
            deprecated = elig.evaluate(static.model_copy(update={"lifecycle_status": "deprecated"}))
            assert deprecated.eligible and "deprecated" in deprecated.warnings


# ── routing overlay ──────────────────────────────────────────────────────────
class TestRoutingIntegration:
    def _state(self, snaps=(), verifs=None):
        return registry_service.LiveState(list(snaps), verifs or {}, [], True)

    def test_disabled_registry_changes_nothing(self):
        with patch.object(settings, "LIVE_REGISTRY_ENABLED", False), patch.object(settings, "OPENAI_API_KEY", "k"):
            models, excluded = model_registry.get_catalog_with_exclusions("coding")
        assert excluded == [] and any(m.model_id == "gpt-4.1" for m in models)

    def test_static_catalog_is_deterministic_for_evaluation(self):
        with patch.object(settings, "OPENAI_API_KEY", "k"), patch.object(registry_service, "live_state", side_effect=AssertionError("must not be consulted")):
            assert model_registry.get_catalog_for_recommendation("coding")

    def test_unavailable_static_model_is_excluded_with_reason(self):
        gone = live("OpenAI", "gpt-4.1", lifecycle_status="unavailable", lifecycle_reason="Absent from 2 consecutive successful provider lists.")
        with patch.object(settings, "OPENAI_API_KEY", "k"), patch.object(registry_service, "live_state", return_value=self._state([gone])):
            models, excluded = model_registry.get_catalog_with_exclusions("coding")
        assert all(m.model_id != "gpt-4.1" for m in models)
        assert any(x["model_id"] == "gpt-4.1" and x["reason"].startswith("Live registry:") for x in excluded)

    def test_unverified_live_model_never_enters_pool(self):
        entry = complete(live())
        with patch.object(settings, "OPENROUTER_API_KEY", "k"), patch.object(registry_service, "live_state", return_value=self._state([entry])):
            models, _ = registry_service.apply_live_registry([])
        assert models == []

    def test_verified_complete_live_model_enters_pool_and_obeys_hard_filters(self):
        entry = complete(live()).model_copy(update={"capabilities": ["general"], "supported_tasks": ["qa"], "supported_domains": ["general"]})
        verifs = {("openrouter", "acme/new"): elig.Verification("validated", datetime.now(timezone.utc))}
        with patch.object(settings, "OPENROUTER_API_KEY", "k"), patch.object(registry_service, "live_state", return_value=self._state([entry], verifs)):
            models, _ = registry_service.apply_live_registry([])
        assert [m.model_id for m in models] == ["acme/new"] and models[0].active
        candidates, filtered = filter_candidates(models, analyze("Explain recursion"), privacy_requirement="strict")
        assert candidates == [] and "data-handling" in filtered[0]["reason"]   # hard privacy constraint still applies

    def test_overlay_fails_open(self):
        models = [model_registry._status(next(m for m in model_registry.api_models() if m.model_id == "gpt-4.1"))]
        with patch.object(registry_service, "live_state", return_value=registry_service.LiveState()):  # persistence unavailable
            assert registry_service.apply_live_registry(models) == (models, [])
        with patch.object(registry_service, "live_state", return_value=self._state()), \
                patch.object(elig, "evaluate", side_effect=RuntimeError("boom")):  # unexpected internal failure
            assert registry_service.apply_live_registry(models) == (models, [])


# ── verification guards ──────────────────────────────────────────────────────
class TestVerificationGuards:
    def test_refuses_apps_unconfigured_incompatible_and_non_text(self):
        gpt = model_registry._status(next(m for m in model_registry.api_models() if m.model_id == "gpt-4.1"))
        image = model_registry._status(next(m for m in model_registry.api_models() if m.model_id == "gpt-image-1"))
        with patch.object(settings, "OPENAI_API_KEY", ""):
            with pytest.raises(inference_verification.VerificationRefused) as e1:
                inference_verification._precheck(gpt)
        assert e1.value.code == "provider_not_configured"
        with patch.object(settings, "OPENAI_API_KEY", "k"):
            with pytest.raises(inference_verification.VerificationRefused) as e2:
                inference_verification._precheck(image)
            assert e2.value.code == "unsupported_modality"
        with pytest.raises(inference_verification.VerificationRefused) as e3:
            inference_verification._precheck(model_registry.get_all_applications()[0])
        assert e3.value.code == "not_inference_model"


# ── API ──────────────────────────────────────────────────────────────────────
class TestApi:
    def test_catalog_is_paged_filterable_and_works_without_persistence(self):
        r = client.get("/api/v1/models/catalog", params={"page_size": 5, "sort": "name"})
        body = r.json()
        assert r.status_code == 200 and len(body["items"]) == 5 and body["total"] >= 40
        assert body["persistence_available"] is False and body["summary"]["by_origin"]["live"] == 0
        assert all("eligibility" in item for item in body["items"])
        one = client.get("/api/v1/models/catalog", params={"search": "gpt-4.1", "provider": "OpenAI"}).json()
        assert {i["model_id"] for i in one["items"]} >= {"gpt-4.1", "gpt-4.1-mini"}
        assert client.get("/api/v1/models/catalog", params={"sort": "bogus"}).status_code == 422
        assert client.get("/api/v1/models/catalog", params={"page_size": 1000}).status_code == 422

    def test_legacy_models_endpoint_still_lists_static_and_apps(self):
        items = client.get("/api/v1/models").json()
        assert any(i["model_id"] == "gpt-4.1" for i in items) and any(i["model_id"].startswith("app/") for i in items)

    def test_eligibility_and_status_and_detail(self):
        with patch.object(settings, "OPENAI_API_KEY", ""):
            body = client.get("/api/v1/models/eligibility", params={"provider": "OpenAI"}).json()
            assert body["eligible"] == [] and body["excluded"][0]["reasons"][0]["code"] == "provider_not_configured"
        status = client.get("/api/v1/models/registry-status").json()
        assert {p["provider"] for p in status["providers"]} == set(pd.PROVIDERS) and "key" not in str(status).lower().replace("api_key", "")
        detail = client.get("/api/v1/models/detail", params={"provider": "OpenAI", "model_id": "gpt-4.1"}).json()
        assert detail["entry"]["model_id"] == "gpt-4.1" and detail["lifecycle_history"] == []
        assert client.get("/api/v1/models/detail", params={"provider": "OpenAI", "model_id": "nope"}).status_code == 404

    def test_admin_endpoints_are_locked_down(self):
        body = {"provider": "openai"}
        with patch.object(settings, "REGISTRY_ADMIN_TOKEN", ""):
            assert client.post("/api/v1/models/registry/refresh", json=body).status_code == 503
            assert client.post("/api/v1/models/discover/openai").status_code == 503
        with patch.object(settings, "REGISTRY_ADMIN_TOKEN", "s3cret"):
            assert client.post("/api/v1/models/registry/refresh", json=body).status_code == 403
            assert client.post("/api/v1/models/registry/refresh", json=body, headers={"X-Registry-Admin-Token": "wrong"}).status_code == 403
            assert client.post("/api/v1/models/registry/verify", json={"provider": "OpenAI", "model_id": "gpt-4.1"}).status_code == 403
            # correct token but persistence not enabled -> clear 503, no provider call
            ok = client.post("/api/v1/models/registry/refresh", json=body, headers={"X-Registry-Admin-Token": "s3cret"})
            assert ok.status_code == 503

    def test_admin_rate_limit(self):
        from app.api.routes import models as routes
        routes._calls["admin"].clear()
        with patch.object(settings, "REGISTRY_ADMIN_TOKEN", "s3cret"):
            codes = [client.post("/api/v1/models/registry/refresh", json={}, headers={"X-Registry-Admin-Token": "s3cret"}).status_code
                     for _ in range(22)]
        routes._calls["admin"].clear()
        assert codes[:20] == [503] * 20 and codes[20:] == [429, 429]


# ── persistence (isolated test database only) ────────────────────────────────
pytestmark_db = pytest.mark.skipif(not HAS_ISOLATED_TEST_DATABASE, reason="TEST_DATABASE_URL is not configured")


def result(*ids, rejected=0, **kw):
    return pd.DiscoveryResult("OpenRouter", [live("OpenRouter", i, **kw) for i in ids], rejected)


@pytestmark_db
class TestPersistence:
    @pytest.fixture(autouse=True)
    def db(self, monkeypatch):
        import psycopg
        from app.services import model_registry_store as store
        monkeypatch.setattr(settings, "LIVE_REGISTRY_ENABLED", True)
        assert settings.DATABASE_URL == os.environ["TEST_DATABASE_URL"]  # never production
        migration = os.path.join(os.path.dirname(__file__), "..", "migrations", "20261118_live_model_registry.sql")
        with psycopg.connect(settings.DATABASE_URL, autocommit=True) as conn:
            conn.execute(open(migration).read())  # idempotent: also proves re-application is safe
            conn.execute("TRUNCATE model_lifecycle_events, model_inference_verifications, model_catalog_snapshots, provider_catalog_refreshes CASCADE")
        registry_service.invalidate_cache()
        self.store = store
        yield

    def count(self, table, where="TRUE"):
        with self.store._conn() as conn:
            return conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE {where}").fetchone()["n"]

    def refresh(self, discover, **kw):
        return self.store.refresh_provider("openrouter", discover, **kw)

    def status_of(self, model_id):
        return next(s for s in self.store.get_current_snapshots() if s.model_id == model_id)

    def test_first_refresh_persists_snapshots_events_and_counts(self):
        out = self.refresh(lambda: result("acme/a", "acme/b"))
        assert out["status"] == "success" and out["entries_new"] == 2
        assert self.count("model_catalog_snapshots") == 2 and self.count("model_lifecycle_events", "event_type='discovered'") == 2
        assert self.status_of("acme/a").lifecycle_status == "newly_discovered"
        row = self.store.get_refresh_status()[0]
        assert row["status"] == "success" and row["entries_seen"] == 2 and row["last_success_at"] is not None

    def test_refresh_is_idempotent_once_state_settles(self):
        self.refresh(lambda: result("acme/a"))
        self.refresh(lambda: result("acme/a"))                      # newly_discovered -> pending_validation
        assert self.status_of("acme/a").lifecycle_status == "pending_validation"
        before = (self.count("model_catalog_snapshots"), self.count("model_lifecycle_events"))
        out = self.refresh(lambda: result("acme/a"))
        assert out["entries_new"] == 0 and out["entries_changed"] == 0
        assert (self.count("model_catalog_snapshots"), self.count("model_lifecycle_events")) == before

    def test_metadata_change_appends_snapshot_and_keeps_history(self):
        self.refresh(lambda: result("acme/a", context_window=1000))
        self.refresh(lambda: result("acme/a", context_window=1000))
        self.refresh(lambda: result("acme/a", context_window=2000))
        assert self.status_of("acme/a").context_window == 2000
        history = self.store.get_lifecycle_history("openrouter", "acme/a")
        assert [h["event_type"] for h in history][:1] == ["metadata_changed"] and len(history) == 3
        assert self.count("model_catalog_snapshots") == 3   # append-only: older snapshots remain

    def test_absence_requires_threshold_then_reappearance_revalidates(self):
        self.refresh(lambda: result("acme/a", "acme/b"))
        self.refresh(lambda: result("acme/a", "acme/b"))
        self.refresh(lambda: result("acme/a"))
        assert self.status_of("acme/b").lifecycle_status == "pending_validation" and self.status_of("acme/b").consecutive_missing_refreshes == 1
        self.refresh(lambda: result("acme/a"))
        gone = self.status_of("acme/b")
        assert gone.lifecycle_status == "unavailable" and "2 consecutive" in gone.lifecycle_reason
        n = self.count("model_catalog_snapshots")
        self.refresh(lambda: result("acme/a"))
        assert self.count("model_catalog_snapshots") == n   # already unavailable: no churn
        self.refresh(lambda: result("acme/a", "acme/b"))
        assert self.status_of("acme/b").lifecycle_status == "pending_validation"

    def test_partial_provider_response_does_not_prove_absence(self):
        self.refresh(lambda: result("acme/a", "acme/b"))
        self.refresh(lambda: result("acme/a", rejected=1))
        assert self.status_of("acme/b").consecutive_missing_refreshes == 0

    def test_provider_failure_preserves_last_known_good_and_records_safe_error(self):
        self.refresh(lambda: result("acme/a"))
        def boom():
            raise pd.DiscoveryError("authentication")
        out = self.refresh(boom)
        assert out["status"] == "failed" and out["error_code"] == "authentication"
        assert self.status_of("acme/a").lifecycle_status == "newly_discovered" and self.count("model_catalog_snapshots") == 1
        row = self.store.get_refresh_status()[0]
        assert row["status"] == "failed" and row["last_success_at"] is not None   # last good refresh still reported
        assert "credentials" in row["error_message_safe"] and not any(a.lower() in str(row).lower() for a in ("bearer", "sk-"))
        assert any(a["kind"] == "refresh_failure" for a in self.store.get_activity())

    def test_unexpected_discovery_exception_is_sanitised(self):
        def boom():
            raise RuntimeError("password=hunter2 upstream body")
        out = self.refresh(boom)
        assert out["status"] == "failed"
        assert "hunter2" not in str(self.store.get_refresh_history())

    def test_invalid_entries_roll_back_the_whole_refresh(self):
        bad = pd.DiscoveryResult("OpenRouter", [live("OpenRouter", "acme/a"), live("OpenAI", "gpt-x")], 0)   # provider mismatch
        out = self.refresh(lambda: bad)
        assert out["status"] == "failed" and self.count("model_catalog_snapshots") == 0

    def test_live_lease_blocks_second_refresh_and_expired_lease_is_recovered(self):
        with self.store._conn() as conn:
            conn.execute("""INSERT INTO provider_catalog_refreshes (refresh_id, provider, status, started_at, lease_expires_at)
                VALUES (gen_random_uuid(), 'openrouter', 'running', now(), now() + interval '5 minutes')""")
        assert self.refresh(lambda: result("acme/a"))["status"] == "already_running"
        with self.store._conn() as conn:
            conn.execute("UPDATE provider_catalog_refreshes SET lease_expires_at = now() - interval '1 minute'")
        assert self.refresh(lambda: result("acme/a"))["status"] == "success"
        statuses = {r["status"] for r in self.store.get_refresh_history()}
        assert statuses == {"abandoned", "success"}

    def test_abandoned_refresh_cannot_write_late(self):
        refresh_id = self.store._acquire_lease("openrouter", "manual")
        with self.store._conn() as conn:
            conn.execute("UPDATE provider_catalog_refreshes SET status = 'abandoned' WHERE refresh_id = %s", (refresh_id,))
        with pytest.raises(RuntimeError, match="lease_lost"):
            self.store._persist("openrouter", refresh_id, result("acme/a").entries, 0)
        assert self.count("model_catalog_snapshots") == 0

    def test_concurrent_refreshes_serialise_on_the_lease(self):
        import threading, time
        outcomes = []
        def slow():
            time.sleep(1.0)
            return result("acme/a")
        first = threading.Thread(target=lambda: outcomes.append(self.refresh(slow)["status"]))
        first.start()
        time.sleep(0.4)
        outcomes.append(self.refresh(lambda: result("acme/a"))["status"])
        first.join()
        assert sorted(outcomes) == ["already_running", "success"] and self.count("model_catalog_snapshots") == 1

    def test_ttl_skips_fresh_provider(self):
        self.refresh(lambda: result("acme/a"))
        assert self.refresh(lambda: result("acme/a"), only_if_stale=True) == {"provider": "openrouter", "status": "fresh", "skipped": True}
        with patch.object(settings, "REGISTRY_REFRESH_TTL_MINUTES", 0):
            assert self.refresh(lambda: result("acme/a"), only_if_stale=True)["status"] == "success"

    def test_verification_is_separate_and_promotes_pending_models(self):
        self.refresh(lambda: result("acme/a")); self.refresh(lambda: result("acme/a"))
        assert self.status_of("acme/a").lifecycle_status == "pending_validation"
        assert self.store.get_current_verifications() == {}
        self.store.record_verification("OpenRouter", "acme/a", "validated", None, 120)
        assert self.status_of("acme/a").lifecycle_status == "active"
        verification = self.store.get_current_verifications()[("openrouter", "acme/a")]
        assert verification.status == "validated" and self.store.last_verification_at("OpenRouter", "acme/a") is not None
        kinds = [h["event_type"] for h in self.store.get_lifecycle_history("openrouter", "acme/a")]
        assert "inference_verified" in kinds and kinds.count("status_changed") == 2
        self.store.record_verification("OpenRouter", "acme/a", "failed", "invalid_model", 90)
        assert self.store.get_current_verifications()[("openrouter", "acme/a")].status == "failed"
        assert self.status_of("acme/a").lifecycle_status == "active"   # a failed probe never rewrites lifecycle on its own

    def test_end_to_end_verified_model_enters_routing_pool_only_when_complete(self):
        self.refresh(lambda: result("acme/a", capabilities=["general"], supported_tasks=["qa"], supported_domains=["general"]))
        self.refresh(lambda: result("acme/a", capabilities=["general"], supported_tasks=["qa"], supported_domains=["general"]))
        self.store.record_verification("OpenRouter", "acme/a", "validated", None, 50)
        registry_service.invalidate_cache()
        with patch.object(settings, "OPENROUTER_API_KEY", "k"):
            models, _ = registry_service.apply_live_registry([])
            assert models == []    # verified but metadata incomplete: no placeholder scores are invented
            entry = next(e for e in registry_service.build_registry() if e.model_id == "acme/a")
            assert entry.eligibility["eligible"] is False and [r["code"] for r in entry.eligibility["reasons"]] == ["metadata_incomplete"]
        assert entry.catalog_origin == "live" and entry.verification["status"] == "validated"

    def test_static_models_are_overlaid_with_live_evidence(self):
        self.store.refresh_provider("openai", lambda: pd.DiscoveryResult("OpenAI", [live("OpenAI", "gpt-4.1")], 0))
        registry_service.invalidate_cache()
        with patch.object(settings, "OPENAI_API_KEY", "k"):
            entry = next(e for e in registry_service.build_registry() if e.model_id == "gpt-4.1")
            assert entry.catalog_origin == "static" and entry.availability == "listed_by_provider" and entry.eligibility["eligible"]
            assert entry.estimated_quality == .86   # curated scores untouched by discovery
        assert not any(e.model_id == "gpt-4.1" and e.catalog_origin == "live" for e in registry_service.build_registry())


@pytestmark_db
class TestRegistryApiWithDatabase:
    """The admin API end to end against the isolated test database (provider HTTP is stubbed)."""
    H = {"X-Registry-Admin-Token": "s3cret"}

    @pytest.fixture(autouse=True)
    def env(self, monkeypatch):
        import psycopg
        from app.api.routes import models as routes
        monkeypatch.setattr(settings, "LIVE_REGISTRY_ENABLED", True)
        monkeypatch.setattr(settings, "REGISTRY_ADMIN_TOKEN", "s3cret")
        monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "k")
        monkeypatch.setattr(settings, "REGISTRY_VERIFICATION_COOLDOWN_SECONDS", 600)
        migration = os.path.join(os.path.dirname(__file__), "..", "migrations", "20261118_live_model_registry.sql")
        with psycopg.connect(settings.DATABASE_URL, autocommit=True) as conn:
            conn.execute(open(migration).read())
            conn.execute("TRUNCATE model_lifecycle_events, model_inference_verifications, model_catalog_snapshots, provider_catalog_refreshes CASCADE")
        routes._calls["admin"].clear()
        registry_service.invalidate_cache()
        self.payload = {"data": [{"id": "acme/alpha", "name": "Alpha", "context_length": 32000, "pricing": {"prompt": "0.000001", "completion": "0.000002"}},
                                 {"id": "acme/beta", "name": "Beta", "context_length": 8000}]}
        yield
        routes._calls["admin"].clear()

    def refresh(self, **body):
        with patch.object(pd, "_get_json", return_value=self.payload):
            return client.post("/api/v1/models/registry/refresh", json={"provider": "openrouter", **body}, headers=self.H)

    def test_refresh_then_browse_inspect_and_audit(self):
        out = self.refresh().json()["results"][0]
        assert out["status"] == "success" and out["entries_new"] == 2
        page = client.get("/api/v1/models/catalog", params={"origin": "live", "search": "alpha"}).json()
        assert page["total"] == 1 and page["items"][0]["lifecycle_status"] == "newly_discovered"
        assert page["items"][0]["eligibility"]["eligible"] is False and page["persistence_available"] is True
        assert page["summary"]["by_origin"]["live"] == 2
        detail = client.get("/api/v1/models/detail", params={"provider": "OpenRouter", "model_id": "acme/alpha"}).json()
        assert detail["lifecycle_history"][0]["event_type"] == "discovered"
        status = client.get("/api/v1/models/registry-status").json()
        row = next(p for p in status["providers"] if p["provider"] == "openrouter")
        assert status["persistence_available"] and row["status"] == "success" and row["entries_seen"] == 2 and row["stale"] is False
        assert client.get("/api/v1/models/refresh-history").json()[0]["status"] == "success"
        assert {a["kind"] for a in client.get("/api/v1/models/activity").json()} == {"lifecycle"}
        assert client.get("/api/v1/models").json()  # legacy list unaffected
        assert all(i["catalog_origin"] != "live" for i in client.get("/api/v1/models").json())
        assert any(i["catalog_origin"] == "live" for i in client.get("/api/v1/models", params={"include_live": True}).json())
        excluded = client.get("/api/v1/models/eligibility", params={"provider": "OpenRouter"}).json()["excluded"]
        assert {"inference_not_verified", "metadata_incomplete"} <= {r["code"] for r in next(e for e in excluded if e["model_id"] == "acme/alpha")["reasons"]}

    def test_only_if_stale_and_unknown_provider(self):
        self.refresh()
        assert self.refresh(only_if_stale=True).json()["results"][0]["status"] == "fresh"
        assert client.post("/api/v1/models/registry/refresh", json={"provider": "nope"}, headers=self.H).status_code == 422
        with patch.object(settings, "GROQ_API_KEY", ""):
            assert client.post("/api/v1/models/registry/refresh", json={"provider": "groq"}, headers=self.H).json()["results"][0]["status"] == "not_configured"

    def test_failed_refresh_is_reported_safely_and_keeps_data(self):
        self.refresh()
        from urllib.error import HTTPError
        with patch.object(pd, "_get_json", side_effect=HTTPError("u", 401, "bad key sk-secret", {}, None)):
            out = client.post("/api/v1/models/registry/refresh", json={"provider": "openrouter"}, headers=self.H).json()["results"][0]
        assert out["status"] == "failed" and out["error_code"] == "authentication"
        assert client.get("/api/v1/models/catalog", params={"origin": "live"}).json()["total"] == 2
        assert "sk-secret" not in client.get("/api/v1/models/refresh-history").text + client.get("/api/v1/models/registry-status").text
        assert any(a["kind"] == "refresh_failure" for a in client.get("/api/v1/models/activity").json())

    def test_verification_endpoint_records_outcome_enforces_cooldown_and_hides_upstream_errors(self):
        self.refresh()
        class Ok:
            def generate(self, *_a, **_k): return "ok"
        body = {"provider": "OpenRouter", "model_id": "acme/alpha"}
        with patch("app.services.model_adapters.factory.get_adapter", return_value=Ok()):
            first = client.post("/api/v1/models/registry/verify", json=body, headers=self.H)
            again = client.post("/api/v1/models/registry/verify", json=body, headers=self.H)
        assert first.status_code == 200 and first.json()["status"] == "validated"
        assert again.status_code == 409 and again.json()["detail"]["code"] == "cooldown"
        detail = client.get("/api/v1/models/detail", params={"provider": "OpenRouter", "model_id": "acme/alpha"}).json()["entry"]
        assert detail["verification"]["status"] == "validated" and detail["lifecycle_status"] == "newly_discovered"
        # the other model fails with a provider error that must not leak
        from app.services.model_adapters.provider_adapters import ProviderUnavailableError
        class Bad:
            def generate(self, *_a, **_k): raise ProviderUnavailableError("raw upstream text sk-leak", kind="invalid_model")
        with patch("app.services.model_adapters.factory.get_adapter", return_value=Bad()):
            failed = client.post("/api/v1/models/registry/verify", json={"provider": "OpenRouter", "model_id": "acme/beta"}, headers=self.H)
        assert failed.json()["status"] == "failed" and failed.json()["error_code"] == "invalid_model" and "sk-leak" not in failed.text
        assert client.post("/api/v1/models/registry/verify", json={"provider": "OpenRouter", "model_id": "zzz"}, headers=self.H).status_code == 404


@pytestmark_db
class TestRoutingEndToEnd:
    """Real /route-and-generate with live-registry evidence in the isolated test database."""

    @pytest.fixture(autouse=True)
    def env(self, monkeypatch):
        import psycopg, uuid
        from app.services import feedback_store, user_store
        monkeypatch.setattr(settings, "LIVE_REGISTRY_ENABLED", True)
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "k")
        monkeypatch.setattr(settings, "JWT_SECRET", "unit-test-only-secret-do-not-use-in-production")
        migration = os.path.join(os.path.dirname(__file__), "..", "migrations", "20261118_live_model_registry.sql")
        user_store.init_db(); feedback_store.init_feedback_db()
        with psycopg.connect(settings.DATABASE_URL, autocommit=True) as conn:
            conn.execute(open(migration).read())
            conn.execute("TRUNCATE model_lifecycle_events, model_inference_verifications, model_catalog_snapshots, provider_catalog_refreshes CASCADE")
        registry_service.invalidate_cache()
        token = client.post("/api/v1/auth/register", json={"name": "T", "email": f"{uuid.uuid4().hex[:10]}@example.com",
                                                           "password": "Passw0rd!x1", "user_group": "student"}).json()["token"]
        self.headers = {"Authorization": f"Bearer {token}"}
        yield
        registry_service.invalidate_cache()

    def route(self, **extra):
        return client.post("/api/v1/route-and-generate", json={"query": "Write a Python function that sorts a list of integers", **extra}, headers=self.headers)

    def test_live_evidence_removes_model_and_explains_why(self):
        from app.services import model_registry_store as store
        pool = ["gpt-4.1", "gpt-4.1-mini", "o3"]
        before = self.route(model_ids=pool).json()
        assert {"gpt-4.1", "gpt-4.1-mini", "o3"} <= set(before["candidate_models"])
        # Two successful provider lists that omit gpt-4.1 -> "unavailable" with a recorded reason.
        listed = lambda: pd.DiscoveryResult("OpenAI", [live("OpenAI", "gpt-4.1-mini"), live("OpenAI", "o3"), live("OpenAI", "gpt-4.1")], 0)
        store.refresh_provider("openai", listed)
        gone = lambda: pd.DiscoveryResult("OpenAI", [live("OpenAI", "gpt-4.1-mini"), live("OpenAI", "o3")], 0)
        store.refresh_provider("openai", gone)
        store.refresh_provider("openai", gone)
        registry_service.invalidate_cache()
        after = self.route().json()
        assert "gpt-4.1" not in after["candidate_models"] and after["selected_model_id"] != "gpt-4.1"
        reason = next(f["reason"] for f in after["filtered_models"] if f["model_id"] == "gpt-4.1")
        assert reason.startswith("Live registry:")
        blocked = self.route(model_ids=pool)
        assert blocked.status_code == 422 and "gpt-4.1 is excluded from routing" in blocked.json()["detail"]
        assert "gpt-4.1-mini" in self.route(model_ids=["gpt-4.1-mini", "o3"]).json()["candidate_models"]

    def test_discovered_but_unverified_models_never_become_candidates(self):
        from app.services import model_registry_store as store
        store.refresh_provider("openai", lambda: pd.DiscoveryResult("OpenAI", [live("OpenAI", "gpt-future-9")], 0))
        registry_service.invalidate_cache()
        body = self.route().json()
        assert "gpt-future-9" not in body["candidate_models"] and all(f["model_id"] != "gpt-future-9" for f in body["filtered_models"])

    def test_static_routing_is_unchanged_when_live_registry_is_off(self, monkeypatch):
        monkeypatch.setattr(settings, "LIVE_REGISTRY_ENABLED", False)
        registry_service.invalidate_cache()
        body = self.route(model_ids=["gpt-4.1", "o3"]).json()
        assert set(body["candidate_models"]) == {"gpt-4.1", "o3"}
