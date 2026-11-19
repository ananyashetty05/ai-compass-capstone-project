"""Execution access for a recommended model, kept strictly separate from its suitability."""
from typing import Any, Dict

from app.schemas.model import ModelMetadata


def describe(model: ModelMetadata) -> Dict[str, Any]:
    from app.services.registry_eligibility import provider_configured, provider_disabled
    if model.entry_type != "inference_model":
        return {"model_id": model.model_id, "execution_available": False, "credential_configured": None, "status": "open_at_destination",
                "next_step": f"Open {model.model_name} directly at {model.external_url or 'its website'}; AI Compass does not run consumer applications."}
    configured = provider_configured(model.provider)
    if model.source == "live_discovered" and model.inference_access_status != "validated":
        # A discovered model is never executed on the strength of a provider listing alone.
        status, step = "inference_not_verified", f"{model.model_name} was discovered but its inference access has not been verified, so AI Compass will not run it."
    elif provider_disabled(model.provider):
        status, step = "provider_disabled", f"{model.provider} is disabled by this deployment's configuration."
    elif not model.adapter_compatible:
        status, step = "no_adapter", f"AI Compass has no inference adapter for {model.provider}. Use the provider's own API or an available alternative."
    elif not configured:
        status, step = "credential_not_configured", f"Connect {model.provider} (server credential) to run it from AI Compass, or use the provider's own access route; the recommendation itself is unaffected."
    else:
        status, step = "ready", "Ready to run from AI Compass."
    return {"model_id": model.model_id, "execution_available": status == "ready", "credential_configured": configured, "status": status, "next_step": step,
            "documentation_url": model.external_url}
