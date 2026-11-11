import os
os.environ.setdefault("JWT_SECRET", "unit-test-only-secret-do-not-use-in-production")

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.api.routes import evaluation as evaluation_route
from app.schemas.evaluation import OfflineEvaluationRequest
from app.schemas.model import ModelMetadata
from app.schemas.query import QueryProfile
from app.services.offline_evaluation import (
    AI_COMPASS,
    CHEAPEST,
    STATIC,
    STRONGEST,
    evaluate,
)


def profile(**overrides):
    values = dict(
        task_type="coding",
        domain="computer_science",
        complexity=0.4,
        context_requirement=0.2,
        quality_requirement=0.7,
        risk_level=0.1,
        latency_requirement=0.5,
        cost_sensitivity=0.5,
        reliability_requirement=0.8,
        estimated_tokens=1000,
        analysis_method="test",
        required_modalities=["text"],
        required_capabilities=[],
    )
    values.update(overrides)
    return QueryProfile(**values)


def model(model_id, *, quality=.8, price=None, priority=5, reliability=.8):
    return ModelMetadata(
        model_id=model_id,
        model_name=f"Model {model_id}",
        provider="Registry",
        capabilities=["coding"],
        supported_domains=["general", "computer_science"],
        supported_tasks=["coding", "qa"],
        estimated_quality=quality,
        estimated_cost=.5,
        estimated_latency=.5,
        reliability=reliability,
        risk_level=.2,
        context_window=8192,
        cost_per_1k_tokens=price / 1000 if price is not None else 0,
        avg_latency_seconds=2.5,
        fallback_priority=priority,
        active=True,
        source="unit_test_registry",
        input_price_per_million=price,
        availability="configuration_required_for_inference",
        data_provenance="registry_metadata",
    )


class OfflineEvaluationTests(unittest.TestCase):
    def test_all_four_strategies_are_deterministic_without_provider_configuration(self):
        models = [
            model("retired/provider-model-v0", quality=.7, price=8, priority=3),
            model("model-b", quality=.9, price=2, priority=2),
            model("model-a", quality=.9, price=2, priority=2),
        ]
        weights = {"quality": .9, "cost": .02, "latency": .02, "reliability": .02, "risk": .02}
        first = evaluate(models, profile(), weights, [])
        second = evaluate(models, profile(), weights, [])
        self.assertEqual([row.strategy for row in first], [AI_COMPASS, STRONGEST, CHEAPEST, STATIC])
        self.assertEqual(first, second)
        self.assertEqual(first[1].selected_model_id, "model-a")
        self.assertEqual(first[2].selected_model_id, "model-a")
        self.assertEqual(first[3].selected_model_id, "model-a")

    def test_unknown_pricing_is_excluded_from_cheapest_and_disclosed(self):
        priced = model("priced", quality=.8, price=4)
        unknown = model("unknown-price", quality=.9)
        results = evaluate([priced, unknown], profile(), {}, [])
        cheapest = next(row for row in results if row.strategy == CHEAPEST)
        self.assertEqual(cheapest.selected_model_id, "priced")
        self.assertIn("Excluded 1 eligible model", cheapest.selection_rationale)
        self.assertAlmostEqual(cheapest.estimated_cost_usd, .004)
        self.assertTrue(any("Pricing unavailable" in item for item in
                            next(row for row in results if row.strategy == STRONGEST).missing_data))

    def test_missing_quality_score_does_not_break_other_strategies(self):
        models = [model("unscored", quality=None, price=2), model("scored", quality=.7, price=4)]
        results = evaluate(models, profile(), {"quality": .9, "cost": .1}, [])
        self.assertEqual(next(row for row in results if row.strategy == STRONGEST).selected_model_id, "scored")
        self.assertIsNone(next(row for row in results if row.strategy == AI_COMPASS).quality_score)
        compass = next(row for row in results if row.strategy == AI_COMPASS)
        self.assertIsNotNone(compass.routing_score)
        self.assertTrue(any("Quality dimension omitted" in item for item in compass.missing_data))

    def test_no_candidates_returns_explicitly_unavailable_strategies(self):
        results = evaluate([], profile(), {}, [])
        self.assertEqual(len(results), 4)
        self.assertTrue(all(row.status == "unavailable" for row in results))

    def test_endpoint_uses_catalog_without_provider_keys_or_adapter_calls(self):
        models = [model("arbitrary-retired-id", quality=.8, price=2)]
        user = SimpleNamespace(get_routing_weights=lambda: {})
        with (
            patch.object(evaluation_route.user_store, "get_by_id", return_value=user),
            patch.object(evaluation_route, "get_catalog_for_recommendation", return_value=models),
        ):
            response = evaluation_route.evaluate_offline(
                OfflineEvaluationRequest(query="Implement a Python function to sort records."),
                uid="offline-test-user",
            )
        self.assertEqual(response.candidate_count, 1)
        self.assertEqual(len(response.strategy_results), 4)
        self.assertEqual(response.evaluation_method, "offline_registry_metadata")

    def test_unknown_price_cannot_pass_a_max_price_constraint(self):
        models = [model("priced", quality=.8, price=4), model("unknown-price", quality=.7)]
        user = SimpleNamespace(get_routing_weights=lambda: {})
        with (
            patch.object(evaluation_route.user_store, "get_by_id", return_value=user),
            patch.object(evaluation_route, "get_catalog_for_recommendation", return_value=models),
        ):
            response = evaluation_route.evaluate_offline(
                OfflineEvaluationRequest(
                    query="Implement a Python function to sort records.",
                    max_cost=.01,
                ),
                uid="offline-test-user",
            )
        self.assertEqual(response.candidate_count, 1)
        self.assertEqual(response.filtered_models[0]["model_id"], "unknown-price")
        self.assertIn("pricing is unavailable", response.filtered_models[0]["reason"])


if __name__ == "__main__":
    unittest.main()
