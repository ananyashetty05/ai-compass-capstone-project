"""Deterministic evaluation based only on the actual generated response."""
import re
from app.schemas.response import ResponseEvaluation
from app.schemas.query import QueryProfile
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_REFUSAL_PATTERNS = ("i cannot", "i can't", "i'm unable", "unable to help", "no answer")
_SENSITIVE_PATTERNS = ("diagnose", "prescribe", "guaranteed return", "legal advice")


def evaluate(response: str, query: str, query_profile: QueryProfile) -> ResponseEvaluation:
    text = response.strip()
    terms = lambda value: set(re.findall(r"[a-zA-Z]{3,}", value.lower()))
    query_terms = terms(query) - {"what", "when", "where", "which", "with", "that", "this", "from", "your"}
    overlap = len(terms(text) & query_terms) / max(1, len(query_terms))
    relevance = min(1.0, 0.25 + 0.75 * overlap) if text else 0.0
    completeness = min(1.0, len(text.split()) / (35 + int(query_profile.complexity * 100))) if text else 0.0
    refusal = any(pattern in text.lower() for pattern in _REFUSAL_PATTERNS)
    risk = min(1.0, 0.25 * sum(pattern in text.lower() for pattern in _SENSITIVE_PATTERNS))
    quality = max(0.0, min(1.0, 0.55 * relevance + 0.45 * completeness - (0.45 if refusal else 0)))
    accepted = bool(text) and not refusal and quality >= settings.QUALITY_ACCEPTANCE_THRESHOLD and risk <= settings.RISK_ACCEPTANCE_THRESHOLD
    reasons = []
    if not text: reasons.append("Provider returned an empty response.")
    if refusal: reasons.append("Response contains a refusal or inability statement.")
    if quality < settings.QUALITY_ACCEPTANCE_THRESHOLD: reasons.append(f"Calculated quality {quality:.2f} is below the acceptance threshold.")
    if risk > settings.RISK_ACCEPTANCE_THRESHOLD: reasons.append(f"Calculated risk {risk:.2f} exceeds the acceptance threshold.")
    if accepted: reasons.append("Response met deterministic relevance, completeness, and risk criteria.")
    return ResponseEvaluation(quality_score=round(quality, 3), relevance_score=round(relevance, 3), completeness_score=round(completeness, 3), risk_score=round(risk, 3), accepted=accepted, evaluation_reasons=reasons)
