"""Two recommendation categories: Conversational AI vs Developer & API models.

Runs the real pipeline over the real bundled catalogue with no provider credentials, so every assertion about
recommendations is also proof that keys are not needed to recommend. No provider is ever called.
"""
import os
os.environ.setdefault("JWT_SECRET", "unit-test-only-secret-do-not-use-in-production")
import unittest
from unittest.mock import patch

from app.services import access_category as ac, category_evaluation, model_registry, model_taxonomy
from app.services.routing_engine import access as access_mod, audience, pipeline
from tests.engine_helpers import mk

KEYS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY")
HOSTING = {"Groq", "OpenRouter", "Hugging Face", "Together AI", "Amazon Bedrock"}


def route(query, **kw):
    req = pipeline.PipelineRequest(query=query, optimization_mode="disabled", evaluate_response=False, **kw)
    return pipeline.run(req, saved_weights=None, user_id=None, observed_loader=lambda ids: {}, learning_loader=lambda u, ids: {})


def providers(r):
    return {c.provider for c in r.candidates}


class Base(unittest.TestCase):
    keys = ""

    def setUp(self):
        from app.core.config import settings
        self.patches = [patch.object(settings, k, self.keys) for k in KEYS]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()


class OfferingProfileTests(Base):
    def by_id(self, mid):
        return model_taxonomy.classify(next(m for m in model_registry.api_models() if m.model_id == mid))

    def test_categories_follow_the_providers_actual_role(self):
        groq = ac.profile_of(self.by_id("llama-3.3-70b-versatile"))
        self.assertEqual((groq.model_category, groq.access_type), ("developer_api", "hosted_inference"))
        orr = ac.profile_of(self.by_id("deepseek/deepseek-r1"))
        self.assertEqual((orr.model_category, orr.access_type), ("developer_api", "aggregator_api"))
        hf = ac.profile_of(self.by_id("BAAI/bge-m3"))
        self.assertEqual((hf.model_category, hf.access_type), ("developer_api", "hosted_inference"))
        oa = ac.profile_of(self.by_id("gpt-4.1"))
        self.assertEqual((oa.model_category, oa.access_type, oa.integration_supported), ("conversational", "provider_api", True))

    def test_consumer_applications_are_conversational_and_not_integrable(self):
        app = mk("chatgpt-app", entry_type="application_integration", provider="OpenAI")
        p = ac.profile_of(app)
        self.assertEqual((p.model_category, p.access_type, p.integration_supported), ("conversational", "consumer_chat", False))

    def test_entry_with_nothing_verified_is_unclassified_not_guessed(self):
        p = ac.profile_of(mk("acme/mystery", provider="Acme"))
        self.assertEqual(p.model_category, "unclassified")
        self.assertIsNone(p.integration_supported)

    def test_embedding_model_from_a_model_developer_is_developer_category(self):
        p = ac.profile_of(self.by_id("text-embedding-3-small"))
        self.assertEqual(p.model_category, "developer_api")
        self.assertIn("embedding", p.intended_use)


class IntentTests(unittest.TestCase):
    DEV = ["I need an AI model for my college project.", "Which free LLM API can I use?", "I want to integrate AI into my Python application.",
           "Suggest a model for building a chatbot.", "I need an API key for my AI application.", "Which model should I use for my capstone?",
           "I want to build a RAG application.", "I need a model for an AI agent.", "Suggest a free model API for students.",
           "Which Groq or Hugging Face model should I use?", "I need an LLM that I can call through an API."]
    CONV = ["Explain machine learning.", "Help me understand this research paper.", "Summarize this document.", "Write an email.",
            "Solve this mathematical problem.", "Explain this programming concept.", "Help me prepare for an interview.", "Explain what an API is.",
            "What is an AI agent?", "How does RAG work?"]

    def test_every_listed_developer_phrasing_is_developer_intent(self):
        for q in self.DEV:
            a = audience.assess(q)
            self.assertEqual((a.kind, a.category, a.ambiguous), ("developer", "developer_api", False), q)

    def test_every_listed_conversational_phrasing_stays_conversational(self):
        for q in self.CONV:
            a = audience.assess(q)
            self.assertEqual((a.kind, a.category, a.ambiguous), ("conversational", "conversational", False), q)

    def test_free_wording_is_recorded_only_with_developer_intent(self):
        self.assertTrue(audience.assess("Which free LLM API can I use?").prefers_free)
        self.assertFalse(audience.assess("Explain free will.").prefers_free)


class Recommendations(Base):
    def test_1_educational_questions_get_conversational_models(self):
        r = route("Explain the difference between supervised and unsupervised learning.")
        self.assertEqual(r.profile.audience.category, "conversational")
        self.assertTrue(r.candidates)
        self.assertEqual({c.model_category for c in r.candidates}, {"conversational"})

    def test_2_writing_and_summarisation_never_surface_developer_providers(self):
        for q in ("Write a polite email asking my professor for an extension.", "Summarize the causes of the French Revolution in five bullet points."):
            r = route(q)
            self.assertTrue(r.candidates, q)
            self.assertFalse(providers(r) & HOSTING, (q, providers(r)))
            codes = {e.model_id: e.code for e in r.exclusions}
            self.assertEqual(codes.get("llama-3.3-70b-versatile"), "developer_only_model")

    def test_3_project_building_considers_developer_api_models(self):
        r = route("I am building a chatbot for my college project. Which model should I use?")
        self.assertEqual(r.profile.audience.category, "developer_api")
        self.assertIn("developer_api", {c.model_category for c in r.candidates})
        self.assertTrue(providers(r) & {"Groq", "OpenRouter", "Hugging Face"})

    def test_4_free_api_requests_only_return_verified_free_options(self):
        r = route("Suggest a free model API for students.")
        self.assertTrue(r.profile.audience.prefers_free)
        self.assertTrue(r.candidates)
        for c in r.candidates:
            self.assertIn(c.pricing_category, {"completely_free", "free_tier_limited", "self_hosted_open_weight"}, c.model_name)
            self.assertIs(c.free_tier_available, True)
        self.assertIn("Groq", providers(r))

    def test_5_naming_groq_or_hugging_face_returns_those_api_options(self):
        r = route("Which Groq or Hugging Face model should I use?")
        self.assertEqual(r.profile.audience.kind, "developer")
        self.assertTrue({"Groq", "Hugging Face"} <= providers(r))

    def test_6_missing_keys_do_not_remove_recommendation_eligibility(self):
        r = route("I need a free LLM API for my Python college project.")
        groq = [c for c in r.candidates if c.provider == "Groq"]
        self.assertTrue(groq)
        for c in groq:
            self.assertTrue(c.recommendation_eligible)
            self.assertFalse(c.execution_ready)
            self.assertEqual(c.execution_status, "credential_not_configured")

    def test_7_missing_keys_prevent_execution(self):
        m = next(m for m in model_registry.api_models() if m.model_id == "llama-3.3-70b-versatile")
        d = access_mod.describe(m)
        self.assertFalse(d["execution_available"])
        self.assertEqual(d["status"], "credential_not_configured")

    def test_8_unsupported_hugging_face_models_are_not_inference_ready(self):
        from app.core.config import settings
        hf = next(m for m in model_registry.api_models() if m.provider == "Hugging Face")
        with patch.object(settings, "GROQ_API_KEY", "k"), patch.object(settings, "OPENROUTER_API_KEY", "k"):
            d = access_mod.describe(hf)
        self.assertFalse(d["execution_available"])
        self.assertIn(d["status"], {"no_adapter", "credential_not_configured"})
        discovered = hf.model_copy(update={"source": "live_discovered", "inference_access_status": "unverified", "adapter_compatible": True})
        self.assertEqual(access_mod.describe(discovered)["status"], "inference_not_verified")

    def test_9_unknown_pricing_is_never_presented_as_free(self):
        unknown = mk("acme/unknown-price", provider="OpenRouter", inp=None, out=None)
        p = ac.profile_of(unknown)
        self.assertEqual((p.pricing_category, p.free_tier_available), ("unknown", None))
        r = route("Which free LLM API can I use?")
        self.assertNotIn("deepseek-chat", {c.model_id for c in r.candidates})   # pricing not verified in the catalogue
        self.assertEqual(sum(1 for c in r.candidates if c.pricing_category == "unknown"), 0)
        ex = {e.model_id: e.code for e in r.exclusions}
        self.assertIn(ex.get("deepseek-chat"), {"free_access_unverified", "developer_only_model"})

    def test_10_privacy_and_budget_constraints_still_apply_in_both_pools(self):
        for q in ("Explain recursion with an example.", "I need an AI model for my college project."):
            strict = route(q, privacy_requirement="strict")
            self.assertEqual(strict.candidates, [])          # no catalogue model documents restricted data handling: nothing is assumed
            self.assertIn("privacy_unverified", {e.code for e in strict.exclusions} | {x for e in strict.exclusions for x in e.evidence.get("also_failed", [])})
            capped = route(q, max_cost=0.005)
            self.assertTrue(capped.candidates, q)            # non-empty, so the loop below is a real check
            for c in capped.candidates:
                self.assertIsNotNone(c.estimated_cost_usd)
                self.assertLessEqual(c.estimated_cost_usd, 0.005)
            self.assertTrue(any(e.code.startswith("cost") for e in capped.exclusions), q)

    def test_11_scoring_is_unchanged_and_independent_of_category_and_keys(self):
        a = route("I need an AI model for my college project.")
        self.assertEqual(a.scoring_version, "3.0.0")
        from app.core.config import settings
        with patch.object(settings, "GROQ_API_KEY", "k"), patch.object(settings, "OPENROUTER_API_KEY", "k"):
            b = route("I need an AI model for my college project.")
        self.assertEqual([(c.model_id, c.robust_score) for c in a.candidates], [(c.model_id, c.robust_score) for c in b.candidates])
        again = route("I need an AI model for my college project.")
        self.assertEqual([c.model_id for c in a.candidates], [c.model_id for c in again.candidates])   # deterministic tie-breaking

    def test_12_ambiguous_intent_is_not_mixed_and_asks_one_question(self):
        r = route("Which AI model is best for coding?")
        a = r.profile.audience
        self.assertTrue(a.ambiguous)
        self.assertEqual(a.category, "conversational")
        self.assertEqual(r.status, "needs_clarification")
        self.assertTrue(r.profile.needs_clarification)
        self.assertEqual([x.clarifying_question for x in r.profile.ambiguities if x.kind == "intent_category"], [audience.CLARIFY])
        self.assertEqual({c.model_category for c in r.candidates}, {"conversational"})

    def test_explanation_states_which_pool_was_used(self):
        conv = route("Explain photosynthesis simply.")
        dev = route("I need a model for an AI agent.")
        self.assertTrue(any("only Conversational AI models" in w for w in conv.explanation.why_selected))
        self.assertTrue(any("Developer & API models" in w for w in dev.explanation.why_selected))


class CategoryEvaluation(Base):
    def test_suite_reports_measured_metrics_and_no_leakage(self):
        out = category_evaluation.run()
        self.assertEqual(out["cases"], len(category_evaluation.CASES))
        self.assertEqual(out["method"], "offline_registry_metadata")
        self.assertIn("no model was called", out["disclosure"])
        self.assertEqual(out["category_leakage_count"], 0)
        self.assertEqual(out["unverified_shown_as_free"], 0)
        self.assertEqual(out["classification_accuracy"], 1.0)
        self.assertEqual(out["recommendation_coverage"], 1.0)
        self.assertEqual(out["constraint_violation_rate"], 0.0)
        self.assertGreater(out["constraint_cases"], 0)
        self.assertEqual(set(out["by_group"]), {"ordinary_conversational", "project_api", "free_api", "coding_integration", "rag_agent", "ambiguous"})


if __name__ == "__main__":
    unittest.main()
