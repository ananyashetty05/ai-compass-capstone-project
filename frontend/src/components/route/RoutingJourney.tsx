/**
 * Routing journey — the ten decision stages as one consistent node diagram.
 *
 * Every node's status, timing and detail is read from `RouteResponse.engine` (backend stage records, the
 * resolved profile, selection, execution and evaluation). A node is "Completed" only when the backend
 * reported it so; stages that did not run say so and give the server's reason. Nothing is simulated.
 */
import { AlertTriangle, Brain, Check, CircleDashed, Compass, Filter, Gauge, Medal, Play, ScanSearch, Scale, ShieldCheck, SlidersHorizontal, X } from 'lucide-react';
import type { ReactNode } from 'react';
import { Reveal } from '../ui/Reveal';
import { humanizeToken, formatDuration, formatPercent } from '../../utils/format';
import type { EngineResult, EngineStage } from '../../types';

type NodeStatus = 'completed' | 'failed' | 'skipped' | 'not_run';

interface JourneyNode { key: string; label: string; icon: ReactNode; status: NodeStatus; ms: number | null; detail: string }

function fold(engine: EngineResult, names: string[]): { status: NodeStatus; ms: number | null; reason: string } {
  const found = names.map((n) => engine.stages.find((s) => s.name === n)).filter((s): s is EngineStage => !!s);
  if (found.length === 0) return { status: 'not_run', ms: null, reason: 'Not reported by the backend' };
  if (found.some((s) => s.status === 'failed')) return { status: 'failed', ms: found.reduce((a, s) => a + Math.max(0, s.duration_ms), 0), reason: found.find((s) => s.status === 'failed')?.detail ?? '' };
  if (found.every((s) => s.status === 'skipped' || s.status === 'not_run')) return { status: 'skipped', ms: null, reason: found[0]?.detail ?? 'Skipped' };
  return { status: 'completed', ms: found.filter((s) => s.status === 'completed').reduce((a, s) => a + Math.max(0, s.duration_ms), 0), reason: '' };
}

function buildNodes(engine: EngineResult): JourneyNode[] {
  const p = engine.profile;
  const cs = engine.catalogue_summary;
  const winner = engine.candidates.find((c) => c.model_id === engine.selection.selected_model_id);
  const ex = engine.execution;
  const ev = engine.evaluation;
  const exStage = fold(engine, ['execution']);
  const evStage = fold(engine, ['response_evaluation']);
  const decisionAction = ev.decision?.action && ev.decision.action !== 'none' ? ev.decision.action : null;
  const decisionRan = evStage.status === 'completed' && !!decisionAction;

  const u = fold(engine, ['query_understanding']);
  const pr = fold(engine, ['preference_resolution']);
  const fl = fold(engine, ['candidate_discovery', 'hard_constraint_filtering']);
  const sc = fold(engine, ['multi_objective_scoring']);
  const se = fold(engine, ['model_selection']);

  const nodes: JourneyNode[] = [
    { key: 'understand', label: 'Query understanding', icon: <ScanSearch />, ...u2(u, `${humanizeToken(p.complexity.category)} complexity · ≈${p.tokens.input_tokens} input tokens`) },
    { key: 'intent', label: 'Intent & task', icon: <Brain />, ...u2(u, `${humanizeToken(p.primary_intent)} · ${humanizeToken(p.domain)}`) },
    { key: 'requirements', label: 'Requirements', icon: <ShieldCheck />, ...u2(pr, `${engine.preferences.hard_constraints.length} hard constraint(s) · ${p.required_capabilities.length} capability need(s)`) },
    { key: 'preferences', label: 'Preference analysis', icon: <SlidersHorizontal />, ...u2(pr, `${humanizeToken(engine.preferences.weight_source)} weights · ${engine.preferences.adjustments.length} adjustment(s)`) },
    { key: 'filter', label: 'Candidate filtering', icon: <Filter />, ...u2(fl, cs ? `${cs.eligible} eligible · ${cs.excluded_by_constraints + cs.excluded_by_registry} excluded` : `${engine.exclusions.length} excluded`) },
    { key: 'optimise', label: 'Multi-objective scoring', icon: <Scale />, ...u2(sc, `${engine.pool_summary?.scored ?? engine.candidates.length} candidate(s) scored`) },
    { key: 'select', label: 'Model selection', icon: <Medal />, ...u2(se, winner ? `${winner.model_name} · ${humanizeToken(engine.selection.confidence_level)} confidence` : humanizeToken(engine.selection.status)) },
    { key: 'execute', label: 'Model execution', icon: <Play />, ...u2(exStage, exStage.status === 'completed' ? `${humanizeToken(ex.status)}${ex.final_model_name ? ` · ${ex.final_model_name}` : ''}` : ex.blocked_reason || 'Recommendation only — no model was run') },
    { key: 'evaluate', label: 'Response evaluation', icon: <Gauge />, ...u2(evStage, evStage.status === 'completed' ? `${humanizeToken(ev.status)} · ${ev.checks.filter((c) => c.passed).length}/${ev.checks.length} checks passed` : 'No response to evaluate') },
    { key: 'decision', label: 'Accept or escalate', icon: <Compass />, status: decisionRan ? 'completed' : 'not_run', ms: null,
      detail: decisionRan ? `${humanizeToken(decisionAction ?? '')}${ex.escalated ? ' · escalated' : ''}` : 'Needs an executed, evaluated response' },
  ];
  // Paired nodes share one backend step; show its timing once, on the first of the pair.
  nodes[1].ms = null;
  nodes[3].ms = null;
  return nodes;
}

function u2(f: { status: NodeStatus; ms: number | null; reason: string }, detail: string) {
  return { status: f.status, ms: f.ms, detail: f.status === 'completed' ? detail : f.reason || detail };
}

const STATUS_TEXT: Record<NodeStatus, string> = { completed: 'Completed', failed: 'Failed', skipped: 'Not run', not_run: 'Not run' };

export function RoutingJourney({ engine }: { engine: EngineResult }) {
  const nodes = buildNodes(engine);
  const done = nodes.filter((n) => n.status === 'completed').length;
  return (
    <Reveal as="section" className="cx-card rj" ariaLabelledBy="rj-title">
      <header className="cx-card-head">
        <div><p className="cx-kicker">Routing journey</p><h2 id="rj-title">From query to decision</h2></div>
        <span className="cx-note-inline">{done} of {nodes.length} stages ran · status reported by the backend</span>
      </header>
      <ol className="rj-track">
        {nodes.map((n, i) => (
          <li key={n.key} className="rj-node" data-status={n.status} style={{ ['--i' as string]: i }}>
            <span className="rj-badge" aria-hidden="true">{n.status === 'completed' ? <Check /> : n.status === 'failed' ? <X /> : <CircleDashed />}</span>
            <span className="rj-icon" aria-hidden="true">{n.icon}</span>
            <span className="rj-body">
              <span className="rj-step">Stage {i + 1}</span>
              <strong>{n.label}</strong>
              <span className="rj-detail">{n.detail}</span>
            </span>
            <span className="rj-meta">
              <span className="rj-status">{n.status === 'failed' ? <AlertTriangle aria-hidden="true" /> : null}{STATUS_TEXT[n.status]}</span>
              {n.ms !== null ? <span className="rj-time">{formatDuration(n.ms)}</span> : null}
            </span>
          </li>
        ))}
      </ol>
      <p className="cx-note rj-foot">Stages 1–2 come from one backend step, as do 3–4; the timing is shown once, on the first of each pair. Selection confidence: {formatPercent(engine.selection.confidence_value, 0)}.</p>
    </Reveal>
  );
}
