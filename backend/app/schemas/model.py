"""
AI Compass - Pydantic Schemas: Model
"""
from typing import List, Optional
from pydantic import BaseModel, Field


class ModelMetadata(BaseModel):
    """
    Registry entry for a candidate model or specialized AI tool.
    Routing metadata is configured from provider documentation and measured data.
    """
    model_id: str
    model_name: str
    provider: str
    capabilities: List[str] = []
    supported_domains: List[str] = []
    supported_tasks: List[str] = []

    estimated_quality: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Configured or benchmark-derived quality metadata; null when unavailable",
    )
    estimated_cost: float = Field(ge=0.0, le=1.0, description="Normalized configured cost metadata")
    estimated_latency: float = Field(ge=0.0, le=1.0, description="Normalized configured latency metadata")
    reliability: float = Field(ge=0.0, le=1.0, description="Configured reliability metadata")
    risk_level: float = Field(ge=0.0, le=1.0, description="Configured risk metadata")

    context_window: int = Field(default=4096)
    cost_per_1k_tokens: float = Field(default=0.001, description="USD per 1k tokens")
    avg_latency_seconds: float = Field(default=2.0, description="Observed/configured latency metadata")
    fallback_priority: int = Field(default=5, description="Lower = preferred fallback")
    active: bool = True
    source: str = Field(default="provider_config", description="provider_config | routerbench | measured")

    # Extended capability classification
    modality: str = Field(default="text", description="text | image | audio | video | multimodal | presentation | code")
    entry_type: str = Field(
        default="inference_model",
        description="inference_model | application_integration | specialized_ai_tool",
    )
    requires_key: bool = Field(default=True, description="Whether a provider API key is required")
    external_url: Optional[str] = Field(default=None, description="Provider/tool URL for direct access")
    description: Optional[str] = Field(default=None, description="Human-readable capability description")
    model_family: Optional[str] = None
    modalities: List[str] = []
    availability: str = Field(default="unknown", description="available | configured | unavailable | unknown")
    provider_source: Optional[str] = None
    authentication_requirement: str = Field(default="api_key")
    data_provenance: str = Field(default="static_verified_catalog")
    last_verified_at: Optional[str] = None
    input_price_per_million: Optional[float] = None
    output_price_per_million: Optional[float] = None
