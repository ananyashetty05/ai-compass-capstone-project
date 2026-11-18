"""Typed data structures shared by every stage of the Route Query engine.

Python 3.9 compatibility: pydantic evaluates annotations at runtime, so these
models use ``typing.Optional/List/Dict`` rather than ``X | None``.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

ENGINE_VERSION = "2.0.0"
SCORING_VERSION = "2.0.0"


# ── Query understanding ──────────────────────────────────────────────────────

class Requirement(BaseModel):
    kind: str
    value: str
    origin: str = Field(description="explicit (stated by the user) | inferred (derived by the analyzer)")
    evidence: str = Field(default="", description="Describes what triggered it; never contains raw sensitive text")


class Intent(BaseModel):
    name: str
    score: float = Field(ge=0.0, le=1.0)
    registry_tags: List[str] = []


class Ambiguity(BaseModel):
    kind: str
    message: str
    severity: str = Field(description="minor | major")
    clarifying_question: Optional[str] = None


class RiskIndicator(BaseModel):
    category: str
    level: str = Field(description="low | moderate | high")
    count: int = 1
    note: str = ""


class RiskAssessment(BaseModel):
    sensitivity: str = Field(default="none", description="none | low | moderate | high")
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    indicators: List[RiskIndicator] = []
    contains_credentials: bool = False
    recommends_strict_privacy: bool = False
    execution_blocked: bool = False
    execution_block_reason: Optional[str] = None


class ComplexityAssessment(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    category: str = Field(description="simple | moderate | complex | highly_complex")
    components: Dict[str, float] = {}
    weights: Dict[str, float] = {}
    methodology: str = ""


class TokenEstimate(BaseModel):
    input_tokens: int
    output_tokens: int
    method: str
    exact: bool = False
    output_basis: str = ""

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


class QueryProfileV2(BaseModel):
    """Canonical profile passed through filtering, scoring, execution and explanation.

    ``original_query`` is the analysed text. It is kept in the in-memory profile
    for the response but is never written to routing history.
    """
    version: str = ENGINE_VERSION
    original_query: str
    primary_intent: str
    secondary_intents: List[Intent] = []
    intents: List[Intent] = []
    task_type: str = Field(description="Legacy registry task category derived from the primary intent")
    task_tags: List[str] = Field(default=[], description="Registry capability/task tags that satisfy the primary intent")
    domain: str = "general"
    domain_confidence: float = 0.0
    complexity: ComplexityAssessment
    required_capabilities: List[str] = []
    required_modalities: List[str] = ["text"]
    tokens: TokenEstimate
    reasoning_requirement: str = "light"
    structured_output: Optional[str] = None
    explicit_requirements: List[Requirement] = []
    inferred_requirements: List[Requirement] = []
    ambiguities: List[Ambiguity] = []
    needs_clarification: bool = False
    risk: RiskAssessment
    confidence: Dict[str, float] = {}
    user_hint_applied: Optional[str] = None
    analysis_method: str = "lexical_rule_engine_v2"
    notes: List[str] = []


# ── Prompt optimisation ──────────────────────────────────────────────────────

class OptimizationChange(BaseModel):
    kind: str
    description: str


class PromptQuality(BaseModel):
    clarity: float
    specificity: float
    structure: float
    constraint_coverage: float
    ambiguity: float = Field(description="Higher means more ambiguous")
    overall: float
    method: str = "heuristic_indicator_not_validated_against_answer_quality"


class OptimizationResult(BaseModel):
    original_prompt: str
    optimized_prompt: str
    mode: str
    applied: bool
    changes: List[OptimizationChange] = []
    preserved_constraints: List[str] = []
    ambiguities: List[Ambiguity] = []
    warnings: List[str] = []
    intent_preserved: bool = True
    preservation_checks: Dict[str, bool] = {}
    quality_before: Optional[PromptQuality] = None
    quality_after: Optional[PromptQuality] = None
    isolated_untrusted_blocks: int = 0
    model_adaptation: List[str] = []
    method: str = "task_aware_prompt_optimizer_v2"
    options: Dict[str, bool] = {}


# ── Preferences ──────────────────────────────────────────────────────────────

class WeightAdjustment(BaseModel):
    dimension: str
    factor: float
    reason: str


class HardConstraint(BaseModel):
    kind: str
    value: Any
    source: str = Field(description="application | request | user_profile")


class ResolvedPreferences(BaseModel):
    weights: Dict[str, float]
    base_weights: Dict[str, float]
    weight_source: str = Field(description="request_override | saved_profile | system_default")
    adjustments: List[WeightAdjustment] = []
    hard_constraints: List[HardConstraint] = []
    preferred_providers: List[str] = []
    excluded_providers: List[str] = []
    excluded_model_ids: List[str] = []
    defaults_applied: List[str] = []
    warnings: List[str] = []
    precedence: List[str] = [
        "application security and safety constraints",
        "request-level hard constraints",
        "user-level hard restrictions",
        "request weight overrides, then saved user weights",
        "system defaults",
    ]


# ── Candidates, filtering, scoring ──────────────────────────────────────────

class ExclusionRecord(BaseModel):
    model_id: str
    model_name: Optional[str] = None
    provider: Optional[str] = None
    code: str
    requirement: str
    reason: str
    evidence: Dict[str, Any] = {}
    permanence: str = Field(default="unknown", description="permanent | temporary | unknown")
    stage: str = "hard_constraint_filtering"


class MetricEvidence(BaseModel):
    """One objective input for one candidate, with its provenance."""
    dimension: str
    raw_value: Optional[float] = None
    unit: str = ""
    provenance: str = "unavailable"
    confidence: float = 0.0
    missing: bool = True
    note: str = ""


class CandidateScore(BaseModel):
    model_id: str
    model_name: str
    provider: str
    entry_type: str
    executable: bool
    eligible: bool = True
    utilities: Dict[str, Optional[float]] = {}
    contributions: Dict[str, float] = {}
    evidence: Dict[str, MetricEvidence] = {}
    missing_dimensions: List[str] = []
    confidence: float = 0.0
    utility: float = 0.0
    robust_score: float = 0.0
    rank: int = 0
    pareto_optimal: bool = False
    dominated_by: List[str] = []
    estimated_cost_usd: Optional[float] = None
    learning_adjustment: float = 0.0
    task_fit: float = 0.0
    preferred_provider: bool = False
    metadata_status: str = "unknown"


class NormalizationDetails(BaseModel):
    cost_basis: str
    cost_method: str
    latency_basis: str
    ranges: Dict[str, Dict[str, Optional[float]]] = {}
    uncertainty_penalty: float
    missing_policy: str
    notes: List[str] = []


class ScoringConfig(BaseModel):
    version: str = SCORING_VERSION
    uncertainty_penalty: float = 0.25
    missing_policy: str = "pessimistic"
    tie_epsilon: float = 0.005
    weight_perturbation: float = 0.2


class Selection(BaseModel):
    selected_model_id: Optional[str] = None
    runner_up_ids: List[str] = []
    status: str = "selected"
    tie_break_applied: Optional[str] = None
    score_margin: Optional[float] = None
    weight_stability: Optional[float] = None
    confidence_level: str = "low"
    confidence_value: float = 0.0
    caveats: List[str] = []


class StageRecord(BaseModel):
    name: str
    label: str
    status: str = Field(description="completed | skipped | failed | not_run")
    duration_ms: float = 0.0
    detail: str = ""


class DecisionExplanation(BaseModel):
    summary: str
    why_selected: List[str] = []
    why_alternatives_ranked_lower: List[Dict[str, Any]] = []
    hard_constraints_applied: List[str] = []
    influential_objectives: List[Dict[str, Any]] = []
    unavailable_data: List[str] = []
    tradeoffs: List[str] = []
    confidence_statement: str = ""
    facts: List[Dict[str, Any]] = Field(default=[], description="The structured facts every sentence above was generated from")


# ── Execution & evaluation ──────────────────────────────────────────────────

class ExecutionPolicy(BaseModel):
    max_attempts: int = Field(default=3, ge=1, le=6)
    max_retries_per_model: int = Field(default=1, ge=0, le=3)
    max_escalation_depth: int = Field(default=2, ge=0, le=4)
    budget_usd: Optional[float] = Field(default=None, gt=0)
    deadline_seconds: float = Field(default=90.0, gt=0, le=600)
    base_backoff_seconds: float = 0.5
    max_backoff_seconds: float = 8.0
    max_output_tokens: int = Field(default=1024, ge=16, le=8192)


class AttemptRecord(BaseModel):
    attempt: int
    model_id: str
    provider: str
    outcome: str
    error_kind: Optional[str] = None
    retryable: Optional[bool] = None
    latency_ms: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    note: str = ""


class EvaluationCheck(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class EvaluationOutcome(BaseModel):
    status: str = Field(description="not_requested | skipped | unavailable | not_configured | completed")
    method: str = "none"
    accepted: Optional[bool] = None
    checks: List[EvaluationCheck] = []
    heuristic_scores: Dict[str, float] = {}
    judge_model: Optional[str] = None
    notes: List[str] = []


class ExecutionOutcome(BaseModel):
    status: str = Field(description="not_requested | blocked | succeeded | failed | budget_exhausted")
    mode: str = "recommend"
    final_model_id: Optional[str] = None
    final_model_name: Optional[str] = None
    response_text: Optional[str] = None
    attempts: List[AttemptRecord] = []
    escalated: bool = False
    escalation_reason: Optional[str] = None
    total_cost_usd: Optional[float] = None
    total_latency_ms: Optional[float] = None
    blocked_reason: Optional[str] = None
    prompt_sent_source: Optional[str] = Field(default=None, description="original | optimized")
    notes: List[str] = []
