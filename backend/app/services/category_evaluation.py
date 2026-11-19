"""Category-aware offline evaluation (metadata only; no model is ever called).

A fixed, labelled set of queries is run through the real routing pipeline against the catalogue the app is serving.
The labels are written by the project team (``CASES``) and are the only "ground truth" here: they say which audience
each query *should* be treated as. Nothing about answer quality is measured, so nothing about answer quality is claimed.

Metrics
-------
* ``classification_accuracy``   audience (conversational / developer / ambiguous) matches the label
* ``category_leakage_rate``     share of recommended candidates that are in the wrong group for the query:
                                a developer/API offering for a conversational or ambiguous query, or a consumer
                                application / unclassified-integration entry for a developer query
* ``free_tier_accuracy``        for "free" queries, share of candidates with a documented free tier or free download
* ``unverified_shown_as_free``  candidates on a "free" query whose pricing is not verified (must be 0)
* ``constraint_violation_rate`` share of candidates breaking an explicit hard constraint of the case (max cost)
* ``recommendation_coverage``   share of cases that produced at least one candidate
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.services import access_category

CONVERSATIONAL, DEVELOPER, AMBIGUOUS = "conversational", "developer", "ambiguous"
FREE_SET = {"completely_free", "free_tier_limited", "self_hosted_open_weight"}


@dataclass(frozen=True)
class Case:
    id: str
    group: str                 # ordinary_conversational | project_api | free_api | coding_integration | rag_agent | ambiguous
    query: str
    expected: str              # conversational | developer | ambiguous
    wants_free: bool = False
    max_cost: Optional[float] = None


CASES: List[Case] = [
    Case("c1", "ordinary_conversational", "Explain machine learning.", CONVERSATIONAL),
    Case("c2", "ordinary_conversational", "Summarize the causes of the French Revolution in five bullet points.", CONVERSATIONAL),
    Case("c3", "ordinary_conversational", "Write a polite email asking my professor for an extension.", CONVERSATIONAL),
    Case("c4", "ordinary_conversational", "Solve 3x + 7 = 25 and show the steps.", CONVERSATIONAL),
    Case("c5", "ordinary_conversational", "Help me prepare for a software engineering interview.", CONVERSATIONAL),
    Case("c6", "ordinary_conversational", "Explain what an API is.", CONVERSATIONAL),
    Case("c7", "ordinary_conversational", "Explain how a transformer language model works.", CONVERSATIONAL),
    Case("c8", "ordinary_conversational", "Summarize the plot of Hamlet in three sentences.", CONVERSATIONAL, max_cost=0.002),
    Case("p1", "project_api", "I need an AI model for my college project.", DEVELOPER),
    Case("p2", "project_api", "I want to integrate AI into my Python application.", DEVELOPER),
    Case("p3", "project_api", "Which model should I use for my capstone?", DEVELOPER),
    Case("p4", "project_api", "Which Groq or Hugging Face model should I use?", DEVELOPER),
    Case("p5", "project_api", "I need an LLM that I can call through an API.", DEVELOPER),
    Case("f1", "free_api", "Which free LLM API can I use?", DEVELOPER, wants_free=True),
    Case("f2", "free_api", "Suggest a free model API for students.", DEVELOPER, wants_free=True),
    Case("f3", "free_api", "I need a free LLM API for my Python college project.", DEVELOPER, wants_free=True),
    Case("p6", "project_api", "I need an AI model for my college project on a tight budget.", DEVELOPER, max_cost=0.002),
    Case("k1", "coding_integration", "Suggest a model for building a coding assistant inside my IDE plugin project.", DEVELOPER),
    Case("k2", "coding_integration", "I want to build a code review bot for my team's repository.", DEVELOPER),
    Case("r1", "rag_agent", "I want to build a RAG application.", DEVELOPER),
    Case("r2", "rag_agent", "I need a model for an AI agent.", DEVELOPER),
    Case("r3", "rag_agent", "Suggest a model for building a chatbot.", DEVELOPER),
    Case("a1", "ambiguous", "Which AI model is best for coding?", AMBIGUOUS),
    Case("a2", "ambiguous", "Suggest the best LLM for writing essays.", AMBIGUOUS),
    Case("a3", "ambiguous", "Recommend a good AI model.", AMBIGUOUS),
]


def _run_case(case: Case) -> Dict[str, Any]:
    from app.services.routing_engine import pipeline  # imported lazily: this module is imported by the API layer
    req = pipeline.PipelineRequest(query=case.query, optimization_mode="disabled", evaluate_response=False, max_cost=case.max_cost)
    res = pipeline.run(req, saved_weights=None, user_id=None, observed_loader=lambda ids: {}, learning_loader=lambda u, ids: {})
    aud = res.profile.audience
    got = AMBIGUOUS if aud.ambiguous else aud.kind
    rows = list(res.candidates)
    leaked = 0
    free_ok = 0
    unverified_free = 0
    violations = 0
    for c in rows:
        m = res.model_lookup.get(c.model_id)
        prof = access_category.profile_of(m) if m is not None else None
        if prof is None:
            continue
        if case.expected in (CONVERSATIONAL, AMBIGUOUS):
            if prof.model_category == access_category.DEVELOPER_API:
                leaked += 1
        elif prof.integration_supported is False:
            leaked += 1
        if case.wants_free:
            if prof.pricing_category in FREE_SET:
                free_ok += 1
            if prof.pricing_category == "unknown":
                unverified_free += 1
        if case.max_cost is not None and c.estimated_cost_usd is not None and c.estimated_cost_usd > case.max_cost:
            violations += 1
    return {"id": case.id, "group": case.group, "query": case.query, "expected": case.expected, "classified_as": got, "correct": got == case.expected,
            "candidates": len(rows), "leaked": leaked, "free_ok": free_ok, "unverified_shown_as_free": unverified_free, "constraint_violations": violations,
            "top": rows[0].model_name if rows else None, "top_group": rows[0].model_category if rows else None, "status": res.status}


def _rate(num: int, den: int) -> Optional[float]:
    return round(num / den, 4) if den else None


def run(cases: Optional[List[Case]] = None) -> Dict[str, Any]:
    cases = cases if cases is not None else CASES
    rows = [_run_case(c) for c in cases]
    total_cands = sum(r["candidates"] for r in rows)
    free_rows = [r for r in rows if any(c.id == r["id"] and c.wants_free for c in cases)]
    free_cands = sum(r["candidates"] for r in free_rows)
    cost_cases = [r for r in rows if any(c.id == r["id"] and c.max_cost is not None for c in cases)]
    by_group: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        g = by_group.setdefault(r["group"], {"cases": 0, "correct": 0, "candidates": 0, "leaked": 0, "with_candidates": 0})
        g["cases"] += 1; g["correct"] += int(r["correct"]); g["candidates"] += r["candidates"]; g["leaked"] += r["leaked"]; g["with_candidates"] += int(r["candidates"] > 0)
    return {
        "method": "offline_registry_metadata",
        "disclosure": "Metadata only: no model was called and no answer quality was measured. Labels are the project team's own test set; "
                      "results describe how the router classifies and filters, not how good the recommended models are.",
        "cases": len(rows),
        "classification_accuracy": _rate(sum(int(r["correct"]) for r in rows), len(rows)),
        "category_leakage_rate": _rate(sum(r["leaked"] for r in rows), total_cands),
        "category_leakage_count": sum(r["leaked"] for r in rows),
        "free_tier_accuracy": _rate(sum(r["free_ok"] for r in free_rows), free_cands),
        "unverified_shown_as_free": sum(r["unverified_shown_as_free"] for r in rows),
        "constraint_violation_rate": _rate(sum(r["constraint_violations"] for r in cost_cases), sum(r["candidates"] for r in cost_cases)),
        "constraint_cases": len(cost_cases),
        "recommendation_coverage": _rate(sum(int(r["candidates"] > 0) for r in rows), len(rows)),
        "by_group": by_group,
        "results": rows,
    }
