"""End-to-end pipeline and API tests with an injected catalog and mocked adapters (no network, no database)."""
import os
os.environ.setdefault("JWT_SECRET", "unit-test-only-secret-do-not-use-in-production")

import types
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.routing_engine import pipeline
from tests.engine_helpers import mk
from tests.test_engine_execution import FakeAdapter, GOOD, ProviderError

CATALOG = [mk("strong", q=0.95, inp=10, out=30, cost=0.8), mk("mid", q=0.8, inp=1, out=3, cost=0.3), mk("cheap", q=0.62, inp=0.1, out=0.3, cost=0.05)]


def loader(task, modality):
    return list(CATALOG), []


def run(query="Write a Python function that sorts a list of records.", cat=None, **kw):
    cat = CATALOG if cat is None else cat
    return pipeline.run(pipeline.PipelineRequest(query=query, **kw), saved_weights=None, user_id=None, catalog_loader=lambda t, m: (list(cat), kw.pop("_excl", [])),
                        learning_loader=lambda u, ids: {}, observed_loader=lambda ids: {})


class PipelineRecommendTests(unittest.TestCase):
    def test_stages_are_real_and_ordered(self):
        r = run()
        names = [s.name for s in r.stages]
        self.assertEqual(names[:6], ["input_validation", "query_understanding", "category_resolution", "preference_resolution", "prompt_optimization", "candidate_discovery"])
        self.assertIn("multi_objective_scoring", names)
        self.assertEqual(next(s for s in r.stages if s.name == "execution").status, "skipped")
        self.assertNotIn("response_evaluation", names)
        self.assertTrue(all(s.duration_ms >= 0 for s in r.stages))

    def test_recommend_mode_runs_no_model(self):
        called = []
        r = pipeline.run(pipeline.PipelineRequest(query="Explain recursion"), saved_weights=None, user_id=None, catalog_loader=loader,
                         learning_loader=lambda u, i: {}, observed_loader=lambda i: {}, adapter_factory=lambda m: called.append(m))
        self.assertEqual(r.execution.status, "not_requested")
        self.assertEqual(called, [])
        self.assertIn("no model was run", " ".join(r.evaluation.notes).lower())

    def test_selection_and_explanation_present(self):
        r = run()
        self.assertIsNotNone(r.selection.selected_model_id)
        self.assertEqual(r.candidates[0].model_id, r.selection.selected_model_id)
        self.assertTrue(r.explanation.why_selected)

    def test_hard_constraint_changes_pool_and_records_exclusions(self):
        r = run(max_cost=0.0005)
        self.assertNotIn("strong", [c.model_id for c in r.candidates])
        self.assertIn("strong", [e.model_id for e in r.exclusions])

    def test_no_eligible_candidate_returns_guidance(self):
        r = run(excluded_providers=["Test"])
        self.assertEqual(r.candidates, [])
        self.assertEqual(r.selection.status, "no_eligible_candidates")
        self.assertTrue(r.no_candidate_guidance)

    def test_user_edited_prompt_is_used_and_original_kept(self):
        r = run(optimized_prompt="My edited prompt", submit_prompt="optimized")
        self.assertEqual(r.prompt_used, "My edited prompt")
        self.assertEqual(r.optimization.original_prompt, "Write a Python function that sorts a list of records.")

    def test_submit_original(self):
        q = "Write a Python function that sorts a list of records."
        r = run(submit_prompt="original")
        self.assertEqual((r.prompt_used, r.prompt_used_source), (q, "original"))

    def test_optimization_disabled_uses_original(self):
        r = run(optimization_mode="disabled")
        self.assertEqual(r.prompt_used_source, "original")

    def test_unknown_pool_id_rejected(self):
        with self.assertRaises(ValueError):
            run(model_ids=["does-not-exist"])

    def test_invalid_inputs_rejected(self):
        for kw in ({"mode": "bogus"}, {"submit_prompt": "x"}, {"optimization_mode": "turbo"}):
            with self.assertRaises(ValueError, msg=str(kw)):
                run(**kw)
        with self.assertRaises(ValueError):
            run(query="   ")

    def test_reproducible(self):
        a, b = run(), run()
        self.assertEqual([c.model_id for c in a.candidates], [c.model_id for c in b.candidates])
        self.assertEqual([c.robust_score for c in a.candidates], [c.robust_score for c in b.candidates])

    def test_application_pool_is_recommend_only_fallback(self):
        apps = [mk("app1", entry_type="application", q=0.8)]
        r = run(cat=apps)
        self.assertEqual(r.candidate_pool, "applications")
        e = run(cat=apps, mode="execute")
        self.assertEqual(e.candidates, [])

    def test_secrets_not_in_serialised_decision_log_fields(self):
        q = "Debug this: api_key = sk-abcdefghijklmnopqrstuvwx fails"
        r = run(query=q)
        self.assertTrue(r.profile.risk.contains_credentials)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwx", r.profile.risk.model_dump_json())


class PipelineExecuteTests(unittest.TestCase):
    def factory(self, scripts, calls):
        return lambda m: FakeAdapter(scripts.get(m.model_id, [GOOD]), calls)

    def go(self, query="Explain what a hash map is in a few sentences.", scripts=None, **kw):
        calls = []
        r = pipeline.run(pipeline.PipelineRequest(query=query, mode="execute", **kw), saved_weights=None, user_id=None, catalog_loader=loader, learning_loader=lambda u, i: {},
                         observed_loader=lambda i: {}, adapter_factory=self.factory(scripts or {}, calls), sleep=lambda s: None)
        return r, calls

    def test_execute_success_and_evaluation_stage(self):
        r, calls = self.go()
        self.assertEqual(r.execution.status, "succeeded")
        self.assertEqual(len(calls), 1)
        self.assertIn("response_evaluation", [s.name for s in r.stages])
        self.assertIsNone(r.evaluation.judge_model)

    def test_credentials_block_execution(self):
        r, calls = self.go(query="Explain why api_key = sk-abcdefghijklmnopqrstuvwx returns 401 on login")
        self.assertEqual(r.execution.status, "blocked")
        self.assertEqual(calls, [])

    def test_clarification_blocks_execution(self):
        r, calls = self.go(query="fix this")
        self.assertEqual(r.execution.status, "blocked")
        self.assertEqual(calls, [])

    def test_provider_failure_falls_back(self):
        first = run().candidates[0].model_id
        r, calls = self.go(scripts={first: [ProviderError("unavailable", False)]})
        self.assertEqual(r.execution.status, "succeeded")
        self.assertTrue(r.execution.escalated)
        self.assertNotEqual(r.execution.final_model_id, first)

    def test_budget_is_enforced(self):
        r, calls = self.go(budget_usd=0.0000001)
        self.assertEqual(calls, [])
        self.assertEqual(r.execution.status, "budget_exhausted")


# ---------------------------------------------------------------- API ----
class FakePrefs:
    def model_dump(self):
        return {"cost_weight": 0.15}


class FakeUser:
    user_group = "student"
    name = "Tester"
    preferences_customized = False
    routing_preferences = FakePrefs()

    def get_routing_weights(self):
        return None


class RouteApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.patches = [
            patch("app.api.routes.routing.user_store.decode_token", return_value="u1"),
            patch("app.api.routes.routing.user_store.get_by_id", return_value=FakeUser()),
            patch("app.services.model_registry.get_catalog_with_exclusions", side_effect=loader),
            patch("app.api.routes.routing.feedback_store.record_routing_decision"),
            patch("app.api.routes.routing.routing_log_store.record"),
            patch("app.services.routing_engine.observed.load_observed", return_value={}),
            patch("app.services.feedback_store.get_learning_bonuses", return_value={}),
        ]
        for p in self.patches:
            p.start()
        self.h = {"Authorization": "Bearer x"}

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_requires_auth(self):
        with patch("app.api.routes.routing.user_store.decode_token", return_value=None):
            self.assertEqual(self.client.post("/api/v1/route-and-generate", json={"query": "hello there"}).status_code, 401)

    def _post(self, body):
        for prefix in ("/api/v1", "/api", ""):
            r = self.client.post(f"{prefix}/route-and-generate", json=body, headers=self.h)
            if r.status_code != 404:
                return r
        return r

    def test_recommend_response_has_legacy_fields_and_engine(self):
        r = self._post({"query": "Write a Python function that sorts a list of records."})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        for k in ("selected_model_id", "model_scores", "routing_explanation", "response_evaluation", "escalation_info", "optimized_prompt", "engine"):
            self.assertIn(k, d)
        self.assertEqual(d["engine"]["mode"], "recommend")
        self.assertEqual(d["engine"]["execution"]["status"], "not_requested")
        self.assertEqual(d["response_evaluation"]["evaluation_method"], "not_applicable_recommendation_only")
        self.assertNotIn("Write a Python function", d["engine"]["profile"]["original_query"])

    def test_response_carries_provenance_confidence_and_persistence_timing(self):
        d = self._post({"query": "Write a Python function that sorts a list of records."}).json()
        self.assertIn("persistence_ms", d["performance_metrics"])
        self.assertEqual(len(d["engine"]["provenance"]["fingerprint"]), 64)
        self.assertIsNone(d["engine"]["confidence_report"]["combined"])
        self.assertEqual([c["name"] for c in d["engine"]["confidence_report"]["components"]][0], "query_understanding")

    def test_unscorable_models_are_sent_compactly_not_as_full_evidence_blocks(self):
        from tests.engine_helpers import mk
        ghosts = [mk(f"ghost-{i}", q=None, cost=None, latency=None, rel=None, risk=None, inp=None, out=None, caps=[], tasks=[]) for i in range(20)]
        base, _ = loader("coding", "text")
        with patch("app.services.model_registry.get_catalog_with_exclusions", side_effect=lambda t, m, *a, **k: ([*base, *ghosts], [])):
            d = self._post({"query": "Write a Python function that sorts a list of records."}).json()
        e = d["engine"]
        self.assertEqual(e["pool_summary"]["unscored"], 20)
        self.assertEqual(len(e["unscored_candidates"]), 20)
        self.assertEqual(len(e["candidates"]), e["pool_summary"]["scored"])
        self.assertTrue(all("evidence" not in c for c in e["unscored_candidates"]))
        self.assertEqual(d["performance_metrics"]["candidates_scored"], e["pool_summary"]["scored"])
        self.assertEqual(d["performance_metrics"]["candidates_evaluated"], e["pool_summary"]["eligible"])
        self.assertTrue(all(not x["model_id"].startswith("ghost-") for x in d["model_scores"]))
        self.assertTrue(all(any(g.model_id == m for m in d["candidate_models"]) for g in ghosts), "every pool member stays listed")

    def test_a_storage_failure_never_fails_the_routing_request(self):
        with patch("app.api.routes.routing.feedback_store.record_routing_decision", side_effect=RuntimeError("db down")), \
                patch("app.api.routes.routing.routing_log_store.record", side_effect=RuntimeError("db down")):
            r = self._post({"query": "Explain recursion"})
        self.assertEqual(r.status_code, 200, r.text)

    def test_no_eligible_candidate_is_422_with_string_detail(self):
        r = self._post({"query": "Write a Python function", "excluded_providers": ["Test"]})
        self.assertEqual(r.status_code, 422)
        self.assertIsInstance(r.json()["detail"], str)

    def test_bad_weights_rejected(self):
        r = self._post({"query": "Explain recursion", "weight_overrides": {"quality": -1}})
        self.assertEqual(r.status_code, 422)

    def test_idempotent_execute(self):
        calls = []
        with patch("app.services.routing_engine.execution.get_adapter_for", side_effect=lambda m: FakeAdapter([GOOD], calls)), \
                patch("app.services.registry_eligibility.provider_configured", return_value=True):
            body = {"query": "Explain what a hash map is in a few sentences.", "mode": "execute", "idempotency_key": "abc-123"}
            a, b = self._post(body), self._post(body)
        self.assertEqual((a.status_code, b.status_code), (200, 200), a.text)
        self.assertEqual(len(calls), 1)
        self.assertEqual(a.json()["routing_id"], b.json()["routing_id"])


if __name__ == "__main__":
    unittest.main()
