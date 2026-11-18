"""Controlled inference verification.

Catalog visibility does not prove a credential can run a model. This module makes
one tiny, explicit provider call for ONE model, on admin request only, through the
existing adapter. It is never called from routing, never loops over a catalog, and
records only a classified outcome (no prompt/response text, no upstream error body).
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.schemas.model import ModelMetadata
from app.services import registry_eligibility as eligibility
from app.services import model_registry_store as store

_PROBE = "Reply with the single word: ok"


class VerificationRefused(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _precheck(model: ModelMetadata) -> None:
    if model.entry_type != "inference_model":
        raise VerificationRefused("not_inference_model", "Only API inference models can be verified.")
    if eligibility.provider_disabled(model.provider):
        raise VerificationRefused("provider_disabled", "The provider is disabled by configuration.")
    if not eligibility.provider_configured(model.provider):
        raise VerificationRefused("provider_not_configured", "No credentials are configured for this provider.")
    if not model.adapter_compatible:
        raise VerificationRefused("adapter_incompatible", "No inference adapter supports this provider.")
    modalities = set(model.modalities or [model.modality])
    if "text" not in modalities or any(c in model.capabilities for c in ("image-generation", "image-editing")):
        raise VerificationRefused("unsupported_modality", "Automated verification supports text-generation models only.")


def verify(model: ModelMetadata) -> dict:
    """Run one verification. Returns {status, error_code, latency_ms}."""
    from app.services.model_adapters.factory import get_adapter
    from app.services.model_adapters.provider_adapters import ProviderUnavailableError

    _precheck(model)
    last = store.last_verification_at(model.provider, model.model_id)
    if last and datetime.now(timezone.utc) - last < timedelta(seconds=settings.REGISTRY_VERIFICATION_COOLDOWN_SECONDS):
        raise VerificationRefused("cooldown", "This model was verified recently; try again later.")
    started = time.monotonic()
    status, code = "validated", None
    try:
        adapter = get_adapter(model)
        adapter.generate(_PROBE, max_tokens=16)
    except ProviderUnavailableError as exc:
        status, code = "failed", exc.kind
    except Exception:
        status, code = "failed", "upstream"
    latency_ms = int((time.monotonic() - started) * 1000)
    store.record_verification(model.provider, model.model_id, status, code, latency_ms)
    return {"provider": model.provider, "model_id": model.model_id, "status": status, "error_code": code, "latency_ms": latency_ms}
