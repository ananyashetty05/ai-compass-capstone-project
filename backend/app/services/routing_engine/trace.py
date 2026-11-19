"""Sanitized, persistable decision trace.

The trace is the pipeline's own structured result, so every number in it comes from the real routing run.
Privacy: the query, the submitted prompt, the optimiser's text and the model's response are removed; only
structure, scores, reasons and measurements remain.
"""
from typing import Any, Dict

TRACE_FORMAT = "1.0"

# Where each family of values comes from (shown in the UI as data-source labels).
SOURCE_LABELS = {
    "scores.quality|cost|latency|reliability|risk": "per-metric provenance is carried in candidates[].evidence[].provenance (measured | observed | provider_published | benchmark | estimated | unavailable)",
    "scores.preference_alignment": "registry-declared capabilities vs the detected intents (derived)",
    "weights": "user-configured or system default; adjustments are listed individually",
    "execution.latency_ms": "measured by AI Compass for this request",
    "execution.cost_usd": "computed from provider-published prices x provider-reported token usage",
    "evaluation.checks": "deterministic checks run by AI Compass on the response",
    "evaluation.confidence": "unavailable: no model-reported or calibrated confidence exists",
}


def build(result: Any) -> Dict[str, Any]:
    t = result.model_dump()
    t["profile"]["original_query"] = ""
    t["optimization"] = {k: t["optimization"].get(k) for k in ("mode", "applied", "intent_preserved", "method", "changes", "preserved_constraints", "warnings")}
    t["prompt_used"] = ""
    ex = t.get("execution") or {}
    ex["response_text"] = None
    t["execution"] = ex
    t["trace_format"] = TRACE_FORMAT
    t["source_labels"] = SOURCE_LABELS
    return t
