"""
AI Compass - Pydantic Schemas: Model
"""
from typing import Dict, List, Optional
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
    estimated_cost: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Normalized configured cost metadata; null when unavailable")
    estimated_latency: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Normalized configured latency metadata; null when unavailable")
    reliability: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Configured reliability metadata; null when unavailable")
    risk_level: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Configured risk metadata; null when unavailable")

    context_window: int = Field(default=4096)
    cost_per_1k_tokens: Optional[float] = Field(default=None, ge=0.0, description="USD per 1k tokens; null when unavailable")
    avg_latency_seconds: Optional[float] = Field(default=None, ge=0.0, description="Observed/configured latency metadata; null when unavailable")
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
    metric_provenance: Dict[str, str] = Field(default_factory=dict)
    metadata_status: str = Field(default="estimated", description="verified | estimated | incomplete | stale")
    lifecycle_status: str = Field(
        default="active",
        description="active | newly_discovered | deprecated | unavailable | retired | discovery_failed | incompatible",
    )
    adapter_compatible: bool = Field(default=False)
    inference_access_status: str = Field(default="unverified", description="unverified | validated | unavailable | not_applicable")
    routing_eligible: bool = Field(default=False, description="Whether this entry may enter the routing candidate pool")
    privacy_notes: Optional[str] = None
    data_handling_status: str = Field(
        default="unknown",
        description="unknown | provider_documented_restricted | customer_controlled",
    )
    last_verified_at: Optional[str] = None
    input_price_per_million: Optional[float] = None
    output_price_per_million: Optional[float] = None

    # Live-registry bookkeeping (all optional; static catalog rows leave them unset)
    canonical_key: Optional[str] = Field(default=None, description="'<provider-lower>:<provider model id>'")
    first_seen_at: Optional[str] = None
    lifecycle_reason: Optional[str] = Field(default=None, description="Why the current lifecycle status was assigned")
    deprecated_at: Optional[str] = Field(default=None, description="Provider-reported deprecation time")
    retires_at: Optional[str] = Field(default=None, description="Provider-reported retirement time")
    consecutive_missing_refreshes: int = Field(default=0, ge=0, description="Successful provider refreshes that did not list this model")


class RegistryEntry(ModelMetadata):
    """Catalog entry as presented by the live registry (additive superset of ModelMetadata)."""
    catalog_origin: str = Field(default="static", description="static | live | application")
    eligibility: Optional[dict] = Field(default=None, description="{eligible, reasons:[{code,message}], warnings:[{code,message}]}")
    verification: Optional[dict] = Field(default=None, description="Latest inference verification: {status, error_code, verified_at}")
    catalog_last_confirmed_at: Optional[str] = Field(default=None, description="Last successful provider refresh time for this provider")
    catalog_stale: bool = False
