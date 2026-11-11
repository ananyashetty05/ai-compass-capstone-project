"""Schemas for offline, registry-metadata routing evaluation."""
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.query import QueryProfile


class OfflineEvaluationRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Query used to compare routing decisions")
    task_type_hint: Optional[str] = None
    max_cost: Optional[float] = Field(default=None, gt=0)
    max_latency: Optional[float] = Field(default=None, gt=0)
    require_capabilities: Optional[list[str]] = None
    model_ids: Optional[list[str]] = None


class OfflineStrategyResult(BaseModel):
    strategy: str
    status: str
    selected_model_id: Optional[str] = None
    selected_model: Optional[str] = None
    provider: Optional[str] = None
    selection_rationale: str
    routing_score: Optional[float] = None
    quality_score: Optional[float] = None
    quality_source: Optional[str] = None
    estimated_cost_usd: Optional[float] = None
    cost_basis: Optional[str] = None
    input_price_per_million: Optional[float] = None
    latency_seconds: Optional[float] = None
    reliability_score: Optional[float] = None
    risk_score: Optional[float] = None
    capabilities: list[str] = Field(default_factory=list)
    context_window: Optional[int] = None
    availability: Optional[str] = None
    constraint_satisfied: bool
    missing_data: list[str] = Field(default_factory=list)
    data_sources: dict[str, Optional[str]] = Field(default_factory=dict)


class OfflineEvaluationResponse(BaseModel):
    evaluation_method: str = "offline_registry_metadata"
    data_disclosure: str
    query_analysis: QueryProfile
    candidate_count: int
    filtered_models: list[dict[str, str]]
    strategy_results: list[OfflineStrategyResult]
