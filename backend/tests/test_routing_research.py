"""Deterministic unit tests for AI Compass routing research logic.

These tests do not call paid or external model providers. They validate the
routing decision mechanics only; provider-level experiments are separate.
"""
import os
os.environ.setdefault("JWT_SECRET", "unit-test-only-secret-do-not-use-in-production")

import unittest
from app.schemas.model import ModelMetadata
from app.schemas.query import QueryProfile
from app.services.multi_objective_router import route, DEFAULT_WEIGHTS
from app.services import candidate_filter, response_evaluator, query_analyzer


def query_profile(**overrides):
    values = dict(
        task_type="coding",
        domain="computer_science",
        complexity=0.6,
        context_requirement=0.2,
        quality_requirement=0.7,
        risk_level=0.2,
        latency_requirement=0.7,
        cost_sensitivity=0.5,
        reliability_requirement=0.8,
        estimated_tokens=300,
        analysis_method="test_fixture",
    )
    values.update(overrides)
    return QueryProfile(**values)


def model(model_id, *, quality, cost, latency, reliability=0.9, risk=0.1,
          tasks=None, domains=None, capabilities=None):
    return ModelMetadata(
        model_id=model_id,
        model_name=model_id,
        provider="test",
        capabilities=capabilities or ["general", "coding"],
        supported_domains=domains or ["general", "computer_science"],
        supported_tasks=tasks or ["coding", "qa"],
        estimated_quality=quality,
        estimated_cost=cost,
        estimated_latency=latency,
        reliability=reliability,
        risk_level=risk,
        context_window=4096,
        cost_per_1k_tokens=0.001,
        avg_latency_seconds=1.0,
        fallback_priority=1,
        active=True,
        source="test_fixture",
    )


class MultiObjectiveRouterTests(unittest.TestCase):
    def test_normalized_weights_include_all_dimensions(self):
        models = [model("a", quality=0.9, cost=0.2, latency=0.2)]
        decision = route(models, query_profile(), {"quality": 0.8, "cost": 0.2}, [])
        self.assertEqual(set(decision.applied_weights), set(DEFAULT_WEIGHTS))
        self.assertAlmostEqual(sum(decision.applied_weights.values()), 1.0, places=7)
        self.assertGreater(decision.applied_weights["preference_alignment"], 0.0)

    def test_old_five_dimension_profile_gets_alignment_default(self):
        models = [model("a", quality=0.9, cost=0.2, latency=0.2)]
        old_weights = {"quality": 0.7, "cost": 0.9, "latency": 0.6,
                       "reliability": 0.75, "risk": 0.8}
        decision = route(models, query_profile(), old_weights, [])
        self.assertGreater(decision.applied_weights["preference_alignment"], 0.0)
        self.assertAlmostEqual(sum(decision.applied_weights.values()), 1.0, places=7)

    def test_zero_weights_use_documented_defaults(self):
        models = [model("a", quality=0.9, cost=0.2, latency=0.2)]
        decision = route(models, query_profile(), {key: 0 for key in DEFAULT_WEIGHTS}, [])
        self.assertEqual(decision.applied_weights, DEFAULT_WEIGHTS)

    def test_negative_weight_is_rejected(self):
        models = [model("a", quality=0.9, cost=0.2, latency=0.2)]
        with self.assertRaises(ValueError):
            route(models, query_profile(), {"quality": -1.0}, [])

    def test_each_score_dimension_is_bounded(self):
        models = [model("a", quality=0.9, cost=0.2, latency=0.2)]
        decision = route(models, query_profile(), DEFAULT_WEIGHTS, [])
        score = decision.model_scores[0]
        for dimension, value in score.score_breakdown.items():
            with self.subTest(dimension=dimension):
                self.assertGreaterEqual(value, 0.0)
                self.assertLessEqual(value, 1.0)
        self.assertGreaterEqual(score.overall_score, 0.0)
        self.assertLessEqual(score.overall_score, 1.0)

    def test_selects_higher_weighted_candidate(self):
        cheap = model("cheap", quality=0.55, cost=0.05, latency=0.2)
        strong = model("strong", quality=0.95, cost=0.5, latency=0.4)
        decision = route(
            [cheap, strong], query_profile(),
            {"quality": 0.95, "cost": 0.01, "latency": 0.01,
             "reliability": 0.01, "risk": 0.01, "preference_alignment": 0.01}, [],
        )
        self.assertEqual(decision.selected_model_id, "strong")
        self.assertEqual(decision.fallback_model_id, "cheap")

    def test_empty_candidate_list_has_clear_error(self):
        with self.assertRaisesRegex(ValueError, "at least one candidate"):
            route([], query_profile(), DEFAULT_WEIGHTS, [])


class CandidateFilterTests(unittest.TestCase):
    def test_inactive_model_is_filtered(self):
        inactive = model("inactive", quality=0.8, cost=0.2, latency=0.2).model_copy(update={"active": False})
        passing, filtered = candidate_filter.filter_candidates([inactive], query_profile())
        self.assertEqual(passing, [])
        self.assertEqual(filtered[0]["model_id"], "inactive")
        self.assertIn("inactive", filtered[0]["reason"].lower())

    def test_required_capability_is_enforced(self):
        candidate = model("no-math", quality=0.8, cost=0.2, latency=0.2, capabilities=["general"])
        passing, filtered = candidate_filter.filter_candidates(
            [candidate], query_profile(), require_capabilities=["math"]
        )
        self.assertEqual(passing, [])
        self.assertIn("math", filtered[0]["reason"])

    def test_image_task_never_accepts_text_only_model(self):
        text_model = model("text-only", quality=.9, cost=.1, latency=.1)
        profile = query_profile(
            task_type="image-generation",
            required_modalities=["image"],
            required_capabilities=["image-generation"],
        )
        passing, filtered = candidate_filter.filter_candidates([text_model], profile)
        self.assertEqual(passing, [])
        self.assertIn("modality", filtered[0]["reason"])

    def test_context_limit_is_enforced(self):
        candidate = model("short-context", quality=0.8, cost=0.2, latency=0.2).model_copy(
            update={"context_window": 128}
        )
        passing, filtered = candidate_filter.filter_candidates([candidate], query_profile(estimated_tokens=512))
        self.assertEqual(passing, [])
        self.assertIn("Context window", filtered[0]["reason"])


class TaskCategoryHintTests(unittest.TestCase):
    def test_presentation_hint_requires_presentation_capability(self):
        analyzed = query_analyzer.analyze("Create a concise deck about renewable energy")
        hinted = query_analyzer.apply_task_type_hint(analyzed, "presentation")
        self.assertEqual(hinted.task_type, "presentation")
        self.assertEqual(hinted.required_modalities, ["presentation"])
        self.assertEqual(hinted.required_capabilities, ["presentation"])

    def test_unknown_task_hint_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported task category"):
            query_analyzer.apply_task_type_hint(query_profile(), "unknown-task")


class ResponseEvaluatorTests(unittest.TestCase):
    def test_empty_response_is_rejected(self):
        result = response_evaluator.evaluate("  ", "Explain Python functions", query_profile())
        self.assertFalse(result.accepted)
        self.assertEqual(result.quality_score, 0.0)

    def test_refusal_is_rejected_and_explained(self):
        result = response_evaluator.evaluate(
            "I cannot help with that request.", "Explain Python functions", query_profile()
        )
        self.assertFalse(result.accepted)
        self.assertTrue(any("refusal" in reason.lower() for reason in result.evaluation_reasons))

    def test_relevant_sufficient_response_can_be_accepted(self):
        response = (
            "A Python function is a reusable block of code that performs a task. "
            "Functions can accept parameters, process input, and return a result. "
            "They help organize programs into smaller components, reduce repeated code, "
            "and make testing and maintenance easier. Define a function with def, give it "
            "a name, and indent its body. Call it by using the function name and parentheses."
        )
        result = response_evaluator.evaluate(response, "Explain Python functions", query_profile())
        self.assertGreaterEqual(result.quality_score, 0.55)
        self.assertTrue(result.accepted)


if __name__ == "__main__":
    unittest.main()
