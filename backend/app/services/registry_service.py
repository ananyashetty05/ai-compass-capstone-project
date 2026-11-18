"""Read-side composition of the live registry: static catalog + live snapshots +
inference verifications + eligibility. Never calls providers; all failures degrade to
the static catalog so routing is never blocked by registry persistence."""
from __future__ import annotations

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
_cache: dict[str, Any] = {"at": 0.0, "value": None}
_ROUTING_EVIDENCE_REASONS = {"lifecycle_excluded", "inference_verification_failed"}
_LIVE_OVERRIDE_STATES = {"deprecated", "unavailable", "retired"}


class LiveState:
    def __init__(self, snapshots=None, verifications=None, refresh=None, available=False):
        self.snapshots = {canonical_key(s.provider, s.model_id): s for s in (snapshots or [])}
        self.verifications = verifications or {}
        self.refresh = {r["provider"]: r for r in (refresh or [])}
        self.available = available


def invalidate_cache() -> None:
    _cache.update(at=0.0, value=None)


def live_state(use_cache: bool = True) -> LiveState:
    if not store.is_enabled():
        return LiveState()
    if use_cache and _cache["value"] is not None and time.monotonic() - _cache["at"] < _CACHE_TTL_SECONDS:
        return _cache["value"]
    try:
        state = LiveState(store.get_current_snapshots(), store.get_current_verifications(), store.get_refresh_status(), True)
    except Exception:  # migration not applied, DB down, ...: static catalog keeps working
        logger.warning("Live registry unavailable; using static catalog only.")
        state = LiveState()
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


def _entry(model: ModelMetadata, origin: str, state: LiveState, evaluate: bool = True) -> RegistryEntry:
    verification = _verification_for(state, model)
    confirmed, stale = _freshness(state, model.provider) if model.entry_type == "inference_model" else (None, False)
    data = model.model_dump()
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
        entry.routing_eligible = result.eligible
    return entry


def build_registry(include_live: bool = True) -> list[RegistryEntry]:
    state = live_state()
    entries: list[RegistryEntry] = []
    known = set()
    for base in model_registry._API_MODELS:
        status = model_registry._status(base)
        key = canonical_key(status.provider, status.model_id)
        known.add(key)
        entries.append(_entry(_overlay_static(status, state.snapshots.get(key)), "static", state))
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
            if result.eligible:
                kept.append(snap.model_copy(update={"active": True, "routing_eligible": True, "availability": "configured",
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
