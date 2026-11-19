"""Autonomous catalogue: discovery, verification, generation retention, safety. All offline; sources are fakes or fixtures."""
import copy
from datetime import datetime, timedelta, timezone

import pytest

from app.services.catalog import engine, merge, registry, retention, safe_http, sources as S
from app.services.catalog.safe_http import FetchError
from app.services.catalog.state import (AUTH_AGGREGATOR, AUTH_OFFICIAL, CatalogState, DeveloperRecord, Observation, SourceState)
from app.services.catalog.store import MemoryStore, StoreUnavailable
from app.services.catalog.versions import classify, newer

T0 = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)


def dev(slug="acme", **kw):
    return DeveloperRecord(slug=slug, name=slug.title(), openrouter_prefixes=[slug], huggingface_orgs=[slug], official_domains=[f"{slug}.com"], **kw)


def ob(mid, *, src="docs", auth=AUTH_OFFICIAL, provider="Acme", developer="acme", rel=None, price=None, **kw):
    return Observation(source_id=src, authority=auth, offering_provider=provider, offering_model_id=mid, name=kw.pop("name", mid.split("/")[-1]),
                       developer=developer, released_at=rel, output_modalities=("text",), pricing=price, **kw)


class FakeSource:
    kind = "public_aggregator"
    default_interval_minutes = 10

    def __init__(self, source_id="fake", batches=None, scope=None):
        self.source_id = source_id
        self.batches = list(batches or [])
        self.scope = scope

    def fetch(self, state, developers, now):
        item = self.batches.pop(0)
        if isinstance(item, Exception):
            raise item
        obs, complete = item if isinstance(item, tuple) else (item, True)
        return S.SourceResult(observations=obs, complete=complete, raw_count=len(obs), scope=self.scope)


def store_with(*developers):
    st = CatalogState()
    for d in developers or (dev(),):
        st.developers[d.slug] = d
    return MemoryStore(st)


def run(store, src, minutes=0, **kw):
    return engine.refresh(store, [src], trigger="test", now=T0 + timedelta(minutes=minutes), force=True, **kw)


def gen(n, rel):
    return ob(f"acme/nova-{n}", rel=rel)


G2, G3, G4 = gen(2, "2025-01-01T00:00:00+00:00"), gen(3, "2025-06-01T00:00:00+00:00"), gen(4, "2026-01-01T00:00:00+00:00")


# ── classifier ────────────────────────────────────────────────────────────────
def test_versions_are_numeric_not_lexicographic():
    assert newer(classify("acme-model-3.10", "m", "acme"), classify("acme-model-3.9", "m", "acme"))
    assert classify("acme-model-3.10", "m", "acme").sort_key > classify("acme-model-3.9", "m", "acme").sort_key
    assert classify("claude-opus-4-20250514", "Claude Opus 4", "anthropic").lineage_key == "anthropic:claude:text"


def test_unknown_generation_is_unmanaged_not_guessed():
    c = classify("sonar-pro", "Sonar Pro", "perplexity")
    assert c.generation_key is None


# ── A. new generation release ─────────────────────────────────────────────────
def test_A_new_generation_supersedes_oldest_atomically():
    s = store_with()
    run(s, FakeSource(batches=[[G2, G3]]))
    st = s.load()
    assert {m.retention for m in st.models.values()} == {"retained"}
    v = s.version()
    r = run(s, FakeSource(batches=[[G2, G3, G4]]), minutes=1)
    st = s.load()
    assert r.status == "ok" and s.version() == v + 1                       # one commit made both changes
    assert st.models["acme:nova-2"].retention == "superseded" and st.models["acme:nova-2"].publication == "retired"
    assert st.models["acme:nova-3"].publication == st.models["acme:nova-4"].publication == "published"
    types = [e.event_type for e in s.events]
    assert "model_superseded" in types and "generation_superseded" in types
    assert retention.assert_invariants(st) == []


def test_variants_of_retained_generations_are_kept():
    s = store_with()
    run(s, FakeSource(batches=[[G3, G4, ob("acme/nova-4-mini", rel="2026-01-02T00:00:00+00:00"), ob("acme/nova-3-pro", rel="2025-06-02T00:00:00+00:00")]]))
    assert all(m.publication == "published" for m in s.load().models.values())


def test_unverified_new_generation_does_not_retire_anything():
    s = store_with()
    run(s, FakeSource(batches=[[G3, G4]]))
    rumor = ob("acme/nova-5", src="agg", auth=AUTH_AGGREGATOR, provider="OpenRouter", rel="2026-11-01T00:00:00+00:00")
    run(s, FakeSource("agg", [[rumor]]), minutes=1)
    st = s.load()
    assert st.models["acme:nova-3"].publication == "published"
    assert st.models["acme:nova-5"].publication == "unpublished"           # detected only, single aggregator, <24h


# ── B. duplicate discovery ────────────────────────────────────────────────────
def test_B_duplicate_discovery_merges_into_one_model_with_two_offerings():
    s = store_with()
    a = ob("acme/nova-3", price={"input_per_million": 1.0, "output_per_million": 2.0})
    b = ob("acme/nova-3", src="agg", auth=AUTH_AGGREGATOR, provider="OpenRouter", price={"input_per_million": 1.2, "output_per_million": 2.4})
    run(s, FakeSource(batches=[[a, b]]))
    st = s.load()
    assert len(st.models) == 1 and len(st.offerings) == 2
    prices = {o.provider: o.pricing["input_per_million"] for o in st.offerings.values()}
    assert prices == {"Acme": 1.0, "OpenRouter": 1.2}                      # price belongs to each offering


def test_conflicting_values_are_recorded_and_official_wins():
    s = store_with()
    a = ob("acme/nova-3", context_window=200_000)
    b = ob("acme/nova-3", src="agg", auth=AUTH_AGGREGATOR, provider="OpenRouter", context_window=128_000)
    run(s, FakeSource(batches=[[b, a]]))
    m = s.load().models["acme:nova-3"]
    assert m.context_window == 200_000 and m.provenance["context_window"]["authority"] == AUTH_OFFICIAL
    assert m.conflicts and m.conflicts[0]["field"] == "context_window"


# ── H. no release activity => no rewrites ─────────────────────────────────────
def test_H_identical_refresh_writes_nothing():
    s = store_with()
    run(s, FakeSource(batches=[[G3, G4]]))
    before, n_events, changed = s.version(), len(s.events), {k: m.last_changed_at for k, m in s.load().models.items()}
    r = run(s, FakeSource(batches=[[G3, G4]]), minutes=30)
    assert s.version() == before and len(s.events) == n_events and not r.counts["catalog_changed"]
    assert {k: m.last_changed_at for k, m in s.load().models.items()} == changed


# ── C. incomplete / failed provider responses ────────────────────────────────
def test_C_failed_refresh_never_erases_catalogue():
    s = store_with()
    run(s, FakeSource(batches=[[G3, G4]]))
    for i, failure in enumerate([FetchError("timeout"), FetchError("rate_limited"), FetchError("malformed"), RuntimeError("boom")]):
        r = run(s, FakeSource(batches=[failure]), minutes=10 + i)
        assert r.status == "failed"
    st = s.load()
    assert all(m.publication == "published" for m in st.models.values()) and all(o.listed for o in st.offerings.values())
    assert st.sources["fake"].consecutive_failures == 4 and st.sources["fake"].last_error == "adapter_error"


def test_C_missing_model_is_not_discontinued_and_needs_repeated_complete_absence():
    s = store_with()
    full = [ob(f"acme/nova-{n}", src="agg", auth=AUTH_AGGREGATOR, provider="OpenRouter") for n in (3, 4)] + [ob(f"acme/alpha-{i}", src="agg", auth=AUTH_AGGREGATOR, provider="OpenRouter") for i in range(1, 5)]
    run(s, FakeSource("agg", [full]))
    assert s.load().sources["agg"].last_count == 6
    partial = [o for o in full if o.offering_model_id != "acme/nova-4"]
    for i in (1, 2):
        run(s, FakeSource("agg", [partial]), minutes=i)
        assert all(o.listed for o in s.load().offerings.values())            # not yet
    run(s, FakeSource("agg", [partial]), minutes=3)
    st = s.load()
    nova4 = next(o for o in st.offerings.values() if o.offering_model_id == "acme/nova-4")
    assert nova4.listed is False and st.models["acme:nova-4"].lifecycle != "discontinued"
    assert "acme:nova-4" in st.models                                          # never deleted


def test_C_incomplete_or_tiny_response_does_not_count_absences():
    s = store_with()
    full = [ob(f"acme/m-{i}", src="agg", auth=AUTH_AGGREGATOR, provider="OpenRouter") for i in range(1, 9)]
    run(s, FakeSource("agg", [full]))
    run(s, FakeSource("agg", [(full[:6], False)]), minutes=1)               # flagged incomplete
    run(s, FakeSource("agg", [full[:2]]), minutes=2)                        # complete but <50% of last count
    assert all(o.consecutive_missing == 0 and o.listed for o in s.load().offerings.values())


def test_scoped_source_only_counts_absence_inside_its_scope():
    s = store_with(dev("acme"), dev("beta"))
    both = [ob("acme/a-1", src="hf", auth="developer_repository", provider="Hugging Face"), ob("beta/b-1", src="hf", auth="developer_repository", provider="Hugging Face", developer="beta")]
    run(s, FakeSource("hf", [both], scope={"acme", "beta"}))
    for i in range(1, 5):
        run(s, FakeSource("hf", [[both[1]]], scope={"beta"}), minutes=i)       # acme not fetched this run
    assert all(o.listed for o in s.load().offerings.values())


# ── D. ambiguous generation ──────────────────────────────────────────────────
def test_D_contradictory_chronology_goes_to_review_without_supersession():
    s = store_with()
    run(s, FakeSource(batches=[[G2, G3]]))
    odd = ob("acme/nova-5", rel="2024-01-01T00:00:00+00:00")                  # higher number, released long before nova-3
    run(s, FakeSource(batches=[[G2, G3, odd]]), minutes=1)
    st = s.load()
    assert st.lineages["acme:nova:text"].review_reason and "released earlier" in st.lineages["acme:nova:text"].review_reason
    assert st.models["acme:nova-2"].publication == "published"                 # nothing destructive under doubt
    assert st.models["acme:nova-5"].retention == "pending_review"


def test_D_mixed_version_schemes_are_not_compared():
    s = store_with()
    run(s, FakeSource(batches=[[ob("acme/nova-3"), ob("acme/nova-2025-06-01"), ob("acme/nova-4")]]))
    st = s.load()
    assert all(m.retention != "superseded" for m in st.models.values())


# ── E. superseded models stay readable but leave every active surface ────────
def test_E_superseded_model_is_retired_not_deleted(monkeypatch):
    s = store_with()
    run(s, FakeSource(batches=[[G2, G3], [G2, G3, G4]]))
    run(s, FakeSource(batches=[[G2, G3, G4]]), minutes=1)
    monkeypatch.setitem(registry._stores, "mem", s)
    monkeypatch.setattr(registry.settings, "CATALOG_PERSISTENCE_ENABLED", False)
    registry._cache.update(at=registry._EXPIRED, state=None, models=None)
    monkeypatch.setattr(registry, "get_store", lambda: s)
    ids = {m.model_id for m in registry.published_models()}
    assert "acme/nova-4" in ids and "acme/nova-2" not in ids
    old = registry.find("acme/nova-2")
    assert old is not None and old.catalog["retired"] is True and old.lifecycle_status == "retired"
    assert "acme/nova-2" in {m.model_id for m in registry.all_models()}


# ── F. paid model discovered without an API key ──────────────────────────────
OPENROUTER_FIXTURE = [
    {"id": "acme/zeta-2", "name": "Zeta 2", "created": 1760000000, "context_length": 200000, "description": "Paid frontier model",
     "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]}, "top_provider": {"max_completion_tokens": 8192},
     "pricing": {"prompt": "0.000003", "completion": "0.000015"}, "supported_parameters": ["tools", "reasoning"], "hugging_face_id": ""},
    {"id": "acme/zeta-2-free", "name": "Zeta 2 Free", "created": 1760000001, "context_length": 32000, "architecture": {"modality": "text->text"},
     "pricing": {"prompt": "0", "completion": "0"}},
    {"id": "acme/dyn", "name": "Dynamic", "pricing": {"prompt": "-1", "completion": "-1"}},
    {"id": "acme/nopricing", "name": "No pricing"},
    {"id": "unknownco/mystery-1", "name": "Mystery"}, {"id": "broken"}, "garbage", {"id": 5},
]


def test_F_paid_model_discovered_without_inference_credentials(monkeypatch):
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.setattr("app.core.config.settings." + k, "", raising=False)
    src = S.OpenRouterSource(fetcher=lambda *a, **k: safe_http.FetchResult(200, {"data": OPENROUTER_FIXTURE}, 'W/"1"'))
    s = store_with()
    r = run(s, src)
    st = s.load()
    zeta = st.models["acme:zeta-2"]
    off = next(o for o in st.offerings.values() if o.offering_model_id == "acme/zeta-2")
    assert off.pricing["input_per_million"] == pytest.approx(3.0) and off.pricing["output_per_million"] == pytest.approx(15.0)
    assert "tool_calling" in zeta.capabilities and "image_understanding" in zeta.capabilities and zeta.context_window == 200000
    assert zeta.verification == "detected" and zeta.publication == "unpublished"       # a single aggregator needs time/corroboration
    assert r.unregistered_developers == {"unknownco": 1} and r.sources[0]["rejected"] >= 3
    free = next(o for o in st.offerings.values() if o.offering_model_id == "acme/zeta-2-free")
    assert free.pricing["input_per_million"] == 0.0                                   # explicitly free is not unknown
    assert next(o for o in st.offerings.values() if o.offering_model_id == "acme/dyn").pricing is None
    assert next(o for o in st.offerings.values() if o.offering_model_id == "acme/nopricing").pricing is None
    # the model becomes eligible once the aggregator has reported it for 24h, still with no credentials
    run(s, src, minutes=25 * 60)
    z = s.load().models["acme:zeta-2"]
    assert z.verification == "corroborated" and z.publication == "published"
    meta = registry.to_metadata(z, [o for o in s.load().offerings.values() if o.canonical_key == z.canonical_key], s.load())
    assert meta.execution_available is False and meta.input_price_per_million == pytest.approx(3.0) and meta.estimated_quality is None


# ── G. new company without code changes ──────────────────────────────────────
def test_G_new_developer_is_registered_as_data_not_code():
    s = store_with(dev("acme"))
    rows = [{"id": "newco/zeta-1", "name": "Zeta 1", "context_length": 1000, "pricing": {"prompt": "0.000001", "completion": "0.000002"}}]
    src = S.OpenRouterSource(fetcher=lambda *a, **k: safe_http.FetchResult(200, {"data": rows}, None))
    r1 = run(s, src)
    assert r1.unregistered_developers == {"newco": 1} and "newco:zeta-1" not in s.load().models
    st = s.load()
    st.developers["newco"] = dev("newco")
    assert s.commit(st, [], engine.RefreshReport("reg", "t", "x", finished_at="x"), expected_version=st.version, bump=False)
    run(s, src, minutes=1)
    assert "newco:zeta-1" in s.load().models


# ── concurrency, database failure, guards ────────────────────────────────────
def test_concurrent_refresh_is_skipped_not_corrupting():
    s = store_with()
    with s.try_lock() as got:
        assert got
        r = run(s, FakeSource(batches=[[G3]]))
    assert r.status == "skipped" and not s.load().models


def test_optimistic_conflict_writes_nothing():
    s = store_with()

    class Racing(MemoryStore):
        def load(self_inner):
            st = super().load()
            self_inner._state.version += 1          # another writer commits between load and commit
            return st
    racing = Racing(copy.deepcopy(s.load()))
    r = run(racing, FakeSource(batches=[[G3]]))
    assert r.status == "conflict" and not racing._state.models


def test_database_failure_leaves_catalogue_untouched():
    s = store_with()
    run(s, FakeSource(batches=[[G3, G4]]))
    snapshot = copy.deepcopy(s.load())
    s.fail_commits = True
    with pytest.raises(StoreUnavailable):
        run(s, FakeSource(batches=[[G3, G4, gen(5, "2026-06-01T00:00:00+00:00")]]), minutes=5)
    s.fail_commits = False
    assert s.load().models.keys() == snapshot.models.keys() and s.load().version == snapshot.version


def test_mass_removal_guard_aborts_publication(monkeypatch):
    s = store_with()
    words = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota", "kappa"]
    run(s, FakeSource(batches=[[ob(f"acme/{w}-3") for w in words]]))
    assert sum(m.publication == "published" for m in s.load().models.values()) == 10

    def nuke(state, now):
        for m in state.models.values():
            m.retention = "superseded"
        return []
    monkeypatch.setattr(engine.retention_mod, "apply_retention", nuke)
    r = run(s, FakeSource(batches=[[ob("acme/extra-1")]]), minutes=5)
    assert r.status == "aborted" and any("drop" in n for n in r.notes)
    assert all(m.publication == "published" for m in s.load().models.values())
    assert any(e.event_type == "publication_aborted" for e in s.events)


def test_source_backoff_after_failures():
    st = SourceState("x", refresh_interval_minutes=60)
    st.last_attempt_at, st.consecutive_failures = T0.isoformat(), 3
    assert not engine.is_due(st, 60, T0 + timedelta(minutes=300)) and engine.is_due(st, 60, T0 + timedelta(minutes=481))


# ── cache / registry consistency ─────────────────────────────────────────────
def test_registry_reflects_a_published_change_after_invalidation(monkeypatch):
    s = store_with()
    run(s, FakeSource(batches=[[G3]]))
    monkeypatch.setattr(registry, "get_store", lambda: s)
    registry._cache.update(at=registry._EXPIRED, state=None, models=None, origin="seed", version=-1)
    assert {m.model_id for m in registry.published_models()} == {"acme/nova-3"}
    run(s, FakeSource(batches=[[G3, G4]]), minutes=1)
    registry.invalidate()
    assert {m.model_id for m in registry.published_models()} == {"acme/nova-3", "acme/nova-4"}


def test_registry_survives_store_outage_and_serves_seed(monkeypatch):
    registry.reset_for_tests()

    def boom():
        raise StoreUnavailable("down")
    monkeypatch.setattr(registry, "get_store", boom)
    registry._cache.update(at=registry._EXPIRED, state=None, models=None)
    assert len(registry.published_models()) >= 20 and registry.freshness()["store_error"] == "StoreUnavailable"
    registry.reset_for_tests()


# ── source parsing safety ─────────────────────────────────────────────────────
def test_huggingface_filters_quantised_and_untyped_repos():
    rows = [{"id": "acme/nova-3-7B-Instruct", "pipeline_tag": "text-generation", "createdAt": "2026-10-01T00:00:00.000Z", "tags": ["license:apache-2.0"], "safetensors": {"total": 7_000_000_000}},
            {"id": "acme/nova-3-7B-Instruct-GGUF", "pipeline_tag": "text-generation"}, {"id": "acme/nova-3-AWQ", "pipeline_tag": "text-generation"},
            {"id": "acme/dataset-x"}, {"id": "acme/priv", "pipeline_tag": "text-generation", "private": True}]
    r = S.HuggingFaceSource().parse("acme", "acme", rows)
    assert [o.offering_model_id for o in r.observations] == ["acme/nova-3-7B-Instruct"] and r.rejected == 4
    assert r.observations[0].license == "apache-2.0" and r.observations[0].open_weights is True


def test_untrusted_text_is_bounded_and_stripped():
    assert S._text("a\x00b" + "x" * 5000, 100) == "ab" + "x" * 98 and S._text(5) is None


# ── SSRF / destination safety ────────────────────────────────────────────────
@pytest.mark.parametrize("url", ["http://openrouter.ai/x", "https://evil.example/x", "https://u:p@openrouter.ai/x", "https://openrouter.ai:8443/x",
                                 "https://127.0.0.1/x", "https://169.254.169.254/latest", "file:///etc/passwd", "https://openrouter.ai.evil.com/x"])
def test_ssrf_blocked(url):
    with pytest.raises(FetchError) as e:
        safe_http.validate_url(url, ["openrouter.ai"])
    assert e.value.kind == "blocked"


def test_destination_urls_are_domain_restricted():
    assert safe_http.safe_destination_url("https://docs.openai.com/a", ["openai.com"])
    for bad in ("http://openai.com/a", "https://openai.com.evil.io/a", "javascript:alert(1)", "https://evil.io/openai.com", None):
        assert safe_http.safe_destination_url(bad, ["openai.com"]) is None


# ── real OpenRouter payload (captured 2026-11-19) ─────────────────────────────
def _real_pipeline():
    import json, pathlib
    rows = json.loads((pathlib.Path(__file__).parent / "fixtures" / "openrouter_real_sample.json").read_text())

    class Fx:
        def __call__(self, url, **kw):
            return safe_http.FetchResult(status=200, data={"data": rows}, etag=None)
    mem = MemoryStore(registry._seed_state())
    src = S.OpenRouterSource(fetcher=Fx())
    for h in (0, 25):                                    # aggregator-only evidence needs >=24h persistence
        engine.refresh(mem, [src], trigger="test", now=T0 + timedelta(hours=h), force=True)
    return rows, mem.load()


def test_real_payload_alias_rows_are_not_models():
    rows, st = _real_pipeline()
    assert any(str(r["id"]).startswith("~") for r in rows)
    assert not any("~" in k for k in st.models)


def test_real_payload_batch_is_an_offering_not_a_model():
    _, st = _real_pipeline()
    assert not any(m.canonical_key.endswith("-batch") or "-batch-" in m.canonical_key for m in st.models.values())
    assert any(o.offering_model_id.endswith(":batch") for o in st.offerings.values())
    assert all(not m.name.lower().endswith("(batch)") for m in st.models.values())


def test_real_payload_keeps_latest_two_generations_per_lineage():
    _, st = _real_pipeline()
    by_lineage: dict = {}
    for m in st.models.values():
        if m.publication == "published" and m.generation_key:
            by_lineage.setdefault(m.lineage_key, set()).add(m.generation_key)
    assert by_lineage and all(len(g) <= 2 for g in by_lineage.values())
    multi = [m for m in st.models.values() if m.retention == "superseded"]
    assert multi and all(m.publication == "retired" for m in multi)         # superseded => off active surfaces, record kept


def test_real_payload_one_odd_old_row_does_not_freeze_a_family():
    _, st = _real_pipeline()
    gem = [m for m in st.models.values() if m.lineage_key == "google:gemini:text" and m.generation_key and m.generation_key.endswith("@4")]
    assert gem and all(m.publication == "published" for m in gem)


def test_real_payload_discovery_does_not_reroute_a_curated_offering():
    _, st = _real_pipeline()
    meta = registry.to_metadata  # noqa: F841 - public API presence
    llama = [m for m in st.models.values() if m.canonical_key == "meta:llama-3.3-70b"]
    if llama:
        offs = [o for o in st.offerings.values() if o.canonical_key == llama[0].canonical_key]
        if any(o.curated for o in offs) and len(offs) > 1:
            assert registry._primary(offs).curated


# ── K: pagination, explicit failure statuses ──────────────────────────────────
def _hf_row(i):
    return {"id": f"acme/nova-{i}-chat", "pipeline_tag": "text-generation", "createdAt": "2026-10-01T00:00:00.000Z"}


class PagedFetcher:
    """Serves pages of N rows; page k links to page k+1 until `pages` is exhausted."""
    def __init__(self, pages, per_page, always_more=False):
        self.pages, self.per_page, self.always_more, self.urls = pages, per_page, always_more, []

    def __call__(self, url, **kw):
        self.urls.append(url)
        n = len(self.urls)
        rows = [_hf_row(n * 1000 + i) for i in range(self.per_page)]
        nxt = f"https://huggingface.co/api/models?page={n + 1}" if (n < self.pages or self.always_more) else None
        return safe_http.FetchResult(status=200, data=rows, etag=None, next_url=nxt)


def _hf_state(slug="acme"):
    return SourceState(source_id="huggingface")


def test_K_huggingface_follows_every_page_not_just_the_first():
    fx = PagedFetcher(pages=3, per_page=5)
    src = S.HuggingFaceSource(fetcher=fx)
    src.PER_ORG_LIMIT = 5
    res = src.fetch(_hf_state(), {"acme": dev()}, T0)
    assert len(fx.urls) == 3 and len(res.observations) == 15
    assert fx.urls[1].endswith("page=2")


def test_K_page_budget_exhaustion_is_never_reported_as_a_complete_list():
    fx = PagedFetcher(pages=99, per_page=5, always_more=True)
    src = S.HuggingFaceSource(fetcher=fx)
    src.PER_ORG_LIMIT = 5
    res = src.fetch(_hf_state(), {"acme": dev()}, T0)
    assert len(fx.urls) == S.HuggingFaceSource.MAX_PAGES        # bounded
    assert "acme" not in (res.scope or set())                   # more pages exist: absence must not be inferred


def test_K_short_last_page_marks_the_org_complete():
    fx = PagedFetcher(pages=1, per_page=3)
    src = S.HuggingFaceSource(fetcher=fx)
    src.PER_ORG_LIMIT = 5
    assert "acme" in src.fetch(_hf_state(), {"acme": dev()}, T0).scope


def test_link_header_next_is_parsed_and_resolved():
    assert safe_http._next_link('<https://huggingface.co/api/models?cursor=abc>; rel="next"', "https://huggingface.co/api/models") == "https://huggingface.co/api/models?cursor=abc"
    assert safe_http._next_link('</api/models?p=2>; rel="next"', "https://huggingface.co/api/models") == "https://huggingface.co/api/models?p=2"
    assert safe_http._next_link('<https://x/y>; rel="prev"', "https://huggingface.co/") is None and safe_http._next_link(None, "https://a.b") is None


def test_rate_limited_and_timed_out_are_reported_explicitly_and_preserve_data():
    store = store_with()
    run(store, FakeSource(batches=[[G3, G4]]))
    before = {k for k, m in store.load().models.items() if m.publication == "published"}
    for kind, expected in (("rate_limited", "rate_limited"), ("timeout", "timed_out"), ("network", "failed")):
        rep = run(store, FakeSource(batches=[FetchError(kind)]), minutes=60)
        assert rep.sources[0]["status"] == expected and rep.status == "failed"
        assert {k for k, m in store.load().models.items() if m.publication == "published"} == before


# ── benchmark evidence (shape captured from the live OpenRouter payload) ──────
REAL_BENCH_ROW = {"id": "google/gemini-4-neon", "name": "Google: Gemini 4 Neon", "created": 1795006977, "context_length": 1048576,
                  "pricing": {"prompt": "0.000003", "completion": "0.000015"}, "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
                  "supported_parameters": ["tools"], "benchmarks": {"design_arena": [], "artificial_analysis": {
                      "intelligence_index": 61.4, "coding_index": None, "agentic_index": None, "finance_and_accounting_index": 65.1}}}


def test_benchmarks_are_extracted_only_when_numeric_and_in_range():
    b = S._benchmarks(REAL_BENCH_ROW["benchmarks"])
    assert b == {"source": "artificial_analysis", "via": "openrouter", "scale": "0-100", "intelligence_index": 61.4}       # null coding/agentic stay absent
    assert S._benchmarks({"artificial_analysis": {"intelligence_index": 400}}) is None and S._benchmarks({"artificial_analysis": {"intelligence_index": True}}) is None
    assert S._benchmarks(None) is None and S._benchmarks({"design_arena": []}) is None


def test_benchmark_quality_is_reported_as_benchmark_never_as_curated_estimate():
    st = CatalogState()
    d = DeveloperRecord(slug="google", name="Google", openrouter_prefixes=["google"], huggingface_orgs=[], official_domains=["google.com"])
    st.developers["google"] = d
    obs = S.OpenRouterSource().parse([REAL_BENCH_ROW], {"google": d}).observations
    merge.merge_observations(st, obs, T0)
    rec = next(iter(st.models.values()))
    assert rec.benchmarks["intelligence_index"] == 61.4
    off = [o for o in st.offerings.values() if o.canonical_key == rec.canonical_key]
    meta = registry.to_metadata(rec, off, st)
    assert meta.estimated_quality == 0.614 and meta.metric_provenance["quality"] == "benchmark_reported"
    assert meta.estimated_latency is None and meta.reliability is None            # nothing else is invented
    assert meta.catalog["benchmarks"]["via"] == "openrouter"
    rec.curated = {"estimated_quality": 0.9}
    assert registry.to_metadata(rec, off, st).estimated_quality == 0.9            # curated evidence always wins


# ── announcements: discovery signals only (items copied from the real Google / OpenAI feeds, 2026-11-19) ──
REAL_FEED = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Put Gemini to work for you</title><link>https://blog.google/innovation-and-ai/products/gemini-app/tasks-in-gemini-free-new-features/</link><pubDate>Tue, 17 Nov 2026 17:00:00 +0000</pubDate></item>
<item><title><![CDATA[Google Search gets a major upgrade with Gemini 4 Hydrogen]]></title><link>https://blog.google/products-and-platforms/products/search/gemini-4-hydrogen-search-upgrade/</link><pubDate>Thu, 12 Nov 2026 18:00:00 +0000</pubDate></item>
<item><title>Introducing Gemini 7 Quartz &lt;b&gt;today&lt;/b&gt;</title><link>https://blog.google/x/gemini-7-quartz/</link><pubDate>Wed, 18 Nov 2026 09:00:00 +0000</pubDate></item>
<item><title>Old post about Gemini 2</title><link>https://blog.google/x/old/</link><pubDate>Mon, 01 Jan 2024 00:00:00 +0000</pubDate></item>
<item><title>No date item Gemini 9</title><link>https://blog.google/x/nodate/</link></item>
</channel></rss>"""


def test_feed_parser_is_bounded_clean_and_date_filtered():
    from app.services.catalog import announcements as A
    items = A.parse_feed(REAL_FEED, since=None, now=T0 + timedelta(days=1))
    assert [i["url"].rsplit("/", 2)[-2] for i in items] == ["gemini-7-quartz", "tasks-in-gemini-free-new-features", "gemini-4-hydrogen-search-upgrade"]
    assert items[0]["title"] == "Introducing Gemini 7 Quartz today"                 # markup stripped, entities decoded
    assert all("2024" not in i["published_at"] for i in items)                        # outside the first-run window
    assert A.parse_feed(REAL_FEED, since=datetime(2026, 11, 17, 20, tzinfo=timezone.utc), now=T0 + timedelta(days=1))[0]["title"].startswith("Introducing")
    assert len(A.parse_feed("<item><title>x</title></item>" * 5, since=None, now=T0)) == 0


class FeedFetcher:
    def __init__(self, text=REAL_FEED, error=None):
        self.text, self.error, self.calls = text, error, []

    def __call__(self, url, **kw):
        self.calls.append((url, kw))
        if self.error:
            raise self.error
        return safe_http.FetchResult(status=200, data=self.text, etag=None)


def _feed_store():
    d = dev("google", release_feeds=["https://blog.google/innovation-and-ai/technology/ai/rss/"])
    d.official_domains = ["google.com", "blog.google"]
    st = CatalogState()
    st.developers["google"] = d
    return MemoryStore(st), d


def test_announcement_leads_never_create_publish_or_retire_models():
    store, d = _feed_store()
    run(store, FakeSource(batches=[[ob("google/gemini-4-hydrogen", developer="google", provider="Google", rel="2026-11-01T00:00:00+00:00")]]))
    before = {k: (m.publication, m.retention) for k, m in store.load().models.items()}
    fx = FeedFetcher()
    rep = engine.refresh(store, [S.AnnouncementFeedSource(fetcher=fx)], trigger="test", now=T0 + timedelta(days=1), force=True)
    after = store.load()
    assert {k: (m.publication, m.retention) for k, m in after.models.items()} == before            # nothing created, published or retired
    assert fx.calls and fx.calls[0][1].get("as_text") is True and rep.status == "ok"
    evs = [e for e in store.recent_events(limit=50, event_types={"announcement_detected"})]
    states = {e["reason"]: e["to_state"] for e in evs}
    assert states["Google Search gets a major upgrade with Gemini 4 Hydrogen"] in ("published", "awaiting_verification")        # state depends on verification, never "assumed live"
    assert states["Introducing Gemini 7 Quartz today"] == "not_yet_listed"                          # a lead, not a model
    assert "Put Gemini to work for you" not in states                                              # no version => not a model lead


def test_announcements_are_not_repeated_on_the_next_run():
    store, _ = _feed_store()
    run(store, FakeSource(batches=[[ob("google/gemini-4-hydrogen", developer="google", provider="Google", rel="2026-11-01T00:00:00+00:00")]]))
    src = S.AnnouncementFeedSource(fetcher=FeedFetcher())
    engine.refresh(store, [src], trigger="test", now=T0 + timedelta(days=1), force=True)
    n1 = len(store.recent_events(limit=100, event_types={"announcement_detected"}))
    engine.refresh(store, [src], trigger="test", now=T0 + timedelta(days=1, hours=6), force=True)
    assert n1 == 2 and len(store.recent_events(limit=100, event_types={"announcement_detected"})) == n1


def test_feed_must_be_on_the_developers_official_domain():
    store, d = _feed_store()
    d.release_feeds = ["https://evil.example.net/rss.xml"]
    fx = FeedFetcher()
    res = S.AnnouncementFeedSource(fetcher=fx).fetch(SourceState(source_id="announcements"), {"google": d}, T0)
    assert not fx.calls and not res.leads and "not an official domain" in res.notes[0]


def test_feed_failure_is_reported_and_preserves_catalogue():
    store, _ = _feed_store()
    run(store, FakeSource(batches=[[ob("google/gemini-4-hydrogen", developer="google", provider="Google")]]))
    before = set(store.load().models)
    rep = engine.refresh(store, [S.AnnouncementFeedSource(fetcher=FeedFetcher(error=FetchError("rate_limited")))], trigger="test", now=T0 + timedelta(days=1), force=True)
    assert rep.sources[0]["status"] == "rate_limited" and set(store.load().models) == before


def test_announcement_state_distinguishes_published_from_awaiting_verification():
    from app.services.catalog import announcements as A
    store, _ = _feed_store()
    run(store, FakeSource(batches=[[ob("google/gemini-4-hydrogen", developer="google", provider="Google", rel="2026-11-01T00:00:00+00:00")]]))
    st = store.load()
    rec = next(m for m in st.models.values() if m.family == "gemini")
    lead = {"title": "Gemini 4 launch", "url": "https://blog.google/a/", "published_at": "2026-11-18T00:00:00+00:00", "developer": "google"}
    rec.publication = "published"
    assert A.detect([lead], st, "t")[0].to_state == "published"
    rec.publication = "unpublished"
    assert A.detect([lead], st, "t")[0].to_state == "awaiting_verification"
    assert A.detect([{**lead, "title": "Gemini 9 launch", "url": "https://blog.google/b/"}], st, "t")[0].to_state == "not_yet_listed"


# ── announcements as corroboration (independent second source), with precision guarantees ──
def _agg(mid, **kw):
    return ob(mid, src="fake", auth=AUTH_AGGREGATOR, developer="google", provider="OpenRouter", rel="2026-11-10T00:00:00+00:00", **kw)


def _vouch_run(models, feed_text=REAL_FEED, minutes=24 * 60):
    store, _ = _feed_store()
    fx = FeedFetcher(text=feed_text)
    engine.refresh(store, [FakeSource(batches=[models]), S.AnnouncementFeedSource(fetcher=fx)], trigger="test", now=T0 + timedelta(minutes=minutes - 24 * 60 + 60), force=True)
    return store.load()


def test_named_announcement_corroborates_an_aggregator_listing_immediately():
    st = _vouch_run([_agg("google/gemini-4-hydrogen"), _agg("google/gemini-4-neon")])
    hyd, neon = st.models["google:gemini-4-hydrogen"], st.models["google:gemini-4-neon"]
    assert hyd.verification == "corroborated" and hyd.publication == "published" and "announcements" in hyd.sources     # no 24h wait
    assert neon.verification == "detected" and neon.publication == "unpublished"                                      # a sibling is NOT vouched for
    assert hyd.provenance["announcement"]["url"].startswith("https://blog.google/")


def test_announcement_cannot_create_a_model_or_vouch_without_a_listing():
    st = _vouch_run([_agg("google/gemini-3-flash")])                  # feed talks about Gemini 4 / 7: nothing listed for them
    assert not any(m.generation_label in ("4", "7") for m in st.models.values())
    assert st.models["google:gemini-3-flash"].verification == "detected" and "announcements" not in st.models["google:gemini-3-flash"].sources


def test_announcement_must_name_every_distinguishing_token():
    feed = REAL_FEED.replace("Gemini 4 Hydrogen", "Gemini 4 Hydrogen Neon")
    st = _vouch_run([_agg("google/gemini-4-hydrogen-pro")], feed_text=feed)           # "pro" is not in any title
    assert st.models["google:gemini-4-hydrogen-pro"].verification == "detected"


def test_corroboration_never_lowers_and_is_stable_on_rerun():
    store, _ = _feed_store()
    fx = FeedFetcher()
    srcs = lambda: [FakeSource(batches=[[_agg("google/gemini-4-hydrogen")]]), S.AnnouncementFeedSource(fetcher=fx)]
    engine.refresh(store, srcs(), trigger="test", now=T0 + timedelta(hours=1), force=True)
    again = engine.refresh(store, srcs(), trigger="test", now=T0 + timedelta(hours=2), force=True)
    assert not again.counts.get("catalog_changed") and store.load().models["google:gemini-4-hydrogen"].verification == "corroborated"
    engine.refresh(store, [FakeSource(batches=[[_agg("google/gemini-4-hydrogen")]])], trigger="test", now=T0 + timedelta(hours=3), force=True)   # feed absent
    assert store.load().models["google:gemini-4-hydrogen"].verification == "corroborated"


def test_slow_upstream_cannot_stall_a_refresh_and_is_never_called_complete(monkeypatch):
    clock = {"t": 0.0}
    monkeypatch.setattr(S.time, "monotonic", lambda: clock["t"])

    class Slow(PagedFetcher):
        def __call__(self, url, **kw):
            clock["t"] += 15.0                                    # every request "takes" 15s
            return super().__call__(url, **kw)

    fx = Slow(pages=99, per_page=5, always_more=True)
    src = S.HuggingFaceSource(fetcher=fx)
    src.PER_ORG_LIMIT = 5
    many = {f"d{i}": dev(f"d{i}") for i in range(4)}
    res = src.fetch(_hf_state(), many, T0)
    assert len(fx.urls) <= 3 and res.complete is False and not (res.scope or set())          # stopped by the 20s budget, nothing claimed complete
    assert any("time budget" in n for n in res.notes)
