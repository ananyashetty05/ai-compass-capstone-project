"""Offline evaluation of the category-first recommendation engine (metadata only; no product is ever called).

A fixed, labelled query set (``CASES``) is run through the real pipeline against the approved pool. The labels are written
by the project team and are the only ground truth: they say which category each query belongs to. Nothing about the quality of
any product's output is measured, so nothing about output quality is claimed.

Metrics (all computed here, none assumed):
* category_accuracy         resolved category equals the label
* category_purity           share of ranked candidates that serve the resolved category (must be 1.0)
* ranking_consistency       Best Match is rank 1 and the runner-ups are ranks 2-4 of the same ranking
* credential_independence   ranking identical with every provider credential present vs absent
* determinism               two runs give an identical ranking
* recommendation_only       no execution, escalation or response evaluation took place
* confidence                distribution of the selection-confidence level (derived from the ranking only)
"""
from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
from dataclasses import dataclass
from typing import Any, Dict, List
from unittest.mock import patch

from app.data import approved_ecosystem as eco
from app.services import model_registry
from app.services.routing_engine import pipeline


@dataclass(frozen=True)
class Case:
    id: str
    category: str
    query: str


CASES: List[Case] = [
    Case("cv1", "conversational", "Explain how vaccines train the immune system."),
    Case("cv2", "conversational", "Summarize the causes of the French Revolution in five bullet points."),
    Case("cv3", "conversational", "Write a polite email asking my professor for an extension."),
    Case("cv4", "conversational", "What are the latest developments in solar battery storage? Cite sources."),
    Case("im1", "image", "Generate a photorealistic image of a lighthouse at dawn."),
    Case("im2", "image", "Create a logo for a coffee shop with readable text."),
    Case("im3", "image", "Make artistic concept art of a floating city."),
    Case("im4", "image", "Edit this photo to remove the background."),
    Case("vd1", "video", "Create a cinematic video of a rainy city street."),
    Case("vd2", "video", "Generate a short video clip from this image."),
    Case("vd3", "video", "Make a text to video trailer for my game."),
    Case("mv1", "music_voice", "Generate a lofi song with vocals."),
    Case("mv2", "music_voice", "Convert this script to speech with a natural voice."),
    Case("mv3", "music_voice", "Clone my voice for narration."),
    Case("mv4", "music_voice", "Compose an instrumental soundtrack for a documentary."),
    Case("dd1", "document_design", "Make a pitch deck for my startup."),
    Case("dd2", "document_design", "Design a mobile app UI wireframe."),
    Case("dd3", "document_design", "Build a landing page for my portfolio."),
    Case("dd4", "document_design", "Create an Instagram poster with my brand kit."),
    Case("ap1", "api_models", "Which free LLM API should I use for my chatbot project?"),
    Case("ap2", "api_models", "I need an open-source model I can self-host and fine-tune."),
    Case("ap3", "api_models", "Which inference API gives the lowest latency for open models?"),
    Case("ap4", "api_models", "I want one API to switch between many models."),
    Case("cd1", "coding", "Write a Python function to merge two sorted lists."),
    Case("cd2", "coding", "Debug this stack trace in my IDE."),
    Case("cd3", "coding", "Review my pull request and refactor the codebase."),
    Case("cd4", "coding", "Write an AWS Lambda function in Python."),
]


def _run(query: str, mode: str = "recommend"):
    req = pipeline.PipelineRequest(query=query, optimization_mode="disabled", mode=mode)
    return pipeline.run(req, saved_weights=None, user_id=None, observed_loader=lambda ids: {}, learning_loader=lambda u, ids: {})


def _ranking(res) -> List[Any]:
    return [(c.model_id, c.robust_score) for c in res.candidates]


def _with_credentials(present: bool):
    stack = ExitStack()
    stack.enter_context(patch.object(model_registry, "_configured", lambda p: present))
    stack.enter_context(patch("app.services.registry_eligibility.provider_configured", lambda p: present))
    return stack


def run() -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    levels: Counter = Counter()
    confidences: List[float] = []
    for case in CASES:
        res = _run(case.query, mode="execute")          # execute is requested on purpose: it must be ignored
        again = _run(case.query)
        with _with_credentials(True):
            with_keys = _run(case.query)
        with _with_credentials(False):
            without_keys = _run(case.query)
        cat = res.profile.category.category if res.profile.category else None
        by = res.model_lookup
        pure = [eco.serves(by[c.model_id], cat) for c in res.candidates] if cat else []
        ids = [c.model_id for c in res.candidates]
        consistent = bool(ids) and res.selection.selected_model_id == ids[0] and res.selection.runner_up_ids == ids[1:4]
        only = res.mode == "recommend" and res.execution.status == "not_requested" and not res.execution.escalated and res.evaluation.status == "not_requested"
        levels[res.selection.confidence_level] += 1
        confidences.append(res.selection.confidence_value)
        rows.append({
            "id": case.id, "query": case.query, "expected_category": case.category, "resolved_category": cat, "category_ok": cat == case.category,
            "candidates": len(ids), "best_match": res.candidates[0].model_name if res.candidates else None, "suggested": [c.model_name for c in res.candidates[1:4]],
            "pure": all(pure) if pure else False, "consistent": consistent, "credential_independent": _ranking(with_keys) == _ranking(without_keys) == _ranking(res),
            "deterministic": _ranking(res) == _ranking(again), "recommendation_only": only,
            "confidence": res.selection.confidence_value, "confidence_level": res.selection.confidence_level, "tie": res.selection.tie_break_applied})
    n = len(rows)

    def rate(key: str) -> float:
        return round(sum(1 for r in rows if r[key]) / n, 4) if n else 0.0
    per_category = {c: {"cases": sum(1 for r in rows if r["expected_category"] == c), "correct": sum(1 for r in rows if r["expected_category"] == c and r["category_ok"])} for c in eco.CATEGORIES}
    return {
        "method": "offline_category_routing_suite", "metadata_only": True, "cases": n, "pool_size": len(model_registry.approved_models()),
        "disclosure": "Labels come from the project team. The suite measures routing correctness and consistency against those labels; it does not measure how good any product's output is, and no product is run.",
        "metrics": {"category_accuracy": rate("category_ok"), "category_purity": rate("pure"), "ranking_consistency": rate("consistent"),
                    "credential_independence": rate("credential_independent"), "determinism": rate("deterministic"), "recommendation_only": rate("recommendation_only")},
        "confidence": {"levels": {k: levels.get(k, 0) for k in ("high", "medium", "low")}, "mean": round(sum(confidences) / n, 3) if n else 0.0,
                       "note": "Derived from the ranking only (category confidence, ranking margin, feature support). Ties lower it by design. Not calibrated against outcomes."},
        "per_category": per_category, "results": rows}
