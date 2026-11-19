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
  'preference_alignment',
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
  /** unknown | provider_documented_restricted | customer_controlled */
  data_handling_status?: string;
  model_id: string;
  model_name: string;
  provider: string;
  capabilities: string[];
  supported_domains: string[];
  supported_tasks: string[];
  estimated_quality: number | null;
  estimated_cost: number | null;
  estimated_latency: number | null;
  reliability: number | null;
  risk_level: number | null;
  context_window: number;
  cost_per_1k_tokens: number | null;
  avg_latency_seconds: number | null;
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
  metadata_status?: string;
  lifecycle_status?: string;
  adapter_compatible?: boolean;
  inference_access_status?: string;
  routing_eligible?: boolean;
  last_verified_at?: string | null;
  input_price_per_million?: number | null;
  output_price_per_million?: number | null;
  /* Live-registry fields (`backend/app/schemas/model.py::RegistryEntry`) */
  catalog_origin?: 'static' | 'live' | 'application';
  eligibility?: RegistryEligibility | null;
  verification?: { status: 'validated' | 'failed'; error_code: string | null; verified_at: string } | null;
  catalog_last_confirmed_at?: string | null;
  catalog_stale?: boolean;
  lifecycle_reason?: string | null;
  first_seen_at?: string | null;
  deprecated_at?: string | null;
  retires_at?: string | null;
  consecutive_missing_refreshes?: number;
  metric_provenance?: Record<string, string>;
}

export interface EligibilityMessage {
  code: string;
  message: string;
}

export interface RegistryEligibility {
  eligible: boolean;
  reasons: EligibilityMessage[];
  warnings: EligibilityMessage[];
}

export interface RegistryProviderRefresh {
  provider: string;
  display_name?: string;
  configured?: boolean;
  disabled?: boolean;
  status: string | null;
  last_attempt_status?: string | null;
  last_attempt_at?: string | null;
  started_at?: string;
  finished_at?: string | null;
  last_success_at?: string | null;
  stale?: boolean | null;
  error_code?: string | null;
  error_message?: string | null;
  entries_seen?: number | null;
  entries_new?: number | null;
  entries_changed?: number | null;
  entries_missing?: number | null;
  entries_rejected?: number | null;
}

export interface RegistryStatus {
  persistence_available: boolean;
  live_registry_enabled?: boolean;
  admin_configured?: boolean;
  refresh_ttl_minutes?: number;
  providers: RegistryProviderRefresh[];
}

export interface CatalogSummary {
  total: number;
  by_origin: Record<'static' | 'live' | 'application', number>;
  by_lifecycle: Record<string, number>;
  routing_eligible: number;
}

export interface CatalogPage {
  items: ModelInfo[];
  total: number;
  page: number;
  page_size: number;
  summary: CatalogSummary;
  providers: string[];
  persistence_available: boolean;
}

export interface CatalogQuery {
  search?: string;
  provider?: string;
  origin?: string;
  lifecycle?: string;
  eligible?: boolean;
  sort?: string;
  page?: number;
  page_size?: number;
}

export interface LifecycleEvent {
  event_type: string;
  previous_status: string | null;
  new_status: string;
  reason: string | null;
  occurred_at: string;
}

export interface RegistryActivityItem {
  kind: 'lifecycle' | 'refresh_failure';
  provider: string;
  model_id: string | null;
  event_type: string;
  previous_status: string | null;
  new_status: string | null;
  reason: string | null;
  occurred_at: string;
}

export interface RefreshHistoryItem {
  provider: string;
  status: string;
  trigger: string;
  started_at: string;
  finished_at: string | null;
  error_code: string | null;
  error_message_safe: string | null;
  entries_seen: number | null;
  entries_new: number | null;
  entries_changed: number | null;
  entries_missing: number | null;
  entries_rejected: number | null;
}

export interface RefreshResult {
  provider: string;
  status: 'success' | 'failed' | 'fresh' | 'already_running' | 'not_configured';
  error_code?: string;
  entries_seen?: number;
  entries_new?: number;
  entries_changed?: number;
  entries_missing?: number;
}

export interface VerifyResult {
  provider: string;
  model_id: string;
  status: 'validated' | 'failed';
  error_code: string | null;
  latency_ms: number;
}

export interface ModelDetailResponse {
  entry: ModelInfo;
  lifecycle_history: LifecycleEvent[];
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
  required_modalities?: string[];
  required_capabilities?: string[];
  classification_confidence?: number;
  uncertainty_notes?: string[];
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

export type RouteMode = 'recommend' | 'execute';
export type OptimizationMode = 'disabled' | 'conservative' | 'standard' | 'advanced' | 'custom';
export type SubmitPrompt = 'original' | 'optimized';

export interface RouteRequest {
  query: string;
  task_type_hint?: string;
  model_ids?: string[];
  max_cost?: number;
  max_latency?: number;
  require_capabilities?: string[];
  privacy_requirement?: 'standard' | 'strict';
  /** Route Query Engine 2.0 */
  mode?: RouteMode;
  optimization_mode?: OptimizationMode;
  optimization_options?: Record<string, boolean>;
  /** The user-reviewed prompt; when omitted the engine optimizes server-side. */
  optimized_prompt?: string;
  submit_prompt?: SubmitPrompt;
  preferred_providers?: string[];
  excluded_providers?: string[];
  excluded_model_ids?: string[];
  weight_overrides?: Record<string, number>;
  budget_usd?: number;
  evaluate_response?: boolean;
  idempotency_key?: string;
}

export interface OptimizePromptRequest {
  query: string;
  task_type_hint?: string;
  mode?: OptimizationMode;
  options?: Record<string, boolean>;
  model_id?: string;
}

export interface PromptQuality {
  clarity: number;
  specificity: number;
  structure: number;
  constraint_coverage: number;
  ambiguity: number;
  overall: number;
  method: string;
}

export interface EngineAmbiguity {
  kind: string;
  message: string;
  severity: 'minor' | 'major';
  clarifying_question?: string | null;
}

export interface OptimizePromptResponse {
  optimized_prompt: string;
  task_type: string;
  domain: string;
  method: string;
  original_prompt?: string;
  mode?: OptimizationMode;
  applied?: boolean;
  changes?: { kind: string; description: string }[];
  preserved_constraints?: string[];
  ambiguities?: EngineAmbiguity[];
  warnings?: string[];
  intent_preserved?: boolean;
  preservation_checks?: Record<string, boolean>;
  quality_before?: PromptQuality | null;
  quality_after?: PromptQuality | null;
  model_adaptation?: string[];
  isolated_untrusted_blocks?: number;
  needs_clarification?: boolean;
  analysis?: {
    primary_intent: string;
    secondary_intents: string[];
    complexity: string;
    domain: string;
    sensitivity: string;
    tokens_estimate: number;
  };
}

/* ---- Route Query Engine 2.0 payload (`RouteResponse.engine`) ---- */

export interface EngineRequirement { kind: string; value: string; origin: 'explicit' | 'inferred'; evidence: string }
export interface EngineIntent { name: string; score: number; registry_tags: string[] }
export interface EngineRiskIndicator { category: string; level: string; count: number; note: string }

export interface EngineProfile {
  version: string;
  primary_intent: string;
  secondary_intents: EngineIntent[];
  intents: EngineIntent[];
  task_type: string;
  domain: string;
  domain_confidence: number;
  complexity: { score: number; category: string; components: Record<string, number>; weights: Record<string, number>; methodology: string };
  required_capabilities: string[];
  required_modalities: string[];
  tokens: { input_tokens: number; output_tokens: number; method: string; exact: boolean; output_basis: string };
  reasoning_requirement: string;
  structured_output: string | null;
  explicit_requirements: EngineRequirement[];
  inferred_requirements: EngineRequirement[];
  ambiguities: EngineAmbiguity[];
  needs_clarification: boolean;
  risk: {
    sensitivity: string; score: number; indicators: EngineRiskIndicator[]; contains_credentials: boolean;
    recommends_strict_privacy: boolean; execution_blocked: boolean; execution_block_reason?: string | null;
  };
  confidence: Record<string, number>;
  analysis_method: string;
  notes: string[];
}

export interface EngineMetricEvidence {
  dimension: string; raw_value: number | null; unit: string; provenance: string; confidence: number; missing: boolean; note: string;
}

export interface EngineCandidate {
  model_id: string; model_name: string; provider: string; entry_type: string; executable: boolean;
  utilities: Record<string, number | null>;
  contributions: Record<string, number>;
  evidence: Record<string, EngineMetricEvidence>;
  missing_dimensions: string[];
  confidence: number; utility: number; robust_score: number; rank: number;
  pareto_optimal: boolean; dominated_by: string[];
  estimated_cost_usd: number | null;
  learning_adjustment: number; task_fit: number; preferred_provider: boolean; metadata_status: string;
}

export interface EngineExclusion {
  model_id: string; model_name?: string | null; provider?: string | null; code: string; requirement: string; reason: string;
  evidence: Record<string, unknown>; permanence: string; stage: string;
}

export interface EngineStage { name: string; label: string; status: 'completed' | 'skipped' | 'failed' | 'not_run'; duration_ms: number; detail: string }

export interface EngineAttempt {
  attempt: number; model_id: string; provider: string; outcome: string; error_kind?: string | null; retryable?: boolean | null;
  latency_ms?: number | null; input_tokens?: number | null; output_tokens?: number | null; cost_usd?: number | null; note: string;
}

export interface EngineResult {
  version: string;
  scoring_version: string;
  mode: RouteMode;
  status: string;
  profile: EngineProfile;
  optimization: OptimizePromptResponse & { original_prompt: string; optimized_prompt: string };
  preferences: {
    weights: Record<string, number>; base_weights: Record<string, number>; weight_source: string;
    adjustments: { dimension: string; factor: number; reason: string }[];
    hard_constraints: { kind: string; value: unknown; source: string }[];
    defaults_applied: string[]; warnings: string[]; precedence: string[];
  };
  candidates: EngineCandidate[];
  exclusions: EngineExclusion[];
  normalization: { cost_basis: string; cost_method: string; latency_basis: string; uncertainty_penalty: number; missing_policy: string; notes: string[] } | null;
  selection: {
    selected_model_id: string | null; runner_up_ids: string[]; status: string; tie_break_applied?: string | null; score_margin?: number | null;
    weight_stability?: number | null; confidence_level: 'high' | 'medium' | 'low'; confidence_value: number; caveats: string[];
  };
  explanation: {
    summary: string; why_selected: string[]; why_alternatives_ranked_lower: Record<string, unknown>[]; hard_constraints_applied: string[];
    influential_objectives: Record<string, unknown>[]; unavailable_data: string[]; tradeoffs: string[]; confidence_statement: string;
  };
  execution: {
    status: string; mode: string; final_model_id?: string | null; final_model_name?: string | null; attempts: EngineAttempt[]; escalated: boolean;
    escalation_reason?: string | null; total_cost_usd?: number | null; total_latency_ms?: number | null; blocked_reason?: string | null;
    prompt_sent_source?: string | null; notes: string[];
  };
  evaluation: {
    status: string; method: string; accepted?: boolean | null; checks: { name: string; passed: boolean; detail: string }[];
    heuristic_scores: Record<string, number>; judge_model?: string | null; notes: string[];
  };
  stages: EngineStage[];
  candidate_pool: string;
  no_candidate_guidance: Record<string, unknown>;
  prompt_used: string;
  prompt_used_source: 'original' | 'optimized';
  routing_latency_ms: number;
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
  /** Present for Route Query Engine 2.0 responses. */
  engine?: EngineResult;
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
  /** 'recommend' | 'execute' */
  mode?: string;
  execution_status?: string | null;
}

export type RoutingHistoryAvailability = 'available' | 'unsupported' | 'error';
