"""
AI Compass - Pydantic Schemas: Query

QueryRequest now only requires the query text.
The backend loads the user profile automatically from the session/store.
"""
from typing import Optional
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="The user's query text")
    task_type_hint: Optional[str] = Field(
        default=None,
        description="Optional user-selected task category. The analyzer remains the default when omitted.",
    )
    # user_id is resolved server-side from the session token.
    # Clients should NOT send profile/preferences per-query.
    user_id: Optional[str] = Field(
        default=None,
        description="Resolved from auth token; clients must not supply a profile per request."
    )
    # Hard constraints (optional, query-level overrides only)
    max_cost: Optional[float] = Field(default=None)
    max_latency: Optional[float] = Field(default=None)
    require_capabilities: Optional[list] = Field(default=None)
    model_ids: Optional[list[str]] = Field(
        default=None,
        description="Optional selected model pool. When omitted, all eligible catalog models are considered.",
    )


class OptimizePromptRequest(BaseModel):
    query: str = Field(..., min_length=1, description="The user's original query")
    task_type_hint: Optional[str] = Field(default=None)


class OptimizePromptResponse(BaseModel):
    optimized_prompt: str
    task_type: str
    domain: str
    method: str


class QueryProfile(BaseModel):
    """
    Per-query characteristics extracted by the query analyzer.
    Values are calculated by the configured deterministic analyzer. The analyzer
    can be replaced with a trained classifier without changing this contract.
    """
    task_type: str
    domain: str
    complexity: float = Field(ge=0.0, le=1.0)
    context_requirement: float = Field(ge=0.0, le=1.0)
    quality_requirement: float = Field(ge=0.0, le=1.0)
    risk_level: float = Field(ge=0.0, le=1.0)
    latency_requirement: float = Field(ge=0.0, le=1.0)
    cost_sensitivity: float = Field(ge=0.0, le=1.0)
    reliability_requirement: float = Field(ge=0.0, le=1.0)
    estimated_tokens: int = Field(default=256)
    analysis_method: str = Field(default="keyword_rule_analyzer")
    required_modalities: list[str] = Field(default_factory=lambda: ["text"])
    required_capabilities: list[str] = Field(default_factory=list)
