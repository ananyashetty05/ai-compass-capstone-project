"""
AI Compass - Pydantic Schemas: Query

QueryRequest only requires the query text. The backend loads the user profile from the session token.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=50000, description="The user's original query text (never modified)")
    task_type_hint: Optional[str] = Field(default=None, description="Optional user-selected task category.")
    # user_id is resolved server-side from the session token; clients must not supply it.
    user_id: Optional[str] = Field(default=None, description="Resolved from auth token; ignored if supplied.")

    # Execution mode: recommend (default, runs no model) | execute (runs the selected model through its provider adapter)
    mode: str = Field(default="recommend", pattern="^(recommend|execute)$")

    # Prompt optimizer
    optimization_mode: str = Field(default="standard", pattern="^(disabled|conservative|standard|advanced|custom)$")
    optimization_options: Optional[Dict[str, bool]] = Field(default=None, description="Options for mode 'custom'")
    optimized_prompt: Optional[str] = Field(default=None, max_length=60000, description="User-reviewed/edited optimized prompt; used instead of re-optimizing")
    submit_prompt: str = Field(default="optimized", pattern="^(original|optimized)$")

    # Hard constraints (request level)
    max_cost: Optional[float] = Field(default=None, gt=0, description="USD per request, estimated from published prices and estimated tokens")
    max_latency: Optional[float] = Field(default=None, gt=0, description="Seconds")
    require_capabilities: Optional[List[str]] = Field(default=None, max_length=32)
    privacy_requirement: Optional[str] = Field(default=None, pattern="^(standard|strict)$",
                                               description="strict excludes models without documented data-handling metadata")
    model_ids: Optional[List[str]] = Field(default=None, description="Optional selected model pool")
    preferred_providers: Optional[List[str]] = Field(default=None, max_length=16)
    excluded_providers: Optional[List[str]] = Field(default=None, max_length=16)
    excluded_model_ids: Optional[List[str]] = Field(default=None, max_length=64)

    # Request-level objective weights (does not modify saved preferences)
    weight_overrides: Optional[Dict[str, float]] = None

    # Execution controls
    budget_usd: Optional[float] = Field(default=None, gt=0, description="Maximum total spend for execution/escalation")
    evaluate_response: bool = True
    idempotency_key: Optional[str] = Field(default=None, max_length=128)


class OptimizePromptRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=50000, description="The user's original query")
    task_type_hint: Optional[str] = Field(default=None)
    mode: str = Field(default="standard", pattern="^(disabled|conservative|standard|advanced|custom)$")
    options: Optional[Dict[str, bool]] = None
    model_id: Optional[str] = Field(default=None, description="Adapt the prompt to this registry model when its metadata supports it")


class OptimizePromptResponse(BaseModel):
    # legacy fields
    optimized_prompt: str
    task_type: str
    domain: str
    method: str
    # Optimizer 2.0 fields
    original_prompt: str = ""
    mode: str = "standard"
    applied: bool = False
    changes: List[Dict[str, Any]] = []
    preserved_constraints: List[str] = []
    ambiguities: List[Dict[str, Any]] = []
    warnings: List[str] = []
    intent_preserved: bool = True
    preservation_checks: Dict[str, bool] = {}
    quality_before: Optional[Dict[str, Any]] = None
    quality_after: Optional[Dict[str, Any]] = None
    model_adaptation: List[str] = []
    isolated_untrusted_blocks: int = 0
    needs_clarification: bool = False
    analysis: Dict[str, Any] = {}


class QueryProfile(BaseModel):
    """
    Legacy flat per-query characteristics, kept for the offline evaluation study and older clients.
    It is a projection of the canonical QueryProfileV2 (app.services.routing_engine.types).
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
    analysis_method: str = Field(default="lexical_rule_engine_v2")
    required_modalities: List[str] = Field(default_factory=lambda: ["text"])
    required_capabilities: List[str] = Field(default_factory=list)
    classification_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    uncertainty_notes: List[str] = Field(default_factory=list)
