/**
 * Domain constants: routing objectives, groups and the architecture
 * stage list. Keeping these in one place stops the Dashboard,
 * RouteQuery, Explanation and Profile pages from drifting apart.
 */
import type { RoutingObjective } from '../types';

export interface ObjectiveMeta {
  key: RoutingObjective;
  label: string;
  shortLabel: string;
  description: string;
  /** Whether a higher stored value is better for the user. */
  higherIsBetter: boolean;
  scoreField: keyof ObjectiveScoreFields;
}

export interface ObjectiveScoreFields {
  quality_score: number;
  cost_score: number;
  latency_score: number;
  reliability_score: number;
  risk_score: number;
  preference_alignment: number;
  overall_score: number;
}

export const OBJECTIVES: ObjectiveMeta[] = [
  {
    key: 'quality',
    label: 'Quality',
    shortLabel: 'Quality',
    description: 'How well the model’s capability answers match the quality requirement of this query.',
    higherIsBetter: true,
    scoreField: 'quality_score',
  },
  {
    key: 'cost',
    label: 'Cost',
    shortLabel: 'Cost',
    description: 'Cost efficiency, derived as the inverse of the normalised configured cost.',
    higherIsBetter: true,
    scoreField: 'cost_score',
  },
  {
    key: 'latency',
    label: 'Latency',
    shortLabel: 'Latency',
    description: 'Speed, derived as the inverse of the normalised configured latency.',
    higherIsBetter: true,
    scoreField: 'latency_score',
  },
  {
    key: 'reliability',
    label: 'Reliability',
    shortLabel: 'Reliability',
    description: 'The provider-backed reliability metadata for the model.',
    higherIsBetter: true,
    scoreField: 'reliability_score',
  },
  {
    key: 'risk',
    label: 'Risk / Privacy',
    shortLabel: 'Risk',
    description: 'Safety, derived as the inverse of the configured risk level. Higher is safer.',
    higherIsBetter: true,
    scoreField: 'risk_score',
  },
];

export const OBJECTIVE_KEYS = OBJECTIVES.map((o) => o.key);

export const PREFERENCE_ALIGNMENT_META: ObjectiveMeta = {
  key: 'quality', // placeholder key; only scoreField/label are used
  label: 'Preference Alignment',
  shortLabel: 'Preference',
  description: 'How closely the model’s capabilities match the task and domain detected in the query.',
  higherIsBetter: true,
  scoreField: 'preference_alignment',
};

export function objectiveByKey(key: string): ObjectiveMeta | undefined {
  return OBJECTIVES.find((o) => o.key === key);
}

/* ------------------------------------------------------------------ *
 * User groups — mirrors GROUP_DESCRIPTIONS in the backend schema
 * ------------------------------------------------------------------ */

export interface GroupMeta {
  id: string;
  label: string;
  description: string;
}

export const USER_GROUPS: GroupMeta[] = [
  { id: 'student', label: 'Student', description: 'Cost-focused, quality-aware' },
  { id: 'developer', label: 'Developer', description: 'Quality and speed, reliability-first' },
  { id: 'organization', label: 'Organization', description: 'Reliability and privacy, cost-conscious' },
  { id: 'researcher', label: 'Researcher', description: 'Maximum quality, reliability-focused' },
  { id: 'professional', label: 'Professional', description: 'Quality and speed, privacy-aware' },
];

export function groupLabel(id: string | null | undefined): string {
  if (!id) return 'Unassigned';
  return USER_GROUPS.find((g) => g.id === id.toLowerCase())?.label ?? id.charAt(0).toUpperCase() + id.slice(1);
}

export function groupDescription(id: string | null | undefined): string {
  if (!id) return 'No user group is associated with this account.';
  return (
    USER_GROUPS.find((g) => g.id === id.toLowerCase())?.description ??
    'Routing preferences are applied directly for this profile.'
  );
}

/* ------------------------------------------------------------------ *
 * Routing pipeline stages
 *
 * These describe the *routing* work AI Compass performs. The backend
 * returns a single synchronous payload, so the UI never animates
 * through them as if they were live — they are rendered as a compact
 * summary of a completed decision.
 *
 * Note the boundary: "Response Generation", "Response Evaluation" and
 * "Escalation" belong to the provider call that follows the decision,
 * not to the router. They are included so the sequence reads end to
 * end, but they are marked as post-decision so no surface implies AI
 * Compass produced the text.
 * ------------------------------------------------------------------ */

export type PipelineStageState = 'done' | 'current' | 'pending' | 'unknown' | 'escalated';

export interface PipelineStage {
  id: string;
  label: string;
  /** Very short label for the compact horizontal stepper. */
  shortLabel: string;
  /** Short description of what the backend computes in this stage. */
  detail: string;
  /** True for stages performed by the provider call, after the decision. */
  postDecision?: boolean;
}

export const PIPELINE_STAGES: PipelineStage[] = [
  { id: 'analysis', label: 'Query Analysis', shortLabel: 'Analyse', detail: 'Task, domain, complexity, context, quality, cost and risk requirements.' },
  { id: 'candidates', label: 'Candidate Models', shortLabel: 'Candidates', detail: 'Every active provider model in the pool, before any constraint is applied.' },
  { id: 'filtering', label: 'Candidate Filtering', shortLabel: 'Filter', detail: 'Provider models excluded from the pool by hard constraints.' },
  { id: 'scoring', label: 'Multi-Objective Scoring', shortLabel: 'Score', detail: 'Per-model scores across quality, cost, latency, reliability, risk and alignment.' },
  { id: 'selection', label: 'Selected Provider Model', shortLabel: 'Select', detail: 'The provider model with the highest overall routing score under your saved weights.' },
  { id: 'recommendation', label: 'Recommendation', shortLabel: 'Recommend', detail: 'The selected provider model and the prompt adapted for it.' },
  { id: 'generation', label: 'Response Generation', shortLabel: 'Generate', detail: 'Response written by the selected provider model. AI Compass does not generate it.', postDecision: true },
  { id: 'evaluation', label: 'Response Evaluation', shortLabel: 'Evaluate', detail: 'Deterministic quality, relevance, completeness and risk evaluation of the provider response.', postDecision: true },
  { id: 'escalation', label: 'Escalation if Required', shortLabel: 'Escalate', detail: 'Adaptive retry on the next-best provider model when acceptance criteria are not met.', postDecision: true },
  { id: 'final', label: 'Final Response', shortLabel: 'Respond', detail: 'The accepted response, delivered from the provider model that generated it.', postDecision: true },
];

/** The routing stages proper — what AI Compass itself is responsible for. */
export const ROUTING_STAGES = PIPELINE_STAGES.filter((stage) => !stage.postDecision);

/** The post-decision provider stages, shown separately. */
export const POST_DECISION_STAGES = PIPELINE_STAGES.filter((stage) => stage.postDecision);

/**
 * The single sentence that names the system for what it is. Used
 * wherever a surface has room for one line of framing, so no page has
 * to invent its own explanation of the same boundary.
 */
export const ROUTING_LAYER_STATEMENT =
  'AI Compass is the routing layer. It selects the provider model; the provider model generates the response.';

export const ARCHITECTURE_FLOW: { label: string; note: string }[] = [
  { label: 'User Profile', note: 'Fixed group + saved preferences' },
  { label: 'Query', note: 'Submitted by the user' },
  { label: 'Routing layer — Query Analysis', note: 'Task, domain, complexity, risk' },
  { label: 'Routing layer — Candidate Models', note: 'The provider models available' },
  { label: 'Routing layer — Candidate Filtering', note: 'Constraint-based elimination' },
  { label: 'Routing layer — Multi-Objective Scoring', note: 'Weighted scoring' },
  { label: 'Selected Provider Model', note: 'One model chosen from the pool' },
  { label: 'Response Generation', note: 'Written by the provider model' },
  { label: 'Response Evaluation', note: 'Acceptance criteria' },
  { label: 'Escalation if Required', note: 'Adaptive fallback to the next-best model' },
];

/* ------------------------------------------------------------------ *
 * Example prompts — research-relevant, not product marketing
 * ------------------------------------------------------------------ */

export const EXAMPLE_QUERIES: { label: string; text: string }[] = [
  {
    label: 'Concurrency',
    text: 'Explain why a distributed system might experience a race condition and how to prevent it.',
  },
  {
    label: 'Algorithms',
    text: 'Write a Python function that finds the longest common subsequence of two strings and explain its complexity.',
  },
  {
    label: 'Concepts',
    text: 'What are the key differences between supervised and unsupervised learning?',
  },
  {
    label: 'Analysis',
    text: 'Summarise the main causes of the 2008 financial crisis and the policy responses to it.',
  },
  {
    label: 'Reasoning',
    text: 'A train travels 120 km in 90 minutes. If it maintains the same average speed, how long will 400 km take? Show the reasoning.',
  },
];
