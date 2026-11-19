import hmac
import time
from collections import defaultdict, deque
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import get_logger
from app.services.model_registry import (
    get_all_models, get_all_registry_entries, get_model_by_id, get_tool_recommendations,
    discover_openai_models as discover_openai_catalog, discover_openrouter_models as discover_openrouter_catalog,
)
from app.services import inference_verification, provider_discovery, registry_eligibility, registry_service
from app.services import model_registry_store as store
from app.services.model_registry_store import RegistryPersistenceUnavailable

router = APIRouter()
logger = get_logger(__name__)

# ── admin authorisation + rate limiting for operations that spend provider quota ──
_RATE_LIMIT, _RATE_WINDOW = 20, 60.0
_calls: dict[str, deque] = defaultdict(deque)  # per-instance; serverless deployments get per-instance limits only


def require_registry_admin(x_registry_admin_token: Optional[str] = Header(default=None)) -> str:
    expected = settings.REGISTRY_ADMIN_TOKEN
    if not expected:
        raise HTTPException(503, "Registry administration is not configured on this deployment.")
    if not x_registry_admin_token or not hmac.compare_digest(x_registry_admin_token.encode(), expected.encode()):
        raise HTTPException(403, "Registry administrator token required.")
    window = _calls["admin"]
    now = time.monotonic()
    while window and now - window[0] > _RATE_WINDOW:
        window.popleft()
    if len(window) >= _RATE_LIMIT:
        raise HTTPException(429, "Too many registry operations; wait a minute.")
    window.append(now)
    return "admin"


def _persistence_required():
    if not store.is_enabled():
        raise HTTPException(503, "Live registry persistence is not enabled on this deployment.")


# ── read endpoints ────────────────────────────────────────────────────────────

@router.get("/models")
def list_models(routable_only: bool = Query(False, description="Only configured, executable API models"),
                include_live: bool = Query(False, description="Also include live-discovered entries (use /models/catalog to page them)")):
    """List the static catalog (API models + integrations); live-discovered entries are opt-in."""
    if routable_only:
        return get_all_models()
    return registry_service.build_registry(include_live=include_live)


@router.get("/models/pool-stats")
def pool_stats():
    """Model Pool statistics from the same dataset `/models` lists. Primary categories are exclusive and reconcile with the total."""
    from app.services import pool_stats as ps
    from app.services.catalog import registry as catalog_registry
    totals = (catalog_registry.summary() or {}).get("totals", {})
    return ps.compute(registry_service.build_registry(include_live=False), totals)


_SORTS = {
    "name": lambda e: (e.model_name or "").lower(),
    "provider": lambda e: (e.provider.lower(), (e.model_name or "").lower()),
    "context": lambda e: -(e.context_window or 0),
    "lifecycle": lambda e: (e.lifecycle_status, (e.model_name or "").lower()),
    "eligibility": lambda e: (not bool(e.eligibility and e.eligibility["eligible"]), (e.model_name or "").lower()),
}


@router.get("/models/catalog")
def catalog(search: str = Query("", max_length=100), provider: Optional[str] = None, origin: Optional[str] = None,
            lifecycle: Optional[str] = None, eligible: Optional[bool] = None,
            sort: str = Query("provider"), page: int = Query(1, ge=1), page_size: int = Query(24, ge=1, le=100)):
    """Searchable, filterable, paged live catalogue with provenance, lifecycle and eligibility."""
    if sort not in _SORTS:
        raise HTTPException(422, f"sort must be one of: {', '.join(_SORTS)}")
    entries = registry_service.build_registry(include_live=True)
    summary = {
        "total": len(entries),
        "by_origin": {k: sum(1 for e in entries if e.catalog_origin == k) for k in ("static", "live", "application")},
        "routing_eligible": sum(1 for e in entries if e.eligibility and e.eligibility["eligible"]),
        "by_lifecycle": {},
    }
    for e in entries:
        summary["by_lifecycle"][e.lifecycle_status] = summary["by_lifecycle"].get(e.lifecycle_status, 0) + 1
    providers = sorted({e.provider for e in entries})
    needle = search.strip().lower()
    if needle:
        entries = [e for e in entries if needle in e.model_id.lower() or needle in (e.model_name or "").lower()
                   or needle in e.provider.lower() or needle in (e.model_family or "").lower()]
    if provider:
        entries = [e for e in entries if e.provider.lower() == provider.lower()]
    if origin:
        entries = [e for e in entries if e.catalog_origin == origin]
    if lifecycle:
        entries = [e for e in entries if e.lifecycle_status == lifecycle]
    if eligible is not None:
        entries = [e for e in entries if bool(e.eligibility and e.eligibility["eligible"]) == eligible]
    entries.sort(key=_SORTS[sort])
    start = (page - 1) * page_size
    return {"items": entries[start:start + page_size], "total": len(entries), "page": page, "page_size": page_size,
            "summary": summary, "providers": providers, "persistence_available": store.is_enabled()}


@router.get("/models/registry-status")
def registry_status():
    """Safe read-side status; contains no credentials and no upstream error text."""
    return {
        "live_registry_enabled": store.is_enabled(),
        "persistence_available": registry_service.live_state(use_cache=False).available,
        "admin_configured": bool(settings.REGISTRY_ADMIN_TOKEN),
        "refresh_ttl_minutes": settings.REGISTRY_REFRESH_TTL_MINUTES,
        "providers": registry_service.provider_status(),
    }


@router.get("/models/refresh-history")
def refresh_history(provider: Optional[str] = None, limit: int = Query(50, ge=1, le=200)):
    try:
        return store.get_refresh_history(provider, limit)
    except RegistryPersistenceUnavailable:
        return []


@router.get("/models/activity")
def registry_activity(limit: int = Query(50, ge=1, le=200)):
    try:
        return store.get_activity(limit)
    except RegistryPersistenceUnavailable:
        return []


@router.get("/models/eligibility")
def routing_eligibility(provider: Optional[str] = None):
    """Which API models may enter the routing pool, and why each excluded one does not."""
    rows = [e for e in registry_service.build_registry(include_live=True) if e.entry_type == "inference_model"]
    if provider:
        rows = [e for e in rows if e.provider.lower() == provider.lower()]
    compact = [{"provider": e.provider, "model_id": e.model_id, "model_name": e.model_name, "origin": e.catalog_origin,
                "eligible": e.eligibility["eligible"], "reasons": e.eligibility["reasons"], "warnings": e.eligibility["warnings"]}
               for e in rows]
    return {"eligible": [r for r in compact if r["eligible"]], "excluded": [r for r in compact if not r["eligible"]]}


@router.get("/models/detail")
def model_detail(provider: str, model_id: str, history_limit: int = Query(25, ge=1, le=100)):
    entry = next((e for e in registry_service.build_registry(include_live=True, include_retired=True)
                  if e.provider.lower() == provider.lower() and e.model_id == model_id), None)
    if not entry:
        raise HTTPException(404, "Model not found in the registry.")
    try:
        history = store.get_lifecycle_history(provider, model_id, history_limit)
    except Exception:
        history = []
    return {"entry": entry, "lifecycle_history": history}


@router.get("/models/{provider}/{model_id:path}/lifecycle-history")
def lifecycle_history(provider: str, model_id: str, limit: int = Query(50, ge=1, le=200)):
    try:
        return store.get_lifecycle_history(provider, model_id, limit)
    except RegistryPersistenceUnavailable:
        return []


# ── administrative operations (token + rate limited) ──────────────────────────

class RefreshRequest(BaseModel):
    provider: Optional[str] = Field(default=None, description="One provider key; omit to refresh every configured provider")
    only_if_stale: bool = False


@router.post("/models/registry/refresh")
def refresh_registry(body: RefreshRequest, _: str = Depends(require_registry_admin)):
    _persistence_required()
    keys = [body.provider.lower()] if body.provider else [
        k for k, name in provider_discovery.PROVIDERS.items()
        if registry_eligibility.provider_configured(name) and not registry_eligibility.provider_disabled(name)]
    unknown = [k for k in keys if k not in provider_discovery.PROVIDERS]
    if unknown:
        raise HTTPException(422, f"Unknown provider: {unknown[0][:40]}")
    results = []
    for key in keys:
        display = provider_discovery.PROVIDERS[key]
        if not registry_eligibility.provider_configured(display):
            results.append({"provider": key, "status": "not_configured"})
            continue
        results.append(store.refresh_provider(key, lambda k=key: provider_discovery.discover(k), trigger="manual",
                                              only_if_stale=body.only_if_stale))
    registry_service.invalidate_cache()
    return {"results": results}


class VerifyRequest(BaseModel):
    provider: str
    model_id: str


@router.post("/models/registry/verify")
def verify_inference(body: VerifyRequest, _: str = Depends(require_registry_admin)):
    """Verify inference access for ONE model (makes one tiny provider call)."""
    _persistence_required()
    model = next((e for e in registry_service.build_registry(include_live=True)
                  if e.provider.lower() == body.provider.lower() and e.model_id == body.model_id), None)
    if not model:
        raise HTTPException(404, "Model not found in the registry.")
    try:
        result = inference_verification.verify(model)
    except inference_verification.VerificationRefused as exc:
        raise HTTPException(409 if exc.code == "cooldown" else 422, {"code": exc.code, "message": exc.message}) from exc
    registry_service.invalidate_cache()
    return result


@router.post("/models/discover/openai", dependencies=[Depends(require_registry_admin)])
def discover_openai_models():
    """Legacy preview: fetch OpenAI's catalog without persisting it."""
    try:
        return discover_openai_catalog()
    except Exception as exc:
        raise HTTPException(status_code=502, detail="OpenAI discovery is temporarily unavailable.") from exc


@router.post("/models/discover/openrouter", dependencies=[Depends(require_registry_admin)])
def discover_openrouter_models():
    try:
        return discover_openrouter_catalog()
    except Exception as exc:
        raise HTTPException(status_code=502, detail="OpenRouter discovery is temporarily unavailable.") from exc


@router.get("/models/tools")
def list_tools(task_type: str = Query("", description="Filter by task type")):
    """List specialized tool integrations, optionally filtered by task type."""
    return get_tool_recommendations(task_type) if task_type else [
        m for m in get_all_registry_entries() if m.entry_type in ("application_integration", "specialized_ai_tool")
    ]


@router.get("/models/{model_id:path}")
def get_model(model_id: str):
    m = get_model_by_id(model_id)
    if not m:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")
    return m
