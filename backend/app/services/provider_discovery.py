"""Official-API model discovery for the live registry.

Each provider function returns ``DiscoveryResult``: validated, normalised
``ModelMetadata`` entries plus a count of rejected rows. Only fields the provider
actually reports are filled in; quality, latency, reliability and risk stay
``None`` (never a placeholder). Failures raise ``DiscoveryError`` with a safe,
classified message that never contains credentials or upstream bodies.

Endpoints (verified against official documentation, November 2026):
  OpenAI     GET https://api.openai.com/v1/models            (Bearer, unpaginated)
  OpenRouter GET https://openrouter.ai/api/v1/models         (Bearer, unpaginated)
  Groq       GET https://api.groq.com/openai/v1/models       (Bearer, unpaginated)
  Anthropic  Models.list via the official SDK                (cursor pagination handled by the SDK)
  Google     models.list via the official google-genai SDK   (pageToken handled by the SDK)
"""
from __future__ import annotations

import json
import re
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import settings
from app.schemas.model import ModelMetadata
from app.services import model_registry

MAX_MODELS_PER_PROVIDER = 5000
MAX_RESPONSE_BYTES = 20 * 1024 * 1024
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,199}$")

# Provider display names match the static catalog so canonical keys line up.
PROVIDERS = {"openai": "OpenAI", "anthropic": "Anthropic", "google": "Google", "groq": "Groq", "openrouter": "OpenRouter"}


class DiscoveryError(Exception):
    """kind: not_configured | authentication | rate_limited | timeout | network | malformed_response | upstream"""
    def __init__(self, kind: str, message: str | None = None):
        super().__init__(message or kind)
        self.kind = kind
        self.safe_message = message or {
            "not_configured": "Provider credentials are not configured.",
            "authentication": "Provider rejected the configured credentials.",
            "rate_limited": "Provider rate limit reached.",
            "timeout": "Provider request timed out.",
            "network": "Provider network connection failed.",
            "malformed_response": "Provider returned a response that could not be validated.",
        }.get(kind, "Provider model list is temporarily unavailable.")


@dataclass
class DiscoveryResult:
    provider: str
    entries: List[ModelMetadata] = field(default_factory=list)
    rejected: int = 0


def canonical_key(provider: str, model_id: str) -> str:
    return f"{provider.strip().lower()}:{model_id}"


def classify_exception(exc: Exception) -> DiscoveryError:
    if isinstance(exc, DiscoveryError):
        return exc
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if isinstance(exc, HTTPError):
        status = exc.code
    name = type(exc).__name__.lower()
    if status == 429 or "ratelimit" in name:
        return DiscoveryError("rate_limited")
    if status in (401, 403) or "authentication" in name or "permission" in name:
        return DiscoveryError("authentication")
    if isinstance(exc, (socket.timeout, TimeoutError)) or "timeout" in name:
        return DiscoveryError("timeout")
    if isinstance(exc, URLError) or "connection" in name or "network" in name:
        return DiscoveryError("network")
    if isinstance(exc, (ValueError, KeyError, TypeError, json.JSONDecodeError)):
        return DiscoveryError("malformed_response")
    return DiscoveryError("upstream")


def _get_json(url: str, headers: dict[str, str], timeout: float | None = None) -> Any:
    """Fixed-HTTPS GET with a hard size cap. Patched in tests."""
    if not url.startswith("https://"):
        raise DiscoveryError("upstream")
    req = Request(url, headers={**headers, "Accept": "application/json"})
    with urlopen(req, timeout=timeout or settings.PROVIDER_TIMEOUT_SECONDS) as resp:  # nosec B310: fixed HTTPS provider endpoint
        raw = resp.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise DiscoveryError("malformed_response")
    return json.loads(raw)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _price(value: Any) -> float | None:
    """Provider price per token -> USD per million tokens; negative/invalid -> unknown."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number * 1_000_000 if number >= 0 else None


def _positive_int(value: Any, default: int = 0) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _entry(provider_key: str, model_id: Any, *, source: str, now: str, **kw: Any) -> ModelMetadata | None:
    if not isinstance(model_id, str) or not _ID_PATTERN.match(model_id):
        return None
    provider = PROVIDERS[provider_key]
    entry = model_registry._discovered_model(model_id, provider, source=source, now=now, **{
        k: kw[k] for k in ("context", "input_price", "output_price", "description") if k in kw})
    name = kw.get("name")
    update: dict[str, Any] = {
        "canonical_key": canonical_key(provider, model_id), "first_seen_at": now,
        "model_name": name.strip()[:200] if isinstance(name, str) and name.strip() else model_id,
        "deprecated_at": kw.get("deprecated_at"), "retires_at": kw.get("retires_at"),
    }
    if kw.get("modalities"):
        update["modalities"] = kw["modalities"]
        update["modality"] = kw["modalities"][0]
    if kw.get("output_price") is not None:
        update["output_price_per_million"] = kw["output_price"]
    if kw.get("provider_lifecycle") in {"deprecated", "retired"}:
        update["lifecycle_status"] = kw["provider_lifecycle"]
        update["lifecycle_reason"] = f"Provider-reported lifecycle: {kw['provider_lifecycle']}"
        update["metric_provenance"] = {**entry.metric_provenance, "lifecycle": "provider_published"}
    return entry.model_copy(update=update)


def _finish(provider_key: str, rows: list, build: Callable[[Any], ModelMetadata | None]) -> DiscoveryResult:
    if not isinstance(rows, list) or len(rows) > MAX_MODELS_PER_PROVIDER:
        raise DiscoveryError("malformed_response")
    result, seen = DiscoveryResult(PROVIDERS[provider_key]), set()
    for row in rows:
        try:
            item = build(row)
        except Exception:
            item = None
        if item is None or item.model_id in seen:
            result.rejected += 1
            continue
        seen.add(item.model_id)
        result.entries.append(item)
    if rows and not result.entries:
        raise DiscoveryError("malformed_response")  # nothing usable: do not treat as an authoritative empty list
    return result


def _require(key: str) -> str:
    if not key:
        raise DiscoveryError("not_configured")
    return key


def discover_openai() -> DiscoveryResult:
    key = _require(settings.OPENAI_API_KEY)
    payload = _get_json("https://api.openai.com/v1/models", {"Authorization": f"Bearer {key}"})
    now = _now()
    return _finish("openai", (payload or {}).get("data"), lambda r: _entry(
        "openai", r.get("id"), source="https://api.openai.com/v1/models", now=now))


def discover_openrouter() -> DiscoveryResult:
    key = _require(settings.OPENROUTER_API_KEY)
    payload = _get_json("https://openrouter.ai/api/v1/models", {"Authorization": f"Bearer {key}"})
    now = _now()

    def build(r: dict) -> ModelMetadata | None:
        pricing = r.get("pricing") or {}
        arch = r.get("architecture") or {}
        mods = [m for m in (arch.get("input_modalities") or []) if isinstance(m, str)] or None
        return _entry("openrouter", r.get("id"), source="https://openrouter.ai/api/v1/models", now=now,
                      name=r.get("name"), context=_positive_int(r.get("context_length")),
                      input_price=_price(pricing.get("prompt")), output_price=_price(pricing.get("completion")),
                      description=r.get("description") if isinstance(r.get("description"), str) else None,
                      modalities=mods)
    return _finish("openrouter", (payload or {}).get("data"), build)


def discover_groq() -> DiscoveryResult:
    key = _require(settings.GROQ_API_KEY)
    payload = _get_json("https://api.groq.com/openai/v1/models", {"Authorization": f"Bearer {key}"})
    now = _now()

    def build(r: dict) -> ModelMetadata | None:
        # Groq's `active` flag is not documented as a lifecycle signal, so it is not interpreted.
        return _entry("groq", r.get("id"), source="https://api.groq.com/openai/v1/models", now=now,
                      context=_positive_int(r.get("context_window")))
    return _finish("groq", (payload or {}).get("data"), build)


def _anthropic_list_raw() -> list[dict]:
    """All models via the official SDK (it follows cursor pagination)."""
    import anthropic
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=settings.PROVIDER_TIMEOUT_SECONDS, max_retries=0)
    rows = []
    for model in client.models.list(limit=100):
        rows.append(model.model_dump() if hasattr(model, "model_dump") else dict(model))
        if len(rows) > MAX_MODELS_PER_PROVIDER:
            break
    return rows


def discover_anthropic() -> DiscoveryResult:
    _require(settings.ANTHROPIC_API_KEY)
    try:
        rows = _anthropic_list_raw()
    except Exception as exc:
        raise classify_exception(exc) from exc
    now = _now()

    def build(r: dict) -> ModelMetadata | None:
        lifecycle = r.get("lifecycle") if r.get("lifecycle") in {"active", "deprecated", "retired"} else None
        return _entry("anthropic", r.get("id"), source="https://api.anthropic.com/v1/models", now=now,
                      name=r.get("display_name"), context=_positive_int(r.get("max_input_tokens")),
                      deprecated_at=r.get("deprecated_at"), retires_at=r.get("retires_at"),
                      provider_lifecycle=lifecycle if lifecycle != "active" else None)
    return _finish("anthropic", rows, build)


def _gemini_list_raw() -> list[dict]:
    from google import genai
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    rows = []
    for model in client.models.list(config={"page_size": 100}):
        rows.append({
            "name": getattr(model, "name", None), "display_name": getattr(model, "display_name", None),
            "description": getattr(model, "description", None),
            "input_token_limit": getattr(model, "input_token_limit", None),
            "supported_actions": list(getattr(model, "supported_actions", None) or []),
        })
        if len(rows) > MAX_MODELS_PER_PROVIDER:
            break
    return rows


def discover_google() -> DiscoveryResult:
    _require(settings.GEMINI_API_KEY)
    try:
        rows = _gemini_list_raw()
    except Exception as exc:
        raise classify_exception(exc) from exc
    now = _now()

    def build(r: dict) -> ModelMetadata | None:
        name = r.get("name")
        model_id = name.split("/", 1)[1] if isinstance(name, str) and name.startswith("models/") else name
        return _entry("google", model_id, source="https://generativelanguage.googleapis.com/v1beta/models", now=now,
                      name=r.get("display_name"), context=_positive_int(r.get("input_token_limit")),
                      description=r.get("description") if isinstance(r.get("description"), str) else None)
    return _finish("google", rows, build)


DISCOVERERS: dict[str, Callable[[], DiscoveryResult]] = {
    "openai": discover_openai, "openrouter": discover_openrouter, "groq": discover_groq,
    "anthropic": discover_anthropic, "google": discover_google,
}


def discover(provider_key: str) -> DiscoveryResult:
    try:
        fn = DISCOVERERS[provider_key.lower()]
    except KeyError:
        raise DiscoveryError("not_configured", "Unknown provider.") from None
    try:
        return fn()
    except DiscoveryError:
        raise
    except Exception as exc:
        raise classify_exception(exc) from exc
