"""Pydantic schemas for the feedback and learning subsystem."""
from typing import Optional, List
from pydantic import BaseModel, Field


class FeedbackSubmission(BaseModel):
    routing_id: str = Field(description="Opaque ID returned by the routing endpoint")
    model_id: str
    model_name: str
    query_summary: str = Field(max_length=300)
    task_type: str = Field(default="general")
    domain: str = Field(default="general")
    rating: int = Field(ge=1, le=5, description="1–5 star rating")
    thumbs: Optional[str] = Field(default=None, description="'up' | 'down' | null")
    reasons: List[str] = Field(default_factory=list, description="Selected reason tags")
    comment: Optional[str] = Field(default=None, max_length=1000)


class FeedbackRecord(FeedbackSubmission):
    feedback_id: str
    user_id: str
    created_at: str


class ModelSatisfaction(BaseModel):
    """Per-user, per-model learned satisfaction estimate."""
    model_id: str
    model_name: str
    mean_rating: float
    sample_count: int
    confidence: float = Field(description="0–1; higher = more reliable estimate")
    last_updated: str


class LearningState(BaseModel):
    """Summary of what the system has learned for a user."""
    total_feedback: int
    models_rated: int
    satisfaction_estimates: List[ModelSatisfaction]
    learning_active: bool
    cold_start: bool
