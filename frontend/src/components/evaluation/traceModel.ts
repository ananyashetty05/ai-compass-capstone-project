/**
 * Pure helpers for the XAI decision trace. Everything is derived from the recorded `EngineResult`;
 * nothing is invented, and missing data stays missing (null), never zero.
 */
import type { EngineCandidate, EngineResult } from '../../types';

export const DIMS = ['quality', 'cost', 'latency', 'reliability', 'risk', 'preference_alignment'] as const;
export type Dim = (typeof DIMS)[number];
export const DIM_LABEL: Record<Dim, string> = {
  quality: 'Quality', cost: 'Cost', latency: 'Speed', reliability: 'Reliability', risk: 'Risk control', preference_alignment: 'Task fit',
};

export const PROVENANCE_LABEL: Record<string, string> = {
  measured: 'Measured', observed: 'Measured (observed history)', registry_measured: 'Measured (registry)', observed_p50: 'Measured (observed history)',
  provider_published: 'Provider-reported', benchmark: 'Benchmark-derived', estimated: 'Estimated', registry_declared_capabilities: 'Derived from declared capabilities',
  unavailable: 'Unavailable', registry_estimate: 'Estimated', editorial_estimate: 'Editorial estimate', curated_pricing_category: 'Documented access class', vendor_published_strengths: 'Vendor-published',
};
export function provenanceLabel(p: string): string { return PROVENANCE_LABEL[p] ?? p.replace(/_/g, ' '); }

export type StepState = 'done' | 'skipped' | 'failed' | 'warn' | 'idle';
export interface FlowNode { id: string; label: string; state: StepState; summary: string; ms?: number }

const stageOf = (e: EngineResult, name: string) => e.stages.find((s) => s.name === name);
const humanStatus = (x: string) => x.replace(/_/g, ' ');
export const fmtMs = (ms: number | undefined) => (ms === undefined ? '' : `${ms < 10 ? ms.toFixed(1) : Math.round(ms)} ms`);

/**
 * The recommendation pipeline, in the order it really ran. AI Compass recommends and never generates an answer, so the flow
 * ends at the Best Match: there is no response, quality-check or escalation stage to draw.
 */
export function buildFlow(e: EngineResult): FlowNode[] {
  const stage = (id: string, label: string, name: string, fallback: string): FlowNode => {
    const s = stageOf(e, name);
    if (!s) return { id, label, state: 'idle', summary: fallback };
    return { id, label, state: s.status === 'completed' ? 'done' : s.status === 'failed' ? 'failed' : 'skipped', summary: s.detail || humanStatus(s.status), ms: s.duration_ms };
  };
  return [
    { id: 'query', label: 'Query received', state: 'done', summary: `${e.profile.tokens.input_tokens} input tokens (${e.profile.tokens.exact ? 'exact' : 'estimated'})` },
    stage('analysis', 'Query analysis', 'query_understanding', 'Not recorded'),
    stage('category', 'Category resolution', 'category_resolution', e.profile.category ? e.profile.category.label : 'Not recorded'),
    stage('constraints', 'Preferences & constraints', 'preference_resolution', 'Not recorded'),
    stage('filter', 'Category gate & filtering', 'hard_constraint_filtering', 'Not recorded'),
    stage('score', 'Fit scoring', 'multi_objective_scoring', 'Not recorded'),
    stage('select', 'Best Match & confidence', 'model_selection', 'Not recorded'),
  ];
}

export function selectedCandidate(e: EngineResult): EngineCandidate | null {
  return e.candidates.find((c) => c.model_id === e.selection.selected_model_id) ?? e.candidates[0] ?? null;
}

export interface Rejection { code: string; label: string; count: number; items: { id: string; name: string; reason: string; permanence: string }[] }
export function groupRejections(e: EngineResult): Rejection[] {
  const map = new Map<string, Rejection>();
  for (const x of e.exclusions) {
    const g = map.get(x.code) ?? { code: x.code, label: x.requirement, count: 0, items: [] };
    g.count += 1;
    g.items.push({ id: x.model_id, name: x.model_name ?? x.model_id, reason: x.reason, permanence: x.permanence });
    map.set(x.code, g);
  }
  return [...map.values()].sort((a, b) => b.count - a.count);
}

/** Dominant contribution of the winner and its margin over the runner-up on each dimension (real numbers only). */
export function decisiveFactor(e: EngineResult): { dim: Dim; share: number } | null {
  const top = selectedCandidate(e);
  if (!top) return null;
  const total = DIMS.reduce((a, d) => a + (top.contributions[d] ?? 0), 0);
  if (total <= 0) return null;
  const best = DIMS.map((d) => ({ dim: d, v: top.contributions[d] ?? 0 })).sort((a, b) => b.v - a.v)[0];
  return { dim: best.dim, share: best.v / total };
}

const pct = (x: number) => `${Math.round(x * 100)}%`;
const num = (x: number | null | undefined, d = 3) => (typeof x === 'number' && Number.isFinite(x) ? x.toFixed(d) : 'unavailable');

/** A self-contained Markdown report. Built only from the recorded trace. */
export function buildReport(e: EngineResult): string {
  const top = selectedCandidate(e);
  const L: string[] = [];
  L.push('# AI Compass — routing explainability report', '');
  L.push(`Engine ${e.version} · scoring ${e.scoring_version} · mode: ${e.mode} · status: ${e.status}`);
  if (e.recorded_at) L.push(`Recorded: ${e.recorded_at}`);
  L.push('', '## 1. What happened', e.explanation.summary, '');
  const p = e.profile;
  L.push('## 2. How the query was understood');
  L.push(`- Task: ${p.primary_intent.replace(/_/g, ' ')} · domain: ${p.domain} · complexity: ${p.complexity.category} (${num(p.complexity.score, 2)})`);
  if (p.category) L.push(`- Category: ${p.category.label} (confidence ${num(p.category.confidence, 2)}; rules fired: ${p.category.signals.join(', ') || 'none'})${p.category.features.length ? `; features asked for: ${p.category.features.map((f) => f.feature.replace(/_/g, ' ')).join(', ')}` : ''}`);
  if (p.audience) L.push(`- Intent: ${p.audience.kind}${p.audience.signals.length ? ` (rules fired: ${p.audience.signals.join(', ')})` : ''}${p.audience.required_model_types.length ? `; required model type: ${p.audience.required_model_types.join(', ')}` : ''}`);
  L.push(`- Required capabilities: ${p.required_capabilities.join(', ') || 'none beyond the task'} · modalities: ${p.required_modalities.join(', ')}`);
  L.push(`- Sensitivity: ${p.risk.sensitivity}${p.risk.recommends_strict_privacy ? ' (strict privacy recommended)' : ''}`);
  L.push('', '## 3. Constraints and weights');
  L.push(`- Weights (${e.preferences.weight_source.replace(/_/g, ' ')}): ` + DIMS.map((d) => `${DIM_LABEL[d]} ${pct(e.preferences.weights[d] ?? 0)}`).join(', '));
  L.push(`- Hard constraints: ${e.explanation.hard_constraints_applied.join('; ') || 'none set'}`);
  const cs = e.catalogue_summary;
  if (cs) L.push('', '## 4. Candidate funnel', `${cs.catalogue_total} catalogue entries → ${cs.considered} considered → ${cs.eligible} eligible after hard constraints → ${cs.scored} scored → ${cs.selected} selected. API credentials were not used for this comparison.`);
  const rej = groupRejections(e);
  if (rej.length) { L.push('', '### Why other models were removed'); for (const g of rej) L.push(`- ${g.count} × ${g.label}: ` + g.items.slice(0, 4).map((i) => i.name).join(', ') + (g.items.length > 4 ? ', …' : '')); }
  L.push('', '## 5. Why this model');
  if (top) L.push(`**${top.model_name}** (${top.provider}) ranked #1 of ${e.candidates.length} with robust score ${num(top.robust_score)}.`);
  for (const w of e.explanation.why_selected) L.push(`- ${w}`);
  for (const t of e.explanation.tradeoffs) L.push(`- Trade-off: ${t}`);
  L.push(`- ${e.explanation.confidence_statement}`);
  if (e.counterfactuals?.length) { L.push('', '### Counterfactuals (re-computed by re-running the router)'); for (const c of e.counterfactuals) L.push(`- ${c.scenario}: ${c.changed ? `**${c.winner.model_name}** would win instead` : 'the same model would still win'}.`); }
  L.push('', '## 6. Recommendation only');
  L.push('AI Compass recommends products and does not run them, so there is no response to evaluate, no quality check and no escalation. Confidence describes the ranking only.');
  if (e.selection.confidence_formula) L.push(`- Confidence ${num(e.selection.confidence_value, 3)} (${e.selection.confidence_level}): ${e.selection.confidence_formula}`);
  if (e.access?.next_step) L.push('', '## 7. Where to open it', e.access.next_step);
  L.push('', '## Limitations', ...(e.explanation.unavailable_data.length ? e.explanation.unavailable_data.map((u) => `- ${u}`) : ['- None recorded.']), '- Confidence is an uncalibrated engineering estimate, not a statistical probability.');
  return L.join('\n');
}


const DIM_PHRASE: Record<Dim, string> = {
  quality: 'quality', cost: 'low cost', latency: 'speed', reliability: 'reliability', risk: 'low risk', preference_alignment: 'task fit',
};

/** Describes a near-tie honestly: when the selected model is not the strict top scorer, say so and say what decided it. */
export function tieNote(e: EngineResult): string | null {
  const how = e.selection.tie_break_applied;
  if (!how) return null;
  const runner = e.candidates.find((c) => e.selection.runner_up_ids.includes(c.model_id));
  return `Exact tie${runner ? ` with ${runner.model_name}` : ''} (identical scores): decided by ${how}.`;
}

/** One short, data-grounded sentence on why the winner won. Built only from recorded contributions,
 *  constraints and stability; returns null when there is nothing to say. */
export function whyHeadline(e: EngineResult): string | null {
  const top = selectedCandidate(e);
  if (!top) return null;
  const ranked = DIMS.map((d) => ({ d, v: top.contributions[d] ?? 0 })).filter((x) => x.v > 0).sort((a, b) => b.v - a.v);
  const lead = ranked.slice(0, 2).map((x) => DIM_PHRASE[x.d]);
  if (e.candidates.length <= 1) return 'The only model that met every requirement of this query.';
  const first = e.selection.tie_break_applied
    ? `One of ${e.candidates.length} closely matched models; ${top.model_name} was chosen on a tie-break`
    : `Ranked first of ${e.candidates.length} eligible models${lead.length ? `, led by ${lead.join(' and ')}` : ''}`;
  return `${first}.`;
}
