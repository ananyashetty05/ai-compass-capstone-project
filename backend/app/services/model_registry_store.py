"""Append-only persistence for the live model registry (Neon PostgreSQL).

Inactive until LIVE_REGISTRY_ENABLED is true *and* the additive migration
``migrations/20261118_live_model_registry.sql`` has been applied to an approved
database. Reads never trigger provider discovery. Provider failures never alter
stored snapshots (last-known-good data is preserved).
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

try:
    import psycopg
    from psycopg.errors import UniqueViolation
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - psycopg is a declared dependency
    psycopg = None
    UniqueViolation = None
    dict_row = None

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.model import ModelMetadata
from app.services import registry_lifecycle as lifecycle
from app.services.registry_eligibility import Verification

logger = get_logger(__name__)
LEASE_MINUTES = 5  # must exceed worst-case discovery time (provider timeout x pages)


class RegistryPersistenceUnavailable(RuntimeError):
    """The approved registry migration/database is not available."""


def is_enabled() -> bool:
    return bool(settings.LIVE_REGISTRY_ENABLED and psycopg is not None and settings.DATABASE_URL)


def _conn():
    if not is_enabled():
        raise RegistryPersistenceUnavailable("Live registry persistence is not configured.")
    return psycopg.connect(settings.DATABASE_URL, row_factory=dict_row, connect_timeout=5)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _key(provider: str) -> str:
    return provider.strip().lower()


def _hash(snapshot: dict) -> str:
    stable = {k: v for k, v in snapshot.items() if k != "last_verified_at"}
    return hashlib.sha256(json.dumps(stable, sort_keys=True, default=str).encode()).hexdigest()


# ── reads ────────────────────────────────────────────────────────────────────

def get_current_snapshots() -> list[ModelMetadata]:
    with _conn() as conn:
        rows = conn.execute("SELECT snapshot FROM current_model_catalog_snapshots ORDER BY provider, model_id").fetchall()
    return [ModelMetadata.model_validate(row["snapshot"]) for row in rows]


def get_current_verifications() -> dict[tuple[str, str], Verification]:
    with _conn() as conn:
        rows = conn.execute("SELECT provider, model_id, status, error_code, verified_at FROM current_inference_verifications").fetchall()
    return {(r["provider"], r["model_id"]): Verification(r["status"], r["verified_at"], r["error_code"]) for r in rows}


_REFRESH_COLS = ("provider, status, trigger, started_at, finished_at, last_success_at, error_code, error_message_safe, "
                 "entries_seen, entries_new, entries_changed, entries_missing, entries_rejected")


def get_refresh_status() -> list[dict]:
    """Latest attempt per provider plus the last *successful* refresh time."""
    with _conn() as conn:
        return conn.execute(f"""
            SELECT DISTINCT ON (r.provider) r.provider, r.status, r.trigger, r.started_at, r.finished_at,
                   r.error_code, r.error_message_safe, r.entries_seen, r.entries_new, r.entries_changed,
                   r.entries_missing, r.entries_rejected,
                   (SELECT MAX(s.last_success_at) FROM provider_catalog_refreshes s
                      WHERE s.provider = r.provider AND s.status = 'success') AS last_success_at
            FROM provider_catalog_refreshes r ORDER BY r.provider, r.started_at DESC""").fetchall()


def get_refresh_history(provider: str | None = None, limit: int = 50) -> list[dict]:
    with _conn() as conn:
        if provider:
            return conn.execute(f"SELECT {_REFRESH_COLS} FROM provider_catalog_refreshes WHERE provider = %s "
                                "ORDER BY started_at DESC LIMIT %s", (_key(provider), limit)).fetchall()
        return conn.execute(f"SELECT {_REFRESH_COLS} FROM provider_catalog_refreshes ORDER BY started_at DESC LIMIT %s",
                            (limit,)).fetchall()


def get_lifecycle_history(provider: str, model_id: str, limit: int = 50) -> list[dict]:
    with _conn() as conn:
        return conn.execute("""SELECT event_type, previous_status, new_status, reason, occurred_at, refresh_id
            FROM model_lifecycle_events WHERE provider = %s AND model_id = %s
            ORDER BY occurred_at DESC LIMIT %s""", (_key(provider), model_id, limit)).fetchall()


def get_activity(limit: int = 50) -> list[dict]:
    """Auditable feed: lifecycle events and failed/abandoned refreshes, newest first."""
    with _conn() as conn:
        events = conn.execute("""SELECT 'lifecycle' AS kind, provider, model_id, event_type, previous_status, new_status,
            reason, occurred_at FROM model_lifecycle_events ORDER BY occurred_at DESC LIMIT %s""", (limit,)).fetchall()
        failures = conn.execute("""SELECT 'refresh_failure' AS kind, provider, NULL AS model_id, status AS event_type,
            NULL AS previous_status, NULL AS new_status, COALESCE(error_message_safe, error_code) AS reason,
            COALESCE(finished_at, started_at) AS occurred_at FROM provider_catalog_refreshes
            WHERE status IN ('failed', 'abandoned') ORDER BY started_at DESC LIMIT %s""", (limit,)).fetchall()
    return sorted([*events, *failures], key=lambda row: row["occurred_at"], reverse=True)[:limit]


def last_verification_at(provider: str, model_id: str) -> Optional[datetime]:
    with _conn() as conn:
        row = conn.execute("SELECT MAX(verified_at) AS at FROM model_inference_verifications WHERE provider = %s AND model_id = %s",
                           (_key(provider), model_id)).fetchone()
    return row["at"] if row else None


# ── refresh orchestration ───────────────────────────────────────────────────

def _acquire_lease(provider_key: str, trigger: str) -> str | None:
    """Return a refresh id, or None when another refresh holds an unexpired lease."""
    now, refresh_id = _now(), str(uuid.uuid4())
    with _conn() as conn:  # committed on exit
        conn.execute("""UPDATE provider_catalog_refreshes SET status = 'abandoned', finished_at = %s,
            error_code = 'lease_expired', error_message_safe = 'Refresh lease expired before completion.'
            WHERE provider = %s AND status = 'running' AND lease_expires_at < %s""", (now, provider_key, now))
    try:
        with _conn() as conn:
            conn.execute("""INSERT INTO provider_catalog_refreshes (refresh_id, provider, status, trigger, started_at, lease_expires_at)
                VALUES (%s, %s, 'running', %s, %s, %s)""",
                         (refresh_id, provider_key, trigger, now, now + timedelta(minutes=LEASE_MINUTES)))
    except UniqueViolation:
        return None
    return refresh_id


def _finish_failure(refresh_id: str, code: str, message: str) -> None:
    with _conn() as conn:
        conn.execute("""UPDATE provider_catalog_refreshes SET status = 'failed', finished_at = %s, error_code = %s,
            error_message_safe = %s WHERE refresh_id = %s AND status = 'running'""", (_now(), code, message, refresh_id))


def _last_success(provider_key: str) -> Optional[datetime]:
    with _conn() as conn:
        row = conn.execute("SELECT MAX(last_success_at) AS at FROM provider_catalog_refreshes WHERE provider = %s AND status = 'success'",
                           (provider_key,)).fetchone()
    return row["at"] if row else None


def is_stale(provider_key: str) -> bool:
    last = _last_success(provider_key)
    return last is None or _now() - last > timedelta(minutes=settings.REGISTRY_REFRESH_TTL_MINUTES)


def _insert_snapshot(conn, item: ModelMetadata, provider_key: str, now: datetime, refresh_id: Optional[str]) -> str:
    snapshot_id = str(uuid.uuid4())
    data = item.model_dump(mode="json")
    conn.execute("""INSERT INTO model_catalog_snapshots (snapshot_id, provider, model_id, canonical_key, snapshot, content_hash,
        lifecycle_status, adapter_compatible, metadata_status, discovered_at, refresh_id)
        VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s)""",
                 (snapshot_id, provider_key, item.model_id, f"{provider_key}:{item.model_id}", json.dumps(data), _hash(data),
                  item.lifecycle_status, item.adapter_compatible, item.metadata_status, now, refresh_id))
    return snapshot_id


def _insert_event(conn, snapshot_id: str, provider_key: str, model_id: str, event_type: str, previous: Optional[str],
                  new: str, reason: str, now: datetime, refresh_id: Optional[str]) -> None:
    conn.execute("""INSERT INTO model_lifecycle_events (event_id, snapshot_id, provider, model_id, event_type, previous_status,
        new_status, reason, occurred_at, refresh_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                 (str(uuid.uuid4()), snapshot_id, provider_key, model_id, event_type, previous, new, reason, now, refresh_id))


def refresh_provider(provider: str, discover: Callable[[], Any], *, trigger: str = "manual", only_if_stale: bool = False) -> dict:
    """Run one provider refresh. ``discover`` returns an object with ``.entries`` and ``.rejected``
    (or raises ``DiscoveryError``). Caller must enforce authorization."""
    key = _key(provider)
    if only_if_stale and not is_stale(key):
        return {"provider": key, "status": "fresh", "skipped": True}
    refresh_id = _acquire_lease(key, trigger)
    if not refresh_id:
        return {"provider": key, "status": "already_running"}
    try:
        result = discover()
    except Exception as exc:  # DiscoveryError or anything unexpected: record a safe, classified failure
        kind = getattr(exc, "kind", "upstream")
        message = getattr(exc, "safe_message", "Provider model list is temporarily unavailable.")
        _finish_failure(refresh_id, kind, message)
        return {"provider": key, "status": "failed", "refresh_id": refresh_id, "error_code": kind}
    try:
        counts = _persist(key, refresh_id, list(result.entries), int(getattr(result, "rejected", 0)))
        return {"provider": key, "status": "success", "refresh_id": refresh_id, **counts}
    except Exception:
        logger.exception("Registry persistence failed for provider %s", key)
        try:
            _finish_failure(refresh_id, "persistence_error", "Provider catalog could not be stored.")
        except Exception:
            logger.exception("Could not record refresh failure for %s", key)
        return {"provider": key, "status": "failed", "refresh_id": refresh_id, "error_code": "persistence_error"}


def _persist(key: str, refresh_id: str, entries: list[ModelMetadata], rejected: int) -> dict:
    """One transaction: all snapshots/events for this refresh commit together or not at all."""
    now = _now()
    seen_ids = set()
    for item in entries:
        if not item.model_id or _key(item.provider) != key or item.model_id in seen_ids:
            raise ValueError("invalid_provider_response")
        seen_ids.add(item.model_id)
    new = changed = missing = 0
    with _conn() as conn:
        held = conn.execute("SELECT status FROM provider_catalog_refreshes WHERE refresh_id = %s FOR UPDATE", (refresh_id,)).fetchone()
        if not held or held["status"] != "running":
            raise RuntimeError("lease_lost")  # an abandoned refresh must not write
        prior = {r["model_id"]: r for r in conn.execute(
            "SELECT model_id, snapshot, content_hash FROM current_model_catalog_snapshots WHERE provider = %s", (key,)).fetchall()}
        verified = {r["model_id"] for r in conn.execute(
            "SELECT model_id FROM current_inference_verifications WHERE provider = %s AND status = 'validated'", (key,)).fetchall()}
        for item in entries:
            before = prior.get(item.model_id)
            provider_lifecycle = item.lifecycle_status if item.lifecycle_status in {"deprecated", "retired"} else None
            if before is None:
                status, reason = lifecycle.initial_status(adapter_compatible=item.adapter_compatible, provider_lifecycle=provider_lifecycle)
                first_seen, previous = now.isoformat(), None
            else:
                old = ModelMetadata.model_validate(before["snapshot"])
                status, reason = lifecycle.next_status(old.lifecycle_status, adapter_compatible=item.adapter_compatible,
                                                       provider_lifecycle=provider_lifecycle, inference_validated=item.model_id in verified)
                reason = reason or old.lifecycle_reason or ""
                first_seen, previous = old.first_seen_at or now.isoformat(), old.lifecycle_status
            updated = item.model_copy(update={"lifecycle_status": status, "lifecycle_reason": reason or None, "first_seen_at": first_seen,
                                              "consecutive_missing_refreshes": 0})
            data = updated.model_dump(mode="json")
            if before is not None and _hash(data) == before["content_hash"]:
                continue  # idempotent: identical catalog content appends nothing
            snapshot_id = _insert_snapshot(conn, updated, key, now, refresh_id)
            if before is None:
                new += 1
                _insert_event(conn, snapshot_id, key, item.model_id, "discovered", None, status, reason, now, refresh_id)
            else:
                changed += 1
                kind = "status_changed" if previous != status else "metadata_changed"
                _insert_event(conn, snapshot_id, key, item.model_id, kind, previous, status, reason or "Provider metadata changed.", now, refresh_id)
        if rejected == 0:  # absence is meaningful only when every returned row was understood
            for model_id in set(prior) - seen_ids:
                old = ModelMetadata.model_validate(prior[model_id]["snapshot"])
                count = old.consecutive_missing_refreshes + 1
                status, reason = lifecycle.after_missing(old.lifecycle_status, count, settings.REGISTRY_MISSING_REFRESHES_BEFORE_UNAVAILABLE)
                if old.lifecycle_status in {"unavailable", "retired"}:
                    continue
                successor = old.model_copy(update={"consecutive_missing_refreshes": count, "lifecycle_status": status,
                                                   "lifecycle_reason": reason or old.lifecycle_reason,
                                                   "availability": "unavailable" if status == "unavailable" else old.availability})
                snapshot_id = _insert_snapshot(conn, successor, key, now, refresh_id)
                _insert_event(conn, snapshot_id, key, model_id, "missing_from_successful_refresh", old.lifecycle_status, status,
                              reason or f"Absent from {count} successful provider list(s); retained until the threshold.", now, refresh_id)
                missing += 1
        conn.execute("""UPDATE provider_catalog_refreshes SET status = 'success', finished_at = %s, last_success_at = %s,
            entries_seen = %s, entries_new = %s, entries_changed = %s, entries_missing = %s, entries_rejected = %s
            WHERE refresh_id = %s""", (now, now, len(entries), new, changed, missing, rejected, refresh_id))
    return {"entries_seen": len(entries), "entries_new": new, "entries_changed": changed, "entries_missing": missing, "entries_rejected": rejected}


# ── inference verification persistence ───────────────────────────────────────

def record_verification(provider: str, model_id: str, status: str, error_code: Optional[str], latency_ms: Optional[int]) -> None:
    now, key = _now(), _key(provider)
    with _conn() as conn:
        conn.execute("""INSERT INTO model_inference_verifications (verification_id, provider, model_id, status, error_code, latency_ms, verified_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)""", (str(uuid.uuid4()), key, model_id, status, error_code, latency_ms, now))
        current = conn.execute("SELECT snapshot FROM current_model_catalog_snapshots WHERE provider = %s AND model_id = %s",
                               (key, model_id)).fetchone()
        old = ModelMetadata.model_validate(current["snapshot"]) if current else None
        state = old.lifecycle_status if old else "active"
        conn.execute("""INSERT INTO model_lifecycle_events (event_id, snapshot_id, provider, model_id, event_type, previous_status,
            new_status, reason, occurred_at, refresh_id) VALUES (%s, NULL, %s, %s, %s, %s, %s, %s, %s, NULL)""",
                     (str(uuid.uuid4()), key, model_id, "inference_verified" if status == "validated" else "inference_verification_failed",
                      state if old else None, state,
                      "Inference access verified." if status == "validated" else f"Inference verification failed ({error_code}).", now))
        if old and status == "validated" and old.lifecycle_status == lifecycle.PENDING_VALIDATION:
            promoted = old.model_copy(update={"lifecycle_status": lifecycle.ACTIVE, "lifecycle_reason": "Inference access verified."})
            snapshot_id = _insert_snapshot(conn, promoted, key, now, None)
            _insert_event(conn, snapshot_id, key, model_id, "status_changed", old.lifecycle_status, lifecycle.ACTIVE,
                          "Inference access verified.", now, None)
