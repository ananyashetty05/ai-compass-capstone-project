"""Connection reuse, stale-while-revalidate caches, honest scored/unscored accounting, and the simple-coding task-fit rule.
Deterministic: fake connections, no network, no database."""
import os
os.environ.setdefault("JWT_SECRET", "unit-test-only-secret-do-not-use-in-production")

import threading
import time
import unittest
from unittest.mock import patch

from app.core import db
from app.services.catalog import registry
from app.services.routing_engine import pipeline, scoring, understanding
from tests.engine_helpers import mk


class FakeConn:
    opened = 0

    def __init__(self):
        FakeConn.opened += 1
        self.closed, self.commits, self.rollbacks, self.queries = False, 0, 0, 0

    def execute(self, *_a):
        self.queries += 1

    def commit(self): self.commits += 1
    def rollback(self): self.rollbacks += 1
    def close(self): self.closed = True


class FakePsycopg:
    @staticmethod
    def connect(dsn, **kw):
        assert kw["prepare_threshold"] is None, "reused connections must not use prepared statements (transaction poolers)"
        return FakeConn()


class ConnectionPool(unittest.TestCase):
    def setUp(self):
        FakeConn.opened = 0
        db.reset_for_tests()
        self.patch = patch.object(db, "psycopg", FakePsycopg)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        db.reset_for_tests()

    def test_connections_are_reused_and_committed(self):
        for _ in range(5):
            with db.connect("dsn://x") as c:
                pass
        self.assertEqual(FakeConn.opened, 1, "five sequential uses must share one connection")
        self.assertEqual(c.commits, 5)
        self.assertFalse(c.closed)

    def test_error_rolls_back_and_connection_is_still_returned(self):
        with self.assertRaises(ValueError):
            with db.connect("dsn://x") as c:
                raise ValueError("boom")
        self.assertEqual((c.rollbacks, c.commits), (1, 0))
        with db.connect("dsn://x") as again:
            pass
        self.assertIs(again, c)

    def test_stale_and_aged_connections_are_replaced(self):
        with db.connect("dsn://x") as first:
            pass
        with patch.object(db, "MAX_AGE", -1):
            with db.connect("dsn://x") as second:
                pass
        self.assertIsNot(first, second)
        self.assertTrue(first.closed)

    def test_dead_connection_is_discarded_after_idle_validation(self):
        with db.connect("dsn://x") as first:
            pass
        first.execute = lambda *_: (_ for _ in ()).throw(RuntimeError("server closed the connection"))
        with patch.object(db, "VALIDATE_AFTER", -1):
            with db.connect("dsn://x") as second:
                pass
        self.assertIsNot(first, second)

    def test_concurrent_leases_get_distinct_connections(self):
        a, b = db.connect("dsn://x"), db.connect("dsn://x")
        with a as ca, b as cb:
            self.assertIsNot(ca, cb)
        self.assertEqual(FakeConn.opened, 2)


class StaleWhileRevalidate(unittest.TestCase):
    def setUp(self):
        registry.reset_for_tests()

    def tearDown(self):
        registry.reset_for_tests()

    def test_expired_view_is_served_at_once_and_refreshed_in_the_background(self):
        sentinel = object()
        registry._cache.update(state=sentinel, origin="store", version=1, at=time.monotonic() - (registry.settings.CATALOG_CACHE_SECONDS + 5))
        gate, done = threading.Event(), threading.Event()

        def slow_revalidate():
            gate.wait(2)
            registry._cache.update(at=time.monotonic())
            done.set()

        with patch.object(registry, "_revalidate", slow_revalidate):
            t0 = time.monotonic()
            got = registry.state()
            elapsed = time.monotonic() - t0
            self.assertIs(got, sentinel, "the expired view is served, not blocked on")
            self.assertLess(elapsed, 0.3)
            gate.set()
            self.assertTrue(done.wait(2), "a background refresh must have run")

    def test_invalidate_still_forces_a_blocking_reload(self):
        registry._cache.update(state=object(), origin="store", version=1, at=time.monotonic())
        registry.invalidate()
        calls = []
        with patch.object(registry, "_revalidate", lambda: calls.append(1) or registry._cache.update(at=time.monotonic())):
            registry.state()
        self.assertEqual(calls, [1])


class Accounting(unittest.TestCase):
    def test_unscorable_models_are_counted_but_not_called_scored(self):
        ghost = mk("ghost", q=None, cost=None, latency=None, rel=None, risk=None, inp=None, out=None, caps=[], tasks=[])
        cat = [mk("a", q=0.9), mk("b", q=0.7), ghost]
        r = pipeline.run(pipeline.PipelineRequest(query="Write a Python function that sorts a list of records."), saved_weights=None, user_id=None,
                         catalog_loader=lambda t, m: (list(cat), []), learning_loader=lambda u, i: {}, observed_loader=lambda i: {})
        scored = [c for c in r.candidates if scoring.is_scored(c)]
        self.assertEqual(len(r.candidates), 3)
        self.assertEqual({c.model_id for c in scored}, {"a", "b"})
        self.assertEqual(r.candidates[-1].model_id, "ghost", "an unscorable model ranks below every scored one")
        text = " ".join(r.explanation.why_selected)
        self.assertIn("2 scored candidates", text)
        self.assertIn("1 more are in the pool", text)
        self.assertIn("2 scored models", r.explanation.summary)
        fact = next(f for f in r.explanation.facts if f["type"] == "pool")
        self.assertEqual((fact["eligible"], fact["scored"], fact["unscored"]), (3, 2, 1))

    def test_fully_scored_pool_keeps_the_plain_wording(self):
        cat = [mk("a", q=0.9), mk("b", q=0.7)]
        r = pipeline.run(pipeline.PipelineRequest(query="Write a Python function that sorts a list of records."), saved_weights=None, user_id=None,
                         catalog_loader=lambda t, m: (list(cat), []), learning_loader=lambda u, i: {}, observed_loader=lambda i: {})
        self.assertIn("of 2 eligible candidates", " ".join(r.explanation.why_selected))


class SimpleCodingTaskFit(unittest.TestCase):
    def test_trivial_program_accepts_general_purpose_models(self):
        p = understanding.analyze("Generate a python program to print star pattern.")
        self.assertEqual(p.complexity.category, "simple")
        self.assertIn("general", p.task_tags)
        general = mk("generalist", caps=["general", "analysis"], tasks=["analysis", "summarization", "qa"])
        self.assertEqual(scoring.task_fit(general, p), 1.0, "a general-purpose model is a full task fit for a trivial program")

    def test_harder_coding_keeps_the_specialist_requirement(self):
        p = understanding.analyze("Write an async Python web crawler with rate limiting, retries with backoff, and unit tests.")
        self.assertNotEqual(p.complexity.category, "simple")
        self.assertNotIn("general", p.task_tags)
        general = mk("generalist", caps=["general", "analysis"], tasks=["analysis", "summarization", "qa"])
        self.assertEqual(scoring.task_fit(general, p), 0.0)


if __name__ == "__main__":
    unittest.main()
