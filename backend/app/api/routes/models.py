from fastapi import APIRouter, HTTPException, Query
from app.services.model_registry import (
    get_all_models, get_all_registry_entries, get_model_by_id, get_tool_recommendations,
    discover_openai_models as discover_openai_catalog, discover_openrouter_models as discover_openrouter_catalog,
)

router = APIRouter()


@router.get("/models")
def list_models(routable_only: bool = Query(False, description="Only configured, executable API models")):
    """List the complete catalog, including separate integrations."""
    return get_all_models() if routable_only else get_all_registry_entries()


@router.post("/models/discover/openai")
def discover_openai_models():
    """Return a fresh authenticated OpenAI catalog, when an API key is configured."""
    try:
        return discover_openai_catalog()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OpenAI discovery failed: {exc}") from exc


@router.post("/models/discover/openrouter")
def discover_openrouter_models():
    try:
        return discover_openrouter_catalog()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OpenRouter discovery failed: {exc}") from exc


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
