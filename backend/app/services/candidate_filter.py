"""
AI Compass - Candidate Filter
Eliminates models that clearly violate hard constraints BEFORE scoring.

FILTERING = eliminate unsuitable models (hard constraints)
SCORING   = compare remaining candidates (soft objectives)
SELECTION = choose the final model
"""
from typing import List, Tuple, Dict
from app.schemas.model import ModelMetadata
from app.schemas.query import QueryProfile
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def filter_candidates(
    models: List[ModelMetadata],
    query_profile: QueryProfile,
    max_cost: float = None,
    max_latency: float = None,
    require_capabilities: List[str] = None,
) -> Tuple[List[ModelMetadata], List[Dict[str, str]]]:
    """
    Returns (passing_models, filtered_out_list).
    filtered_out_list contains dicts with model_id and reason.
    """
    passing = []
    filtered_out = []

    for model in models:
        reason = _check_hard_constraints(
            model, query_profile, max_cost, max_latency, require_capabilities
        )
        if reason:
            filtered_out.append({"model_id": model.model_id, "reason": reason})
            logger.debug(f"Filtered out {model.model_id}: {reason}")
        else:
            passing.append(model)

    return passing, filtered_out


def _check_hard_constraints(
    model: ModelMetadata,
    query_profile: QueryProfile,
    max_cost: float,
    max_latency: float,
    require_capabilities: List[str],
) -> str:
    """Returns a reason string if the model should be filtered, else empty string."""

    if not model.active:
        return "Model is inactive"

    required_modalities = set(query_profile.required_modalities or ["text"])
    model_modalities = set(model.modalities or [model.modality])
    if not required_modalities.issubset(model_modalities):
        return f"Missing required modality: {', '.join(sorted(required_modalities - model_modalities))}"

    inferred_capabilities = query_profile.required_capabilities or []
    missing_inferred = [c for c in inferred_capabilities if c not in model.capabilities]
    if missing_inferred:
        return f"Missing task capability: {missing_inferred}"

    # Task support check
    if query_profile.task_type not in model.supported_tasks and model.supported_tasks:
        # Only hard-filter if the model has a very narrow task list
        if len(model.supported_tasks) <= 3 and query_profile.task_type not in model.supported_tasks:
            return f"Does not support task type: {query_profile.task_type}"

    # Domain support check
    if (
        query_profile.domain not in model.supported_domains
        and "general" not in model.supported_domains
        and model.supported_domains
    ):
        return f"Does not support domain: {query_profile.domain}"

    # Context window check
    # A zero context window means the catalog has no comparable token-window
    # value (common for consumer applications and image/audio endpoints), not
    # that the application accepts zero input tokens.
    if model.context_window > 0 and query_profile.estimated_tokens > model.context_window:
        return f"Context window too small ({model.context_window} < {query_profile.estimated_tokens})"

    # Hard cost constraint
    if max_cost is not None and model.cost_per_1k_tokens > max_cost:
        return f"Exceeds cost constraint (${model.cost_per_1k_tokens:.4f} > ${max_cost:.4f})"

    # Hard latency constraint
    if max_latency is not None and model.avg_latency_seconds > max_latency:
        return f"Exceeds latency constraint ({model.avg_latency_seconds:.1f}s > {max_latency:.1f}s)"

    # Required capabilities
    if require_capabilities:
        missing = [c for c in require_capabilities if c not in model.capabilities]
        if missing:
            return f"Missing required capabilities: {missing}"

    return ""
