import unittest

from tests.engine_helpers import profile
from app.services.routing_engine import understanding


class IntentTests(unittest.TestCase):
    def test_simple_question(self):
        p = profile("What is the capital of France?")
        self.assertEqual(p.primary_intent, "qa")
        self.assertEqual(p.complexity.category, "simple")
        self.assertFalse(p.needs_clarification)

    def test_coding_request_extracts_language_and_format(self):
        p = profile("Write a Python function that parses CSV files and returns JSON.")
        self.assertEqual(p.primary_intent, "coding")
        kinds = {(r.kind, r.value) for r in p.explicit_requirements}
        self.assertIn(("programming_language", "python"), kinds)
        self.assertIn(("output_format", "json"), kinds)
        self.assertEqual(p.structured_output, "json")
        self.assertTrue(all(r.origin == "explicit" for r in p.explicit_requirements))

    def test_debugging_with_code_block(self):
        p = profile("My script crashes with a TypeError:\n```python\nprint(1 + 'a')\n```\nPlease debug it.")
        self.assertEqual(p.primary_intent, "debugging")
        self.assertIn("coding", p.task_tags)

    def test_multi_intent_query_reports_secondary_tasks(self):
        p = profile("Analyse this dataset, identify anomalies, and explain the findings in a report.\n" + "\n".join(f"row{i},{i * 3},{i % 4}" for i in range(12)))
        names = {i.name for i in p.intents}
        self.assertEqual(p.primary_intent, "data_analysis")
        self.assertTrue(names & {"reasoning", "writing"}, names)

    def test_math_proof_is_math_not_education(self):
        self.assertEqual(profile("Prove that the sum of two even numbers is even, step by step.").primary_intent, "math")

    def test_generation_intents_set_hard_requirements(self):
        p = profile("Generate an image of a lighthouse at dawn")
        self.assertEqual(p.primary_intent, "image_generation")
        self.assertEqual(p.required_capabilities, ["image-generation"])
        self.assertEqual(p.required_modalities, ["image"])

    def test_no_substring_false_positives(self):
        # "withdraw" must not trigger image generation, "eclipse" must not trigger video
        self.assertEqual(profile("How do I withdraw money from the eclipse bank account?").primary_intent, "qa")

    def test_task_hint_overrides_but_is_recorded(self):
        p = profile("Tell me about batteries", hint="research")
        self.assertEqual(p.primary_intent, "research")
        self.assertEqual(p.user_hint_applied, "research")
        with self.assertRaises(ValueError):
            profile("hello there friend", hint="not-a-task")


class ComplexityTests(unittest.TestCase):
    def test_hard_query_scores_higher_than_simple(self):
        hard = profile("Design a distributed system architecture for a payment platform. Compare trade-offs of consensus protocols, justify the choice, analyze race conditions, "
                       "and provide a step-by-step migration plan. Output as a table; must not exceed 300 words.")
        easy = profile("What is the capital of France?")
        self.assertGreater(hard.complexity.score, easy.complexity.score + 0.3)
        self.assertIn(hard.complexity.category, {"complex", "highly_complex"})
        self.assertAlmostEqual(sum(hard.complexity.weights.values()), 1.0, places=6)
        self.assertTrue(0.0 <= hard.complexity.score <= 1.0)

    def test_ambiguity_does_not_inflate_complexity(self):
        self.assertEqual(profile("fix this").complexity.category, "simple")


class AmbiguityTests(unittest.TestCase):
    def test_missing_referent_needs_clarification(self):
        p = profile("fix this")
        self.assertTrue(p.needs_clarification)
        self.assertTrue(any(a.severity == "major" for a in p.ambiguities))
        self.assertTrue(all(a.clarifying_question for a in p.ambiguities if a.severity == "major"))

    def test_missing_attachment_flagged(self):
        self.assertTrue(profile("Summarize the attached document").needs_clarification)

    def test_contradictory_length_is_minor(self):
        p = profile("Give a brief but comprehensive explanation of how TLS handshakes work.")
        self.assertTrue(any(a.kind == "contradiction" for a in p.ambiguities))
        self.assertFalse(p.needs_clarification)

    def test_pasted_content_resolves_referent(self):
        p = profile("Summarize this:\n" + "A paragraph about energy storage. " * 20)
        self.assertFalse(p.needs_clarification)


class TokenTests(unittest.TestCase):
    def test_estimates_are_labelled_not_exact(self):
        p = profile("x" * 4000 + " explain this")
        self.assertFalse(p.tokens.exact)
        self.assertTrue(p.tokens.method)
        self.assertGreaterEqual(p.tokens.input_tokens, 900)
        self.assertGreater(p.tokens.output_tokens, 0)

    def test_explicit_length_limit_drives_output_estimate(self):
        p = profile("Explain recursion in under 50 words.")
        self.assertEqual(p.tokens.output_basis, "explicit_words_limit")
        self.assertLessEqual(p.tokens.output_tokens, 100)


class RiskTests(unittest.TestCase):
    def test_credentials_detected_without_echoing_them(self):
        p = profile("Debug this: api_key = sk-abcdefghijklmnopqrstuvwx and it fails with 401")
        self.assertTrue(p.risk.contains_credentials)
        self.assertEqual(p.risk.sensitivity, "high")
        self.assertTrue(p.risk.execution_blocked)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwx", p.risk.model_dump_json())

    def test_luhn_valid_card_flagged_invalid_ignored(self):
        self.assertEqual(understanding.assess_risk("card 4111 1111 1111 1111").sensitivity, "high")
        self.assertEqual(understanding.assess_risk("number 4111111111111112").sensitivity, "none")

    def test_medical_is_moderate_and_not_blocked(self):
        r = profile("What dosage of ibuprofen is typical for a patient with a fever?").risk
        self.assertEqual(r.sensitivity, "moderate")
        self.assertFalse(r.execution_blocked)

    def test_clean_query_has_no_risk(self):
        self.assertEqual(profile("Explain binary search").risk.sensitivity, "none")


class ValidationTests(unittest.TestCase):
    def test_empty_and_oversized_rejected(self):
        with self.assertRaises(ValueError):
            understanding.analyze("   ")
        with self.assertRaises(ValueError):
            understanding.analyze("a" * 50_001)


if __name__ == "__main__":
    unittest.main()
