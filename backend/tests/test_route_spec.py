"""Route Query spec-level tests: reproducibility, best-vs-executable, confidence, query-dependent weights, complexity,
scenario coverage (budget, latency, privacy, unknown data, missing metadata, retired, new model, large catalogue) and
a regression guard on the labelled understanding sets. Deterministic; no network, no database."""
import os
os.environ.setdefault("JWT_SECRET", "unit-test-only-secret-do-not-use-in-production")

import time
import unittest
from unittest.mock import patch

from app.services.routing_engine import calibration, pipeline, understanding
from tests.engine_helpers import mk


def run(query, cat, **kw):
    return pipeline.run(pipeline.PipelineRequest(query=query, **kw), saved_weights=None, user_id=None,
                        catalog_loader=lambda t, m: (list(cat), []), learning_loader=lambda u, i: {}, observed_loader=lambda i: {})


CAT = [mk("strong", q=0.95, inp=10, out=30, cost=0.8, latency=0.4), mk("mid", q=0.8, inp=1, out=3, cost=0.3, latency=0.6), mk("cheap", q=0.62, inp=0.1, out=0.3, cost=0.05, latency=0.9)]
Q = "Write a Python function that sorts a list of records."


class Reproducibility(unittest.TestCase):
    def test_identical_inputs_give_identical_fingerprint_and_ranking(self):                     # scenario 27
        a, b = run(Q, CAT), run(Q, CAT)
        self.assertEqual(a.provenance["fingerprint"], b.provenance["fingerprint"])
        self.assertEqual([c.model_id for c in a.candidates], [c.model_id for c in b.candidates])
        self.assertEqual([c.robust_score for c in a.candidates], [c.robust_score for c in b.candidates])

    def test_catalogue_order_does_not_change_the_decision(self):
        a, b = run(Q, CAT), run(Q, list(reversed(CAT)))
        self.assertEqual(a.provenance["fingerprint"], b.provenance["fingerprint"])
        self.assertEqual(a.selection.selected_model_id, b.selection.selected_model_id)

    def test_a_price_change_changes_the_fingerprint(self):
        changed = [mk("strong", q=0.95, inp=11, out=30, cost=0.8, latency=0.4), *CAT[1:]]
        self.assertNotEqual(run(Q, CAT).provenance["fingerprint"], run(Q, changed).provenance["fingerprint"])

    def test_constraint_and_query_are_part_of_the_fingerprint_and_the_query_text_is_not_stored(self):
        base = run(Q, CAT)
        self.assertNotEqual(base.provenance["fingerprint"], run(Q, CAT, max_cost=0.5).provenance["fingerprint"])
        self.assertNotEqual(base.provenance["fingerprint"], run(Q + " Also add types.", CAT).provenance["fingerprint"])
        self.assertNotIn("sorts a list", str(base.provenance))
        self.assertEqual(base.provenance["engine_version"], pipeline.ENGINE_VERSION)


class BestVersusExecutable(unittest.TestCase):
    def setUp(self):
        self.cat = [mk("best", q=0.95, provider="NoKey"), mk("ok", q=0.7, provider="HasKey", cost=0.5)]

    def _run(self, configured):
        with patch("app.services.registry_eligibility.provider_configured", lambda p: p in configured), patch("app.services.registry_eligibility.provider_disabled", lambda p: False):
            return run("Write a Python function that sorts a list of records.", self.cat)

    def test_unavailable_best_match_is_not_substituted_but_an_executable_alternative_is_named(self):   # scenario 15
        r = self._run({"HasKey"})
        self.assertEqual(r.selection.selected_model_id, "best")
        self.assertFalse(r.access["execution_available"])
        alt = r.executable_alternative
        self.assertEqual(alt["model_id"], "ok")
        self.assertFalse(alt["substituted"])
        self.assertIn("not substituted", alt["statement"])

    def test_no_alternative_is_reported_honestly(self):
        alt = self._run(set()).executable_alternative
        self.assertIsNone(alt["model_id"])
        self.assertIn("no other eligible model", alt["statement"])

    def test_no_alternative_block_when_best_match_can_run(self):
        self.assertIsNone(self._run({"NoKey", "HasKey"}).executable_alternative)

    def test_comparison_never_needs_credentials(self):
        r = self._run(set())
        self.assertEqual(len(r.candidates), 2)
        self.assertFalse(r.catalogue_summary["credentials_used_for_comparison"])


class Confidence(unittest.TestCase):
    def test_components_are_separate_and_never_merged(self):
        r = run(Q, CAT)
        names = [c.name for c in r.confidence_report.components]
        self.assertEqual(names, ["query_understanding", "model_suitability", "execution_readiness", "response_acceptance"])
        self.assertIsNone(r.confidence_report.combined)
        self.assertTrue(all(c.calibrated is False for c in r.confidence_report.components))
        self.assertFalse(r.confidence_report.calibration["validated"])
        self.assertEqual(r.confidence_report.components[3].kind, "not_applicable")

    def test_calibration_metrics_are_correct(self):
        self.assertAlmostEqual(calibration.brier_score([1.0, 0.0], [1, 0]), 0.0)
        self.assertAlmostEqual(calibration.brier_score([0.5, 0.5], [1, 0]), 0.25)
        self.assertAlmostEqual(calibration.expected_calibration_error([0.9] * 10, [1] * 9 + [0]), 0.0)
        self.assertAlmostEqual(calibration.expected_calibration_error([0.9] * 10, [1] * 5 + [0] * 5), 0.4)
        self.assertFalse(calibration.status(20)["can_validate"])
        self.assertTrue(calibration.status(500)["can_validate"])
        with self.assertRaises(ValueError):
            calibration.brier_score([], [])


class QueryDependentWeights(unittest.TestCase):
    def w(self, q):
        return run(q, CAT).preferences.weights

    def test_explicit_cheapest_is_stronger_than_the_default_and_is_reported(self):
        base, cheap = self.w("Classify these reviews as positive or negative: great, awful."), self.w("Use the cheapest suitable model to classify these reviews: great, awful.")
        self.assertGreater(cheap["cost"], base["cost"] * 1.4)
        adj = run("Use the cheapest suitable model to classify these reviews: great, awful.", CAT).preferences.adjustments
        self.assertTrue(any(a.dimension == "cost" and a.origin == "explicit" and a.factor >= 2.0 for a in adj))

    def test_difficulty_raises_quality_weight_and_is_labelled_inferred(self):
        easy = self.w("What is the capital of France?")
        hard = run("Prove that there are infinitely many prime numbers, rigorously, step by step.", CAT)
        self.assertGreater(hard.preferences.weights["quality"], easy["quality"])
        self.assertTrue(any(a.dimension == "quality" and a.origin == "inferred" for a in hard.preferences.adjustments))

    def test_a_speed_wish_cannot_remove_quality_from_the_decision(self):
        w = self.w("Respond as quickly as possible, immediately, asap: what is 2+2? Fastest answer.")
        self.assertGreaterEqual(w["quality"], 0.18 - 1e-9)
        self.assertAlmostEqual(sum(w.values()), 1.0, places=6)

    def test_simple_arithmetic_does_not_demand_a_reasoning_specialist(self):
        p = understanding.analyze("What is 17 * 23?")
        self.assertEqual(p.reasoning_requirement, "light")
        self.assertIn("qa", p.task_tags)


class ComplexityDoesNotDependOnLength(unittest.TestCase):
    def band(self, q):
        return understanding.analyze(q).complexity

    def test_short_proof_is_not_simple(self):
        c = self.band("Prove that there are infinitely many prime numbers.")
        self.assertIn(c.category, {"complex", "highly_complex"})
        self.assertTrue(c.adjustments)                       # the floor rule that applied is reported

    def test_long_plain_summarisation_stays_simple_or_moderate(self):
        c = self.band("Summarize this:\n" + "The committee met on Tuesday and discussed the budget. " * 80)
        self.assertIn(c.category, {"simple", "moderate"})

    def test_hard_marker_and_enumerated_requirements_raise_the_band(self):
        self.assertGreaterEqual(["simple", "moderate", "complex", "highly_complex"].index(
            self.band("Write a Python async web crawler with rate limiting, retries with exponential backoff and unit tests.").category), 2)
        self.assertEqual(self.band("What is 2+2?").category, "simple")


class ScenarioCoverage(unittest.TestCase):
    def test_strict_budget_removes_over_budget_models_before_scoring(self):                      # 9
        r = run(Q, CAT, max_cost=0.0005)
        self.assertEqual([c.model_id for c in r.candidates], ["cheap"])
        self.assertTrue(all(e.code == "cost_exceeds_limit" for e in r.exclusions if e.model_id in {"strong", "mid"}))

    def test_strict_latency_with_unknown_latency_excludes_rather_than_assumes(self):               # 10, 20
        cat = [mk("known", avg_latency=1.0), mk("unknown", avg_latency=0.0)]
        r = run(Q, cat, max_latency=2.0)
        self.assertEqual([c.model_id for c in r.candidates], ["known"])
        self.assertEqual(next(e for e in r.exclusions if e.model_id == "unknown").code, "latency_unverifiable")

    def test_strict_privacy_excludes_models_without_documented_data_handling(self):                # 11
        cat = [mk("documented", privacy="provider_documented_restricted"), mk("undocumented", privacy="unknown")]
        r = run(Q, cat, privacy_requirement="strict")
        self.assertEqual([c.model_id for c in r.candidates], ["documented"])
        self.assertEqual(next(e for e in r.exclusions if e.model_id == "undocumented").code, "privacy_unverified")

    def test_unknown_pricing_under_a_cost_cap_is_excluded_not_treated_as_free(self):               # 19
        cat = [mk("priced", inp=1, out=2), mk("unpriced", inp=None, out=None)]
        r = run(Q, cat, max_cost=1.0)
        self.assertEqual([c.model_id for c in r.candidates], ["priced"])
        self.assertEqual(next(e for e in r.exclusions if e.model_id == "unpriced").code, "cost_unverifiable")

    def test_unknown_values_stay_unknown_in_scoring(self):                                         # 19-21
        r = run(Q, [mk("a", inp=None, out=None, q=None), mk("b")])
        a = next(c for c in r.candidates if c.model_id == "a")
        self.assertIn("quality", a.missing_dimensions)
        self.assertIsNone(a.utilities["quality"])
        self.assertLess(a.confidence, next(c for c in r.candidates if c.model_id == "b").confidence)

    def test_missing_capability_metadata_is_not_assumed_supported(self):                           # 21
        r = run(Q, [mk("blank", caps=[], tasks=[]), mk("coder")])
        blank = next(c for c in r.candidates if c.model_id == "blank")
        self.assertEqual(r.selection.selected_model_id, "coder")                       # unknown fit never beats declared fit
        self.assertIn("preference_alignment", blank.missing_dimensions)
        self.assertIsNone(blank.utilities["preference_alignment"])                     # unknown stays unknown, not 0 and not 1
        # a *required* capability that the metadata does not list is a hard exclusion
        r2 = run("Generate an image of a lighthouse at dawn.", [mk("blank", caps=[], tasks=[], modalities=["text", "image"]), mk("painter", caps=["image-generation"], modalities=["text", "image"], tasks=["image-generation"])])
        self.assertEqual([c.model_id for c in r2.candidates], ["painter"])
        self.assertEqual(next(e for e in r2.exclusions if e.model_id == "blank").code, "capability_missing")

    def test_no_candidate_is_reported_with_reasons_and_nothing_is_relaxed(self):                   # 14
        r = run(Q, CAT, max_cost=1e-12)
        self.assertEqual(r.status, "no_eligible_candidates")
        self.assertEqual(r.candidates, [])
        self.assertEqual({e.code for e in r.exclusions}, {"cost_exceeds_limit"})
        self.assertTrue(r.no_candidate_guidance["suggestions"])

    def test_retired_model_is_excluded_and_a_new_model_is_considered(self):                        # 29, 30
        retired = mk("old"); retired.lifecycle_status = "retired"
        fresh = mk("brand-new", q=0.99)
        r = run(Q, [*CAT, retired, fresh])
        self.assertNotIn("old", [c.model_id for c in r.candidates])
        self.assertEqual(next(e for e in r.exclusions if e.model_id == "old").code, "lifecycle_excluded")
        self.assertIn("brand-new", [c.model_id for c in r.candidates])

    def test_ambiguous_request_asks_for_clarification_and_caps_confidence(self):                   # 13
        r = run("fix this", CAT)
        self.assertEqual(r.status, "needs_clarification")
        self.assertLessEqual(r.selection.confidence_value, 0.45)

    def test_multi_intent_is_detected(self):                                                       # 12
        p = understanding.analyze("Analyse this dataset, create visualisations and explain the important findings.\n```csv\na,b\n1,2\n```")
        self.assertEqual(p.primary_intent, "data_analysis")
        self.assertIn("reasoning", {i.name for i in p.secondary_intents})

    def test_large_catalogue_stays_fast_and_deterministic(self):                                   # 28
        big = [mk(f"m{i:04d}", q=0.5 + (i % 50) / 120, inp=0.1 + (i % 17), out=0.3 + (i % 23), latency=(i % 10) / 10, provider=f"P{i % 12}") for i in range(800)]
        t0 = time.perf_counter()
        a = run(Q, big)
        dt = time.perf_counter() - t0
        b = run(Q, list(reversed(big)))
        self.assertEqual(len(a.candidates), 800)
        self.assertEqual(a.selection.selected_model_id, b.selection.selected_model_id)
        self.assertLess(dt, 5.0, f"800-model routing took {dt:.2f}s")


class ParetoHandlesMissingData(unittest.TestCase):
    def test_missing_metrics_never_make_a_model_look_dominated(self):
        full = mk("full", q=0.9, inp=1, out=2, latency=0.2, rel=0.9, risk=0.1)
        partial = mk("partial", q=0.5, inp=1, out=2, latency=0.8, rel=None, risk=0.1)       # unknown reliability
        r = run(Q, [full, partial])
        p = next(c for c in r.candidates if c.model_id == "partial")
        self.assertIn("reliability", p.missing_dimensions)
        self.assertEqual(p.dominated_by, [])           # incomparable with `full`: different known metrics

    def test_a_clearly_worse_comparable_model_is_dominated(self):
        good = mk("good", q=0.9, rel=0.9, risk=0.1)
        bad = mk("bad", q=0.5, rel=0.5, risk=0.5)
        r = run(Q, [good, bad])
        self.assertEqual(next(c for c in r.candidates if c.model_id == "bad").dominated_by, ["good"])
        self.assertTrue(next(c for c in r.candidates if c.model_id == "good").pareto_optimal)


class ExecutionTimeLimit(unittest.TestCase):
    def test_wall_clock_deadline_stops_further_attempts_and_says_so(self):                          # 17
        from tests.test_engine_execution import Harness, ProviderError
        models = [mk("a", q=0.9), mk("b", q=0.8), mk("c", q=0.7)]
        h = Harness({m.model_id: [ProviderError("unavailable", False)] for m in models}, models, deadline_seconds=10)
        ticks = iter([0.0, 0.0, 50.0, 50.0, 50.0, 50.0, 50.0, 50.0])      # the clock jumps past the 10 s deadline after the first attempt
        import random
        from app.services.routing_engine import execution
        out, _ = execution.execute(ranked=h.rows, models=h.models, prompt="P", query=h.query, profile=h.p, policy=h.policy, prompt_source="optimized",
                                   adapter_factory=h.factory, sleep=h.sleeps.append, rng=random.Random(1), clock=lambda: next(ticks, 50.0))
        self.assertEqual(out.status, "failed")
        self.assertLess(len(out.attempts), 3)
        self.assertTrue(any("time limit" in n for n in out.notes))


class EvidenceCaches(unittest.TestCase):
    def test_observed_telemetry_is_cached_briefly_and_failures_are_not_cached(self):
        from app.services import routing_log_store
        from app.services.routing_engine import observed
        observed.clear_cache()
        calls = []
        with patch.object(routing_log_store, "observed_stats", lambda ids, days: calls.append(1) or {}):
            observed.load_observed(["a", "b"]); observed.load_observed(["b", "a"])
            self.assertEqual(len(calls), 1)                         # same candidate set, one query
            observed.load_observed(["a", "b", "c"])
            self.assertEqual(len(calls), 2)                         # a different set is a different key
        observed.clear_cache()
        def boom(ids, days):
            raise RuntimeError("db down")
        with patch.object(routing_log_store, "observed_stats", boom):
            self.assertEqual(observed.load_observed(["a"]), {})
        with patch.object(routing_log_store, "observed_stats", lambda ids, days: {"a": observed.ObservedStats(model_id="a", samples=9, successes=9)}):
            self.assertIn("a", observed.load_observed(["a"]))       # the earlier failure was not remembered
        observed.clear_cache()

    def test_learning_bonuses_are_cached_per_user_and_invalidated_by_feedback(self):
        from app.services import feedback_store
        feedback_store.invalidate_learning_cache()
        calls = []
        with patch.object(feedback_store, "_load_learning_bonuses", lambda uid, ids=None: calls.append(uid) or {"m1": 0.05, "m2": -0.02}):
            self.assertEqual(feedback_store.get_learning_bonuses("u1", ["m1"]), {"m1": 0.05})
            self.assertEqual(feedback_store.get_learning_bonuses("u1", ["m2"]), {"m2": -0.02})
            self.assertEqual(len(calls), 1)
            feedback_store.get_learning_bonuses("u2", ["m1"])
            self.assertEqual(len(calls), 2)                         # another user is never served u1's cache
            feedback_store.invalidate_learning_cache("u1")
            feedback_store.get_learning_bonuses("u1", ["m1"])
            self.assertEqual(len(calls), 3)
        feedback_store.invalidate_learning_cache()


class UnderstandingRegressionGuard(unittest.TestCase):
    """Guards against regressions on the hand-labelled sets (see benchmarks/understanding_eval.py for the caveats)."""
    def test_tuning_and_held_out_sets(self):
        from benchmarks import understanding_eval as ev
        tuned, held = ev.evaluate(cases=ev.CASES), ev.evaluate(cases=ev.HELD_OUT)
        self.assertGreaterEqual(tuned["primary_intent_accuracy"], 0.95)
        self.assertEqual(tuned["complexity_within_one_band"], 1.0)
        self.assertGreaterEqual(held["primary_intent_accuracy"], 0.9)
        self.assertEqual(held["complexity_within_one_band"], 1.0)


if __name__ == "__main__":
    unittest.main()
