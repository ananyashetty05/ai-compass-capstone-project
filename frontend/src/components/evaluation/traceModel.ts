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
  unavailable: 'Unavailable', registry_estimate: 'Estimated',
};
export function provenanceLabel(p: string): string { return PROVENANCE_LABEL[p] ?? p.replace(/_/g, ' '); }

export type StepState = 'done' | 'skipped' | 'failed' | 'warn' | 'idle';
export interface FlowNode { id: string; label: string; state: StepState; summary: string; lane: 'route' | 'respond'; ms?: number; action?: 'accept' | 'verify' | 'escalate' | null }

const stageOf = (e: EngineResult, name: string) => e.stages.find((s) => s.name === name);
const humanStatus = (x: string) => x.replace(/_/g, ' ');
export const fmtMs = (ms: number | undefined) => (ms === undefined ? '' : `${ms < 10 ? ms.toFixed(1) : Math.round(ms)} ms`);

export function buildFlow(e: EngineResult): FlowNode[] {
  const nodes: Omit<FlowNode, 'lane'>[] = [];
  const stage = (id: string, label: string, name: string, fallback: string): Omit<FlowNode, 'lane'> => {
    const s = stageOf(e, name);
    if (!s) return { id, label, state: 'idle', summary: fallback };
    return { id, label, state: s.status === 'completed' ? 'done' : s.status === 'failed' ? 'failed' : 'skipped', summary: s.detail || humanStatus(s.status), ms: s.duration_ms };
  };
  nodes.push({ id: 'query', label: 'Query received', state: 'done', summary: `${e.profile.tokens.input_tokens} input tokens (${e.profile.tokens.exact ? 'exact' : 'estimated'})` });
  nodes.push(stage('analysis', 'Query analysis', 'query_understanding', 'Not recorded'));
  nodes.push(stage('constraints', 'Preferences & constraints', 'preference_resolution', 'Not recorded'));
  nodes.push(stage('filter', 'Candidate filtering', 'hard_constraint_filtering', 'Not recorded'));
  nodes.push(stage('score', 'Multi-objective scoring', 'multi_objective_scoring', 'Not recorded'));
  nodes.push(stage('select', 'Model selected', 'model_selection', 'Not recorded'));
  const ex = e.execution;
  const ran = ex.attempts.some((a) => a.outcome === 'success');
  const recommendOnly = ex.status === 'not_requested';
  nodes.push({ id: 'generate', label: 'Response generation', state: ran ? 'done' : recommendOnly ? 'skipped' : 'failed',
    summary: recommendOnly ? 'Not run: recommendation mode' : ran ? `${ex.attempts.filter((a) => a.outcome === 'success').length} successful attempt(s)` : (ex.blocked_reason ?? 'No response was produced') });
  const ev = e.evaluation;
  nodes.push({ id: 'quality', label: 'Quality check', state: ev.status === 'completed' ? (ev.accepted ? 'done' : 'warn') : 'skipped',
    summary: ev.status === 'completed' ? `${ev.checks.filter((c) => c.passed).length}/${ev.checks.length} checks passed` : ev.status === 'not_requested' ? 'Not run: nothing to evaluate' : `Not run (${ev.status.replace(/_/g, ' ')})` });
  const act = ev.decision?.action;
  nodes.push({ id: 'decision', label: 'Accept / Verify / Escalate', state: !act || act === 'none' ? 'skipped' : act === 'accept' ? 'done' : act === 'verify' ? 'warn' : 'failed',
    summary: act && act !== 'none' ? `Decision: ${act}` : 'No decision: no response was evaluated' });
  const events = ex.escalation_events ?? [];
  nodes.push({ id: 'escalate', label: 'Adaptive escalation', state: events.length > 0 ? 'warn' : 'skipped', summary: events.length > 0 ? `${events.length} escalation(s)` : 'Not triggered' });
  nodes.push({ id: 'final', label: 'Final answer', state: ran ? 'done' : 'skipped', summary: ran ? (ex.final_model_name ?? 'Returned') : 'No answer: this run recommends a model' });
  const routeIds = new Set(['query', 'analysis', 'constraints', 'filter', 'score', 'select']);
  const out = nodes
    // Escalation only appears in the flow when it actually happened; otherwise the decision node says so.
    .filter((n) => n.id !== 'escalate' || events.length > 0)
    .map((n) => ({ ...n, lane: routeIds.has(n.id) ? ('route' as const) : ('respond' as const) }));
  const d = out.find((n) => n.id === 'decision');
  if (d) d.action = act === 'accept' || act === 'verify' || act === 'escalate' ? act : null;
  return out;
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
  L.push('', '## 6. Execution and evaluation');
  if (e.execution.status === 'not_requested') L.push('No model was run (recommendation mode), so there is no response to evaluate. No quality, latency or cost was measured.');
  else {
    for (const a of e.execution.attempts) L.push(`- Attempt ${a.attempt}: ${a.model_id} → ${a.outcome}${a.latency_ms != null ? `, ${Math.round(a.latency_ms)} ms (measured)` : ''}${a.cost_usd != null ? `, $${a.cost_usd.toFixed(6)} (computed)` : ''}${a.note ? ` — ${a.note}` : ''}`);
    for (const c of e.evaluation.checks) L.push(`- Check ${c.name}: ${c.passed ? 'passed' : 'failed'} — ${c.detail}`);
    if (e.evaluation.decision) L.push(`- Decision: **${e.evaluation.decision.action}** (${e.evaluation.decision.rule}) — ${e.evaluation.decision.reason}`);
    for (const n of e.evaluation.checks_not_run ?? []) L.push(`- Not run: ${n.check} — ${n.reason}`);
  }
  if (e.access) L.push('', '## 7. Access', `Execution access: ${e.access.execution_available ? 'ready' : (e.access.status ?? 'unknown').replace(/_/g, ' ')}. ${e.access.next_step ?? ''}`);
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
  const eps = e.scoring_config?.tie_epsilon;
  return `Near-tie${runner ? ` with ${runner.model_name}` : ''}${eps != null ? ` (scores within ${eps})` : ''}: decided by ${how}.`;
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
