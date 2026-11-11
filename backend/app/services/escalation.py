"""Adaptive escalation through real configured providers only."""
from typing import List
from app.schemas.model import ModelMetadata
from app.schemas.routing import RoutingDecision
from app.schemas.response import ResponseEvaluation, EscalationInfo
from app.services.model_adapters.factory import get_adapter
from app.services.model_adapters.provider_adapters import ProviderUnavailableError
from app.services import response_evaluator, prompt_adapter
from app.schemas.query import QueryProfile
from app.core.config import settings


def escalate_if_needed(initial_response: str, initial_eval: ResponseEvaluation,
                       routing_decision: RoutingDecision, query: str,
                       query_profile: QueryProfile, all_models: List[ModelMetadata],
                       initial_usage: dict,
                       initial_optimized_prompt: str) -> tuple[str, ResponseEvaluation, EscalationInfo, list[dict], str]:
    usages = [initial_usage]
    if initial_eval.accepted:
        return initial_response, initial_eval, EscalationInfo(escalated=False, attempts=1, final_status="success"), usages, initial_optimized_prompt
    models = {model.model_id: model for model in all_models}
    attempts, current_response, current_eval, fallback_id = 1, initial_response, initial_eval, None
    current_optimized_prompt = initial_optimized_prompt
    failures = []
    for score in sorted(routing_decision.model_scores, key=lambda item: item.overall_score, reverse=True):
        if score.model_id == routing_decision.selected_model_id or attempts >= settings.MAX_ESCALATION_ATTEMPTS:
            continue
        model = models.get(score.model_id)
        if not model or not model.active:
            continue
        attempts += 1
        # Generate a new prompt adapted for the escalated model.
        escalation_prompt = prompt_adapter.adapt(query, query_profile, model)
        try:
            adapter = get_adapter(model)
            response = adapter.generate(escalation_prompt)
        except ProviderUnavailableError as exc:
            failures.append(f"{model.model_id}: {exc}")
            continue
        usages.append(adapter.get_usage() | {"model_id": model.model_id})
        fallback_id, current_response = model.model_id, response
        current_optimized_prompt = escalation_prompt
        current_eval = response_evaluator.evaluate(response, query, query_profile)
        if current_eval.accepted:
            break
    return current_response, current_eval, EscalationInfo(
        escalated=fallback_id is not None,
        escalation_trigger="response_did_not_meet_acceptance_criteria" if fallback_id else None,
        original_model_id=routing_decision.selected_model_id if fallback_id else None,
        fallback_model_id=fallback_id,
        escalation_reason="; ".join(current_eval.evaluation_reasons + failures) or None,
        attempts=attempts,
        final_status="success" if current_eval.accepted else "acceptance_not_met",
    ), usages, current_optimized_prompt
