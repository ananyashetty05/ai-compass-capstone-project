"""Persistence for the catalogue. One authoritative store; ``MemoryStore`` for tests/seed-only, ``PgStore`` for Neon.

``commit`` is atomic and optimistic: it succeeds only if the stored version still equals the version that was loaded.
Models are never deleted (history stays readable); retirement is a state, not a row removal.
"""
from __future__ import annotations

import copy
import json
import threading
from contextlib import contextmanager
from dataclasses import asdict
from typing import Optional

from app.core.config import settings
from app.services.catalog.state import (CatalogState, Event, state_from_dict, state_to_dict)

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
except ImportError:  # pragma: no cover
    psycopg = None
    dict_row = None
    Jsonb = None

_TABLE_KEYS = {"developers": ("catalog_developers", "slug"), "lineages": ("catalog_lineages", "lineage_key"), "generations": ("catalog_generations", "generation_key"),
               "models": ("catalog_models", "canonical_key"), "offerings": ("catalog_offerings", "offering_key"), "sources": ("catalog_sources", "source_id")}


class StoreUnavailable(RuntimeError):
    pass


class MemoryStore:
    def __init__(self, state: Optional[CatalogState] = None):
        self._state = state or CatalogState()
        self.events: list = []
        self.runs: list = []
        self._lock = threading.Lock()
        self.fail_commits = False

    def version(self) -> int:
        return self._state.version

    def load(self) -> CatalogState:
        return copy.deepcopy(self._state)

    @contextmanager
    def try_lock(self):
        got = self._lock.acquire(blocking=False)
        try:
            yield got
        finally:
            if got:
                self._lock.release()

    def commit(self, state, events, report, *, expected_version: int, bump: bool) -> bool:
        if self.fail_commits:
            raise StoreUnavailable("simulated database failure")
        if self._state.version != expected_version:
            return False
        self._state = copy.deepcopy(state)
        self.events.extend(copy.deepcopy(events))
        self.runs.append(copy.deepcopy(report))
        return True

    def recent_events(self, limit: int = 50, event_types: Optional[set] = None) -> list:
        evs = [e for e in reversed(self.events) if not event_types or e.event_type in event_types]
        return [asdict(e) for e in evs[:limit]]

    def recent_runs(self, limit: int = 20) -> list:
        return [asdict(r) for r in reversed(self.runs[-limit:])]

    def model_history(self, key: str, limit: int = 50) -> list:
        return [asdict(e) for e in reversed(self.events) if e.entity_key == key][:limit]


class PgStore:
    """Normalised tables (see migrations/20261121_model_catalog.sql). Row payloads are JSONB; keys, states and FKs are real columns."""
    LOCK_KEY = 7314202

    def __init__(self, dsn: Optional[str] = None):
        if psycopg is None:
            raise StoreUnavailable("psycopg is not installed")
        self._dsn = dsn or settings.DATABASE_URL
        if not self._dsn:
            raise StoreUnavailable("DATABASE_URL is not configured")
        self._fp: dict = {}

    def _conn(self, autocommit: bool = False):
        # prepare_threshold=None: safe behind a transaction-pooling endpoint (Neon pooler) as well as a direct one.
        if not autocommit:
            from app.core import db      # reused connections; commit/rollback semantics identical to `with psycopg.connect(...)`
            return db.connect(self._dsn, row_factory=dict_row, connect_timeout=5)
        return psycopg.connect(self._dsn, row_factory=dict_row, connect_timeout=5, prepare_threshold=None, autocommit=autocommit)

    def version(self) -> int:
        with self._conn() as c:
            row = c.execute("SELECT version FROM catalog_meta WHERE id = 1").fetchone()
        return row["version"] if row else 0

    def load(self) -> CatalogState:
        data: dict = {"version": 0, "published_at": None}
        with self._conn() as c, c.transaction():
            meta = c.execute("SELECT version, published_at FROM catalog_meta WHERE id = 1").fetchone()
            if meta:
                data["version"], data["published_at"] = meta["version"], meta["published_at"].isoformat() if meta["published_at"] else None
            for name, (table, key) in _TABLE_KEYS.items():
                data[name] = {r[key]: r["data"] for r in c.execute(f"SELECT {key}, data FROM {table}").fetchall()}
        self._fp = {n: {k: _fp(v) for k, v in data[n].items()} for n in _TABLE_KEYS}
        return state_from_dict(data)

    @contextmanager
    def try_lock(self):
        # Single-flight is an optimisation only (correctness comes from the versioned commit). It MUST be transaction-scoped: behind a
        # transaction-pooling endpoint (Neon pooler) a session-level lock is taken on one server connection and "unlocked" on another,
        # leaks, and then blocks every later refresh. An xact lock is held inside ONE transaction and Postgres releases it on commit,
        # rollback or client death. (Lock key bumped from 7314201: that key may still be held by a leaked session-level lock.)
        with self._conn() as conn, conn.transaction():
            got = conn.execute("SELECT pg_try_advisory_xact_lock(%s) AS ok", (self.LOCK_KEY,)).fetchone()["ok"]
            yield got

    def commit(self, state, events, report, *, expected_version: int, bump: bool) -> bool:
        payload = state_to_dict(state)
        with self._conn() as c, c.transaction():
            c.execute("INSERT INTO catalog_meta (id, version) VALUES (1, 0) ON CONFLICT (id) DO NOTHING")   # race-safe first run
            row = c.execute("SELECT version FROM catalog_meta WHERE id = 1 FOR UPDATE").fetchone()
            if row["version"] != expected_version:
                return False
            # parents before children so foreign keys hold
            for name in ("developers", "lineages", "generations", "models", "offerings", "sources"):
                table, key = _TABLE_KEYS[name]
                for k, v in payload[name].items():
                    if self._fp.get(name, {}).get(k) == _fp(v):
                        continue
                    cols, vals = _columns(name, k, v)
                    names = ", ".join([key] + list(cols) + ["data", "updated_at"])
                    marks = ", ".join(["%s"] * (len(cols) + 2) + ["now()"])          # key + columns + data, then the timestamp
                    sets = ", ".join(f"{col} = EXCLUDED.{col}" for col in list(cols) + ["data"]) + ", updated_at = now()"
                    c.execute(f"INSERT INTO {table} ({names}) VALUES ({marks}) ON CONFLICT ({key}) DO UPDATE SET {sets}", [k, *vals, Jsonb(v)])
            for e in events:
                c.execute("INSERT INTO catalog_events (occurred_at, event_type, entity_type, entity_key, from_state, to_state, reason, run_id) "
                          "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", [e.occurred_at, e.event_type, e.entity_type, e.entity_key, e.from_state, e.to_state, e.reason, e.run_id])
            c.execute("INSERT INTO catalog_refresh_runs (run_id, trigger, started_at, finished_at, status, summary) VALUES (%s,%s,%s,%s,%s,%s) "
                      "ON CONFLICT (run_id) DO NOTHING", [report.run_id, report.trigger, report.started_at, report.finished_at, report.status, Jsonb(_report_summary(report))])
            if bump:
                c.execute("UPDATE catalog_meta SET version = %s, published_at = %s WHERE id = 1", [state.version, state.published_at])
        return True

    def recent_events(self, limit: int = 50, event_types: Optional[set] = None) -> list:
        sql, args = "SELECT occurred_at, event_type, entity_type, entity_key, from_state, to_state, reason, run_id FROM catalog_events", []
        if event_types:
            sql += " WHERE event_type = ANY(%s)"
            args.append(list(event_types))
        with self._conn() as c:
            rows = c.execute(sql + " ORDER BY id DESC LIMIT %s", [*args, limit]).fetchall()
        return [{**r, "occurred_at": r["occurred_at"].isoformat()} for r in rows]

    def recent_runs(self, limit: int = 20) -> list:
        with self._conn() as c:
            rows = c.execute("SELECT run_id, trigger, started_at, finished_at, status, summary FROM catalog_refresh_runs ORDER BY started_at DESC LIMIT %s", [limit]).fetchall()
        return [{**r, "started_at": r["started_at"].isoformat(), "finished_at": r["finished_at"].isoformat() if r["finished_at"] else None} for r in rows]

    def model_history(self, key: str, limit: int = 50) -> list:
        with self._conn() as c:
            rows = c.execute("SELECT occurred_at, event_type, from_state, to_state, reason FROM catalog_events WHERE entity_key = %s ORDER BY id DESC LIMIT %s", [key, limit]).fetchall()
        return [{**r, "occurred_at": r["occurred_at"].isoformat()} for r in rows]


def _fp(v) -> str:
    return json.dumps(v, sort_keys=True, default=str)


def _columns(name: str, key: str, v: dict):
    if name == "lineages":
        return ("developer_slug",), (v.get("developer"),)
    if name == "generations":
        return ("lineage_key", "retention", "verification"), (v["lineage_key"], v["retention"], v["verification"])
    if name == "models":
        return (("developer_slug", "lineage_key", "generation_key", "verification", "retention", "lifecycle", "publication", "availability"),
                (v.get("developer"), v["lineage_key"], v.get("generation_key"), v["verification"], v["retention"], v["lifecycle"], v["publication"], v["availability"]))
    if name == "offerings":
        return ("canonical_key", "provider", "listed"), (v["canonical_key"], v["provider"], v["listed"])
    if name == "sources":
        return ("status",), (v["status"],)
    return (), ()


def _report_summary(r) -> dict:
    return {"sources": r.sources, "counts": r.counts, "notes": r.notes[:10], "unregistered_developers": r.unregistered_developers, "version": r.version}
