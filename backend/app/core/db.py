"""Small reusable PostgreSQL connection pool (no extra dependency).

Why: every request used to open several brand-new TLS connections to the database (catalogue version, live registry, telemetry,
learning, three decision-record writes). Connection setup, not the queries, dominated the request time. This keeps a few idle
connections for reuse.

Drop-in for ``with psycopg.connect(...) as conn:``: the block commits on success, rolls back on error, and the connection goes back
to the pool instead of closing. Idle connections are validated before reuse (a serverless database closes idle sessions) and retired
after ``MAX_AGE``. Prepared statements are disabled so reuse is also safe behind a transaction-pooling endpoint.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    import psycopg
except Exception:                                    # pragma: no cover - psycopg is optional at import time
    psycopg = None

MAX_IDLE = 4            # idle connections kept per distinct (dsn, options)
MAX_AGE = 240.0         # seconds a connection may live before it is retired
VALIDATE_AFTER = 20.0   # idle seconds after which a connection is checked with SELECT 1 before use

_pools: Dict[Tuple, "_Pool"] = {}
_pools_lock = threading.Lock()


class _Pool:
    def __init__(self, dsn: str, kwargs: dict):
        self.dsn, self.kwargs = dsn, kwargs
        self._idle: List[Tuple[Any, float, float]] = []      # (connection, created_at, last_used_at)
        self._lock = threading.Lock()

    def _new(self):
        return psycopg.connect(self.dsn, **self.kwargs), time.monotonic()

    def acquire(self):
        while True:
            with self._lock:
                item = self._idle.pop() if self._idle else None
            if item is None:
                return self._new()
            conn, created, last = item
            now = time.monotonic()
            if conn.closed or now - created > MAX_AGE:
                _close(conn)
                continue
            if now - last > VALIDATE_AFTER:
                try:
                    conn.execute("SELECT 1")
                    conn.rollback()
                except Exception:
                    _close(conn)
                    continue
            return conn, created

    def release(self, conn, created: float, healthy: bool) -> None:
        if not healthy or conn.closed:
            _close(conn)
            return
        with self._lock:
            if len(self._idle) < MAX_IDLE:
                self._idle.append((conn, created, time.monotonic()))
                return
        _close(conn)

    def close_all(self) -> None:
        with self._lock:
            idle, self._idle = self._idle, []
        for conn, _, _ in idle:
            _close(conn)


def _close(conn) -> None:
    try:
        conn.close()
    except Exception:
        pass


class _Lease:
    """Context manager with the commit/rollback semantics of ``with psycopg.connect(...)``."""
    def __init__(self, pool: _Pool):
        self._pool, self._conn, self._created = pool, None, 0.0

    def __enter__(self):
        self._conn, self._created = self._pool.acquire()
        return self._conn

    def __exit__(self, exc_type, exc, tb):
        conn, healthy = self._conn, True
        try:
            if exc_type is None:
                conn.commit()
            else:
                conn.rollback()
        except Exception:
            healthy = False
        self._pool.release(conn, self._created, healthy)
        return False


def connect(dsn: str, **kwargs):
    """Pooled replacement for ``psycopg.connect``. Use only as ``with connect(...) as conn``."""
    if psycopg is None:
        raise RuntimeError("PostgreSQL support is unavailable; install psycopg[binary].")
    kwargs.setdefault("connect_timeout", 5)
    kwargs["prepare_threshold"] = None
    key = (dsn, tuple(sorted((k, repr(v)) for k, v in kwargs.items())))
    with _pools_lock:
        pool = _pools.get(key)
        if pool is None:
            pool = _pools[key] = _Pool(dsn, kwargs)
    return _Lease(pool)


def prewarm(dsn: str, n: int = 3, **kwargs) -> int:
    """Open ``n`` connections ahead of the first request. Best effort; never raises."""
    opened: List[Any] = []
    try:
        leases = [connect(dsn, **kwargs) for _ in range(n)]
        for lease in leases:
            opened.append((lease, lease.__enter__()))
        return len(opened)
    except Exception:
        return len(opened)
    finally:
        for lease, _ in opened:
            lease.__exit__(None, None, None)


def reset_for_tests() -> None:
    with _pools_lock:
        pools, _ = list(_pools.values()), _pools.clear()
    for p in pools:
        p.close_all()
