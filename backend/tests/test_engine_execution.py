"""Execution, retry, fallback, escalation, budget and evaluation tests with mocked adapters (no network)."""
import random
import unittest

from tests.engine_helpers import mk, prefs, profile
from app.services.routing_engine import execution, filtering, scoring
from app.services.routing_engine.types import ExecutionPolicy


class ProviderError(Exception):
    def __init__(self, kind, retryable):
        super().__init__(kind)
        self.kind, self.retryable = kind, retryable


class FakeAdapter:
    def __init__(self, script, calls):
        self.script, self.calls, self._u = list(script), calls, {}

    def generate(self, prompt, **kw):
        self.calls.append(prompt)
        step = self.script.pop(0) if self.script else "ok"
        if isinstance(step, Exception):
            raise step
        self._u = {"input_tokens": 100, "output_tokens": 50, "latency_ms": 10.0}
        return step

    def get_usage(self):
        return self._u


class Harness:
    def __init__(self, scripts, models, query="Explain what a hash map is in a few sentences.", **policy):
        self.p = profile(query)
        self.query = query
        self.models = {m.model_id: m for m in models}
        pr = prefs(self.p)
        rows, _ = scoring.score_candidates(models, self.p, pr)
        self.rows = sorted(rows, key=lambda r: r.rank)
        self.scripts, self.calls, self.sleeps = scripts, [], []
        self.policy = ExecutionPolicy(**policy)

    def factory(self, model):
        return FakeAdapter(self.scripts.get(model.model_id, []), self.calls)

    def run(self, **kw):
        return execution.execute(ranked=self.rows, models=self.models, prompt="PROMPT", query=self.query, profile=self.p, policy=self.policy, prompt_source="optimized",
                                 adapter_factory=self.factory, sleep=self.sleeps.append, rng=random.Random(1), **kw)


GOOD = "A hash map stores key-value pairs and uses a hash function to find a slot. Lookups are typically constant time."


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.a = mk("a", q=0.9)
        self.b = mk("b", q=0.8)

    def test_success_first_try(self):
        h = Harness({"a": [GOOD]}, [self.a, self.b])
        out, ev = h.run()
        self.assertEqual(out.status, "succeeded")
        self.assertEqual(out.final_model_id, h.rows[0].model_id)
        self.assertFalse(out.escalated)
        self.assertEqual(len(out.attempts), 1)
        self.assertEqual(h.calls, ["PROMPT"])
        self.assertIsNotNone(out.total_cost_usd)

    def test_retryable_error_retries_with_backoff_then_succeeds(self):
        first = Harness({}, [self.a, self.b]).rows[0].model_id
        h = Harness({first: [ProviderError("rate_limit", True), GOOD]}, [self.a, self.b], base_backoff_seconds=0.5, max_backoff_seconds=2.0)
        out, _ = h.run()
        self.assertEqual(out.status, "succeeded")
        self.assertEqual(out.final_model_id, first)
        self.assertEqual(len(h.sleeps), 1)
        self.assertTrue(0 <= h.sleeps[0] <= 0.5)
        self.assertEqual([a.outcome for a in out.attempts], ["error", "success"])

    def test_retries_are_bounded(self):
        first = Harness({}, [self.a, self.b]).rows[0].model_id
        h = Harness({first: [ProviderError("timeout", True)] * 10}, [self.a, self.b], max_retries_per_model=1, max_attempts=6)
        out, _ = h.run()
        errs = [a for a in out.attempts if a.model_id == first]
        self.assertEqual(len(errs), 2)  # initial + one retry

    def test_permanent_error_not_retried_and_falls_back(self):
        first = Harness({}, [self.a, self.b]).rows[0].model_id
        h = Harness({first: [ProviderError("invalid_request", False)]}, [self.a, self.b])
        out, _ = h.run()
        self.assertEqual(h.sleeps, [])
        self.assertTrue(out.escalated)
        self.assertEqual(out.escalation_reason, "provider_error_fallback")
        self.assertNotEqual(out.final_model_id, first)

    def test_auth_failure_skips_remaining_models_from_same_provider(self):
        a, b, c = mk("a", q=0.9, provider="P1"), mk("b", q=0.85, provider="P1"), mk("c", q=0.7, provider="P2")
        h = Harness({}, [a, b, c])
        h.scripts = {h.rows[0].model_id: [ProviderError("authentication", False)]}
        out, _ = h.run()
        used = {x.model_id for x in out.attempts}
        failed_provider = h.models[h.rows[0].model_id].provider
        self.assertFalse(any(h.models[m].provider == failed_provider for m in used if m != h.rows[0].model_id))
        self.assertEqual(out.status, "succeeded")

    def test_all_fail_reports_failed(self):
        h = Harness({"a": [ProviderError("unavailable", False)], "b": [ProviderError("unavailable", False)]}, [self.a, self.b])
        out, ev = h.run()
        self.assertEqual(out.status, "failed")
        self.assertIsNone(out.response_text)

    def test_max_attempts_bound(self):
        models = [mk(f"m{i}", q=0.9 - i * 0.01) for i in range(5)]
        h = Harness({m.model_id: [ProviderError("unavailable", False)] for m in models}, models, max_attempts=2)
        out, _ = h.run()
        self.assertLessEqual(len(out.attempts), 2)

    def test_budget_skips_unaffordable_models(self):
        pricey, cheap = mk("pricey", q=0.95, inp=1000, out=3000), mk("cheap", q=0.7, inp=0.1, out=0.2)
        h = Harness({}, [pricey, cheap], budget_usd=0.01)
        out, _ = h.run()
        self.assertIn("skipped_budget", [a.outcome for a in out.attempts])
        self.assertEqual(out.final_model_id, "cheap")

    def test_budget_with_unknown_price_cannot_be_enforced(self):
        h = Harness({}, [mk("unpriced", inp=None, out=None)], budget_usd=1.0)
        out, _ = h.run()
        self.assertEqual(out.attempts[0].outcome, "skipped_budget")
        self.assertEqual(out.status, "budget_exhausted")
        self.assertIsNone(out.response_text)

    def test_escalation_only_to_higher_quality_and_bounded(self):
        # invalid JSON from the first (lower-quality listed first by a preference for cost) model triggers escalation to a stronger one
        q = "List three fruits as JSON."
        weak, strong = mk("weak", q=0.6, inp=0.1, out=0.2), mk("strong", q=0.95, inp=2, out=6)
        h = Harness({"weak": ["not json at all"], "strong": ['["apple","pear","plum"]']}, [weak, strong], query=q)
        h.rows = sorted(h.rows, key=lambda r: r.model_id != "weak")  # force weak first
        out, ev = h.run()
        self.assertEqual(out.final_model_id, "strong")
        self.assertTrue(out.escalated)
        self.assertEqual(out.escalation_reason, "response_did_not_meet_acceptance_checks")
        self.assertTrue(ev.accepted)

    def test_no_escalation_to_lower_quality(self):
        q = "List three fruits as JSON."
        top, low = mk("top", q=0.95), mk("low", q=0.5)
        h = Harness({"top": ["not json"], "low": ['["a"]']}, [top, low], query=q)
        h.rows = sorted(h.rows, key=lambda r: r.model_id != "top")
        out, ev = h.run()
        self.assertEqual(out.final_model_id, "top")
        self.assertFalse(ev.accepted)
        self.assertEqual(h.calls.count("PROMPT"), 1)


class EvaluationTests(unittest.TestCase):
    def test_honest_status_without_judge(self):
        ev = execution.evaluate_response(GOOD, profile("Explain a hash map"), "Explain a hash map")
        text = ev.model_dump_json().lower()
        self.assertIn("judge", text)
        self.assertTrue(any(c.name == "non_empty" and c.passed for c in ev.checks))

    def test_empty_response_rejected(self):
        self.assertFalse(execution.evaluate_response("  ", profile("Explain a hash map"), "Explain a hash map").accepted)

    def test_refusal_detected(self):
        ev = execution.evaluate_response("I cannot help with that.", profile("Explain a hash map"), "Explain a hash map")
        self.assertFalse(next(c for c in ev.checks if c.name == "not_a_refusal").passed)

    def test_json_validity_checked(self):
        p = profile("List three fruits as JSON.")
        self.assertTrue(next(c for c in execution.evaluate_response('```json\n["a"]\n```', p, "x").checks if c.name == "valid_json").passed)
        self.assertFalse(next(c for c in execution.evaluate_response("fruits: a, b", p, "x").checks if c.name == "valid_json").passed)

    def test_word_limit_checked(self):
        p = profile("Explain recursion in under 5 words.")
        ev = execution.evaluate_response("Recursion is a function calling itself repeatedly forever", p, "x")
        self.assertFalse(next(c for c in ev.checks if c.name.startswith("length_")).passed)


if __name__ == "__main__":
    unittest.main()
