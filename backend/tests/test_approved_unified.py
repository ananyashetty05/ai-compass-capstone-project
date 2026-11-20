"""The single recommendation algorithm on the real approved pool: exact ordering, removal invariance, honest features, determinism.

No network, no database, no provider calls (recommendation only).
"""
import os
os.environ.setdefault("JWT_SECRET", "unit-test-only-secret-do-not-use-in-production")

import unittest

from app.services.ecosystem_evaluation import CASES
from app.services.routing_engine import ecosystem, pipeline
from tests.test_approved_ecosystem import ids, route


class ExactOrdering(unittest.TestCase):
    def test_order_is_exactly_by_score_and_never_by_a_tolerance_window(self):
        """Before unification, products within 0.005 of the leader were re-ordered by approved-list order. A higher score must now always rank higher."""
        for c in CASES:
            res = route(c.query)
            scores = [round(r.robust_score, 12) for r in res.candidates]
            self.assertEqual(scores, sorted(scores, reverse=True), c.id)

    def test_products_that_tie_on_documented_evidence_are_reported_as_a_set_not_as_a_winner(self):
        """ER-PCR: the old editorial quality rating separated these products. Without verified evidence they are equally suitable and the response says so."""
        res = route("Create a cinematic video of a rainy city street.")
        by = {r.model_name: r.robust_score for r in res.candidates}
        self.assertEqual(by["Gemini Omni / Veo"], by["Runway Gen-3"])
        self.assertEqual(res.selection.decision_status, "indistinguishable")
        self.assertIn("Gemini Omni / Veo", [c.model_name for c in res.candidates if c.model_id in res.selection.alternative_ids] + [res.candidates[0].model_name])

    def test_a_documented_feature_difference_does_separate_products(self):
        res = route("Create an Instagram poster with my brand kit.")
        scores = [round(r.robust_score, 12) for r in res.candidates]
        self.assertGreater(scores[0], scores[1])
        self.assertEqual(res.selection.decision_status, "recommended")

    def test_a_list_order_tie_is_never_presented_as_a_verified_winner(self):
        """Equal scores may still be ordered by the fixed rule, but the decision status must then be indistinguishable (or needs_clarification), never recommended."""
        bad = []
        for c in CASES:
            sel = route(c.query).selection
            if sel.tie_break_applied and "approved-list order" in sel.tie_break_applied and sel.decision_status not in {"indistinguishable", "needs_clarification"}:
                bad.append((c.id, sel.decision_status))
        self.assertEqual(bad, [])

    def test_deterministic_and_credential_independent(self):
        for c in CASES[:10]:
            self.assertEqual(ids(route(c.query)), ids(route(c.query)))


class RemovalInvariance(unittest.TestCase):
    """Removing a candidate that is not the winner must not change the winner; removing the winner promotes the runner-up."""

    def test_all_evaluation_queries(self):
        checked = 0
        for c in CASES:
            full = route(c.query)
            order = ids(full)
            if len(order) < 3:
                continue
            for victim in order[1:]:
                rest = [m for m in order if m != victim]
                again = route(c.query, model_ids=rest)
                self.assertEqual(ids(again)[0], order[0], f"{c.id}: removing non-winner {victim} changed the winner")
                self.assertEqual(ids(again), rest, f"{c.id}: removing {victim} changed the relative order of the others")
                checked += 1
            promoted = route(c.query, model_ids=order[1:])
            self.assertEqual(ids(promoted)[0], order[1], c.id)
        self.assertGreater(checked, 60)


class FeatureMatching(unittest.TestCase):
    def feats(self, q):
        r = ecosystem.resolve(q)
        return [f["feature"] for f in r.features], r.unsatisfiable_features

    def test_image_to_video_is_recognised_from_natural_phrasing(self):
        f, _ = self.feats("Generate a short video clip from this image.")
        self.assertIn("image_to_video", f)
        res = route("Generate a short video clip from this image.")
        self.assertEqual({r.model_name for r in res.candidates if "image_to_video" in r.matched_features}, {"Runway Gen-3", "Kling AI", "Higgsfield AI"})
        self.assertIn(res.candidates[0].model_name, {"Runway Gen-3", "Kling AI", "Higgsfield AI"})

    def test_feature_nobody_in_the_category_can_satisfy_is_disclosed_and_not_counted(self):
        f, dropped = self.feats("Edit this photo to remove the background.")
        self.assertEqual(f, ["image_edit"])
        self.assertEqual(dropped, ["multimodal_input"])
        res = route("Edit this photo to remove the background.")
        self.assertEqual({r.feature_coverage for r in res.candidates if "image-editing" in r.strengths}, {1.0})

    def test_instagram_poster_is_not_a_video_request(self):
        f, _ = self.feats("Create an Instagram poster with my brand kit.")
        self.assertNotIn("social_video", f)
        self.assertEqual(route("Create an Instagram poster with my brand kit.").candidates[0].model_name, "Canva")

    def test_text_to_speech_separates_voice_products(self):
        res = route("Convert this script to speech with a natural voice.")
        self.assertEqual({r.model_name for r in res.candidates if r.feature_coverage == 1.0}, {"ElevenLabs", "Sarvam AI", "Cartesia"})

    def test_still_category_first(self):
        for c in CASES:
            res = route(c.query)
            self.assertEqual(res.profile.category.category, c.category, c.id)
            self.assertTrue(all(ecosystem.serves(res.model_lookup[r.model_id], c.category) for r in res.candidates), c.id)


class SingleVersion(unittest.TestCase):
    def test_no_algorithm_switch_exists(self):
        fields = set(pipeline.PipelineRequest.model_fields)
        self.assertFalse(fields & {"algorithm_version", "scoring_variant", "hurwicz_alpha", "privacy_scope"})
        self.assertNotIn("v2", pipeline.PipelineResult.model_fields)
        from app.core.config import settings
        self.assertFalse(hasattr(settings, "ALGORITHM_VERSION"))

    def test_selection_reports_exact_weight_margin(self):
        sel = route("Create a cinematic video of a rainy city street.").selection
        self.assertTrue(sel.weight_margin is None or 0.0 <= sel.weight_margin <= 1.0)
        if sel.weight_margin is not None:
            self.assertTrue(sel.weight_margin_rival)


if __name__ == "__main__":
    unittest.main()
