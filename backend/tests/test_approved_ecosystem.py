"""Approved ecosystem pool, category-first routing, one consistent ranking, selection-based confidence, recommendation-only.

Real pipeline against the real approved pool. Provider credentials are forced on/off by patching the one function that reads them.
No network, no database, no provider calls. Run against POOL_SOURCE=approved (see conftest).
"""
import os
os.environ.setdefault("JWT_SECRET", "unit-test-only-secret-do-not-use-in-production")

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.data import approved_ecosystem as eco
from app.services import model_registry, registry_service
from app.services.routing_engine import pipeline, scoring
from main import app
from tests.test_engine_pipeline import FakeUser

APPROVED_NAMES = {
    "conversational": {"Claude", "ChatGPT", "Gemini", "Perplexity", "DeepSeek", "Grok"},
    "image": {"Nano Banana", "Adobe Firefly", "GPT Image 1", "Midjourney", "DALL·E 3", "FLUX"},
    "video": {"Sora", "Runway Gen-3", "Kling AI", "Gemini Omni / Veo", "Higgsfield AI"},
    "music_voice": {"Suno", "ElevenLabs", "Lyria", "Mureka.ai", "Sarvam AI", "Cartesia", "GPT Live"},
    "document_design": {"Gamma", "Lovable", "Figma", "Canva"},
    "api_models": {"Hugging Face", "AI21", "OpenRouter", "Groq"},
    "coding": {"GitHub Copilot", "Cursor", "Amazon Q Developer", "Codex", "Claude Code"},
}


def route(query, **kw):
    req = pipeline.PipelineRequest(query=query, optimization_mode="disabled", **kw)
    return pipeline.run(req, saved_weights=None, user_id=None, observed_loader=lambda ids: {}, learning_loader=lambda u, ids: {})


def ids(res):
    return [c.model_id for c in res.candidates]


class PoolTests(unittest.TestCase):
    def test_pool_is_exactly_the_approved_list_and_within_the_cap(self):
        models = model_registry.approved_models()
        self.assertLessEqual(len(models), eco.MAX_POOL_SIZE)
        self.assertEqual({m.model_name for m in models}, set().union(*APPROVED_NAMES.values()))
        for category, names in APPROVED_NAMES.items():
            self.assertEqual({m.model_name for m in models if m.ecosystem_category == category}, names, category)
        self.assertEqual(len({m.model_id for m in models}), len(models), "model ids must be unique")

    def test_counts_reconcile(self):
        counts = eco.category_counts()
        self.assertEqual(sum(counts["primary"].values()), counts["total"])
        self.assertEqual(counts["total"], 37)

    def test_secondary_membership_is_explicit(self):
        by = {m.model_name: m for m in model_registry.approved_models()}
        self.assertEqual(set(by["Gemini"].secondary_categories), {"document_design", "coding"})
        self.assertEqual(by["Canva"].secondary_categories, ["image"])
        self.assertTrue(all(not m.secondary_categories for n, m in by.items() if n not in {"Gemini", "Canva"}))

    def test_every_surface_lists_only_the_approved_pool(self):
        approved_ids = {m.model_id for m in model_registry.approved_models()}
        self.assertEqual({m.model_id for m in model_registry.get_catalog_with_exclusions()[0]}, approved_ids)
        self.assertEqual({m.model_id for m in model_registry.get_all_registry_entries()}, approved_ids)
        self.assertEqual({e.model_id for e in registry_service.build_registry()}, approved_ids)

    def test_metrics_are_labelled_editorial_estimates(self):
        for m in model_registry.approved_models():
            for field, key in (("estimated_quality", "quality"), ("estimated_latency", "latency"), ("reliability", "reliability"), ("risk_level", "risk")):
                v = getattr(m, field)
                self.assertIsNotNone(v, f"{m.model_name}.{field}")
                self.assertTrue(0.0 <= v <= 1.0)
                self.assertEqual(m.metric_provenance[key], "editorial_estimate", f"{m.model_name}.{key}")
            for field in ("estimated_cost", "input_price_per_million"):
                self.assertIsNone(getattr(m, field), f"{m.model_name}.{field}")  # no invented prices


class CategoryRoutingTests(unittest.TestCase):
    CASES = [
        ("Generate an image of a red car", "image"), ("Create a logo for my bakery", "image"), ("Make a pitch deck for my startup", "document_design"),
        ("Design a mobile app UI wireframe", "document_design"), ("Write a Python function to reverse a linked list", "coding"),
        ("Debug this stack trace in my IDE", "coding"), ("Create a cinematic video of a city at night", "video"), ("Generate a lofi song with vocals", "music_voice"),
        ("Clone my voice for narration", "music_voice"), ("Which free LLM API should I use for my chatbot?", "api_models"),
        ("Explain photosynthesis to a ten year old", "conversational"), ("What are the latest news about AI, with citations?", "conversational"),
    ]

    def test_query_is_routed_to_its_category_and_only_that_category_is_compared(self):
        for query, category in self.CASES:
            with self.subTest(query=query):
                r = route(query)
                self.assertEqual(r.profile.category.category, category)
                by = {m.model_id: m for m in r.model_lookup.values()}
                self.assertTrue(r.candidates)
                for c in r.candidates:
                    self.assertTrue(eco.serves(by[c.model_id], category), f"{c.model_name} does not serve {category}")
                # every other-category product is excluded with the category reason, never silently dropped
                excluded = {e.model_id: e for e in r.exclusions}
                for mid, m in by.items():
                    if mid not in {c.model_id for c in r.candidates}:
                        self.assertIn(mid, excluded)
                        self.assertIn(excluded[mid].code, {"category_mismatch", "subtype_unsupported"})

    def test_music_and_voice_subtypes_are_not_mixed(self):
        song = {c.model_name for c in route("Generate a song with vocals about summer").candidates}
        voice = {c.model_name for c in route("Convert this text to speech in a natural voice").candidates}
        self.assertIn("Suno", song); self.assertNotIn("ElevenLabs", song)
        self.assertIn("ElevenLabs", voice); self.assertNotIn("Suno", voice)

    def test_secondary_category_products_are_compared_inside_that_category(self):
        self.assertIn("Canva", {c.model_name for c in route("Generate an image of a red car").candidates})
        self.assertIn("Gemini", {c.model_name for c in route("Make a pitch deck for my startup").candidates})
        self.assertIn("Gemini", {c.model_name for c in route("Write a Python function to reverse a list").candidates})
        self.assertNotIn("Gemini", {c.model_name for c in route("Create a cinematic video of a city").candidates})

    def test_features_change_the_best_match(self):
        text_in_image = route("Generate a photorealistic image with readable text for a poster")
        self.assertEqual(text_in_image.candidates[0].model_name, "GPT Image 1")
        art = route("Generate artistic concept art illustration of a dragon")
        self.assertEqual(art.candidates[0].model_name, "Midjourney")
        aws = route("Write a Lambda function in Python and review my AWS code in the IDE")
        self.assertEqual(aws.candidates[0].model_name, "Amazon Q Developer")
        news = route("What are the latest news about AI, with citations?")
        self.assertEqual(news.candidates[0].model_name, "Perplexity")

    def test_ranking_is_deterministic(self):
        for query, _ in self.CASES:
            self.assertEqual([(c.model_id, c.robust_score) for c in route(query).candidates], [(c.model_id, c.robust_score) for c in route(query).candidates])

    def test_ranking_is_ordered_by_score_and_exact_ties_follow_list_order(self):
        r = route("Explain photosynthesis to a ten year old")
        scores = [c.robust_score for c in r.candidates]
        self.assertEqual(scores, sorted(scores, reverse=True))
        for a, b in zip(r.candidates, r.candidates[1:]):
            if a.robust_score == b.robust_score:
                self.assertLess(a.editorial_order, b.editorial_order)

    def test_every_candidate_has_all_four_editorial_metrics(self):
        for q in ("Explain photosynthesis", "Generate an image of a red car", "Write a Python function", "Create a video of a city", "Which free LLM API should I use?"):
            for c in route(q).candidates:
                for d in ("quality", "latency", "reliability", "risk"):
                    # ER-PCR: editorial ratings are displayed (value present, labelled) but never ranked
                    self.assertIsNotNone(c.evidence[d].raw_value, f"{c.model_name}.{d}")
                    self.assertFalse(c.evidence[d].used_in_ranking and c.evidence[d].tier == "unverified_estimate", f"{c.model_name}.{d}")
                    expected = {"editorial_estimate", "estimate"} if d == "risk" else {"editorial_estimate"}  # risk is derived from the query's sensitivity (named process)
                    self.assertIn(c.evidence[d].provenance, expected, f"{c.model_name}.{d}")


class CredentialIndependenceTests(unittest.TestCase):
    QUERIES = ["Generate an image of a red car", "Write a Python function to reverse a list", "Which free LLM API should I use for my chatbot?"]

    def test_ranking_is_identical_with_every_key_present_or_absent(self):
        for q in self.QUERIES:
            with patch.object(model_registry, "_configured", lambda p: True):
                with_keys = route(q)
            with patch.object(model_registry, "_configured", lambda p: False):
                without_keys = route(q)
            self.assertEqual([(c.model_id, c.robust_score) for c in with_keys.candidates], [(c.model_id, c.robust_score) for c in without_keys.candidates], q)
            self.assertEqual(with_keys.selection.selected_model_id, without_keys.selection.selected_model_id)
            self.assertEqual(with_keys.selection.confidence_value, without_keys.selection.confidence_value)

    def test_settings_keys_do_not_change_the_ranking(self):
        keys = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY")
        before = {k: getattr(settings, k) for k in keys}
        try:
            for k in keys:
                setattr(settings, k, "")
            empty = [c.model_id for c in route(self.QUERIES[0]).candidates]
            for k in keys:
                setattr(settings, k, "sk-test-not-a-real-key-0000000000")
            full = [c.model_id for c in route(self.QUERIES[0]).candidates]
        finally:
            for k, v in before.items():
                setattr(settings, k, v)
        self.assertEqual(empty, full)

    def test_catalogue_summary_states_no_credentials_were_used(self):
        self.assertFalse(route(self.QUERIES[0]).catalogue_summary["credentials_used_for_comparison"])


class RecommendationOnlyTests(unittest.TestCase):
    def test_execute_mode_is_downgraded_and_nothing_runs(self):
        called = []
        req = pipeline.PipelineRequest(query="Write a Python function to reverse a list", mode="execute", optimization_mode="disabled")
        r = pipeline.run(req, saved_weights=None, user_id=None, observed_loader=lambda i: {}, learning_loader=lambda u, i: {}, adapter_factory=lambda m: called.append(m))
        self.assertEqual(r.mode, "recommend")
        self.assertEqual(r.execution.status, "not_requested")
        self.assertEqual(r.execution.attempts, [])
        self.assertFalse(r.execution.escalated)
        self.assertEqual(r.evaluation.status, "not_requested")
        self.assertEqual(called, [])
        self.assertNotIn("execution", [s.name for s in r.stages if s.status == "completed"])

    def test_access_never_depends_on_a_credential(self):
        r = route("Generate an image of a red car")
        self.assertEqual(r.access["status"], "open_at_destination")
        self.assertFalse(r.access["execution_available"])
        self.assertIsNone(r.executable_alternative)


class ConfidenceTests(unittest.TestCase):
    def test_components_and_formula(self):
        r = route("Generate a photorealistic image with readable text for a poster")
        s = r.selection
        c = s.confidence_components
        expected = round(0.35 * c["category_confidence"] + 0.35 * c["ranking_margin"] + 0.30 * c["feature_support"], 3)
        self.assertEqual(s.confidence_value, expected)
        self.assertEqual(s.confidence_level, "high")
        self.assertIn("no model answer", s.confidence_formula)
        self.assertEqual(r.confidence_report.combined, s.confidence_value)

    def test_report_has_no_response_or_execution_component(self):
        names = {c.name for c in route("Explain recursion").confidence_report.components}
        self.assertEqual(names, {"category_confidence", "ranking_margin", "feature_support"})

    def test_confidence_does_not_change_with_any_execution_input(self):
        base = route("Write a Python function to reverse a list")
        with patch.object(model_registry, "_configured", lambda p: True):
            other = route("Write a Python function to reverse a list", mode="execute", budget_usd=1.0, evaluate_response=True)
        self.assertEqual(base.selection.confidence_value, other.selection.confidence_value)

    def test_a_tie_lowers_confidence_honestly(self):
        tie = route("Explain photosynthesis to a ten year old").selection
        clear = route("What are the latest news about AI, with citations?").selection
        self.assertLessEqual(tie.confidence_components["ranking_margin"], clear.confidence_components["ranking_margin"])
        self.assertLessEqual(tie.confidence_value, clear.confidence_value)

    def test_ambiguity_caps_confidence(self):
        s = route("Generate an image of a red car and a video of it").selection
        self.assertLessEqual(s.confidence_value, 0.60)

    def test_level_thresholds(self):
        for q in ("Explain photosynthesis", "Generate an image of a red car", "Make a pitch deck for my startup"):
            s = route(q).selection
            expected = "high" if s.confidence_value >= 0.75 else "medium" if s.confidence_value >= 0.5 else "low"
            self.assertEqual(s.confidence_level, expected)


class CostPreferenceTests(unittest.TestCase):
    def test_pricing_is_ignored_unless_the_user_states_a_cost_preference(self):
        r = route("Generate an image of a red car")
        self.assertEqual(r.normalization.cost_basis, "not_used")
        self.assertIsNone(r.candidates[0].utilities.get("cost"))

    def test_a_stated_cost_preference_uses_the_documented_access_class(self):
        r = route("Generate an image of a red car", weight_overrides={"cost": 0.6, "preference_alignment": 0.4})
        self.assertEqual(r.normalization.cost_basis, "access_class")
        self.assertTrue(any(c.utilities.get("cost") is not None for c in r.candidates))


class ApiConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.patches = [
            patch("app.api.routes.routing.user_store.decode_token", return_value="u1"),
            patch("app.api.routes.routing.user_store.get_by_id", return_value=FakeUser()),
            patch("app.api.routes.routing.feedback_store.record_routing_decision"),
            patch("app.api.routes.routing.routing_log_store.record"),
            patch("app.api.routes.routing.routing_log_store.record_trace"),
            patch("app.services.routing_engine.observed.load_observed", return_value={}),
            patch("app.services.feedback_store.get_learning_bonuses", return_value={}),
        ]
        for p in self.patches:
            p.start()
        self.h = {"Authorization": "Bearer x"}

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def post(self, body):
        for prefix in ("/api/v1", "/api", ""):
            r = self.client.post(f"{prefix}/route-and-generate", json=body, headers=self.h)
            if r.status_code != 404:
                return r
        return r

    def test_best_match_suggested_and_candidates_are_one_ranking(self):
        for q in ("Generate an image of a red car", "Make a pitch deck for my startup", "Write a Python function to reverse a list", "Explain photosynthesis to a child"):
            with self.subTest(q=q):
                r = self.post({"query": q, "mode": "execute"})
                self.assertEqual(r.status_code, 200, r.text)
                d = r.json()
                e = d["engine"]
                ranking = [x["model_id"] for x in e["ranking"]]
                self.assertEqual(d["selected_model_id"], ranking[0])
                self.assertEqual(d["final_model_id"], ranking[0])
                self.assertEqual(e["best_match_id"], ranking[0])
                self.assertEqual(d["candidate_models"], ranking)
                self.assertEqual([m["model_id"] for m in d["model_scores"]], ranking)
                self.assertEqual(e["suggested_ids"], ranking[1:4])
                self.assertEqual([t["model_id"] for t in d["tool_recommendations"]], ranking[1:4])
                self.assertEqual([a["model_id"] for a in d["ranked_alternatives"]], ranking[1:5])
                self.assertEqual(e["selection"]["selected_model_id"], ranking[0])
                cat = e["profile"]["category"]["category"]
                self.assertTrue(all(x["category"] == cat or cat in eco_secondary(x["model_id"]) for x in e["ranking"]))

    def test_response_is_recommendation_only(self):
        d = self.post({"query": "Write a Python function to reverse a list", "mode": "execute"}).json()
        self.assertTrue(d["engine"]["recommendation_only"])
        self.assertEqual(d["engine"]["mode"], "recommend")
        self.assertFalse(d["escalation_info"]["escalated"])
        self.assertIsNone(d["escalation_info"]["escalation_reason"])
        self.assertEqual(d["response_evaluation"]["evaluation_method"], "not_applicable_recommendation_only")
        self.assertEqual(d["request_usage"], [])
        self.assertNotIn("sk-", str(d))

    def test_unscored_pool_members_do_not_appear(self):
        d = self.post({"query": "Generate an image of a red car"}).json()
        self.assertEqual(d["engine"]["unscored_candidates"], [])


class PoolStatsAndEvaluationTests(ApiConsistencyTests):
    def test_pool_stats_reconcile_with_the_listed_pool(self):
        d = self.client.get("/api/v1/models/pool-stats").json()
        listed = self.client.get("/api/v1/models").json()
        self.assertEqual(d["pool_total"], len(listed))
        self.assertEqual(sum(d["primary"].values()), d["pool_total"])
        self.assertEqual(d["primary"], {c: len(n) for c, n in APPROVED_NAMES.items()})
        self.assertTrue(d["integrity"]["ok"], d["integrity"])
        self.assertLessEqual(d["pool_total"], d["cap"])
        self.assertEqual({e["model_name"] for e in listed}, set().union(*APPROVED_NAMES.values()))

    def test_catalog_endpoint_lists_only_approved_entries(self):
        d = self.client.get("/api/v1/models/catalog?page_size=100").json()
        self.assertEqual({i["model_name"] for i in d["items"]}, set().union(*APPROVED_NAMES.values()))

    def test_ecosystem_suite_reports_computed_metrics(self):
        with patch("app.api.routes.evaluation.user_store.decode_token", return_value="u1"), patch("app.api.routes.evaluation.user_store.get_by_id", return_value=FakeUser()):
            d = self.client.get("/api/v1/evaluate/ecosystem", headers=self.h).json()
        self.assertEqual(d["cases"], len(d["results"]))
        self.assertTrue(d["metadata_only"])
        for key in ("category_purity", "ranking_consistency", "credential_independence", "determinism", "recommendation_only"):
            self.assertEqual(d["metrics"][key], 1.0, key)
        self.assertEqual(sum(v["cases"] for v in d["per_category"].values()), d["cases"])

    def test_offline_evaluation_compares_inside_the_category_only(self):
        with patch("app.api.routes.evaluation.user_store.decode_token", return_value="u1"), patch("app.api.routes.evaluation.user_store.get_by_id", return_value=FakeUser()):
            d = self.client.post("/api/v1/evaluate/offline", json={"query": "Generate an image of a red car"}, headers=self.h).json()
        names = {s["selected_model"] for s in d["strategy_results"] if s["status"] == "selected"}
        self.assertEqual({s["strategy"] for s in d["strategy_results"]}, {"aicompass", "static", "strongest", "cheapest"})
        self.assertEqual({s["strategy"] for s in d["strategy_results"] if s["status"] == "selected"}, {"aicompass", "static", "strongest", "cheapest"})
        self.assertTrue(all(s["quality_score"] is not None for s in d["strategy_results"] if s["status"] == "selected"))
        self.assertTrue(names <= APPROVED_NAMES["image"] | {"Canva"})
        self.assertEqual(d["catalog_coverage"]["execution_ready_models"], 0)


def eco_secondary(model_id):
    return next(m.secondary_categories for m in model_registry.approved_models() if m.model_id == model_id)


if __name__ == "__main__":
    unittest.main()
