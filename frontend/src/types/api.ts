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
  catalog_origin?: 'static' | 'live' | 'application' | 'approved';
  /* Approved ecosystem (`backend/app/data/approved_ecosystem.py`) */
  ecosystem_category?: EcosystemCategory | null;
  secondary_categories?: EcosystemCategory[];
  product_kind?: string | null;
  strengths?: string[];
  ecosystem_approved?: boolean;
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
  /* Capability & intended-use taxonomy (`backend/app/services/model_taxonomy.py`). Unknown stays unknown. */
  developer?: string | null;
  provider_role?: 'model_developer' | 'inference_provider' | 'model_aggregator' | 'model_hub' | 'cloud_platform' | 'application' | 'unknown';
  model_type?: string;
  use_categories?: Array<'conversational' | 'developer'>;
  /** ONE mutually exclusive category; category totals add up to the pool total. `use_categories` above are overlapping routing tags. */
  primary_category?: PrimaryCategory;
  /** Recommendation group, derived from verified fields (never from a provider name in a query). */
  model_category?: ModelGroup;
  access_type?: 'consumer_chat' | 'provider_api' | 'hosted_inference' | 'aggregator_api' | 'self_hosted' | 'unknown';
  intended_use?: string[];
  integration_supported?: boolean | null;
  pricing_category?: PricingCategory;
  free_tier_available?: boolean | null;
  category_basis?: string | null;
  category_kind?: string;
  classification_basis?: 'curated' | 'derived' | 'unverified';
  classification_reason?: string | null;
  /** Overlapping capabilities; never summed into a total. */
  capability_tags?: string[];
  weights_status?: 'open_weights' | 'proprietary' | 'unknown';
  license_name?: string | null;
  free_download?: boolean | null;
  free_access?: 'free' | 'limited_free' | 'paid' | 'unknown';
  free_access_note?: string | null;
  deployment_options?: string[];
  api_available?: boolean | null;
  embedding_dimensions?: number | null;
  taxonomy_status?: 'curated' | 'derived' | 'unclassified';
  /* Independent state flags — never collapsed into one "available" */
  comparison_eligible?: boolean;
  execution_available?: boolean;
  user_access_configured?: boolean;
  /** Autonomous-catalogue lifecycle/provenance block. Absent for consumer applications. */
  catalog?: CatalogBlock | null;
}

export interface CatalogDestination { kind: string; label: string; url: string; provider: string; verified: boolean }
export interface CatalogOffering {
  provider: string; model_id: string; listed: boolean; authority: string;
  input_per_million: number | null; output_per_million: number | null; pricing_known: boolean;
  context_window: number | null; deprecated: boolean;
}
export type GenerationStatus = 'retained' | 'superseded' | 'unmanaged' | 'pending_review' | 'unverified';
export type VerificationLevel = 'detected' | 'corroborated' | 'officially_confirmed';
export interface CatalogBlock {
  canonical_key: string; developer_slug: string | null; lineage_key: string; generation_label: string | null;
  generation_status: GenerationStatus; generation_reason: string | null; verification_level: VerificationLevel;
  lifecycle: string; publication: 'published' | 'retired' | 'unpublished'; availability: string;
  released_at: string | null; released_at_kind: string; variants: string[]; retired: boolean; superseded_at: string | null;
  first_seen_at: string | null; last_changed_at: string | null; sources: string[];
  field_provenance: Record<string, { source: string; authority: string }>; conflicts: Array<{ field: string; chosen: string; others: string[] }>;
  offerings: CatalogOffering[]; destinations: CatalogDestination[]; primary_provider: string;
}

export interface CatalogSourceHealth {
  source_id: string; kind: string; status: 'never_run' | 'ok' | 'partial' | 'failed' | 'rate_limited' | 'timed_out'; last_attempt_at: string | null; last_success_at: string | null;
  consecutive_failures: number; last_count: number; last_error: string | null; refresh_interval_minutes: number;
}
export interface CatalogEventRow { occurred_at: string; event_type: string; entity_type: string; entity_key: string; from_state: string | null; to_state: string | null; reason: string | null; run_id: string | null; name?: string }
export interface CatalogEcosystem {
  origin: 'store' | 'offline_seed' | 'seed'; live: boolean; version: number; published_at: string | null; store_error: string | null; note: string | null;
  totals: { published: number; retired: number; awaiting_verification: number; developers: number; retained_generations: number; lineages_needing_review: number; registered_developers: number };
  developers: Array<{ developer: string; name: string; models: number }>;
  recent_events: CatalogEventRow[]; recent_announcements?: CatalogEventRow[]; recent_runs: Array<{ run_id: string; trigger: string; started_at: string; finished_at: string | null; status: string }>;
  sources: CatalogSourceHealth[]; last_success_at: string | null;
}
export interface CatalogFamily {
  lineage_key: string; developer: string | null; family: string; track: string; review_reason: string | null;
  generations: Array<{ generation_key: string; label: string; retention: GenerationStatus; reason: string | null; verification: VerificationLevel; first_released_at: string | null; models: Array<{ canonical_key: string; name: string; publication: string }> }>;
  unmanaged_models: Array<{ canonical_key: string; name: string; publication: string }>;
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
  /** Candidates with at least one real objective value; the rest are in the pool but cannot be compared. */
  candidates_scored?: number;
  models_filtered?: number;
  escalated?: boolean;
  user_group?: string;
  total_estimated_cost?: number | null;
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

export type EcosystemCategory = 'conversational' | 'image' | 'video' | 'music_voice' | 'document_design' | 'api_models' | 'coding';

/** The ONE category a query is routed into before any product is ranked. */
export interface EngineCategory {
  category: EcosystemCategory; label: string; scores: Record<string, number>; signals: string[]; confidence: number;
  runner_up?: EcosystemCategory | null; runner_up_score: number; ambiguous: boolean; required_subtype?: string | null;
  features: Array<{ feature: string; accepts: string[] }>; reason: string; method: string;
}

/** One row of the single ranking that feeds Best Match, Suggested and Candidates. */
export interface EngineRankingRow {
  rank: number; model_id: string; model_name: string; provider: string; category: EcosystemCategory | null; role: 'primary' | 'secondary' | null; score: number;
  fit_breakdown: Record<string, number>; matched_features: string[]; unmet_features: string[]; strengths: string[]; external_url?: string | null;
  description?: string | null; pricing_category?: PricingCategory | null; entry_type: string; product_kind?: string | null;
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
  category?: EngineCategory | null;
  analysis_method: string;
  notes: string[];
  /** conversational vs developer intent, with the rules that fired */
  audience?: { kind: 'conversational' | 'developer'; category?: 'conversational' | 'developer_api'; ambiguous?: boolean; clarifying_question?: string | null; signals: string[]; required_model_types: string[]; prefers_free: boolean; requires_open_weights: boolean; method: string };
}

export interface EngineMetricEvidence {
  dimension: string; raw_value: number | null; unit: string; provenance: string; confidence: number; missing: boolean; note: string;
  /** ER-PCR evidence tier: measured | documented | estimate | unverified_estimate | unknown. Only the first three may rank candidates. */
  tier?: string; used_in_ranking?: boolean; freshness?: string; source?: string | null; date?: string | null; sample_size?: number | null;
}

export interface EngineCandidate {
  model_id: string; model_name: string; provider: string; entry_type: string; executable: boolean;
  utilities: Record<string, number | null>;
  contributions: Record<string, number>;
  evidence: Record<string, EngineMetricEvidence>;
  missing_dimensions: string[];
  confidence: number; utility: number; robust_score: number; rank: number;
  /** Best case if every unknown ranking objective were perfect (display only; never ranks). */
  score_upper?: number; evidence_gaps?: string[];
  pareto_optimal: boolean; dominated_by: string[];
  estimated_cost_usd: number | null;
  learning_adjustment: number; task_fit: number; preferred_provider: boolean; metadata_status: string;
  /** Always true for a ranked candidate: it passed the hard constraints. Never depends on a credential. */
  recommendation_eligible?: boolean;
  /** Adapter and server credential both present right now. Reported beside the score; never part of it. */
  execution_ready?: boolean;
  execution_status?: string | null;
  model_category?: ModelGroup | null;
  access_type?: string | null;
  pricing_category?: PricingCategory | null;
  free_tier_available?: boolean | null;
  /* Approved-ecosystem comparison; null/empty for legacy rows */
  ecosystem_category?: EcosystemCategory | null;
  category_role?: 'primary' | 'secondary' | null;
  feature_coverage?: number | null;
  matched_features?: string[];
  unmet_features?: string[];
  fit_breakdown?: Record<string, number>;
  external_url?: string | null;
  strengths?: string[];
  editorial_order?: number;
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
    adjustments: { dimension: string; factor: number; reason: string; origin?: 'explicit' | 'inferred' }[];
    hard_constraints: { kind: string; value: unknown; source: string }[];
    defaults_applied: string[]; warnings: string[]; precedence: string[];
  };
  candidates: EngineCandidate[];
  /** Pool members with no objective data: listed so the whole pool stays visible, but there is nothing to compare. */
  unscored_candidates?: Array<{ model_id: string; model_name: string; provider: string; metadata_status: string; recommendation_eligible?: boolean; execution_ready?: boolean; execution_status?: string | null }>;
  pool_summary?: { eligible: number; scored: number; unscored: number };
  exclusions: EngineExclusion[];
  normalization: { cost_basis: string; cost_method: string; latency_basis: string; uncertainty_penalty: number; missing_policy: string; notes: string[] } | null;
  selection: {
    selected_model_id: string | null; runner_up_ids: string[]; status: string; tie_break_applied?: string | null; score_margin?: number | null;
    weight_stability?: number | null; weight_margin?: number | null; weight_margin_rival?: string | null; confidence_level: 'high' | 'medium' | 'low'; confidence_value: number; caveats: string[];
    decision_status?: 'recommended' | 'qualified' | 'insufficient_evidence' | 'indistinguishable' | 'needs_clarification' | 'no_eligible_candidates';
    decision_reason?: string | null; alternative_ids?: string[]; evidence_gaps?: string[]; not_ranked?: { objective: string; tier: string; reason: string }[];
    /** Selection confidence is derived from the ranking only. Nothing a model answered can change it. */
    confidence_formula?: string;
    confidence_components?: { category_confidence?: number; ranking_margin?: number; feature_support?: number; score_margin?: number };
  };
  /** True for the approved ecosystem: AI Compass recommends and never runs a product. */
  recommendation_only?: boolean;
  /** The one ranking behind Best Match, Suggested and Candidates. */
  ranking?: EngineRankingRow[];
  best_match_id?: string;
  suggested_ids?: string[];
  explanation: {
    summary: string; why_selected: string[]; why_alternatives_ranked_lower: Record<string, unknown>[]; hard_constraints_applied: string[];
    influential_objectives: Record<string, unknown>[]; unavailable_data: string[]; tradeoffs: string[]; confidence_statement: string;
  };
  execution: {
    status: string; mode: string; final_model_id?: string | null; final_model_name?: string | null; attempts: EngineAttempt[]; escalated: boolean;
    escalation_reason?: string | null; total_cost_usd?: number | null; total_latency_ms?: number | null; blocked_reason?: string | null;
    prompt_sent_source?: string | null; notes: string[];
    escalation_events?: { sequence: number; from_model_id: string; to_model_id?: string | null; trigger: string; detail: string; original_response: string; outcome: string }[];
  };
  evaluation: {
    status: string; method: string; accepted?: boolean | null; checks: { name: string; passed: boolean; detail: string }[];
    heuristic_scores: Record<string, number>; judge_model?: string | null; notes: string[];
    decision?: { action: 'accept' | 'verify' | 'escalate' | 'none'; rule: string; reason: string; failed_checks: string[]; pending_checks: string[] } | null;
    confidence?: Record<string, unknown>;
    checks_not_run?: { check: string; reason: string }[];
  };
  stages: EngineStage[];
  candidate_pool: string;
  no_candidate_guidance: Record<string, unknown>;
  prompt_used: string;
  prompt_used_source: 'original' | 'optimized';
  routing_latency_ms: number;
  access?: { model_id?: string; execution_available?: boolean; credential_configured?: boolean | null; status?: string; next_step?: string; documentation_url?: string | null };
  counterfactuals?: EngineCounterfactual[];
  provenance?: EngineProvenance;
  confidence_report?: EngineConfidenceReport;
  executable_alternative?: { model_id: string | null; model_name?: string; provider?: string; rank?: number; score_gap_to_best_match?: number | null; statement: string; substituted: boolean } | null;
  catalogue_summary?: { catalogue_total: number; considered: number; excluded_by_registry: number; eligible: number; excluded_by_constraints: number; scored: number; selected: number; credentials_used_for_comparison: boolean; audience: string; category?: 'conversational' | 'developer_api'; intent_ambiguous?: boolean; pool_source?: string; category_resolved?: EcosystemCategory | null; category_members?: number | null };
  scoring_config?: { version: string; uncertainty_penalty: number; missing_policy: string; missing_prior?: number; near_tie_margin?: number; safe_weight_shift?: number } | null;
  trace_available?: boolean;
  recorded_at?: string;
}

export interface EngineProvenance {
  fingerprint: string; engine_version: string; scoring_version: string; reproducibility: string; inputs_hashed: string[];
  catalogue: { candidates: number; content_sha256: string; version: number | null; origin: string; published_at: string | null };
}

export interface EngineConfidenceComponent {
  name: string; value: number | null; kind: 'heuristic_estimate' | 'deterministic' | 'not_applicable'; calibrated: boolean; basis: string; detail: Record<string, unknown>;
}

export interface EngineConfidenceReport {
  components: EngineConfidenceComponent[]; combined: number | null; combined_note: string;
  calibration: { validated: boolean; labelled_outcomes: number; minimum_for_validation: number; can_validate: boolean; statement: string };
}

export interface EngineCounterfactual {
  kind: 'weight_shift' | 'constraint_relaxed';
  scenario: string;
  changed_input: string;
  changed: boolean;
  winner: { model_id: string; model_name: string; provider: string; robust_score: number; candidates: number; confidence_level: string };
  eligible_before?: number;
  eligible_after?: number;
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
  catalog_coverage?: CatalogCoverage | null;
}

/** Metadata-only coverage of the evaluated pool; nothing here was measured by running a model. */
export interface CatalogCoverage {
  metadata_only: boolean;
  evaluated_models: number;
  providers: number;
  recommendation_only_models: number;
  execution_ready_models: number;
  recommendation_only_share: number | null;
  models_with_missing_metadata: number;
  missing_metadata_share: number | null;
  selection_by_strategy: Array<{ strategy: string; selected_model_id: string | null; provider: string | null; execution_ready: boolean | null }>;
  note: string;
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

export type ModelGroup = 'conversational' | 'developer_api' | 'unclassified';
export type PricingCategory = 'completely_free' | 'free_tier_limited' | 'pay_as_you_go' | 'paid_subscription' | 'self_hosted_open_weight' | 'unknown';

export type PrimaryCategory = 'conversational' | 'developer' | 'application' | 'unclassified';

/** `GET /models/pool-stats` — computed on the server from the same list `/models` returns. */
export interface PoolStats {
  scope: string;
  pool_total: number;
  canonical_models: number;
  applications: number;
  primary: Record<string, number>;
  /** Approved ecosystem: hard cap, products per category (a product can serve more than one) and its members. */
  cap?: number;
  serving?: Record<string, number>;
  ecosystem?: { categories: Array<{ id: EcosystemCategory; label: string; primary_count: number; serving_count: number; members: Array<{ model_id: string; model_name: string; role: 'primary' | 'secondary' }> }>; secondary_memberships: Array<{ model_id: string; model_name: string; primary: EcosystemCategory; also_serves: EcosystemCategory[] }>; note: string };
  /** Recommendation groups; mutually exclusive, add up to the pool total. */
  categories?: { counts: Record<ModelGroup, number>; pricing: Record<string, number>; access: Record<string, number>; note: string };
  primary_labels: Record<string, string>;
  kinds: Record<string, Array<{ kind: string; label: string; count: number }>>;
  capabilities: { overlapping: boolean; note: string; counts: Record<string, number> };
  classification_basis: Record<string, number>;
  provider_offerings: { count: number; providers: number; note: string };
  pending_verification: number | null;
  retired: number | null;
  lineages_needing_review: number | null;
  integrity: { ok: boolean; checks: Array<{ check: string; ok: boolean; detail?: unknown }>; problems: unknown[] };
  /** Recommendation and execution counted separately, over inference models. The groups overlap. */
  access?: PoolAccess;
}

export interface PoolAccess {
  scope: string;
  catalog_models: number;
  recommendation_eligible: number;
  execution_ready: number;
  recommendation_only: number;
  provider_not_configured: number;
  adapter_unavailable: number;
  metadata_incomplete: number;
  metadata_stale: number;
  metadata_status: Record<string, number>;
  note: string;
}
