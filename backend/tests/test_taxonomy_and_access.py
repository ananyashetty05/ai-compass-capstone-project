"""Acceptance tests: conversational vs developer routing, key-free comparison, counterfactuals, access separation.

These run the real pipeline against the real static catalogue with NO provider credentials configured,
which is itself the proof that comparison does not depend on API keys.
"""
import os
os.environ.setdefault("JWT_SECRET", "unit-test-only-secret-do-not-use-in-production")
import unittest
from unittest.mock import patch

from app.services import model_registry, model_taxonomy
from app.services.routing_engine import pipeline

NO_KEYS = {"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "", "GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OPENROUTER_API_KEY": ""}


def route(query, **kw):
    req = pipeline.PipelineRequest(query=query, optimization_mode="disabled", **kw)
    return pipeline.run(req, saved_weights=None, user_id=None, observed_loader=lambda ids: {}, learning_loader=lambda u, ids: {})


class Base(unittest.TestCase):
    def setUp(self):
        from app.core.config import settings
        self.patches = [patch.object(settings, k, v) for k, v in NO_KEYS.items()]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()


class CategorisationTests(Base):
    def by_id(self, mid):
        return next(m for m in model_registry.api_models() if m.model_id == mid)

    def test_general_question_gets_conversational_models_only(self):
        r = route("Explain the difference between supervised and unsupervised learning.")
        self.assertEqual(r.profile.audience.kind, "conversational")
        self.assertTrue(r.candidates)
        for c in r.candidates:
            self.assertIn("conversational", model_taxonomy.classify(r.model_lookup[c.model_id]).use_categories)
        codes = {e.code for e in r.exclusions}
        self.assertIn("developer_only_model", codes)

    def test_student_free_chatbot_project_is_developer_intent_with_evidence_based_free_filter(self):
        r = route("I am building a chatbot for my college project. Suggest free AI models I can integrate.")
        self.assertEqual(r.profile.audience.kind, "developer")
        self.assertTrue(r.profile.audience.prefers_free)
        self.assertTrue(r.candidates)
        for c in r.candidates:
            m = model_taxonomy.classify(r.model_lookup[c.model_id])
            self.assertTrue(m.free_download or m.free_access in {"free", "limited_free"}, m.model_id)
            self.assertIn("developer", m.use_categories)
        reasons = {e.code for e in r.exclusions}
        self.assertTrue({"not_free", "free_access_unverified"} <= reasons, reasons)
        self.assertEqual(r.profile.audience.signals.count("building_an_application"), 1)

    def test_rag_query_recommends_embedding_models_only(self):
        r = route("Suggest an embedding model for my RAG application.")
        self.assertEqual(r.profile.audience.required_model_types, ["embedding"])
        self.assertTrue(r.candidates)
        self.assertTrue(all(model_taxonomy.classify(r.model_lookup[c.model_id]).model_type == "embedding" for c in r.candidates))
        self.assertTrue(all(c.task_fit == 1.0 for c in r.candidates))
        self.assertIn("quality", r.candidates[0].missing_dimensions)  # no benchmark data is invented for unmeasured models
        self.assertEqual(r.selection.confidence_level, "low")

    def test_embedding_models_never_answer_ordinary_questions(self):
        r = route("What is the capital of France?")
        ids = {c.model_id for c in r.candidates}
        self.assertFalse(ids & {"text-embedding-3-small", "text-embedding-3-large", "BAAI/bge-m3", "nomic-ai/nomic-embed-text-v1.5"})

    def test_explaining_rag_is_still_conversational(self):
        self.assertEqual(route("Explain what retrieval-augmented generation is.").profile.audience.kind, "conversational")

    def test_coding_project_considers_coding_models(self):
        r = route("Which free open-weights model can I use to build an AI coding assistant for my project?")
        self.assertEqual(r.profile.audience.kind, "developer")
        self.assertIn("coding", r.profile.required_capabilities)
        ids = {c.model_id for c in r.candidates}
        self.assertIn("Qwen/Qwen2.5-Coder-32B-Instruct", ids)
        for c in r.candidates:
            self.assertEqual(model_taxonomy.classify(r.model_lookup[c.model_id]).weights_status, "open_weights")

    def test_open_chat_model_on_a_model_hub_is_developer_category_not_conversational(self):
        """A chat model hosted on Hugging Face is a developer/API offering: it is not an ordinary-question recommendation,
        and it is recommended once the user says they are building something."""
        r = route("Explain how photosynthesis works in simple terms.")
        self.assertNotIn("Qwen/Qwen2.5-72B-Instruct", {c.model_id for c in r.candidates})
        ex = {e.model_id: e for e in r.exclusions}
        self.assertEqual(ex["Qwen/Qwen2.5-72B-Instruct"].code, "developer_only_model")
        self.assertEqual(ex["Qwen/Qwen2.5-Coder-32B-Instruct"].code, "developer_only_model")
        d = route("I am building a chatbot for my project; which open-weights model should I use?")
        self.assertIn("Qwen/Qwen2.5-72B-Instruct", {c.model_id for c in d.candidates})

    def test_providers_are_not_model_developers(self):
        groq = model_taxonomy.classify(self.by_id("llama-3.3-70b-versatile"))
        self.assertEqual((groq.provider, groq.developer, groq.provider_role), ("Groq", "Meta", "inference_provider"))
        orr = model_taxonomy.classify(self.by_id("deepseek/deepseek-r1"))
        self.assertEqual((orr.provider_role, orr.developer), ("model_aggregator", "DeepSeek"))
        hf = model_taxonomy.classify(self.by_id("BAAI/bge-m3"))
        self.assertEqual((hf.provider_role, hf.developer), ("model_hub", "BAAI"))

    def test_unknown_models_stay_unclassified(self):
        from tests.engine_helpers import mk
        out = model_taxonomy.classify(mk("acme/mystery"))
        self.assertEqual((out.taxonomy_status, out.use_categories, out.weights_status, out.free_access), ("unclassified", [], "unknown", "unknown"))


class KeylessComparisonTests(Base):
    def test_models_without_credentials_are_compared_and_can_win(self):
        r = route("Write a Python function that merges two sorted lists.")
        self.assertTrue(r.candidates)
        self.assertGreater(len(r.candidates), 5)
        self.assertEqual(r.catalogue_summary["credentials_used_for_comparison"], False)
        top = r.model_lookup[r.selection.selected_model_id]
        self.assertFalse(model_registry._configured(top.provider))
        self.assertEqual(r.access["status"], "credential_not_configured")
        self.assertFalse(r.access["execution_available"])
        self.assertIn("recommendation itself is unaffected", r.access["next_step"])

    def test_missing_credentials_never_appear_as_exclusion_reasons(self):
        r = route("Write a Python function that merges two sorted lists.")
        self.assertNotIn("provider_not_configured", {e.code for e in r.exclusions})

    def test_registry_flags_are_independent(self):
        e = next(m for m in model_registry.get_all_registry_entries() if m.model_id == "gpt-4.1")
        self.assertTrue(e.comparison_eligible and e.routing_eligible)
        self.assertFalse(e.execution_available)
        self.assertFalse(e.user_access_configured)

    def test_execute_mode_skips_unrunnable_top_pick_without_calling_any_provider(self):
        r = route("Write a Python function that merges two sorted lists.", mode="execute")
        self.assertTrue(r.candidates)  # still ranked
        self.assertEqual(r.execution.status, "failed")
        self.assertTrue(all(a.outcome == "skipped_no_access" for a in r.execution.attempts))
        self.assertFalse(r.execution.escalated)

    def test_comparison_makes_no_provider_calls(self):
        with patch("app.services.routing_engine.execution.get_adapter_for") as ga:
            route("Explain recursion with an example.")
            ga.assert_not_called()


class CounterfactualTests(Base):
    def test_counterfactuals_come_from_rerunning_the_router(self):
        r = route("Write a Python function that merges two sorted lists.")
        kinds = {c["kind"] for c in r.counterfactuals}
        self.assertIn("weight_shift", kinds)
        base = r.selection.selected_model_id
        for c in r.counterfactuals:
            self.assertEqual(c["changed"], c["winner"]["model_id"] != base)

    def test_constraint_relaxation_only_when_the_constraint_was_applied(self):
        r = route("Write a Python function that merges two sorted lists.")
        self.assertNotIn("constraint_relaxed", {c["kind"] for c in r.counterfactuals})
        r2 = route("Write a Python function that merges two sorted lists.", max_cost=0.002)
        self.assertIn("constraint_relaxed", {c["kind"] for c in r2.counterfactuals})


if __name__ == "__main__":
    unittest.main()


class GenerationRequestTests(Base):
    """A request for an image/video/audio artefact must reach the models that can produce it."""

    def test_image_request_selects_an_image_model_not_a_routing_failure(self):
        r = route("I have to create an image of a car. Very realistic and animated yet cost efficient yet fast.")
        self.assertIn("image-generation", r.profile.required_capabilities)
        self.assertEqual([c.model_id for c in r.candidates], ["gpt-image-1"])
        self.assertEqual(r.selection.selected_model_id, "gpt-image-1")
        self.assertTrue(any("animation" in c for c in r.selection.caveats))

    def test_text_models_are_still_excluded_for_image_requests(self):
        r = route("Generate an image of a red sports car")
        ids = {e.model_id for e in r.exclusions}
        self.assertIn("gpt-4.1", ids)
        self.assertNotIn("gpt-image-1", ids)

    def test_verbless_image_requests_are_image_generation(self):
        for q in ("Car image realistic.", "A photorealistic image of a mountain at dawn", "realistic picture of a red car"):
            r = route(q)
            self.assertIn("image-generation", r.profile.required_capabilities, q)
            self.assertEqual(r.selection.selected_model_id, "gpt-image-1", q)

    def test_analysis_of_an_attached_image_is_not_generation(self):
        r = route("Describe what is in this image and explain the chart")
        self.assertNotIn("image-generation", r.profile.required_capabilities)
