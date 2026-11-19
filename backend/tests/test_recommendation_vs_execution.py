"""Recommendation eligibility vs execution eligibility.

A provider credential decides whether AI Compass can RUN a model. It must never decide whether a model can be RECOMMENDED.
Real pipeline, real static catalogue, provider credentials forced on or off by patching the one function that reads them.
No network, no database, no provider calls.
"""
import os
os.environ.setdefault("JWT_SECRET", "unit-test-only-secret-do-not-use-in-production")

import unittest
from unittest.mock import patch

from app.schemas.evaluation import CatalogCoverage
from app.services import model_registry, offline_evaluation, pool_stats
from app.services.routing_engine import access, pipeline
from tests.engine_helpers import mk

QUERY = "Write a Python function that merges two sorted lists."


def keys(configured):
    """Force which providers count as configured: a set of lower-case provider names, or None for all."""
    return patch.object(model_registry, "_configured", lambda p: True if configured is None else p.lower() in configured)


def route(query=QUERY, **kw):
    req = pipeline.PipelineRequest(query=query, optimization_mode="disabled", **kw)
    return pipeline.run(req, saved_weights=None, user_id=None, observed_loader=lambda ids: {}, learning_loader=lambda u, ids: {})


def ranking(res):
    return [(r.model_id, r.robust_score, r.utility) for r in res.candidates]


def fingerprint(res):
    p = res.provenance
    return p["fingerprint"] if isinstance(p, dict) else p.fingerprint


class RecommendationDoesNotNeedKeys(unittest.TestCase):
    def test_1_model_without_a_key_can_be_recommended(self):                                   # case 1
        with keys(set()):
            r = route()
        top = next(c for c in r.candidates if c.model_id == r.selection.selected_model_id)
        self.assertEqual(r.selection.status, "selected")
        self.assertTrue(top.recommendation_eligible)
        self.assertFalse(top.execution_ready)
        self.assertEqual(top.execution_status, "credential_not_configured")
        self.assertGreater(len({c.provider for c in r.candidates}), 3, "several unconfigured providers must stay in the pool")

    def test_2_model_with_a_key_is_recommended_when_suitable(self):                            # case 2
        with keys(set()):
            top_provider = next(c for c in route().candidates if c.rank == 1).provider
        with keys({top_provider.lower()}):
            r = route()
        top = next(c for c in r.candidates if c.rank == 1)
        self.assertEqual(top.provider, top_provider)
        self.assertEqual(r.selection.selected_model_id, top.model_id)
        if top.execution_status != "no_adapter":
            self.assertTrue(top.execution_ready)

    def test_5_unconfigured_providers_stay_in_the_catalogue(self):                             # case 5
        with keys(set()):
            cat, _ = model_registry.get_catalog_with_exclusions("", "text", live=False)
        api = [m for m in cat if m.entry_type == "inference_model"]
        self.assertEqual({m.model_id for m in api}, {m.model_id for m in model_registry.api_models()})
        self.assertTrue(all(m.comparison_eligible and m.routing_eligible for m in api))
        self.assertFalse(any(m.execution_available for m in api))

    def test_11_credentials_never_change_the_ranking_or_scores(self):                          # case 11
        with keys(set()):
            none_ = route()
        with keys(None):
            all_ = route()
        self.assertEqual(ranking(none_), ranking(all_))
        self.assertEqual(none_.selection.selected_model_id, all_.selection.selected_model_id)
        self.assertEqual(fingerprint(none_), fingerprint(all_))
        self.assertFalse(any(c.execution_ready for c in none_.candidates))


class AdapterAndDiscovery(unittest.TestCase):
    def test_3_4_no_adapter_is_recommendable_but_not_executable(self):                         # case 3, 4
        m = mk("no-adapter", q=0.99, provider="Acme").model_copy(update={"adapter_compatible": False})
        with keys(None):                                                                        # even with every credential present
            r = pipeline.run(pipeline.PipelineRequest(query=QUERY, optimization_mode="disabled"), saved_weights=None, user_id=None,
                             catalog_loader=lambda t, mm: ([m, mk("other", q=0.5, provider="Other")], []),
                             observed_loader=lambda i: {}, learning_loader=lambda u, i: {})
            d = access.describe(m)
        self.assertEqual(r.selection.selected_model_id, "no-adapter")
        self.assertFalse(d["execution_available"])
        self.assertEqual(d["status"], "no_adapter")
        row = next(c for c in r.candidates if c.model_id == "no-adapter")
        self.assertTrue(row.recommendation_eligible)
        self.assertFalse(row.execution_ready)
        self.assertEqual(r.executable_alternative["model_id"], "other")
        self.assertFalse(r.executable_alternative["substituted"])

    def test_8_discovered_unverified_model_is_not_executable(self):                            # case 8
        from datetime import datetime, timezone
        from app.services import registry_eligibility as elig, registry_service
        from tests.test_live_registry import complete, live
        entry = complete(live()).model_copy(update={"capabilities": ["general"], "supported_tasks": ["qa"], "supported_domains": ["general"]})
        state = lambda verifs=None: registry_service.LiveState([entry], verifs or {}, [], True)
        verified = {("openrouter", "acme/new"): elig.Verification("validated", datetime.now(timezone.utc))}

        with keys(None), patch.object(registry_service, "live_state", return_value=state()):
            pool, _ = registry_service.apply_live_registry([])
            reg = registry_service._entry(entry, "live", state())
            self.assertEqual(pool, [], "an unverified discovery is never pooled")
            self.assertFalse(reg.routing_eligible)
            self.assertFalse(reg.execution_available, "even with every credential present")
            self.assertEqual(access.describe(entry)["status"], "inference_not_verified")

        with keys(set()), patch.object(registry_service, "live_state", return_value=state(verified)):   # verified, but NO credential
            pool, _ = registry_service.apply_live_registry([])
            reg = registry_service._entry(entry, "live", state(verified))
            no_key_status = access.describe(pool[0])["status"]
        self.assertEqual([m.model_id for m in pool], ["acme/new"], "verified and complete: recommendable without a key")
        self.assertTrue(reg.routing_eligible)
        self.assertFalse(reg.execution_available)
        self.assertEqual(no_key_status, "credential_not_configured")

        with keys(None), patch.object(registry_service, "live_state", return_value=state(verified)):
            pool, _ = registry_service.apply_live_registry([])
            self.assertTrue(access.describe(pool[0])["execution_available"])


class BestVsExecutable(unittest.TestCase):
    def test_9_best_recommendation_and_best_executable_alternative_differ(self):               # case 9
        with keys(set()):
            base = route()
        best = base.selection.selected_model_id
        best_provider = next(c.provider for c in base.candidates if c.model_id == best)
        other = next(c.provider for c in base.candidates if c.provider != best_provider and c.execution_status != "no_adapter")
        with keys({other.lower()}):
            r = route()
        self.assertEqual(r.selection.selected_model_id, best, "a key for another provider must not change the recommendation")
        alt = r.executable_alternative
        self.assertIsNotNone(alt["model_id"])
        self.assertNotEqual(alt["model_id"], best)
        self.assertFalse(alt["substituted"])
        self.assertEqual(alt["provider"].lower(), other.lower())
        self.assertEqual(ranking(r), ranking(base))

    def test_10_recommendation_only_never_fabricates_a_response(self):                         # case 10
        with keys(set()):
            rec = route()
            ex = route(mode="execute")
        self.assertEqual(rec.execution.status, "not_requested")
        self.assertIsNone(rec.execution.response_text)
        self.assertNotEqual(ex.execution.status, "succeeded")
        self.assertIsNone(ex.execution.response_text)
        # Unconfigured models are recorded as skipped, with no latency, tokens or cost: nothing was called.
        self.assertTrue(ex.execution.attempts)
        self.assertTrue(all(a.outcome == "skipped_no_access" and a.latency_ms is None and a.input_tokens is None and a.cost_usd is None
                            for a in ex.execution.attempts))
        self.assertEqual(ex.selection.selected_model_id, rec.selection.selected_model_id, "the recommendation is preserved, not replaced")
        self.assertNotIn("response_evaluation", [s.name for s in ex.stages if s.status == "completed"])


class PoolCountsAndEvaluation(unittest.TestCase):
    def test_pool_stats_separates_recommendation_from_execution(self):
        from app.services import registry_service
        with keys(set()):
            a = pool_stats.compute(registry_service.build_registry(include_live=False))["access"]
        self.assertEqual(a["recommendation_eligible"], a["catalog_models"])
        self.assertEqual(a["execution_ready"], 0)
        self.assertEqual(a["recommendation_only"], a["catalog_models"])
        self.assertEqual(a["provider_not_configured"], a["catalog_models"])
        with keys(None):
            b = pool_stats.compute(registry_service.build_registry(include_live=False))["access"]
        self.assertEqual(b["catalog_models"], a["catalog_models"])
        self.assertEqual(b["recommendation_eligible"], a["recommendation_eligible"], "credentials must not change recommendation eligibility")
        self.assertGreater(b["execution_ready"], 0)
        self.assertEqual(b["recommendation_only"], b["recommendation_eligible"] - b["execution_ready"])

    def test_13_offline_evaluation_covers_the_full_catalogue(self):                            # case 13
        with keys(set()):
            cat, _ = model_registry.get_catalog_with_exclusions("coding", "text", live=False)
        models = [m for m in cat if m.entry_type == "inference_model"]
        self.assertGreater(len(models), 10)
        from tests.test_offline_evaluation import profile
        weights = {"quality": .4, "cost": .2, "latency": .15, "reliability": .15, "risk": .1}
        results = offline_evaluation.evaluate(models=models, query_profile=profile(), weights=weights, filtered_out=[])
        cov = offline_evaluation.catalog_coverage(models, results)
        self.assertIsInstance(cov, CatalogCoverage)
        self.assertTrue(cov.metadata_only)
        self.assertEqual(cov.evaluated_models, len(models))
        self.assertEqual(cov.execution_ready_models, 0)
        self.assertEqual(cov.recommendation_only_models, len(models))
        self.assertEqual(cov.recommendation_only_share, 1.0)
        self.assertGreater(cov.providers, 3)
        self.assertEqual({s["strategy"] for s in cov.selection_by_strategy}, {r.strategy for r in results})
        self.assertIn("not measured", cov.note)

    def test_coverage_of_an_empty_pool_is_unknown_not_zero(self):
        cov = offline_evaluation.catalog_coverage([], [])
        self.assertIsNone(cov.recommendation_only_share)
        self.assertIsNone(cov.missing_metadata_share)


if __name__ == "__main__":
    unittest.main()
