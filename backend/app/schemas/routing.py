"""
AI Compass - Pydantic Schemas: Routing
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class ModelScore(BaseModel):
    model_id: str
    quality_score: Optional[float] = None
    cost_score: float
    latency_score: float
    reliability_score: float
    risk_score: float
    preference_alignment: float
    overall_score: float
    score_breakdown: Dict[str, Optional[float]] = {}


class RoutingDecision(BaseModel):
    selected_model_id: str
    fallback_model_id: Optional[str] = None
    candidate_models: List[str] = []
    filtered_out_models: List[Dict[str, str]] = []
    model_scores: List[ModelScore] = []
    routing_reason: List[str] = []
    applied_weights: Dict[str, float] = {}
    applied_constraints: Dict[str, Any] = {}
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    routing_latency_ms: float = 0.0
    learning_active: bool = False
