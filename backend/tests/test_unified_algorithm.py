"""Unit tests for the unified algorithm's own rules (live-catalogue pool, injected models; deterministic)."""
import os
os.environ.setdefault("JWT_SECRET", "unit-test-only-secret-do-not-use-in-production")

import itertools
import random
import unittest

from app.services.routing_engine import filtering, pipeline, robustness, scoring
from app.services.routing_engine.types import ScoringConfig
from tests.engine_helpers import MEASURED_PROV, mk, prefs, profile


def run_pipeline(catalog, query="Write a Python function that sorts a list of records.", **kw):
    return pipeline.run(pipeline.PipelineRequest(query=query, **kw), saved_weights=None, user_id=None, catalog_loader=lambda t, m: (list(catalog), []),
                        learning_loader=lambda u, ids: {}, observed_loader=lambda ids: {})


class MissingMetrics(unittest.TestCase):
    def setUp(self):
        self.p = profile()
        self.pr = prefs(self.p)

    def score(self, models):
        rows, _ = scoring.score_candidates(models, self.p, self.pr)
        return {r.model_id: r for r in rows}

    def test_unknown_metric_earns_no_credit_and_is_reported_as_a_gap(self):
        """ER-PCR: an unknown is not a prior, not zero and not perfect; it is not credited, and the gap is reported when the user prioritised that objective."""
        p = profile()
        pr = prefs(p, weight_overrides={"reliability": 10, "quality": 0.5, "cost": 0.5, "latency": 0.5, "risk": 0.5})
        rows, _ = scoring.score_candidates([mk("known", rel=0.85, prov=MEASURED_PROV), mk("unknown", rel=None, prov=MEASURED_PROV)], p, pr)
        by = {r.model_id: r for r in rows}
        self.assertIn("reliability", by["unknown"].missing_dimensions)
        self.assertIn("reliability", by["unknown"].evidence_gaps)
        self.assertEqual(by["unknown"].adjusted_values["reliability"], 0.0)
        self.assertLess(by["unknown"].confidence, by["known"].confidence)

    def test_unknown_is_neither_the_worst_nor_the_best_it_is_not_credited(self):
        p = profile()
        pr = prefs(p, weight_overrides={"reliability": 10, "quality": 0.5, "cost": 0.5, "latency": 0.5, "risk": 0.5})
        rows, _ = scoring.score_candidates([mk("poor_known", rel=0.10, prov=MEASURED_PROV), mk("unknown", rel=None, prov=MEASURED_PROV), mk("good_known", rel=0.95, prov=MEASURED_PROV)], p, pr)
        by = {r.model_id: r for r in rows}
        self.assertLess(by["unknown"].robust_score, by["good_known"].robust_score)
        self.assertLessEqual(by["unknown"].robust_score, by["poor_known"].robust_score + 0.55)  # fit share is the same for all three
        self.assertGreater(by["unknown"].score_upper, by["unknown"].robust_score)  # best case is displayed separately and never ranks

    def test_an_unknown_metric_never_beats_an_equally_good_known_one(self):
        by = self.score([mk("a_known", rel=0.5), mk("b_unknown", rel=None)])
        self.assertGreaterEqual(by["a_known"].robust_score, by["b_unknown"].robust_score)


class ExactOrderingLive(unittest.TestCase):
    def test_small_score_gap_is_ordered_by_score_not_by_list_order(self):
        p = profile(); pr = prefs(p)
        pr = prefs(p, weight_overrides={"quality": 10, "cost": 0.5, "latency": 0.5, "reliability": 0.5, "risk": 0.5})
        a, b = mk("listed_first", q=0.800, prov=MEASURED_PROV), mk("listed_second", q=0.803, prov=MEASURED_PROV)
        rows, _ = scoring.score_candidates([a, b], p, pr)
        rows[0].editorial_order, rows[1].editorial_order = 0, 1
        self.assertLess(abs(rows[0].robust_score - rows[1].robust_score), 0.005)
        sel = scoring.select(rows, pr, p)
        self.assertEqual(sel.selected_model_id, "listed_second")
        self.assertIsNone(sel.tie_break_applied)

    def test_tie_rules_apply_only_to_exactly_equal_scores(self):
        p = profile(); pr = prefs(p)
        rows, _ = scoring.score_candidates([mk("b_same"), mk("a_same")], p, pr)
        sel = scoring.select(rows, pr, p)
        self.assertEqual(sel.selected_model_id, "a_same")
        self.assertIsNotNone(sel.tie_break_applied)

    def test_removing_a_non_winner_never_changes_the_winner(self):
        rnd = random.Random(7)
        p = profile(); pr = prefs(p)
        violations = 0
        for _ in range(300):
            models = [mk(f"m{i}", q=rnd.random(), rel=rnd.choice([None, rnd.random()]), latency=rnd.random(), cost=rnd.random(), risk=rnd.random()) for i in range(6)]
            rows, _ = scoring.score_candidates(models, p, pr)
            win = scoring.select(rows, pr, p).selected_model_id
            drop = next(m for m in models if m.model_id != win)
            rows2, _ = scoring.score_candidates([m for m in models if m is not drop], p, pr)
            violations += scoring.select(rows2, pr, p).selected_model_id != win
        self.assertEqual(violations, 0)


class WeightMargin(unittest.TestCase):
    def test_margin_is_exact_against_brute_force_search(self):
        rnd = random.Random(11)
        dims = ["a", "b", "c"]
        for _ in range(40):
            w = {d: rnd.random() + 0.05 for d in dims}
            tot = sum(w.values()); w = {d: v / tot for d, v in w.items()}
            top = {d: rnd.random() for d in dims}; riv = {d: rnd.random() for d in dims}
            if sum(w[d] * top[d] for d in dims) <= sum(w[d] * riv[d] for d in dims):
                continue
            m = robustness.weight_margin(top, riv, w)
            # brute force: smallest total-variation shift over a fine grid of weight vectors at which the rival catches up
            best = None
            n = 120
            for i, j in itertools.product(range(n + 1), repeat=2):
                if i + j > n:
                    continue
                w2 = {"a": i / n, "b": j / n, "c": (n - i - j) / n}
                if sum(w2[d] * riv[d] for d in dims) >= sum(w2[d] * top[d] for d in dims) - 1e-12:
                    tv = 0.5 * sum(abs(w2[d] - w[d]) for d in dims)
                    best = tv if best is None else min(best, tv)
            if m is None:
                self.assertIsNone(best)
            else:
                self.assertIsNotNone(best)
                self.assertLessEqual(m, best + 1e-9)               # exact optimum can never exceed a grid point
                self.assertGreaterEqual(m, best - 2.5 / n)        # and sits within one grid cell of the best grid point

    def test_winner_ahead_on_every_objective_has_no_finite_margin(self):
        self.assertIsNone(robustness.weight_margin({"a": 0.9, "b": 0.9}, {"a": 0.1, "b": 0.2}, {"a": 0.5, "b": 0.5}))

    def test_selection_exposes_the_margin(self):
        p = profile(); pr = prefs(p, weight_overrides={"quality": 4, "reliability": 4, "cost": 0.5, "latency": 0.5, "risk": 0.5})
        rows, _ = scoring.score_candidates([mk("hi", q=0.95, rel=0.9, prov=MEASURED_PROV), mk("lo", q=0.5, rel=0.95, prov=MEASURED_PROV)], p, pr)
        sel = scoring.select(rows, pr, p)
        self.assertEqual(sel.weight_margin_rival, "lo")
        self.assertGreater(sel.weight_margin, 0.0)


class UnitPriceLimits(unittest.TestCase):
    def setUp(self):
        self.p = profile()

    def check(self, model, **kw):
        pr = prefs(self.p, **kw)
        return [e.code for e in filtering.check_model(model, self.p, pr)]

    def test_input_and_output_price_limits(self):
        self.assertEqual(self.check(mk("ok", inp=1, out=4), max_input_price_per_million=2, max_output_price_per_million=5), [])
        self.assertIn("unit_price_exceeds_limit", self.check(mk("dear_in", inp=3, out=4), max_input_price_per_million=2))
        self.assertIn("unit_price_exceeds_limit", self.check(mk("dear_out", inp=1, out=9), max_output_price_per_million=5))

    def test_unpublished_price_cannot_be_verified_so_it_is_excluded(self):
        self.assertIn("cost_unverifiable", self.check(mk("nopx", inp=None, out=None), max_input_price_per_million=2))

    def test_request_cost_limit_wording_is_an_estimate(self):
        pr = prefs(self.p, max_cost=0.0000001)
        e = filtering.check_model(mk("x", inp=10, out=30), self.p, pr)[0]
        self.assertEqual(e.code, "cost_exceeds_limit")
        self.assertIn("not a guaranteed or billed amount", e.reason)

    def test_limits_flow_through_the_pipeline(self):
        cat = [mk("cheap", inp=0.5, out=1.0), mk("dear", inp=8, out=20)]
        res = run_pipeline(cat, max_input_price_per_million=1.0)
        self.assertEqual([c.model_id for c in res.candidates], ["cheap"])
        self.assertIn("unit_price_exceeds_limit", {e.code for e in res.exclusions})


class StrictPrivacyNote(unittest.TestCase):
    def test_undated_documentation_is_flagged_on_the_selected_model(self):
        cat = [mk("doc", privacy="provider_documented_restricted")]
        res = run_pipeline(cat, privacy_requirement="strict")
        self.assertEqual(res.selection.selected_model_id, "doc")
        self.assertTrue(any("verification date" in c for c in res.selection.caveats), res.selection.caveats)

    def test_stale_documentation_is_flagged_and_fresh_is_not(self):
        old = mk("old", privacy="provider_documented_restricted").model_copy(update={"last_verified_at": "2020-01-01T00:00:00Z"})
        res = run_pipeline([old], privacy_requirement="strict")
        self.assertTrue(any("days ago" in c for c in res.selection.caveats))
        from datetime import datetime, timezone
        fresh = mk("fresh", privacy="provider_documented_restricted").model_copy(update={"last_verified_at": datetime.now(timezone.utc).isoformat()})
        self.assertIsNone(pipeline._privacy_doc_note(fresh))

    def test_models_without_documented_handling_are_still_excluded(self):
        res = run_pipeline([mk("undocumented", privacy="unknown")], privacy_requirement="strict")
        self.assertEqual(res.status, "no_eligible_candidates")


if __name__ == "__main__":
    unittest.main()
