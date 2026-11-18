"""Decision log: summaries never leak sensitive text (pure), and persistence round-trip (isolated DB only)."""
import os
os.environ.setdefault("JWT_SECRET", "unit-test-only-secret-do-not-use-in-production")

import json
import unittest
import uuid

from app.services import routing_log_store as store
from app.services.routing_engine import pipeline
from tests.conftest import HAS_ISOLATED_TEST_DATABASE
from tests.engine_helpers import mk


class SummaryTests(unittest.TestCase):
    def test_sensitive_queries_are_withheld(self):
        for s in ("moderate", "high"):
            self.assertEqual(store.summarize_query("my password is hunter2", s), "[withheld: sensitive content]")

    def test_plain_summary_truncated(self):
        out = store.summarize_query("word " * 100, "none")
        self.assertLessEqual(len(out), 81)


@unittest.skipUnless(HAS_ISOLATED_TEST_DATABASE, "requires TEST_DATABASE_URL with the route-query-engine migration applied")
class PersistenceTests(unittest.TestCase):
    def setUp(self):
        if not store.table_available(force=True):
            self.skipTest("migration 20261119_route_query_engine.sql not applied to the test database")

    def _result(self, query):
        cat = [mk("a", q=0.9), mk("b", q=0.7)]
        return pipeline.run(pipeline.PipelineRequest(query=query), saved_weights=None, user_id=None, catalog_loader=lambda t, m: (list(cat), []),
                            learning_loader=lambda u, i: {}, observed_loader=lambda i: {})

    def test_round_trip_and_ownership(self):
        rid, uid = str(uuid.uuid4()), f"user-{uuid.uuid4()}"
        self.assertTrue(store.record(rid, uid, self._result("Write a Python function that sorts a list of records.")))
        self.assertIn(rid, [h["id"] for h in store.history(uid)])
        self.assertIsNotNone(store.get_decision(uid, rid))
        self.assertIsNone(store.get_decision("someone-else", rid))

    def test_no_secret_or_prompt_text_persisted(self):
        rid, uid = str(uuid.uuid4()), f"user-{uuid.uuid4()}"
        secret = "sk-abcdefghijklmnopqrstuvwx"
        store.record(rid, uid, self._result(f"Debug this: api_key = {secret} fails with 401 on login"))
        blob = json.dumps(store.get_decision(uid, rid), default=str)
        self.assertNotIn(secret, blob)
        self.assertNotIn("fails with 401", blob)


if __name__ == "__main__":
    unittest.main()
