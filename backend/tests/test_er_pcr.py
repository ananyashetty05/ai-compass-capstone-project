"""ER-PCR (Evidence-aware Robust Preference-Constrained Routing): evidence, mathematics, decisions, behaviour, real-time.

Deterministic. No network, no database, no provider calls.
"""
import os
os.environ.setdefault("JWT_SECRET", "unit-test-only-secret-do-not-use-in-production")

import itertools
import math
import random
import time
import unittest
from datetime import date
from unittest.mock import patch

from app.services.routing_engine import cells as cells_mod, decision, filtering, normalization as N, pipeline, scoring
from app.services.routing_engine.evidence import (T0, T1, T1U, T2, T3, EvidenceRecord, applies, effective_tier, freshness, records_for)
from app.services.routing_engine.observed import ObservedStats
from app.services.routing_engine.policy import FIT, POLICY, validate_weights
from tests.engine_helpers import MEASURED_PROV, mk, prefs, profile

P = profile("Write a Python function that sorts a list of records.")
QUALITY_FIRST = {"quality": 10, "cost": 0.5, "latency": 0.5, "reliability": 0.5, "risk": 0.5}
COST_FIRST = {"cost": 10, "quality": 0.5, "latency": 0.5, "reliability": 0.5, "risk": 0.5}
SPEED_FIRST = {"latency": 10, "quality": 0.5, "cost": 0.5, "reliability": 0.5, "risk": 0.5}


def rank(models, p=P, **kw):
    pr = prefs(p, **{k: v for k, v in kw.items() if k not in {"observed", "store", "today"}})
    passing, excluded = filtering.filter_candidates(models, p, pr)
    rows, norm = scoring.score_candidates(passing, p, pr, observed=kw.get("observed"), evidence_store=kw.get("store"), today=kw.get("today"))
    return scoring.select(rows, pr, p), sorted(rows, key=lambda r: r.rank), excluded, norm


class EvidenceTiers(unittest.TestCase):
    def test_stale_evidence_is_demoted_one_tier_and_undated_measurement_is_documented(self):
        self.assertEqual(effective_tier(T3, "stale"), T2)
        self.assertEqual(effective_tier(T2, "stale"), T1)
        self.assertEqual(effective_tier(T1, "stale"), T1U)
        self.assertEqual(effective_tier(T3, "undated"), T2)
        self.assertEqual(effective_tier(T3, "fresh"), T3)

    def test_freshness_windows_are_per_metric_policy(self):
        today = date(2026, 11, 20)
        self.assertEqual(freshness("2026-11-01", POLICY.freshness_for("pricing"), today), "fresh")
        self.assertEqual(freshness("2026-01-01", POLICY.freshness_for("pricing"), today), "stale")
        self.assertEqual(freshness("2026-01-01", POLICY.freshness_for("capability"), today), "fresh")
        self.assertEqual(freshness(None, 90, today), "undated")

    def test_evidence_applies_only_to_the_exact_model_version_and_matching_task(self):
        r = EvidenceRecord(metric="quality", value=0.9, unit="0-1", source="s", tier=T3, model_id="m-v2", date="2026-11-01", scope="coding")
        self.assertTrue(applies(r, "m-v2", "coding"))
        self.assertFalse(applies(r, "m-v1", "coding"))          # another version
        self.assertFalse(applies(r, "m-v2", "translation"))     # another task
        self.assertEqual(records_for({"m-v2": [r]}, "m-v1", "coding", "quality"), [])

    def test_unverified_estimate_never_ranks_and_is_labelled(self):
        _, rows, _, _ = rank([mk("a", q=0.99), mk("b", q=0.1)], weight_overrides=QUALITY_FIRST)
        for r in rows:
            self.assertIsNone(r.utilities["quality"])
            self.assertEqual(r.evidence["quality"].tier, "unverified_estimate")
            self.assertFalse(r.evidence["quality"].used_in_ranking)
            self.assertIsNotNone(r.evidence["quality"].raw_value)       # displayed, not hidden

    def test_a_dated_record_for_the_exact_model_ranks_and_carries_its_metadata(self):
        rec = EvidenceRecord(metric="quality", value=0.9, unit="0-1 task success", source="https://example.org/eval", tier=T3, model_id="a", date="2026-11-10",
                             scope="all", method="held-out suite", sample_size=500)
        sel, rows, _, _ = rank([mk("a", q=None), mk("b", q=None)], weight_overrides=QUALITY_FIRST, store={"a": [rec]}, today=date(2026, 11, 20))
        by = {r.model_id: r for r in rows}
        self.assertEqual(sel.selected_model_id, "a")
        e = by["a"].evidence["quality"]
        self.assertEqual((e.tier, e.used_in_ranking, e.sample_size, e.source, e.date), ("measured", True, 500, "https://example.org/eval", "2026-11-10"))
        self.assertIn("quality", by["b"].evidence_gaps)

    def test_a_stale_record_is_demoted_not_dropped(self):
        rec = EvidenceRecord(metric="quality", value=0.9, unit="0-1", source="s", tier=T2, model_id="a", date="2024-01-01")
        _, rows, _, _ = rank([mk("a", q=None)], weight_overrides=QUALITY_FIRST, store={"a": [rec]}, today=date(2026, 11, 20))
        self.assertEqual(rows[0].evidence["quality"].freshness, "stale")
        self.assertEqual(rows[0].evidence["quality"].tier, "estimate")      # T2 -> T1: still rankable, flagged

    def test_registry_provenance_must_name_a_process_to_rank(self):
        _, rows, _, _ = rank([mk("a", q=0.7, prov=MEASURED_PROV)], weight_overrides=QUALITY_FIRST)
        self.assertEqual(rows[0].utilities["quality"], 0.7)
        _, rows, _, _ = rank([mk("a", q=0.7, prov={"quality": "estimated"})], weight_overrides=QUALITY_FIRST)
        self.assertIsNone(rows[0].utilities["quality"])


class Eligibility(unittest.TestCase):
    def test_unknown_price_cannot_satisfy_a_cost_cap(self):
        pr = prefs(P, max_cost=0.01)
        passing, ex = filtering.filter_candidates([mk("unpriced", inp=None, out=None), mk("ok", inp=0.1, out=0.2)], P, pr)
        self.assertEqual([m.model_id for m in passing], ["ok"])
        self.assertEqual(ex[0].code, "cost_unverifiable")

    def test_unknown_privacy_cannot_satisfy_mandatory_privacy(self):
        pr = prefs(P, privacy_requirement="strict")
        passing, ex = filtering.filter_candidates([mk("unk", privacy="unknown"), mk("doc", privacy="provider_documented_restricted")], P, pr)
        self.assertEqual([m.model_id for m in passing], ["doc"])
        self.assertEqual(ex[0].code, "privacy_unverified")

    def test_high_score_never_overrides_a_hard_constraint(self):
        sel, rows, ex, _ = rank([mk("best", q=0.99, inp=100, out=300, prov=MEASURED_PROV), mk("ok", q=0.5, inp=0.1, out=0.3, prov=MEASURED_PROV)], max_cost=0.001,
                                weight_overrides=QUALITY_FIRST)
        self.assertEqual(sel.selected_model_id, "ok")
        self.assertEqual([e.model_id for e in ex], ["best"])

    def test_no_eligible_result_is_explicit(self):
        pr = prefs(P, excluded_providers=["Test"])
        passing, ex = filtering.filter_candidates([mk("a")], P, pr)
        sel = scoring.select([], pr, P)
        self.assertEqual((passing, sel.decision_status, sel.selected_model_id), ([], "no_eligible_candidates", None))
        self.assertTrue(ex and ex[0].reason)


class Mathematics(unittest.TestCase):
    def test_direction_higher_utility_is_always_better(self):
        self.assertGreater(N.cost_utility(1e-4), N.cost_utility(1e-2))
        self.assertGreater(N.latency_utility(0.5), N.latency_utility(20))
        self.assertGreater(N.risk_suitability(0.1), N.risk_suitability(0.9))

    def test_fixed_anchors_are_candidate_independent(self):
        # the utility of a value must not depend on which other candidates exist
        u = N.cost_utility(0.003)
        self.assertEqual(u, N.cost_utility(0.003))
        a = rank([mk("a", inp=1, out=4, prov=MEASURED_PROV), mk("b", inp=50, out=200, prov=MEASURED_PROV)])[1]
        b = rank([mk("a", inp=1, out=4, prov=MEASURED_PROV)])[1]
        self.assertEqual(next(r for r in a if r.model_id == "a").utilities["cost"], b[0].utilities["cost"])

    def test_normalization_saturates_and_is_bounded(self):
        for x in (1e-12, 1e-5, 1e-3, 0.1, 5.0):
            self.assertTrue(0.0 <= N.cost_utility(x) <= 1.0)
        self.assertEqual(N.cost_utility(0), 1.0)
        self.assertEqual(N.latency_utility(1e-9), 1.0)
        self.assertEqual(N.latency_utility(1e6), 0.0)

    def test_invalid_numbers_are_unknown_not_best_or_worst(self):
        for bad in (None, float("nan"), float("inf"), -1.0):
            self.assertIsNone(N.cost_utility(bad))
            self.assertIsNone(N.latency_utility(bad))
        self.assertIsNone(N.unit_interval(1.5))
        self.assertIsNone(N.unit_interval(float("nan")))

    def test_weight_validation_rejects_instead_of_repairing(self):
        for bad in ({}, {"a": -1}, {"a": float("nan")}, {"a": 0, "b": 0}, {"a": "x"}):
            with self.assertRaises(ValueError, msg=str(bad)):
                validate_weights(bad)
        self.assertAlmostEqual(sum(validate_weights({"a": 3, "b": 1}).values()), 1.0)

    def test_primary_weights_sum_to_one_and_explicit_priorities_are_separated_from_defaults(self):
        pr = prefs(P, weight_overrides=COST_FIRST)
        explicit, prioritised = decision.explicit_weights(pr.base_weights, pr.adjustments, scoring.DEFAULT_WEIGHTS)
        self.assertEqual(prioritised, ["cost"])
        w = decision.primary_weights(explicit, prioritised)
        self.assertAlmostEqual(sum(w.values()), 1.0)
        self.assertAlmostEqual(w[FIT], POLICY.fit_share)
        _, none_prioritised = decision.explicit_weights(prefs(P).base_weights, prefs(P).adjustments, scoring.DEFAULT_WEIGHTS)
        self.assertEqual(none_prioritised, [])
        self.assertEqual(decision.primary_weights(explicit, []), {FIT: 1.0})

    def test_explicit_wording_is_a_stated_priority_but_inferred_difficulty_is_not(self):
        explicit = profile("Explain quantum computing quickly and cheaply, it must be very accurate.")
        rows, _ = scoring.score_candidates([mk("a"), mk("b", q=0.2)], explicit, prefs(explicit))
        self.assertTrue({"cost", "latency"} <= set(rows[0].score_weights))      # the user asked for these in words
        hard = profile("Prove that there are infinitely many primes and verify every step of the argument carefully.")
        pr = prefs(hard)
        inferred = [a for a in pr.adjustments if a.origin == "inferred"]
        rows, _ = scoring.score_candidates([mk("a"), mk("b", q=0.2)], hard, pr)
        self.assertIn("quality", rows[0].score_weights)   # "verify carefully" is an explicit accuracy request
        self.assertTrue(inferred)
        self.assertNotIn("cost", rows[0].score_weights, "an inferred multiplier (cost x0.9 for a complex task) must never rank candidates")

    def test_scores_are_finite_and_in_unit_interval(self):
        rnd = random.Random(5)
        models = [mk(f"m{i}", q=rnd.random(), inp=rnd.random() * 20, out=rnd.random() * 60, prov=MEASURED_PROV, avg_latency=rnd.random() * 30, rel=rnd.random()) for i in range(30)]
        for ov in (QUALITY_FIRST, COST_FIRST, SPEED_FIRST, None):
            _, rows, _, _ = rank(models, **({"weight_overrides": ov} if ov else {}))
            for r in rows:
                for v in (r.robust_score, r.score_upper, r.confidence):
                    self.assertTrue(math.isfinite(v) and 0.0 <= v <= 1.0 + 1e-9)
                self.assertGreaterEqual(r.score_upper + 1e-9, r.robust_score)

    def test_unknown_is_not_credited_and_best_case_is_displayed_separately(self):
        _, rows, _, _ = rank([mk("known", rel=0.9, prov=MEASURED_PROV), mk("gap", rel=None, prov=MEASURED_PROV)], weight_overrides={"reliability": 10, "quality": 0.5, "cost": 0.5, "latency": 0.5, "risk": 0.5})
        by = {r.model_id: r for r in rows}
        self.assertLess(by["gap"].robust_score, by["known"].robust_score)
        self.assertGreater(by["gap"].score_upper, by["gap"].robust_score)
        self.assertEqual(by["gap"].evidence_gaps, ["reliability"])

    def test_exact_weight_margin_matches_brute_force(self):
        from app.services.routing_engine import robustness
        w = {"a": 0.5, "b": 0.3, "c": 0.2}
        top, riv = {"a": 0.9, "b": 0.5, "c": 0.4}, {"a": 0.6, "b": 0.9, "c": 0.8}
        m = robustness.weight_margin(top, riv, w)
        best = None
        n = 200
        for i, j in itertools.product(range(n + 1), repeat=2):
            if i + j > n:
                continue
            w2 = {"a": i / n, "b": j / n, "c": (n - i - j) / n}
            if sum(w2[d] * riv[d] for d in w) >= sum(w2[d] * top[d] for d in w) - 1e-12:
                tv = 0.5 * sum(abs(w2[d] - w[d]) for d in w)
                best = tv if best is None else min(best, tv)
        self.assertLessEqual(m, best + 1e-9)
        self.assertGreater(m, best - 0.01)


class Decisions(unittest.TestCase):
    def test_status_function_covers_every_branch(self):
        base = dict(n=3, tied_top=1, strict_leader=True, gaps_top=[], margin=0.5, feedback_decided=False, needs_clarification=False)
        self.assertEqual(decision.status(**base)[0], "recommended")
        self.assertEqual(decision.status(**{**base, "n": 0})[0], "no_eligible_candidates")
        self.assertEqual(decision.status(**{**base, "needs_clarification": True})[0], "needs_clarification")
        self.assertEqual(decision.status(**{**base, "gaps_top": ["quality"]})[0], "insufficient_evidence")
        self.assertEqual(decision.status(**{**base, "tied_top": 2})[0], "indistinguishable")
        self.assertEqual(decision.status(**{**base, "feedback_decided": True})[0], "qualified")
        self.assertEqual(decision.status(**{**base, "margin": 0.01})[0], "qualified")

    def test_equal_evidence_is_reported_as_indistinguishable_with_alternatives(self):
        sel, rows, _, _ = rank([mk("b-model"), mk("a-model")])
        self.assertEqual(sel.decision_status, "indistinguishable")
        self.assertEqual(sel.alternative_ids, ["b-model"] if sel.selected_model_id == "a-model" else ["a-model"])
        self.assertEqual(sel.selected_model_id, "a-model")          # fixed deterministic fallback

    def test_prioritised_objective_without_evidence_gives_insufficient_evidence(self):
        sel, _, _, _ = rank([mk("a", q=0.9), mk("b", q=0.2)], weight_overrides=QUALITY_FIRST)
        self.assertEqual(sel.decision_status, "insufficient_evidence")
        self.assertIn("quality", sel.evidence_gaps)
        self.assertLessEqual(sel.confidence_value, 0.45)

    def test_verified_priority_with_a_clear_leader_is_recommended(self):
        sel, _, _, _ = rank([mk("hi", q=0.95, prov=MEASURED_PROV), mk("lo", q=0.30, prov=MEASURED_PROV)], weight_overrides=QUALITY_FIRST)
        self.assertEqual((sel.selected_model_id, sel.decision_status), ("hi", "recommended"))

    def test_feedback_only_separates_equal_evidence_and_is_declared_qualified(self):
        pr = prefs(P)
        rows, _ = scoring.score_candidates([mk("a"), mk("b")], P, pr, learning={"b": 0.1})
        sel = scoring.select(rows, pr, P)
        self.assertEqual((sel.selected_model_id, sel.decision_status), ("b", "qualified"))
        rows, _ = scoring.score_candidates([mk("hi", q=0.9, prov=MEASURED_PROV), mk("lo", q=0.2, prov=MEASURED_PROV)], P, prefs(P, weight_overrides=QUALITY_FIRST), learning={"lo": 0.2})
        self.assertEqual(scoring.select(rows, prefs(P, weight_overrides=QUALITY_FIRST), P).selected_model_id, "hi")   # feedback never beats evidence

    def test_clarification_is_not_hidden(self):
        p = profile("fix this")
        pr = prefs(p)
        rows, _ = scoring.score_candidates([mk("a"), mk("b", q=0.5)], p, pr)
        self.assertEqual(scoring.select(rows, pr, p).decision_status, "needs_clarification")


class Behaviour(unittest.TestCase):
    MODELS = lambda self: [  # noqa: E731
        mk("premium", q=0.95, inp=15, out=60, avg_latency=12.0, rel=0.97, prov=MEASURED_PROV),
        mk("budget", q=0.60, inp=0.1, out=0.4, avg_latency=6.0, rel=0.90, prov=MEASURED_PROV),
        mk("fast", q=0.75, inp=1.0, out=3.0, avg_latency=0.6, rel=0.92, prov=MEASURED_PROV)]

    def test_quality_cost_latency_priorities_each_choose_their_candidate(self):
        for ov, expect in ((QUALITY_FIRST, "premium"), (COST_FIRST, "budget"), (SPEED_FIRST, "fast")):
            with self.subTest(priority=list(ov)[0]):
                sel, *_ = rank(self.MODELS(), weight_overrides=ov)
                self.assertEqual(sel.selected_model_id, expect)

    def test_conflicting_priorities_are_balanced_by_the_user_weights(self):
        sel, rows, *_ = rank(self.MODELS(), weight_overrides={"quality": 5, "cost": 5, "latency": 0.5, "reliability": 0.5, "risk": 0.5})
        self.assertEqual(set(rows[0].score_weights), {FIT, "quality", "cost"})
        self.assertIn(sel.selected_model_id, {"premium", "budget", "fast"})

    def test_privacy_priority_uses_documented_handling_only(self):
        p = profile("My password = hunter2hunter2 login fails, what dosage of ibuprofen?")
        pr = prefs(p, weight_overrides={"risk": 10, "quality": 0.5, "cost": 0.5, "latency": 0.5, "reliability": 0.5})
        rows, _ = scoring.score_candidates([mk("unk", privacy="unknown"), mk("doc", privacy="provider_documented_restricted")], p, pr)
        by = {r.model_id: r for r in rows}
        self.assertGreater(by["doc"].utilities["risk"], by["unk"].utilities["risk"])
        self.assertEqual(by["doc"].evidence["risk"].tier, "documented")

    def test_incomplete_registry_does_not_reward_missing_fields(self):
        full = mk("full", q=0.5, prov=MEASURED_PROV)
        sparse = mk("sparse", q=None, rel=None, latency=None, risk=None, inp=None, out=None)
        _, rows, _, _ = rank([sparse, full], weight_overrides=QUALITY_FIRST)
        self.assertEqual(rows[0].model_id, "full")

    def test_adding_or_removing_a_non_winner_never_changes_the_order_of_others(self):
        models = self.MODELS()
        full = rank(models, weight_overrides=COST_FIRST)[1]
        order = [r.model_id for r in full]
        for victim in order[1:]:
            rest = [m for m in models if m.model_id != victim]
            again = [r.model_id for r in rank(rest, weight_overrides=COST_FIRST)[1]]
            self.assertEqual(again, [m for m in order if m != victim])
        extra = mk("extra", q=0.1, inp=90, out=300, avg_latency=50.0, prov=MEASURED_PROV)
        with_extra = [r.model_id for r in rank(models + [extra], weight_overrides=COST_FIRST)[1]]
        self.assertEqual([m for m in with_extra if m != "extra"], order)

    def test_input_order_does_not_change_the_result(self):
        models = self.MODELS()
        for ov in (QUALITY_FIRST, COST_FIRST):
            ref = [r.model_id for r in rank(models, weight_overrides=ov)[1]]
            for perm in itertools.permutations(models):
                self.assertEqual([r.model_id for r in rank(list(perm), weight_overrides=ov)[1]], ref)

    def test_determinism(self):
        a = [(r.model_id, r.robust_score) for r in rank(self.MODELS(), weight_overrides=COST_FIRST)[1]]
        b = [(r.model_id, r.robust_score) for r in rank(self.MODELS(), weight_overrides=COST_FIRST)[1]]
        self.assertEqual(a, b)

    def test_observed_telemetry_is_measured_evidence_only_with_enough_samples(self):
        obs = {"a": ObservedStats(model_id="a", samples=60, successes=60, latency_p50_seconds=0.5), "b": ObservedStats(model_id="b", samples=2, successes=2, latency_p50_seconds=0.5)}
        _, rows, _, _ = rank([mk("a", avg_latency=9.0), mk("b", avg_latency=9.0)], weight_overrides=SPEED_FIRST, observed=obs)
        by = {r.model_id: r for r in rows}
        self.assertEqual(by["a"].evidence["latency"].tier, "measured")
        self.assertIn("latency", by["b"].evidence_gaps)


class Explanations(unittest.TestCase):
    def test_explanation_separates_ranked_and_not_ranked_evidence(self):
        res = pipeline.run(pipeline.PipelineRequest(query=P.query if hasattr(P, "query") else "Write a Python function that sorts a list of records."), saved_weights=None, user_id=None,
                           catalog_loader=lambda t, m: ([mk("a", q=0.9), mk("b", q=0.5)], []), learning_loader=lambda u, i: {}, observed_loader=lambda i: {})
        facts = {f["type"]: f for f in res.explanation.facts}
        self.assertIn("data_quality", facts)
        self.assertIn("evidence_by_tier", facts["data_quality"])
        self.assertIn("unverified_estimate", facts["data_quality"]["evidence_by_tier"])
        self.assertTrue(any("never used to rank" in x for x in res.explanation.unavailable_data))
        self.assertIn("not a probability", res.explanation.confidence_statement)
        self.assertTrue(res.selection.decision_status)


class RealTime(unittest.TestCase):
    def test_fifty_candidates_no_provider_or_network_calls(self):
        rnd = random.Random(1)
        models = [mk(f"m{i:02d}", q=rnd.random(), inp=rnd.random() * 20, out=rnd.random() * 60, avg_latency=rnd.random() * 30, rel=rnd.random(), prov=MEASURED_PROV) for i in range(50)]
        import socket
        with patch.object(socket.socket, "connect", side_effect=AssertionError("network call during ranking")):
            t = time.perf_counter()
            for _ in range(20):
                sel, rows, _, _ = rank(models, weight_overrides=QUALITY_FIRST)
            per_call_ms = (time.perf_counter() - t) * 1000 / 20
        self.assertEqual(len(rows), 50)
        self.assertLess(per_call_ms, 500, f"ranking 50 candidates took {per_call_ms:.1f} ms")  # generous bound; measured value is reported by research/er_pcr_benchmark.py


if __name__ == "__main__":
    unittest.main()
