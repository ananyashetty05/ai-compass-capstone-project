"""Append-only persistence for provider model-list discoveries.

The module remains inactive until the additive migration is applied to an approved
Neon database. It never falls back to a production URL in tests.
"""
from __future__ import annotations
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

from app.core.config import settings
from app.schemas.model import ModelMetadata

LEASE_MINUTES = 5

class RegistryPersistenceUnavailable(RuntimeError):
    """The approved registry migration/database is not available."""

def _conn():
    if not settings.LIVE_REGISTRY_ENABLED or psycopg is None or not settings.DATABASE_URL:
        raise RegistryPersistenceUnavailable("Live registry persistence is not configured.")
    return psycopg.connect(settings.DATABASE_URL, row_factory=dict_row)

def _now() -> datetime:
    return datetime.now(timezone.utc)

def get_current_snapshots() -> list[ModelMetadata]:
    with _conn() as conn:
        rows = conn.execute("SELECT snapshot FROM current_model_catalog_snapshots ORDER BY provider, model_id").fetchall()
    return [ModelMetadata.model_validate(row["snapshot"]) for row in rows]

def get_refresh_status() -> list[dict]:
    with _conn() as conn:
        return conn.execute("""SELECT DISTINCT ON (provider) provider, status, started_at, finished_at,
            last_success_at, error_code, error_message_safe FROM provider_catalog_refreshes
            ORDER BY provider, started_at DESC""").fetchall()

def get_refresh_history(provider: str | None = None, limit: int = 50) -> list[dict]:
    with _conn() as conn:
        if provider:
            return conn.execute("""SELECT provider, status, started_at, finished_at, last_success_at, error_code, error_message_safe
                FROM provider_catalog_refreshes WHERE provider = %s ORDER BY started_at DESC LIMIT %s""", (provider, limit)).fetchall()
        return conn.execute("""SELECT provider, status, started_at, finished_at, last_success_at, error_code, error_message_safe
            FROM provider_catalog_refreshes ORDER BY started_at DESC LIMIT %s""", (limit,)).fetchall()

def get_lifecycle_history(provider: str, model_id: str, limit: int = 50) -> list[dict]:
    with _conn() as conn:
        return conn.execute("""SELECT event_type, previous_status, new_status, occurred_at, refresh_id
            FROM model_lifecycle_events events JOIN model_catalog_snapshots snapshots ON snapshots.snapshot_id = events.snapshot_id
            WHERE snapshots.provider = %s AND snapshots.model_id = %s ORDER BY occurred_at DESC LIMIT %s""",
            (provider, model_id, limit)).fetchall()

def _acquire_lease(provider: str) -> str | None:
    now, refresh_id = _now(), str(uuid.uuid4())
    with _conn() as conn:
        conn.execute("""UPDATE provider_catalog_refreshes SET status = 'abandoned', finished_at = %s,
            error_code = 'lease_expired', error_message_safe = 'Refresh lease expired before completion.'
            WHERE provider = %s AND status = 'running' AND lease_expires_at < %s""", (now, provider, now))
        try:
            conn.execute("""INSERT INTO provider_catalog_refreshes
                (refresh_id, provider, status, started_at, lease_expires_at)
                VALUES (%s, %s, 'running', %s, %s)""", (refresh_id, provider, now, now + timedelta(minutes=LEASE_MINUTES)))
        except Exception:
            return None
    return refresh_id

def _finish_failure(refresh_id: str, code: str) -> None:
    with _conn() as conn:
        conn.execute("""UPDATE provider_catalog_refreshes SET status = 'failed', finished_at = %s,
            error_code = %s, error_message_safe = 'Provider catalog refresh failed.' WHERE refresh_id = %s""",
            (_now(), code, refresh_id))

def refresh_provider(provider: str, discover: Callable[[], Iterable[ModelMetadata]]) -> dict:
    """Persist one successful provider list. Caller must enforce authorization."""
    refresh_id = _acquire_lease(provider)
    if not refresh_id:
        return {"provider": provider, "status": "running"}
    try:
        entries = list(discover())
        seen: set[str] = set()
        if any(not item.model_id or item.provider.lower() != provider.lower() or item.model_id in seen or seen.add(item.model_id) for item in entries):
            raise ValueError("invalid_provider_response")
        now = _now()
        with _conn() as conn:
            prior = {row["model_id"]: row["lifecycle_status"] for row in conn.execute(
                "SELECT model_id, lifecycle_status FROM current_model_catalog_snapshots WHERE provider = %s", (provider,)).fetchall()}
            for item in entries:
                snapshot_id = str(uuid.uuid4())
                conn.execute("""INSERT INTO model_catalog_snapshots
                    (snapshot_id, provider, model_id, snapshot, lifecycle_status, adapter_compatible, metadata_status, discovered_at, refresh_id)
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                    (snapshot_id, provider, item.model_id, json.dumps(item.model_dump(mode="json")), item.lifecycle_status,
                     item.adapter_compatible, item.metadata_status, now, refresh_id))
                conn.execute("""INSERT INTO model_lifecycle_events
                    (event_id, snapshot_id, event_type, previous_status, new_status, occurred_at, refresh_id)
                    VALUES (%s, %s, 'discovered', %s, %s, %s, %s)""",
                    (str(uuid.uuid4()), snapshot_id, prior.get(item.model_id), item.lifecycle_status, now, refresh_id))
            # Absence is meaningful only after this provider returned a successful list.
            # Preserve the former snapshot and append an unavailable successor.
            for model_id in set(prior) - {item.model_id for item in entries}:
                previous = conn.execute("""SELECT snapshot FROM current_model_catalog_snapshots
                    WHERE provider = %s AND model_id = %s""", (provider, model_id)).fetchone()
                if not previous:
                    continue
                unavailable = ModelMetadata.model_validate(previous["snapshot"]).model_copy(update={
                    "active": False, "routing_eligible": False, "availability": "unavailable",
                    "lifecycle_status": "unavailable",
                })
                snapshot_id = str(uuid.uuid4())
                conn.execute("""INSERT INTO model_catalog_snapshots
                    (snapshot_id, provider, model_id, snapshot, lifecycle_status, adapter_compatible, metadata_status, discovered_at, refresh_id)
                    VALUES (%s, %s, %s, %s::jsonb, 'unavailable', %s, %s, %s, %s)""",
                    (snapshot_id, provider, model_id, json.dumps(unavailable.model_dump(mode="json")),
                     unavailable.adapter_compatible, unavailable.metadata_status, now, refresh_id))
                conn.execute("""INSERT INTO model_lifecycle_events
                    (event_id, snapshot_id, event_type, previous_status, new_status, occurred_at, refresh_id)
                    VALUES (%s, %s, 'missing_from_successful_refresh', %s, 'unavailable', %s, %s)""",
                    (str(uuid.uuid4()), snapshot_id, prior[model_id], now, refresh_id))
            conn.execute("""UPDATE provider_catalog_refreshes SET status = 'success', finished_at = %s, last_success_at = %s
                            WHERE refresh_id = %s""", (now, now, refresh_id))
        return {"provider": provider, "status": "success", "refresh_id": refresh_id, "entries": len(entries)}
    except ValueError as exc:
        _finish_failure(refresh_id, str(exc))
    except Exception:
        _finish_failure(refresh_id, "provider_unavailable")
    return {"provider": provider, "status": "failed"}
