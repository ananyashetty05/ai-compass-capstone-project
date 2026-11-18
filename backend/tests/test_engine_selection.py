"""Filtering, scoring, selection and decision-scenario tests (deterministic)."""
import unittest

from tests.engine_helpers import mk, prefs, profile
from app.services.routing_engine import filtering, scoring
from app.services.routing_engine.observed import ObservedStats, wilson_lower_bound
from app.services.routing_engine.preferences import DEFAULT_WEIGHTS, normalize_weights
from app.services.routing_engine.types import ScoringConfig

P = profile("Write a Python function that sorts a list of records.")


def rank(models, p=P, **kw):
    pr = prefs(p, **{k: v for k, v in kw.items() if k not in {"observed", "learning"}})
    passing, excluded = filtering.filter_candidates(models, p, pr)
    rows, norm = scoring.score_candidates(passing, p, pr, observed=kw.get("observed"), learning=kw.get("learning"))
    return scoring.select(rows, pr, p), sorted(rows, key=lambda r: r.rank), excluded, norm


class WeightTests(unittest.TestCase):
    def test_defaults_sum_to_one(self):
        self.assertAlmostEqual(sum(DEFAULT_WEIGHTS.values()), 1.0, places=9)

    def test_normalisation(self):
        w = normalize_weights({"quality": 3, "cost": 1})
        self.assertAlmostEqual(sum(w.values()), 1.0, places=9)
        self.assertGreater(w["quality"], w["cost"])

    def test_invalid_weights_rejected(self):
        for bad in ({"quality": -1}, {"cost": float("nan")}):
            with self.assertRaises(ValueError, msg=str(bad)):
                normalize_weights(bad)

    def test_precedence_request_over_saved_over_default(self):
        self.assertEqual(prefs(P).weight_source, "system_default")
        self.assertEqual(prefs(P, saved_weights={"quality": 1}).weight_source, "saved_profile")
        self.assertEqual(prefs(P, saved_weights={"quality": 1}, weight_overrides={"cost": 1}).weight_source, "request_override")

    def test_query_derived_adjustments_are_bounded_and_reported(self):
        p = profile("Explain quantum computing quickly and cheaply, it must be very accurate.")
        r = prefs(p)
        self.assertTrue(all(a.factor <= 1.5 for a in r.adjustments))
        self.assertAlmostEqual(sum(r.weights.values()), 1.0, places=9)


class FilteringTests(unittest.TestCase):
    def test_hard_constraints_exclude_with_structured_records(self):
        models = [mk("ok"), mk("small", ctx=100), mk("app", entry_type="application")]
        q = profile("Write a Python function and debug the long file " + "x " * 500)
        pr = prefs(q)
        passing, excluded = filtering.filter_candidates(models, q, pr, mode="execute")
        codes = {e.model_id: e.code for e in excluded}
        self.assertEqual(codes["small"], "context_insufficient")
        self.assertEqual(codes["app"], "not_executable")
        self.assertEqual([m.model_id for m in passing], ["ok"])
        self.assertTrue(all(e.requirement and e.reason and e.permanence for e in excluded))

    def test_user_exclusions(self):
        pr = prefs(P, excluded_providers=["Bad"], excluded_model_ids=["b"])
        _, ex = filtering.filter_candidates([mk("a", provider="Bad"), mk("b"), mk("c")], P, pr)
        self.assertEqual({e.model_id: e.code for e in ex}, {"a": "provider_excluded_by_user", "b": "model_excluded_by_user"})

    def test_unknown_price_cannot_pass_max_cost(self):
        pr = prefs(P, max_cost=0.01)
        passing, ex = filtering.filter_candidates([mk("unpriced", inp=None, out=None), mk("cheap", inp=0.1, out=0.2)], P, pr)
        self.assertEqual([m.model_id for m in passing], ["cheap"])
        self.assertEqual(ex[0].code, "cost_unverifiable")

    def test_cost_limit_enforced(self):
        pr = prefs(P, max_cost=0.0000001)
        _, ex = filtering.filter_candidates([mk("pricey", inp=50, out=200)], P, pr)
        self.assertEqual(ex[0].code, "cost_exceeds_limit")

    def test_no_eligible_guidance_names_blockers(self):
        pr = prefs(P, excluded_providers=["Test"])
        _, ex = filtering.filter_candidates([mk("a")], P, pr)
        g = filtering.no_candidate_guidance(ex)
        self.assertTrue(g)

    def test_modality_requirement(self):
        p = profile("Generate an image of a lighthouse at dawn")
        pr = prefs(p)
        passing, ex = filtering.filter_candidates([mk("txt")], p, pr)
        self.assertEqual(passing, [])
        self.assertIn(ex[0].code, {"capability_missing", "modality_unsupported"})


class ScoringTests(unittest.TestCase):
    def test_utilities_bounded_and_reproducible(self):
        models = [mk("a", q=0.9, inp=5, out=15), mk("b", q=0.6, inp=0.2, out=0.6), mk("c", q=0.75, inp=1, out=3)]
        s1, r1, _, _ = rank(models)
        s2, r2, _, _ = rank(list(reversed(models)))
        self.assertEqual(s1.selected_model_id, s2.selected_model_id)
        self.assertEqual([r.model_id for r in r1], [r.model_id for r in r2])
        for r in r1:
            for u in r.utilities.values():
                self.assertTrue(u is None or 0.0 <= u <= 1.0)

    def test_missing_data_is_not_zero_or_best(self):
        full = mk("full", q=0.7)
        gap = mk("gap", q=None, rel=None)
        _, rows, _, _ = rank([full, gap])
        g = next(r for r in rows if r.model_id == "gap")
        self.assertIn("quality", g.missing_dimensions)
        self.assertLess(g.confidence, next(r for r in rows if r.model_id == "full").confidence)
        self.assertEqual(rows[0].model_id, "full")

    def test_missing_dimension_never_beats_complete_equal_model(self):
        a, b = mk("a", q=0.8), mk("b", q=0.8, latency=None)
        sel, rows, _, _ = rank([b, a])
        self.assertEqual(sel.selected_model_id, "a")

    def test_cheap_preference_picks_cheap(self):
        models = [mk("strong", q=0.95, inp=15, out=60, cost=0.9), mk("cheap", q=0.7, inp=0.1, out=0.4, cost=0.05)]
        sel, *_ = rank(models, weight_overrides={"cost": 10, "quality": 1, "latency": 1, "reliability": 1, "risk": 1, "preference_alignment": 1})
        self.assertEqual(sel.selected_model_id, "cheap")

    def test_quality_preference_picks_strong(self):
        models = [mk("strong", q=0.95, inp=15, out=60, cost=0.9), mk("cheap", q=0.6, inp=0.1, out=0.4, cost=0.05)]
        sel, *_ = rank(models, weight_overrides={"quality": 10, "cost": 0.5, "latency": 0.5, "reliability": 1, "risk": 1, "preference_alignment": 1})
        self.assertEqual(sel.selected_model_id, "strong")

    def test_latency_preference_picks_fast(self):
        models = [mk("slow", q=0.9, latency=0.9, avg_latency=20.0), mk("fast", q=0.8, latency=0.05, avg_latency=1.0)]
        sel, *_ = rank(models, weight_overrides={"latency": 10, "quality": 1, "cost": 1, "reliability": 1, "risk": 1, "preference_alignment": 1})
        self.assertEqual(sel.selected_model_id, "fast")

    def test_preferences_change_ranking(self):
        models = [mk("strong", q=0.95, inp=15, out=60, cost=0.9), mk("cheap", q=0.65, inp=0.1, out=0.4, cost=0.05)]
        a, *_ = rank(models, weight_overrides={"quality": 10, "cost": 0.5, "latency": 0.5, "reliability": 1, "risk": 1, "preference_alignment": 1})
        b, *_ = rank(models, weight_overrides={"cost": 10, "quality": 0.5, "latency": 0.5, "reliability": 1, "risk": 1, "preference_alignment": 1})
        self.assertNotEqual(a.selected_model_id, b.selected_model_id)

    def test_high_scoring_model_removed_by_hard_constraint(self):
        models = [mk("best", q=0.99, inp=100, out=300), mk("ok", q=0.7, inp=0.1, out=0.3)]
        sel, rows, ex, _ = rank(models, max_cost=0.001)
        self.assertEqual(sel.selected_model_id, "ok")
        self.assertEqual([e.model_id for e in ex], ["best"])

    def test_tie_break_is_deterministic_by_model_id(self):
        sel1, *_ = rank([mk("b-model"), mk("a-model")])
        sel2, *_ = rank([mk("a-model"), mk("b-model")])
        self.assertEqual(sel1.selected_model_id, "a-model")
        self.assertEqual(sel2.selected_model_id, "a-model")
        self.assertTrue(sel1.tie_break_applied)

    def test_preferred_provider_breaks_tie(self):
        sel, *_ = rank([mk("a-model", provider="X"), mk("b-model", provider="Y")], preferred_providers=["Y"])
        self.assertEqual(sel.selected_model_id, "b-model")

    def test_pareto_marks_dominated(self):
        good = mk("good", q=0.9, cost=0.1, latency=0.1, rel=0.95, risk=0.05, inp=0.5, out=1)
        bad = mk("bad", q=0.5, cost=0.9, latency=0.9, rel=0.6, risk=0.4, inp=5, out=20)
        _, rows, _, _ = rank([good, bad])
        by = {r.model_id: r for r in rows}
        self.assertTrue(by["good"].pareto_optimal)
        self.assertFalse(by["bad"].pareto_optimal)
        self.assertIn("good", by["bad"].dominated_by)

    def test_single_candidate_selected_with_caveat(self):
        sel, rows, _, _ = rank([mk("only")])
        self.assertEqual(sel.selected_model_id, "only")
        self.assertEqual(len(rows), 1)

    def test_no_candidates_status(self):
        pr = prefs(P)
        sel = scoring.select([], pr, P)
        self.assertEqual(sel.status, "no_eligible_candidates")
        self.assertIsNone(sel.selected_model_id)
        with self.assertRaises(ValueError):
            scoring.score_candidates([], P, pr)

    def test_confidence_capped_when_clarification_needed(self):
        p = profile("fix this")
        pr = prefs(p)
        rows, _ = scoring.score_candidates([mk("a"), mk("b", q=0.5)], p, pr)
        sel = scoring.select(rows, pr, p)
        self.assertLessEqual(sel.confidence_value, 0.45)
        self.assertNotEqual(sel.confidence_level, "high")

    def test_weight_stability_reported(self):
        sel, *_ = rank([mk("a", q=0.95), mk("b", q=0.5)])
        self.assertIsNotNone(sel.weight_stability)
        self.assertTrue(0.0 <= sel.weight_stability <= 1.0)

    def test_observed_reliability_uses_wilson_lower_bound(self):
        self.assertLess(wilson_lower_bound(9, 10), 0.9)
        self.assertAlmostEqual(wilson_lower_bound(0, 0), 0.0)
        obs = {"a": ObservedStats(model_id="a", samples=50, successes=50, latencies=[1.0] * 50), "b": ObservedStats(model_id="b", samples=2, successes=2, latencies=[1.0, 1.0])}
        _, rows, _, _ = rank([mk("a", rel=0.5), mk("b", rel=0.5)], observed=obs)
        by = {r.model_id: r for r in rows}
        self.assertGreater(by["a"].utilities["reliability"], by["b"].utilities["reliability"])
        self.assertEqual(by["b"].evidence["reliability"].provenance, "estimated")

    def test_learning_adjustment_is_bounded(self):
        _, rows, _, _ = rank([mk("a")], learning={"a": 5.0})
        self.assertLessEqual(abs(rows[0].learning_adjustment), 0.2 + 1e-9)

    def test_sensitive_query_penalises_unverified_data_handling(self):
        p = profile("My password = hunter2hunter2 login fails, what dosage of ibuprofen?")
        pr = prefs(p)
        rows, _ = scoring.score_candidates([mk("unk", privacy="unknown", risk=0.1), mk("restricted", privacy="restricted", risk=0.1)], p, pr)
        by = {r.model_id: r for r in rows}
        self.assertLessEqual(by["unk"].utilities["risk"], by["restricted"].utilities["risk"])

    def test_scoring_config_exposed(self):
        self.assertEqual(ScoringConfig().missing_policy, "pessimistic")


if __name__ == "__main__":
    unittest.main()
