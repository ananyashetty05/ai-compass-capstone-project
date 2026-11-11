import os
os.environ.setdefault("JWT_SECRET", "unit-test-only-secret-do-not-use-in-production")

import unittest

from app.services import prompt_optimizer, query_analyzer


class PromptOptimizerTests(unittest.TestCase):
    def optimize(self, query, task_type_hint=None):
        profile = query_analyzer.analyze(query)
        profile = query_analyzer.apply_task_type_hint(profile, task_type_hint)
        return prompt_optimizer.optimize(query, profile)

    def test_summary_query_gets_summary_specific_guidance(self):
        query = "Summarise the main causes of the 2008 financial crisis and the policy responses to it."
        result = self.optimize(query)
        self.assertEqual(result.task_type, "summarization")
        self.assertIn(query, result.prompt)
        self.assertIn("If source material is provided", result.prompt)
        self.assertIn("Causes or contributing factors", result.prompt)
        self.assertIn("Responses or interventions", result.prompt)
        self.assertNotIn("housing market", result.prompt.lower())

    def test_coding_and_research_use_different_structures(self):
        coding = self.optimize("Implement a Python function that sorts records.")
        research = self.optimize("Research current approaches to battery recycling.")
        self.assertEqual(coding.task_type, "coding")
        self.assertEqual(research.task_type, "research")
        self.assertIn("implementation requirements", coding.prompt)
        self.assertIn("Focused tests", coding.prompt)
        self.assertIn("evidence gaps", research.prompt)
        self.assertNotEqual(coding.prompt, research.prompt)

    def test_writing_and_presentation_keep_the_original_request(self):
        writing_query = "Write a short welcome note for new volunteers."
        presentation_query = "Create a slide deck about urban gardens."
        writing = self.optimize(writing_query, "creative")
        presentation = self.optimize(presentation_query)
        self.assertIn(writing_query, writing.prompt)
        self.assertIn("audience", writing.prompt)
        self.assertEqual(presentation.task_type, "presentation")
        self.assertIn(presentation_query, presentation.prompt)
        self.assertIn("one main idea", presentation.prompt)

    def test_explicit_education_and_image_hints_use_relevant_guidance(self):
        education = self.optimize("Explain fractions with examples.", "education")
        image = self.optimize("Generate a watercolor image of a lighthouse.", "image-generation")
        self.assertIn("clear progression", education.prompt)
        self.assertIn("composition", image.prompt)
        self.assertEqual(image.method, "Task-aware local optimizer")

    def test_long_query_does_not_get_an_unbounded_template(self):
        query = "Analyze the stated issue. " * 100
        result = self.optimize(query, "analysis")
        self.assertIn(query.strip(), result.prompt)
        self.assertEqual(result.prompt.count("\n- "), 2)


if __name__ == "__main__":
    unittest.main()
