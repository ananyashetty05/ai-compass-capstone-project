"""Compatibility wrapper for the task-aware local prompt optimizer."""
from app.schemas.query import QueryProfile
from app.services.prompt_optimizer import optimize


def adapt(query: str, query_profile: QueryProfile) -> str:
    """Return a structured, task-aware prompt without external inference."""
    return optimize(query, query_profile).prompt
