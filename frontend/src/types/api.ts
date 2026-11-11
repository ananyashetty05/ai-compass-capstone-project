/**
 * AI Compass — Domain types
 *
 * These interfaces mirror the FastAPI Pydantic schemas in
 * `backend/app/schemas/*`. Fields the backend declares as
 * `Optional` are modelled as `T | null` so the UI can distinguish
 * "unavailable" from "zero".
 */

/* ------------------------------------------------------------------ *
 * Routing objectives
 * ------------------------------------------------------------------ */

export const ROUTING_OBJECTIVES = [
  'quality',
  'cost',
  'latency',
  'reliability',
  'risk',
] as const;

export type RoutingObjective = (typeof ROUTING_OBJECTIVES)[number];

/** The five objectives a user can weight, mapped 1:1 to backend keys. */
export type RoutingPreferences = Record<RoutingObjective, number>;

/** Normalised weights returned by the router (sums to 1). */
export type AppliedWeights = Record<RoutingObjective, number> & Record<string, number>;

export type UserGroup = string;

/* ------------------------------------------------------------------ *
 * User profile
 * ------------------------------------------------------------------ */

export type FontSizePreference = 'small' | 'default' | 'large';

export interface AccessibilityPreferences {
  font_size: FontSizePreference;
  reduced_motion: boolean;
  high_contrast: boolean;
}

export type ThemePreference = 'light' | 'dark' | 'system';

/** `backend/app/schemas/profile.py::PersistentUserProfile` */
export interface UserProfile {
  user_id: string;
  name: string;
  email: string;
  /** Fixed during onboarding. Never chosen per query. */
  user_group: UserGroup;
  routing_preferences: RoutingPreferences;
  accessibility_preferences: AccessibilityPreferences;
  theme_preference: string;
  preferences_customized: boolean;
}

export interface GroupOption {
  group: UserGroup;
  description: string;
}

export interface GroupDefaults extends GroupOption {
  default_preferences: RoutingPreferences;
}

export interface RegisterPayload {
  name: string;
  email: string;
  password: string;
  user_group: UserGroup;
  routing_preferences?: Partial<RoutingPreferences>;
  theme_preference?: ThemePreference;
}

export interface UpdateProfilePayload {
  name?: string;
  theme_preference?: ThemePreference;
  accessibility_preferences?: Partial<AccessibilityPreferences>;
}

export interface AuthResponse {
  token: string;
  profile: UserProfile;
}

/* ------------------------------------------------------------------ *
 * Model pool
 * ------------------------------------------------------------------ */

/** `backend/app/schemas/model.py::ModelMetadata` */
export interface ModelInfo {
  model_id: string;
  model_name: string;
  provider: string;
  capabilities: string[];
  supported_domains: string[];
  supported_tasks: string[];
  estimated_quality: number | null;
  estimated_cost: number;
  estimated_latency: number;
  reliability: number;
  risk_level: number;
  context_window: number;
  cost_per_1k_tokens: number;
  avg_latency_seconds: number;
  fallback_priority: number;
  active: boolean;
  source: string;
  modality: string;
  entry_type: string;
  requires_key: boolean;
  external_url?: string | null;
  description?: string | null;
  model_family?: string | null;
  modalities?: string[];
  availability?: string;
  provider_source?: string | null;
  authentication_requirement?: string;
  data_provenance?: string;
  last_verified_at?: string | null;
  input_price_per_million?: number | null;
  output_price_per_million?: number | null;
}

/* ------------------------------------------------------------------ *
 * Query analysis
 * ------------------------------------------------------------------ */

/** `backend/app/schemas/query.py::QueryProfile` */
export interface QueryProfile {
  task_type: string;
  domain: string;
  complexity: number;
  context_requirement: number;
  quality_requirement: number;
  risk_level: number;
  latency_requirement: number;
  cost_sensitivity: number;
  reliability_requirement: number;
  estimated_tokens: number;
  analysis_method: string;
}

/* ------------------------------------------------------------------ *
 * Routing decision
 * ------------------------------------------------------------------ */

/** `backend/app/schemas/routing.py::ModelScore` */
export interface ModelScore {
  model_id: string;
  quality_score: number | null;
  cost_score: number;
  latency_score: number;
  reliability_score: number;
  risk_score: number;
  preference_alignment: number;
  overall_score: number;
  score_breakdown?: Record<string, number | null>;
}

export interface FilteredModel {
  model_id: string;
  reason: string;
}

/** `backend/app/services/explanation.py::build_explanation` */
export interface ExplanationUserContext {
  user_group?: UserGroup;
  user_name?: string;
  routing_preferences?: RoutingPreferences;
  preferences_customized?: boolean;
}

export interface ExplanationQueryCharacteristics {
  task_type?: string;
  domain?: string;
  complexity?: number;
  quality_requirement?: number;
  risk_level?: number;
}

export interface RoutingExplanation {
  routing_system?: { name?: string; type?: string };
  selected_model?: string;
  selected_model_name?: string;
  fallback_model_id?: string | null;
  routing_reason?: string[];
  applied_weights?: AppliedWeights;
  user_context?: ExplanationUserContext;
  query_characteristics?: ExplanationQueryCharacteristics;
  score_breakdown?: Record<string, number>;
  overall_score?: number;
  filtered_out?: FilteredModel[];
  candidate_count?: number;
  routing_latency_ms?: number;
  narrative?: string;
  applied_constraints?: Record<string, unknown>;
}

/** `backend/app/schemas/response.py::ResponseEvaluation` */
export interface ResponseEvaluation {
  quality_score: number;
  relevance_score: number;
  completeness_score: number;
  /** Higher = riskier. */
  risk_score: number;
  accepted: boolean;
  evaluation_reasons: string[];
  evaluation_method: string;
}

/** `backend/app/schemas/response.py::EscalationInfo` */
export interface EscalationInfo {
  escalated: boolean;
  escalation_trigger: string | null;
  original_model_id: string | null;
  fallback_model_id: string | null;
  escalation_reason: string | null;
  attempts: number;
  final_status: string;
}

export interface PerformanceMetrics {
  total_latency_ms?: number;
  routing_latency_ms?: number;
  candidates_evaluated?: number;
  models_filtered?: number;
  escalated?: boolean;
  user_group?: string;
  total_estimated_cost?: number;
}

export interface RequestUsage {
  model_id: string;
  latency_ms?: number | null;
  estimated_cost?: number | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  total_tokens?: number | null;
}

export interface RouteRequest {
  query: string;
  task_type_hint?: string;
  model_ids?: string[];
  max_cost?: number;
  max_latency?: number;
  require_capabilities?: string[];
}

export interface OptimizePromptRequest {
  query: string;
  task_type_hint?: string;
}

export interface OptimizePromptResponse {
  optimized_prompt: string;
  task_type: string;
  domain: string;
  method: string;
}

/** Ranked alternative model from the routing decision */
export interface RankedAlternative {
  model_id: string;
  model_name: string;
  provider: string;
  overall_score: number;
  quality_score: number;
  cost_score: number;
  latency_score: number;
  reliability_score: number;
  risk_score: number;
  score_breakdown?: Record<string, number>;
  description?: string | null;
  modality: string;
}

/** Tool recommendation for specialized tasks */
export interface ToolRecommendation {
  model_id: string;
  model_name: string;
  provider: string;
  modality: string;
  entry_type: string;
  description?: string | null;
  external_url?: string | null;
  requires_key: boolean;
  capabilities: string[];
}

/** `backend/app/schemas/response.py::RouteAndGenerateResponse` */
export interface RouteResponse {
  routing_system: { name: string; type: string };
  routing_id: string;
  query: string;
  profile: UserGroup;
  query_analysis: QueryProfile;
  candidate_models: string[];
  filtered_models: FilteredModel[];
  model_scores: ModelScore[];
  selected_model_id: string;
  selected_model_name: string;
  routing_explanation: RoutingExplanation;
  generated_response: string;
  response_evaluation: ResponseEvaluation;
  escalation_info: EscalationInfo;
  final_model_id: string;
  final_model_name: string;
  performance_metrics: PerformanceMetrics;
  request_usage: RequestUsage[];
  optimized_prompt?: string | null;
  learning_active: boolean;
  ranked_alternatives: RankedAlternative[];
  tool_recommendations: ToolRecommendation[];
  recommended_destination: {
    provider: string;
    entry_type: string;
    official_url?: string | null;
    availability: string;
    data_provenance: string;
    last_verified_at?: string | null;
  };
}

/* ------------------------------------------------------------------ *
 * Feedback & Learning
 * ------------------------------------------------------------------ */

export interface FeedbackSubmission {
  routing_id: string;
  model_id: string;
  model_name: string;
  query_summary: string;
  task_type: string;
  domain: string;
  rating: number;        // 1–5
  thumbs: 'up' | 'down' | null;
  reasons: string[];
  comment: string | null;
}

export interface FeedbackRecord extends FeedbackSubmission {
  feedback_id: string;
  user_id: string;
  created_at: string;
}

export interface ModelSatisfaction {
  model_id: string;
  model_name: string;
  mean_rating: number;
  sample_count: number;
  confidence: number;
  last_updated: string;
}

export interface LearningState {
  total_feedback: number;
  models_rated: number;
  satisfaction_estimates: ModelSatisfaction[];
  learning_active: boolean;
  cold_start: boolean;
}

/* ------------------------------------------------------------------ *
 * Evaluation
 * ------------------------------------------------------------------ */

/** Legacy shape retained for existing research export helpers. */
export interface BaselineResult {
  strategy: string;
  selected_model: string;
  quality: number;
  /** 1 − normalised registry cost. */
  cost_efficiency: number;
  actual_estimated_cost: number | null;
  latency_ms: number | null;
  reliability: number;
  escalated: boolean;
  preference_alignment: number | null;
  usage?: RequestUsage;
}

export type OfflineEvaluationStrategy = 'aicompass' | 'strongest' | 'cheapest' | 'static';

export interface OfflineEvaluationRequest {
  query: string;
  task_type_hint?: string;
  max_cost?: number;
  max_latency?: number;
  require_capabilities?: string[];
  model_ids?: string[];
}

export interface OfflineStrategyResult {
  strategy: OfflineEvaluationStrategy;
  status: 'selected' | 'unavailable';
  selected_model_id: string | null;
  selected_model: string | null;
  provider: string | null;
  selection_rationale: string;
  routing_score: number | null;
  quality_score: number | null;
  quality_source: string | null;
  estimated_cost_usd: number | null;
  cost_basis: string | null;
  input_price_per_million: number | null;
  latency_seconds: number | null;
  reliability_score: number | null;
  risk_score: number | null;
  capabilities: string[];
  context_window: number | null;
  availability: string | null;
  constraint_satisfied: boolean;
  missing_data: string[];
  data_sources: Record<string, string | null>;
}

export interface OfflineEvaluationResponse {
  evaluation_method: 'offline_registry_metadata';
  data_disclosure: string;
  query_analysis: QueryProfile;
  candidate_count: number;
  filtered_models: FilteredModel[];
  strategy_results: OfflineStrategyResult[];
}

/**
 * Strategy identifiers used by the offline evaluation workflow.
 *
 * These are decision *policies*, not models. `aicompass` is the adaptive
 * routing strategy implemented by this system; the remaining three are
 * fixed reference policies. None of them is an LLM, and none of them is
 * part of AI Compass.
 */
export const EVALUATION_STRATEGIES = {
  aicompass: 'AI Compass Routing Strategy',
  strongest: 'Strongest Model Baseline',
  cheapest: 'Cheapest Model Baseline',
  static: 'Static Ranking Baseline',
} as const;

export type EvaluationStrategyKey = keyof typeof EVALUATION_STRATEGIES;

/* ------------------------------------------------------------------ *
 * System health
 * ------------------------------------------------------------------ */

export type ProviderId = 'openai' | 'anthropic' | 'google' | 'groq' | (string & {});

export interface ProviderStatus {
  /** True when the backend holds a server-side credential. */
  credential_configured: boolean;
  disabled: boolean;
}

export interface HealthResponse {
  status: string;
  service: string;
  providers: Record<ProviderId, ProviderStatus>;
}

export type HealthState = 'online' | 'degraded' | 'offline' | 'unknown';

/* ------------------------------------------------------------------ *
 * Routing history
 * ------------------------------------------------------------------ */

/**
 * Contract for a future backend `GET /routing-history` endpoint.
 * The UI consumes this only when the endpoint exists; it never
 * synthesises entries client-side.
 */
export interface RoutingHistoryEntry {
  id: string;
  timestamp: string;
  query_summary: string;
  selected_model_id: string;
  selected_model_name: string;
  final_model_id: string;
  final_model_name: string;
  routing_latency_ms: number | null;
  total_latency_ms: number | null;
  estimated_cost: number | null;
  escalated: boolean;
}

export type RoutingHistoryAvailability = 'available' | 'unsupported' | 'error';
