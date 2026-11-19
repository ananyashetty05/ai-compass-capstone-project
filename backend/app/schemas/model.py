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

    # ── Capability & intended-use taxonomy (see services/model_taxonomy.py) ──
    # Every value is either curated from published provider/developer documentation or left
    # "unknown"/empty. Nothing here is inferred from a provider name alone.
    developer: Optional[str] = Field(default=None, description="Organisation that trained/published the model (not the hosting provider)")
    provider_role: str = Field(default="unknown", description="model_developer | inference_provider | model_aggregator | model_hub | cloud_platform | application")
    model_type: str = Field(default="unclassified", description="chat | reasoning_chat | code_chat | embedding | image_generation | consumer_app | unclassified")
    use_categories: List[str] = Field(default_factory=list, description="Routing audience tags (overlapping): conversational and/or developer; empty = unclassified")
    primary_category: str = Field(default="unclassified", description="ONE mutually exclusive category: conversational | developer | application | unclassified")
    category_kind: str = Field(default="unclassified", description="Sub-type inside the primary category (embedding, code, speech, base_model, chat, ...)")
    classification_basis: str = Field(default="unverified", description="curated | derived | unverified")
    classification_reason: Optional[str] = Field(default=None, description="Why this primary category was assigned")
    capability_tags: List[str] = Field(default_factory=list, description="Overlapping capabilities (chat, coding, vision_input, ...); never summed into totals")
    weights_status: str = Field(default="unknown", description="open_weights | proprietary | unknown (weights availability, not an OSI claim)")
    license_name: Optional[str] = None
    free_download: Optional[bool] = Field(default=None, description="Weights can be downloaded without payment (None = unknown)")
    free_access: str = Field(default="unknown", description="free | limited_free | paid | unknown (hosted inference through the listed provider)")
    free_access_note: Optional[str] = None
    deployment_options: List[str] = Field(default_factory=list, description="hosted_api | local_download | consumer_app")
    api_available: Optional[bool] = None
    embedding_dimensions: Optional[int] = None
    taxonomy_status: str = Field(default="unclassified", description="curated | derived | unclassified")
    # ── Recommendation category / access route / pricing class (derived by services/access_category.py; never guessed) ──
    model_category: str = Field(default="unclassified", description="conversational | developer_api | unclassified")
    access_type: str = Field(default="unknown", description="consumer_chat | provider_api | hosted_inference | aggregator_api | self_hosted | unknown")
    intended_use: List[str] = Field(default_factory=list, description="general_assistant | project_integration | coding | reasoning | embedding | multimodal | agent_development | rag | specialized")
    integration_supported: Optional[bool] = Field(default=None, description="Documented integration route (API or local weights); None = not verified")
    pricing_category: str = Field(default="unknown", description="completely_free | free_tier_limited | pay_as_you_go | paid_subscription | self_hosted_open_weight | unknown")
    free_tier_available: Optional[bool] = Field(default=None, description="True only when a free tier/free access is documented; None = unknown")
    category_basis: Optional[str] = None
    # ── Independent state flags (deliberately not collapsed into one 'available') ──
    comparison_eligible: bool = Field(default=True, description="Can be compared using published metadata; never depends on credentials")
    execution_available: bool = Field(default=False, description="AI Compass can run it right now (adapter + provider credential on the server)")
    user_access_configured: bool = Field(default=False, description="A server credential for the model's provider is configured")

    # Live-registry bookkeeping (all optional; static catalog rows leave them unset)
    canonical_key: Optional[str] = Field(default=None, description="'<provider-lower>:<provider model id>'")
    first_seen_at: Optional[str] = None
    lifecycle_reason: Optional[str] = Field(default=None, description="Why the current lifecycle status was assigned")
    deprecated_at: Optional[str] = Field(default=None, description="Provider-reported deprecation time")
    retires_at: Optional[str] = Field(default=None, description="Provider-reported retirement time")
    consecutive_missing_refreshes: int = Field(default=0, ge=0, description="Successful provider refreshes that did not list this model")
    catalog: Optional[dict] = Field(default=None, description="Autonomous-catalogue lifecycle/provenance block (see services/catalog/registry.py)")


class RegistryEntry(ModelMetadata):
    """Catalog entry as presented by the live registry (additive superset of ModelMetadata)."""
    catalog_origin: str = Field(default="static", description="static | live | application")
    eligibility: Optional[dict] = Field(default=None, description="{eligible, reasons:[{code,message}], warnings:[{code,message}]}")
    verification: Optional[dict] = Field(default=None, description="Latest inference verification: {status, error_code, verified_at}")
    catalog_last_confirmed_at: Optional[str] = Field(default=None, description="Last successful provider refresh time for this provider")
    catalog_stale: bool = False
