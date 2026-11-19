"""Read-side composition of the live registry: static catalog + live snapshots +
inference verifications + eligibility. Never calls providers; all failures degrade to
the static catalog so routing is never blocked by registry persistence."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.model import ModelMetadata, RegistryEntry
from app.services import model_registry, registry_eligibility as eligibility
from app.services import model_registry_store as store
from app.services.provider_discovery import PROVIDERS, canonical_key

logger = get_logger(__name__)
_CACHE_TTL_SECONDS = 30
_STALE_SERVE_SECONDS = 600       # an expired live view this young is served at once while a background refresh runs
_EXPIRED = float("-inf")         # not 0.0: time.monotonic() can be small shortly after boot, making 0.0 look fresh
_cache: dict[str, Any] = {"at": _EXPIRED, "value": None}
_refreshing = threading.Event()
_ROUTING_EVIDENCE_REASONS = {"lifecycle_excluded", "inference_verification_failed"}
_LIVE_OVERRIDE_STATES = {"deprecated", "unavailable", "retired"}


class LiveState:
    def __init__(self, snapshots=None, verifications=None, refresh=None, available=False):
        self.snapshots = {canonical_key(s.provider, s.model_id): s for s in (snapshots or [])}
        self.verifications = verifications or {}
        self.refresh = {r["provider"]: r for r in (refresh or [])}
        self.available = available


def invalidate_cache() -> None:
    _cache.update(at=_EXPIRED, value=None)


def _load_live_state() -> LiveState:
    try:
        return LiveState(store.get_current_snapshots(), store.get_current_verifications(), store.get_refresh_status(), True)
    except Exception:  # migration not applied, DB down, ...: static catalog keeps working
        logger.warning("Live registry unavailable; using static catalog only.")
        return LiveState()


def _refresh_live_in_background() -> None:
    if _refreshing.is_set():
        return
    _refreshing.set()

    def work():
        try:
            _cache.update(at=time.monotonic(), value=_load_live_state())
        finally:
            _refreshing.clear()
    threading.Thread(target=work, name="live-registry-refresh", daemon=True).start()


def live_state(use_cache: bool = True) -> LiveState:
    """Live registry view. Stale-while-revalidate: an expired but recent view is served immediately and refreshed in the background."""
    if not store.is_enabled():
        return LiveState()
    if use_cache:
        cached, age = _cache["value"], time.monotonic() - _cache["at"]
        if cached is not None and age < _CACHE_TTL_SECONDS:
            return cached
        if cached is not None and cached.available and age < _STALE_SERVE_SECONDS:
            _refresh_live_in_background()
            return cached
    state = _load_live_state()
    _cache.update(at=time.monotonic(), value=state)
    return state


def _verification_for(state: LiveState, model: ModelMetadata) -> Optional[eligibility.Verification]:
    return state.verifications.get((model.provider.lower(), model.model_id))


def _freshness(state: LiveState, provider: str) -> tuple[Optional[str], bool]:
    row = state.refresh.get(provider.lower())
    last = row.get("last_success_at") if row else None
    if last is None:
        return None, state.available and provider.lower() in PROVIDERS
    stale = datetime.now(timezone.utc) - last > timedelta(minutes=settings.REGISTRY_REFRESH_TTL_MINUTES)
    return last.isoformat(), stale


def _overlay_static(model: ModelMetadata, live: Optional[ModelMetadata]) -> ModelMetadata:
    """Apply provider-reported lifecycle evidence to a curated static entry without touching its scores."""
    if live is None:
        return model
    update: dict[str, Any] = {}
    if live.lifecycle_status in _LIVE_OVERRIDE_STATES:
        update.update(lifecycle_status=live.lifecycle_status, lifecycle_reason=live.lifecycle_reason,
                      deprecated_at=live.deprecated_at, retires_at=live.retires_at)
        if live.lifecycle_status == "unavailable":
            update["availability"] = "not_listed_by_provider"
    else:
        update["availability"] = "listed_by_provider" if live.lifecycle_status != "incompatible" else model.availability
        update["first_seen_at"] = live.first_seen_at
    return model.model_copy(update=update)


# Reasons that remove a model from comparison/routing. Credentials and adapters are deliberately absent:
# they only decide whether AI Compass can *execute* the model.
_KEYLESS_BLOCKERS = {"provider_disabled", "lifecycle_excluded", "inference_verification_failed", "metadata_incomplete"}
# A live-discovered model has no curated metadata, so verified inference evidence is part of *recommending* it (its identifier
# and metadata are unreliable until then). That is evidence about the model, not a credential: a missing key or adapter still
# only affects execution.
_LIVE_ONLY_BLOCKERS = _KEYLESS_BLOCKERS | {"inference_not_verified", "inference_verification_stale"}


def routing_blockers(model: ModelMetadata, reasons: list[str]) -> list[str]:
    """Eligibility reasons that remove a model from the recommendation pool. Credentials and adapters are never among them."""
    # Catalogue models with unknown price or context stay recommendable: the engine scores unknown values as unknown (lower
    # confidence, never a perfect score) and strict budget/privacy constraints still exclude them. Live-discovered models have
    # no curated metadata at all, so for them incomplete metadata does block.
    wanted = _LIVE_ONLY_BLOCKERS if eligibility.is_live_only(model) else _KEYLESS_BLOCKERS - {"metadata_incomplete"}
    return [r for r in reasons if r in wanted]


def _entry(model: ModelMetadata, origin: str, state: LiveState, evaluate: bool = True) -> RegistryEntry:
    from app.services import access_category, model_taxonomy
    if model.taxonomy_status == "unclassified":
        model = model_taxonomy.classify(model)
    verification = _verification_for(state, model)
    confirmed, stale = _freshness(state, model.provider) if model.entry_type == "inference_model" else (None, False)
    data = model.model_dump()
    data.update(access_category.profile_of(model).as_dict())
    data.update(catalog_origin=origin, catalog_last_confirmed_at=confirmed, catalog_stale=stale)
    if verification is not None:
        data["verification"] = {"status": verification.status, "error_code": verification.error_code,
                                "verified_at": verification.verified_at.isoformat()}
    entry = RegistryEntry(**data)
    if evaluate:
        result = eligibility.evaluate(model, verification=verification, catalog_stale=stale and origin == "live")
        entry.eligibility = {
            "eligible": result.eligible, "reasons": result.explain(),
            "warnings": [{"code": w, "message": eligibility.WARNINGS.get(w, w)} for w in result.warnings],
        }
        blockers = routing_blockers(model, result.reasons)
        routable = model.entry_type == "inference_model" and not blockers
        entry.routing_eligible = routable
        entry.comparison_eligible = routable
        entry.execution_available = result.eligible
        entry.eligibility.update({
            "routing_eligible": routable,
            "routing_blockers": [{"code": r, "message": eligibility.REASONS.get(r, r)} for r in blockers],
            "execution_available": result.eligible,
            "execution_requirements": [{"code": r, "message": eligibility.REASONS.get(r, r)} for r in result.reasons if r not in blockers],
        })
    return entry


def build_registry(include_live: bool = True, include_retired: bool = False) -> list[RegistryEntry]:
    state = live_state()
    entries: list[RegistryEntry] = []
    known = set()
    for base in model_registry.api_models():
        status = model_registry._status(base)
        key = canonical_key(status.provider, status.model_id)
        known.add(key)
        entries.append(_entry(_overlay_static(status, state.snapshots.get(key)), "static", state))
    if include_retired:
        # Superseded generations never appear in active surfaces; they stay resolvable for history, logs and evaluations.
        from app.services.catalog import registry as catalog_registry
        for old in (m for m in catalog_registry.all_models() if m.catalog and m.catalog["publication"] == "retired"):
            retired = model_registry._status(old).model_copy(update={"active": False, "routing_eligible": False, "comparison_eligible": False, "execution_available": False})
            entries.append(_entry(retired, "static", state, evaluate=False))
    for app in model_registry.get_all_applications():
        item = app.model_copy(update={"inference_access_status": "not_applicable", "routing_eligible": False})
        entries.append(_entry(item, "application", state, evaluate=False))
    if include_live:
        for key, snap in state.snapshots.items():
            if key not in known:
                entries.append(_entry(snap, "live", state))
    return entries


def apply_live_registry(models: list[ModelMetadata]) -> tuple[list[ModelMetadata], list[dict]]:
    """Adjust the routing candidate list using live evidence. Fail-open to the input on any problem."""
    state = live_state()
    if not state.available:
        return models, []
    kept: list[ModelMetadata] = []
    exclusions: list[dict] = []
    seen = set()
    try:
        for model in models:
            key = canonical_key(model.provider, model.model_id)
            seen.add(key)
            effective = _overlay_static(model, state.snapshots.get(key))
            result = eligibility.evaluate(effective, verification=_verification_for(state, effective))
            blocking = [r for r in result.reasons if r in _ROUTING_EVIDENCE_REASONS]
            if blocking:
                exclusions.append({"model_id": model.model_id,
                                   "reason": "Live registry: " + "; ".join(eligibility.REASONS[r] for r in blocking)})
            else:
                kept.append(model)
        for key, snap in state.snapshots.items():
            if key in seen:
                continue
            result = eligibility.evaluate(snap, verification=state.verifications.get((snap.provider.lower(), snap.model_id)))
            if not routing_blockers(snap, result.reasons):
                # Recommendation-eligible once verified with complete metadata. `result.eligible` additionally needs a credential
                # and an adapter, so it only decides whether the model can be executed.
                kept.append(snap.model_copy(update={"active": True, "routing_eligible": True,
                                                    "availability": "configured" if result.eligible else "configuration_required_for_inference",
                                                    "inference_access_status": "validated"}))
    except Exception:
        logger.exception("Live registry overlay failed; using static catalog.")
        return models, []
    return kept, exclusions


def provider_status() -> list[dict]:
    state = live_state(use_cache=False)
    rows = []
    for key, display in PROVIDERS.items():
        row = state.refresh.get(key) or {}
        confirmed, stale = _freshness(state, display)
        rows.append({
            "provider": key, "display_name": display, "configured": eligibility.provider_configured(display),
            "disabled": eligibility.provider_disabled(display), "status": row.get("status"), "last_attempt_status": row.get("status"),
            "last_attempt_at": row["started_at"].isoformat() if row.get("started_at") else None,
            "last_success_at": confirmed, "stale": stale if state.available else None,
            "error_code": row.get("error_code"), "error_message": row.get("error_message_safe"),
            "entries_seen": row.get("entries_seen"), "entries_new": row.get("entries_new"),
            "entries_changed": row.get("entries_changed"), "entries_missing": row.get("entries_missing"),
            "entries_rejected": row.get("entries_rejected"),
        })
    return rows
