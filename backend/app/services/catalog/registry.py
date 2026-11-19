"""The single authoritative active registry. Every consumer (Model Pool, routing, evaluation, search, Inspect) reads here.

* No second registry: this module only *derives* ``ModelMetadata`` views from the one ``CatalogState``.
* Works offline: with no persisted catalogue it builds the state from the curated snapshot source alone, so behaviour
  without the migration is the same as before. A failed or missing database never empties the registry.
* The view is cached per process and re-validated against the store version, so a published change reaches every surface
  within ``CATALOG_CACHE_SECONDS`` (or immediately after ``invalidate()``).
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.model import ModelMetadata
from app.services import model_classifier
from app.services.catalog import engine, sources as src_mod
from app.services.catalog.safe_http import safe_destination_url
from app.services.catalog.state import CatalogState, ModelRecord, OfferingRecord
from app.services.catalog.store import MemoryStore, PgStore, StoreUnavailable

logger = get_logger(__name__)
_DATA = Path(__file__).resolve().parents[2] / "data"
_lock = threading.RLock()
_EXPIRED = float("-inf")     # not 0.0: time.monotonic() can be < CATALOG_CACHE_SECONDS shortly after boot, which made 0.0 look "fresh"
_cache: dict = {"at": _EXPIRED, "state": None, "origin": "seed", "version": -1, "models": None, "error": None}
_stores: dict = {}
ADAPTER_PROVIDERS = {"openai", "anthropic", "google", "groq", "openrouter"}


# ── store selection ───────────────────────────────────────────────────────────
def persistence_enabled() -> bool:
    return bool(settings.CATALOG_PERSISTENCE_ENABLED and settings.DATABASE_URL)


def get_store():
    with _lock:
        if persistence_enabled():
            if "pg" not in _stores:
                _stores["pg"] = PgStore()
            return _stores["pg"]
        if "mem" not in _stores:
            mem = MemoryStore()
            engine.refresh(mem, [src_mod.SeedSource()], trigger="bootstrap", force=True)
            _stores["mem"] = mem
        return _stores["mem"]


def reset_for_tests() -> None:
    with _lock:
        _stores.clear()
        _cache.update(at=_EXPIRED, state=None, origin="seed", version=-1, models=None, error=None)


def invalidate() -> None:
    with _lock:
        _cache.update(at=_EXPIRED)


def _seed_state() -> CatalogState:
    with _lock:
        if "seed" not in _stores:
            mem = MemoryStore()
            engine.refresh(mem, [src_mod.SeedSource()], trigger="bootstrap", force=True)
            _stores["seed"] = mem
        return _stores["seed"].load()


STALE_SERVE_SECONDS = 600.0      # an expired view this young is served immediately while a background refresh runs
_refresh_lock = threading.Lock()  # one revalidation at a time, held across the database round trips (never `_lock`)
_refresh_running = threading.Event()


def _fresh() -> bool:
    return _cache["state"] is not None and time.monotonic() - _cache["at"] < settings.CATALOG_CACHE_SECONDS


def _revalidate() -> None:
    """Re-check the persisted catalogue and update the cached view. Database I/O happens outside ``_lock``."""
    try:
        store = get_store()
        version = store.version()
        with _lock:
            if _cache["state"] is not None and version == _cache["version"] and _cache["origin"] == "store":
                _cache["at"] = time.monotonic()
                return
        loaded = store.load()
        with _lock:
            if any(m.publication == "published" for m in loaded.models.values()):
                _set(loaded, "store" if persistence_enabled() else "offline_seed", loaded.version)
            else:
                _set(_seed_state(), "seed", -1)          # migration applied but nothing published yet
            _cache["error"] = None
    except Exception as exc:                             # noqa: BLE001 - registry must keep serving
        with _lock:
            logger.warning("catalogue store unavailable (%s); serving %s", type(exc).__name__, "last good view" if _cache["state"] else "seed")
            _cache["error"] = type(exc).__name__
            if _cache["state"] is None:
                _set(_seed_state(), "seed", -1)
            _cache["at"] = time.monotonic()


def _refresh_in_background() -> None:
    if _refresh_running.is_set():
        return
    _refresh_running.set()

    def work():
        try:
            with _refresh_lock:
                if not _fresh():
                    _revalidate()
        finally:
            _refresh_running.clear()
    threading.Thread(target=work, name="catalogue-refresh", daemon=True).start()


def state() -> CatalogState:
    """Current catalogue view. Never raises: database failure degrades to the last good view, then to the seed.

    Stale-while-revalidate: once the cached view passes ``CATALOG_CACHE_SECONDS`` it is still served at once (up to
    ``STALE_SERVE_SECONDS`` old) and refreshed in the background, so a request never waits on the database just because a cache
    interval elapsed. ``invalidate()`` and a first call (nothing cached) still revalidate before returning.
    """
    with _lock:
        if _fresh():
            return _cache["state"]
        age = time.monotonic() - _cache["at"]
        serve_stale = _cache["state"] is not None and _cache["origin"] == "store" and age < STALE_SERVE_SECONDS
        cached = _cache["state"]
    if serve_stale:
        _refresh_in_background()
        return cached
    with _refresh_lock:
        with _lock:
            if _fresh():
                return _cache["state"]
        _revalidate()
    with _lock:
        return _cache["state"]


def warm() -> None:
    """Load the catalogue ahead of the first request. Best effort."""
    try:
        state()
    except Exception:
        pass


def _set(st: CatalogState, origin: str, version: int) -> None:
    _cache.update(state=st, origin=origin, version=version, at=time.monotonic(), models=None)


def origin() -> str:
    state()
    return _cache["origin"]


# ── derivation of ModelMetadata views ─────────────────────────────────────────
def _provider_domains() -> dict:
    raw = json.loads((_DATA / "developers.json").read_text())
    return {p["name"].lower(): p["domains"] for p in raw.get("providers", [])}


def _primary(offerings: list) -> Optional[OfferingRecord]:
    live = [o for o in offerings if o.listed] or offerings
    if not live:
        return None

    def rank(o: OfferingRecord):
        price = (o.pricing or {}).get("input_per_million")
        free_tier = price == 0 and any((x.pricing or {}).get("input_per_million") for x in live)     # rate-limited free variants are not the headline offering
        batch = o.offering_model_id.lower().endswith(":batch") and any(not x.offering_model_id.lower().endswith(":batch") for x in live)   # async-only route
        return (0 if o.provider.lower() in ADAPTER_PROVIDERS else 1, 1 if batch else 0, 0 if o.curated else 1, 1 if free_tier else 0, 0 if price is not None else 1, price if price is not None else 0.0,
                {"official_documentation": 0, "developer_repository": 1, "provider_reported": 2, "aggregator_reported": 3}.get(o.authority, 9), o.provider)
    return sorted(live, key=rank)[0]


def _destinations(rec: ModelRecord, offerings: list, st: CatalogState) -> list:
    dev = st.developers.get(rec.developer or "")
    prov = _provider_domains()
    out, seen = [], set()
    for o in offerings:
        allowed = list(prov.get(o.provider.lower(), [])) + (list(dev.official_domains) if dev else [])
        for u in o.urls:
            url = safe_destination_url(u.get("url"), allowed)
            if url and url not in seen:
                seen.add(url)
                out.append({"kind": u.get("kind", "documentation"), "label": u.get("label") or "Open", "url": url, "provider": o.provider, "verified": True})
    order = {"documentation": 0, "model_page": 1, "model_repository": 2, "provider_catalog": 3}
    return sorted(out, key=lambda d: order.get(d["kind"], 9))


def to_metadata(rec: ModelRecord, offerings: list, st: CatalogState) -> ModelMetadata:
    cur = rec.curated or {}
    tax = rec.taxonomy or {}
    prim = _primary(offerings)
    pcur = (prim.curated if prim and prim.curated else None) or cur
    price = (prim.pricing if prim else None) or {}
    inp, outp = price.get("input_per_million"), price.get("output_per_million")
    dests = _destinations(rec, offerings, st)
    doc = next((d["url"] for d in dests if d["kind"] == "documentation"), None) or (dests[0]["url"] if dests else None)
    provider = prim.provider if prim else "Unknown"
    modalities = list(rec.input_modalities or ["text"])
    out_m = rec.output_modalities or ["text"]
    modality = "image" if out_m == ["image"] else (out_m[0] if out_m[0] != "embeddings" else "text")
    if len(modalities) > 1 and modality == "text":
        modalities = modalities
    bench = rec.benchmarks or {}
    # A curated estimate always wins. Otherwise a real, independent benchmark index (0-100) is the only evidence-backed quality signal;
    # it is reported as such, never as a curated estimate, and latency/reliability/risk stay unknown.
    bench_quality = round(bench["intelligence_index"] / 100.0, 3) if not pcur.get("estimated_quality") and isinstance(bench.get("intelligence_index"), (int, float)) else None
    quality_known = pcur.get("estimated_quality") is not None or bench_quality is not None
    prov = rec.provenance
    pricing_prov = "unavailable" if inp is None and outp is None else ("provider_published" if prim and prim.authority in ("official_documentation", "developer_repository") else "aggregator_reported")
    mp = dict(pcur.get("metric_provenance") or {})
    mp.setdefault("pricing", pricing_prov)
    mp.setdefault("capabilities", "provider_published" if prov.get("capabilities", {}).get("authority") in ("official_documentation", "developer_repository", "merged") else "aggregator_reported")
    mp.setdefault("context_window", "unavailable" if rec.context_window is None else "provider_published")
    for k in ("quality", "latency", "reliability", "risk"):
        mp.setdefault(k, "estimated" if pcur.get("estimated_quality") is not None else "unavailable")
    if bench_quality is not None:
        mp["quality"] = "benchmark_reported"
    dev = st.developers.get(rec.developer or "")
    meta = ModelMetadata(
        model_id=prim.offering_model_id if prim else rec.canonical_key, model_name=rec.name, provider=provider,
        model_family=pcur.get("model_family") or rec.family.replace("-", " ").title(),
        capabilities=list(rec.capabilities), supported_domains=list(pcur.get("supported_domains") or []), supported_tasks=list(pcur.get("supported_tasks") or []),
        estimated_quality=pcur.get("estimated_quality") if pcur.get("estimated_quality") is not None else bench_quality, estimated_cost=pcur.get("estimated_cost"), estimated_latency=pcur.get("estimated_latency"),
        reliability=pcur.get("reliability"), risk_level=pcur.get("risk_level"),
        context_window=rec.context_window or 0, cost_per_1k_tokens=(inp / 1000) if inp is not None else None,
        avg_latency_seconds=pcur.get("avg_latency_seconds"), fallback_priority=pcur.get("fallback_priority", 8), active=rec.publication == "published",
        source="catalog", modality=modality, modalities=modalities, entry_type="inference_model", requires_key=True, external_url=doc,
        description=rec.description, availability="unknown", provider_source=doc, authentication_requirement="api_key",
        data_provenance="catalog_pipeline", metric_provenance=mp, metadata_status=("stale" if set(rec.sources) <= {"curated_snapshot"} else ("verified" if rec.verification == "officially_confirmed" and quality_known else ("estimated" if quality_known else "incomplete"))),
        lifecycle_status={"superseded": "retired", "unavailable": "unavailable", "deprecated": "deprecated"}.get(rec.lifecycle, "active" if rec.publication == "published" else "newly_discovered"),
        lifecycle_reason=rec.retention_reason, adapter_compatible=provider.lower() in ADAPTER_PROVIDERS, last_verified_at=st.published_at,
        input_price_per_million=inp, output_price_per_million=outp, developer=dev.name if dev else (rec.developer or None),
        license_name=rec.license, canonical_key=f"{provider.lower()}:{prim.offering_model_id}" if prim else rec.canonical_key, first_seen_at=rec.first_seen_at,
        embedding_dimensions=pcur.get("embedding_dimensions"), retires_at=prim.expires_at if prim else None,
    )
    if tax:
        meta.model_type = tax.get("model_type") or "unclassified"
        meta.use_categories = list(tax.get("use_categories") or [])
        meta.weights_status = tax.get("weights_status") or "unknown"
        meta.license_name = tax.get("license_name") or rec.license
        meta.free_download = tax.get("free_download")
        meta.free_access, meta.free_access_note = tax.get("free_access") or "unknown", tax.get("free_access_note")
        meta.deployment_options = list(tax.get("deployment_options") or [])
        meta.api_available = tax.get("api_available")
        meta.taxonomy_status = tax.get("taxonomy_status") or "curated"
    else:
        meta.taxonomy_status = "unclassified"
        meta.weights_status = {True: "open_weights", False: "proprietary"}.get(rec.open_weights, "unknown")
    cls = model_classifier.classify(
        name=rec.name, offering_ids=[o.offering_model_id for o in offerings] or [rec.canonical_key], in_m=rec.input_modalities, out_m=rec.output_modalities,
        caps=rec.capabilities, sources=rec.sources, open_weights=rec.open_weights,
        curated_type=(tax.get("model_type") if tax else None), curated_categories=(tax.get("use_categories") if tax else None))
    meta.primary_category, meta.category_kind = cls.primary_category, cls.kind
    meta.classification_basis, meta.classification_reason, meta.capability_tags = cls.basis, cls.reason, cls.capability_tags
    if cls.basis == "derived":
        # Derived from declared modalities / serving route: fills only what curation left empty, and says so.
        meta.model_type, meta.use_categories, meta.taxonomy_status = cls.model_type, list(cls.use_categories), "derived"
        if meta.api_available is None:
            meta.api_available = True if any(o.provider.lower() != "hugging face" for o in offerings) else None
    meta.catalog = {
        "canonical_key": rec.canonical_key, "developer_slug": rec.developer, "lineage_key": rec.lineage_key, "generation_label": rec.generation_label,
        "generation_status": rec.retention, "generation_reason": rec.retention_reason, "verification_level": rec.verification, "lifecycle": rec.lifecycle,
        "publication": rec.publication, "availability": rec.availability, "released_at": rec.released_at, "released_at_kind": rec.released_at_kind,
        "variants": list(rec.variants), "retired": rec.publication == "retired", "superseded_at": rec.superseded_at, "first_seen_at": rec.first_seen_at,
        "last_changed_at": rec.last_changed_at, "sources": list(rec.sources), "field_provenance": prov, "conflicts": list(rec.conflicts),
        "offerings": [{"provider": o.provider, "model_id": o.offering_model_id, "listed": o.listed, "authority": o.authority,
                       "input_per_million": (o.pricing or {}).get("input_per_million"), "output_per_million": (o.pricing or {}).get("output_per_million"),
                       "pricing_known": bool(o.pricing), "context_window": o.context_window, "deprecated": o.deprecated} for o in offerings],
        "destinations": dests, "primary_provider": provider, "benchmarks": rec.benchmarks,
    }
    return meta


def _offerings_by_model(st: CatalogState) -> dict:
    out: dict = {}
    for o in st.offerings.values():
        out.setdefault(o.canonical_key, []).append(o)
    return out


def _views() -> dict:
    st = state()
    with _lock:
        if _cache["models"] is None:
            by = _offerings_by_model(st)
            _cache["models"] = {k: to_metadata(m, by.get(k, []), st) for k, m in st.models.items()}
        return _cache["models"]


def published_models() -> list:
    """The active registry: published models only (superseded/unpublished are excluded from every active surface)."""
    return [m.model_copy(deep=True) for m in sorted(_views().values(), key=lambda m: (m.provider.lower(), m.model_id)) if m.catalog and m.catalog["publication"] == "published"]


def all_models() -> list:
    """Published + retired, for historical lookups (old routing logs and evaluations still resolve)."""
    return [m.model_copy(deep=True) for m in _views().values() if m.catalog and m.catalog["publication"] in ("published", "retired")]


def find(model_id: str, provider: Optional[str] = None) -> Optional[ModelMetadata]:
    """Resolve by any offering's model id, including retired models and non-primary offerings."""
    best = None
    for m in _views().values():
        for o in (m.catalog or {}).get("offerings", []):
            if o["model_id"] == model_id and (provider is None or o["provider"].lower() == provider.lower()):
                if m.model_id == model_id:
                    return m.model_copy(deep=True)
                best = best or m
    return best.model_copy(deep=True) if best else None


def freshness() -> dict:
    st = state()
    srcs = []
    for s in st.sources.values():
        srcs.append({"source_id": s.source_id, "kind": s.kind, "status": s.status, "last_attempt_at": s.last_attempt_at, "last_success_at": s.last_success_at,
                     "consecutive_failures": s.consecutive_failures, "last_count": s.last_count, "last_error": s.last_error,
                     "refresh_interval_minutes": s.refresh_interval_minutes})
    return {"origin": origin(), "version": st.version, "published_at": st.published_at, "store_error": _cache["error"], "sources": srcs,
            "persistence_enabled": persistence_enabled()}


# ── read models for the API / UI ───────────────────────────────────────────────
def summary() -> dict:
    st = state()
    views = _views()
    pub = [m for m in st.models.values() if m.publication == "published"]
    retired = [m for m in st.models.values() if m.publication == "retired"]
    pending = [m for m in st.models.values() if m.publication == "unpublished"]
    live = origin() == "store"
    # Offline, the only "source" is the bundled snapshot loaded at process start: its timestamps would be fabricated freshness.
    srcs = freshness()["sources"] if live else []
    by_dev: dict = {}
    for m in pub:
        d = by_dev.setdefault(m.developer or "unknown", {"developer": m.developer or "unknown", "name": (st.developers.get(m.developer or "") and st.developers[m.developer].name) or (m.developer or "Unknown"), "models": 0})
        d["models"] += 1
    retained_gens = [g for g in st.generations.values() if g.retention == "retained"]
    review = [l for l in st.lineages.values() if l.review_reason]
    recent, runs, announced = [], [], []
    if live:
        try:
            store = get_store()
            for e in store.recent_events(limit=12, event_types={"model_discovered", "model_superseded", "model_published"}):
                rec = st.models.get(e["entity_key"])
                recent.append({**e, "name": rec.name if rec else (e.get("reason") if e.get("event_type") == "announcement_detected" else None) or e["entity_key"]})
            runs = store.recent_runs(limit=5)
            announced = [{**e, "name": e.get("reason") or e["entity_key"]} for e in store.recent_events(limit=8, event_types={"announcement_detected"})]   # own list: model events would otherwise bury them
        except Exception as exc:                          # noqa: BLE001
            logger.warning("catalogue events unavailable: %s", type(exc).__name__)
    return {
        "origin": _cache["origin"], "live": live, "version": st.version, "published_at": st.published_at if live else None, "store_error": _cache["error"],
        "totals": {"published": len(pub), "retired": len(retired), "awaiting_verification": len(pending), "developers": len(by_dev),
                   "retained_generations": len(retained_gens), "lineages_needing_review": len(review), "registered_developers": len(st.developers)},
        "developers": sorted(by_dev.values(), key=lambda d: (-d["models"], d["name"])),
        "recent_events": recent, "recent_announcements": announced, "recent_runs": runs, "sources": srcs,
        "last_success_at": max((s["last_success_at"] for s in srcs if s["last_success_at"]), default=None),
        "note": None if live else "Offline snapshot: live discovery is not running on this deployment, so freshness and recent-discovery data are unavailable.",
    }


def families() -> list:
    st = state()
    out = []
    for lk, lin in sorted(st.lineages.items()):
        gens = [g for g in st.generations.values() if g.lineage_key == lk]
        gens.sort(key=lambda g: tuple(g.sort_key), reverse=True)
        members = [m for m in st.models.values() if m.lineage_key == lk]
        out.append({"lineage_key": lk, "developer": lin.developer, "family": lin.family, "track": lin.track, "review_reason": lin.review_reason,
                    "generations": [{"generation_key": g.generation_key, "label": g.label, "retention": g.retention, "reason": g.retention_reason,
                                     "verification": g.verification, "first_released_at": g.first_released_at,
                                     "models": [{"canonical_key": m.canonical_key, "name": m.name, "publication": m.publication} for m in members if m.generation_key == g.generation_key]}
                                    for g in gens],
                    "unmanaged_models": [{"canonical_key": m.canonical_key, "name": m.name, "publication": m.publication} for m in members if not m.generation_key]})
    return out


def diff_summary(before: CatalogState, after: CatalogState, sample: int = 40) -> dict:
    """What a refresh would change, for dry runs and admin review (no secrets, bounded size)."""
    new = [m for k, m in after.models.items() if k not in before.models]
    changed_pub = [(k, before.models[k].publication, m.publication) for k, m in after.models.items() if k in before.models and before.models[k].publication != m.publication]
    multi = []
    for lk in sorted({m.lineage_key for m in after.models.values()}):
        gens = sorted((g for g in after.generations.values() if g.lineage_key == lk), key=lambda g: tuple(g.sort_key), reverse=True)
        if len(gens) > 2:
            multi.append({"lineage": lk, "generations": [{"label": g.label, "retention": g.retention} for g in gens]})
    pub = lambda st: sum(1 for m in st.models.values() if m.publication == "published")
    return {
        "models_before": len(before.models), "models_after": len(after.models), "published_before": pub(before), "published_after": pub(after),
        "new_models": len(new), "new_sample": [{"key": m.canonical_key, "name": m.name, "verification": m.verification, "publication": m.publication,
                                                "generation": m.generation_label, "confidence": m.classification_confidence} for m in new[:sample]],
        "publication_changes": [{"key": k, "from": a, "to": b} for k, a, b in changed_pub[:sample]],
        "retired_after": sum(1 for m in after.models.values() if m.publication == "retired"),
        "lineages_under_review": [{"lineage": l.lineage_key, "reason": l.review_reason} for l in after.lineages.values() if l.review_reason][:sample],
        "multi_generation_lineages": multi[:sample],
        "offerings_after": len(after.offerings),
    }
