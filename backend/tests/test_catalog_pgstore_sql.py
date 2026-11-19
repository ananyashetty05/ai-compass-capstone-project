"""PgStore SQL composition, verified against a recording fake connection (no live database is available in CI).

This proves statement shape, placeholder/parameter agreement, FK-safe ordering and the optimistic-version path. It does NOT
prove the SQL executes on PostgreSQL: that needs the migration applied to a disposable database.
"""
import re
from contextlib import contextmanager

import pytest

from app.services.catalog import engine, store as store_mod
from app.services.catalog.state import state_to_dict
from tests.test_catalog_lifecycle import FakeSource, G3, G4, dev, run, store_with


class Cur:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row

    def fetchall(self):
        return []


class FakeConn:
    def __init__(self, version=0):
        self.sql, self.version = [], version

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    @contextmanager
    def transaction(self):
        yield

    def execute(self, sql, params=None):
        self.sql.append((" ".join(sql.split()), list(params or [])))
        if "FOR UPDATE" in sql:
            return Cur({"version": self.version})
        return Cur()


def make_store(conn):
    pg = store_mod.PgStore.__new__(store_mod.PgStore)
    pg._dsn, pg._fp = "x", {}
    pg._conn = lambda autocommit=False: conn
    return pg


def committed(version_in_db=0):
    src = store_with(dev("acme"))
    run(src, FakeSource(batches=[[G3, G4]]))
    state, conn = src.load(), FakeConn(version_in_db)
    report = engine.RefreshReport("r1", "test", "2026-11-19T00:00:00+00:00", finished_at="2026-11-19T00:00:01+00:00")
    return make_store(conn), conn, state, report


def test_every_insert_has_matching_columns_placeholders_and_params():
    pg, conn, state, report = committed(0)
    state.version = 1
    assert pg.commit(state, [], report, expected_version=0, bump=True) is True
    inserts = [(s, p) for s, p in conn.sql if s.startswith("INSERT INTO catalog_") and "ON CONFLICT" in s and "catalog_meta" not in s and "refresh_runs" not in s]
    assert inserts
    for sql, params in inserts:
        cols = [c.strip() for c in re.search(r"\(([^)]*)\) VALUES", sql).group(1).split(",")]
        marks = re.search(r"VALUES \((.*?)\) ON CONFLICT", sql).group(1).split(",")
        assert len(cols) == len(marks), sql
        assert sum(1 for m in marks if m.strip() == "%s") == len(params), sql


def test_parents_are_written_before_children():
    pg, conn, state, report = committed(0)
    state.version = 1
    pg.commit(state, [], report, expected_version=0, bump=True)
    order = [re.match(r"INSERT INTO (\w+)", s).group(1) for s, _ in conn.sql if s.startswith("INSERT INTO catalog_") and "ON CONFLICT" in s]
    first = {t: order.index(t) for t in dict.fromkeys(order)}
    assert first["catalog_lineages"] < first["catalog_generations"] < first["catalog_models"] < first["catalog_offerings"]


def test_version_mismatch_writes_nothing():
    pg, conn, state, report = committed(version_in_db=7)
    assert pg.commit(state, [], report, expected_version=0, bump=True) is False
    assert not any(s.startswith("INSERT INTO catalog_models") or s.startswith("UPDATE") for s, _ in conn.sql)


def test_unchanged_rows_are_not_rewritten():
    pg, conn, state, report = committed(1)
    payload = state_to_dict(state)
    pg._fp = {n: {k: store_mod._fp(v) for k, v in payload[n].items()} for n in store_mod._TABLE_KEYS}
    pg.commit(state, [], report, expected_version=1, bump=False)
    assert not [s for s, _ in conn.sql if s.startswith("INSERT INTO catalog_models") or s.startswith("INSERT INTO catalog_offerings")]
    assert not [s for s, _ in conn.sql if s.startswith("UPDATE catalog_meta")]                    # no version churn


def test_lock_is_transaction_scoped_never_session_level():
    """Session advisory locks leak behind a transaction pooler (lock and unlock land on different server connections)."""
    class LockConn(FakeConn):
        def execute(self, sql, params=None):
            self.sql.append((" ".join(sql.split()), list(params or [])))
            return Cur({"ok": True})

    conn = LockConn()
    pg = make_store(conn)
    with pg.try_lock() as got:
        assert got is True
    text = " ".join(s for s, _ in conn.sql)
    assert "pg_try_advisory_xact_lock" in text
    assert "pg_try_advisory_lock" not in text and "pg_advisory_unlock" not in text
    assert conn.sql[0][1] == [store_mod.PgStore.LOCK_KEY] and store_mod.PgStore.LOCK_KEY != 7314201


def test_lock_not_acquired_is_reported_without_raising():
    class Busy(FakeConn):
        def execute(self, sql, params=None):
            return Cur({"ok": False})
    with make_store(Busy()).try_lock() as got:
        assert got is False
