"""
AI Compass - Persistent User Profile Schema

Separates three distinct concepts:
  1. user_group   — fixed classification set during onboarding (e.g. "student")
  2. routing_preferences — saved priority weights, editable from Profile page
  3. QueryProfile — extracted per-query characteristics (separate module)

Default routing_preferences are REPRESENTATIVE CONFIGURATION VALUES for the prototype.
They are NOT scientifically derived. They are clearly documented as defaults.
"""
from typing import Dict, Optional
from pydantic import BaseModel, Field

# Representative default preferences per user group.
# These are prototype configuration defaults — not scientifically validated values.
GROUP_DEFAULT_PREFERENCES: Dict[str, Dict[str, float]] = {
    "student": {
        "quality": 0.70,
        "cost": 0.90,
        "latency": 0.60,
        "reliability": 0.75,
        "risk": 0.80,
        "preference_alignment": 0.50,
    },
    "developer": {
        "quality": 0.90,
        "cost": 0.50,
        "latency": 0.85,
        "reliability": 0.90,
        "risk": 0.70,
        "preference_alignment": 0.50,
    },
    "organization": {
        "quality": 0.85,
        "cost": 0.75,
        "latency": 0.70,
        "reliability": 0.95,
        "risk": 0.95,
        "preference_alignment": 0.50,
    },
    "researcher": {
        "quality": 0.95,
        "cost": 0.40,
        "latency": 0.50,
        "reliability": 0.90,
        "risk": 0.75,
        "preference_alignment": 0.50,
    },
    "professional": {
        "quality": 0.85,
        "cost": 0.60,
        "latency": 0.80,
        "reliability": 0.90,
        "risk": 0.85,
        "preference_alignment": 0.50,
    },
}

GROUP_DESCRIPTIONS: Dict[str, str] = {
    "student": "Cost-focused · Quality-aware",
    "developer": "Quality & speed · Reliability-first",
    "organization": "Reliability & privacy · Cost-conscious",
    "researcher": "Maximum quality · Reliability-focused",
    "professional": "Quality & speed · Privacy-aware",
}


class RoutingPreferences(BaseModel):
    quality: float = Field(default=0.80, ge=0.0, le=1.0)
    cost: float = Field(default=0.60, ge=0.0, le=1.0)
    latency: float = Field(default=0.60, ge=0.0, le=1.0)
    reliability: float = Field(default=0.80, ge=0.0, le=1.0)
    risk: float = Field(default=0.75, ge=0.0, le=1.0)
    # Importance assigned to query/model capability fit. Added with a default
    # so existing stored five-dimensional profiles remain backward compatible.
    preference_alignment: float = Field(default=0.50, ge=0.0, le=1.0)


class AccessibilityPreferences(BaseModel):
    font_size: str = "default"
    reduced_motion: bool = False
    high_contrast: bool = False


class PersistentUserProfile(BaseModel):
    """
    The full persistent user profile stored in the backend.
    user_group is fixed after onboarding and is the source of truth —
    the frontend must NOT override it per-query.
    """
    user_id: str
    name: str
    email: str
    user_group: str = Field(description="Fixed group set during onboarding: student|developer|organization|researcher|professional")
    routing_preferences: RoutingPreferences = Field(default_factory=RoutingPreferences)
    accessibility_preferences: AccessibilityPreferences = Field(default_factory=AccessibilityPreferences)
    theme_preference: str = "system"
    preferences_customized: bool = Field(
        default=False,
        description="True if user has manually edited preferences away from group defaults"
    )

    def get_routing_weights(self) -> Dict[str, float]:
        """
        Convert saved preferences to normalized routing weights.
        Preferences are importance scores (0–1); weights are normalized to sum to 1.
        """
        prefs = self.routing_preferences.model_dump()
        total = sum(prefs.values())
        if total == 0:
            total = 1.0
        return {k: round(v / total, 4) for k, v in prefs.items()}


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1)
    email: str = Field(..., min_length=3)
    user_group: str = Field(..., description="student|developer|organization|researcher|professional")
    routing_preferences: Optional[RoutingPreferences] = None
    accessibility_preferences: Optional[AccessibilityPreferences] = None
    theme_preference: str = "system"


class UpdatePreferencesRequest(BaseModel):
    routing_preferences: RoutingPreferences
