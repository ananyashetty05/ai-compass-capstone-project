"""
AI Compass - Pydantic Schemas: Response & Evaluation
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ResponseEvaluation(BaseModel):
    """Deterministic evaluation calculated from the generated response."""
    quality_score: float = Field(ge=0.0, le=1.0)
    relevance_score: float = Field(ge=0.0, le=1.0)
    completeness_score: float = Field(ge=0.0, le=1.0)
    risk_score: float = Field(ge=0.0, le=1.0, description="Higher = more risky")
    accepted: bool
    evaluation_reasons: List[str] = []
    evaluation_method: str = "deterministic_response_evaluation"


class EscalationInfo(BaseModel):
    escalated: bool = False
    escalation_trigger: Optional[str] = None
    original_model_id: Optional[str] = None
    fallback_model_id: Optional[str] = None
    escalation_reason: Optional[str] = None
    attempts: int = 1
    final_status: str = "success"


class RouteAndGenerateResponse(BaseModel):
    routing_system: Dict[str, str]
    routing_id: str = ""
    query: str
    profile: str
    query_analysis: Dict[str, Any]
    candidate_models: List[str]
    filtered_models: List[Dict[str, str]]
    model_scores: List[Dict[str, Any]]
    selected_model_id: str
    selected_model_name: str
    routing_explanation: Dict[str, Any]
    generated_response: str
    response_evaluation: Dict[str, Any]
    escalation_info: Dict[str, Any]
    final_model_id: str
    final_model_name: str
    performance_metrics: Dict[str, Any]
    request_usage: List[Dict[str, Any]] = []
    optimized_prompt: Optional[str] = None
    learning_active: bool = False
    # Ranked alternatives (top N models that were not selected)
    ranked_alternatives: List[Dict[str, Any]] = []
    # Tool recommendations for specialized tasks
    tool_recommendations: List[Dict[str, Any]] = []
    recommended_destination: Dict[str, Any] = {}
