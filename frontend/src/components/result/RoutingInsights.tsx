/**
 * "How this was decided" — the routing pipeline, the query analysis and
 * the filtering outcome for one routing run. Every figure comes from the
 * `RouteResponse`; nothing is estimated here.
 */
import { ArrowRight, Ban, Filter, LifeBuoy, ListChecks, ScanSearch } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Reveal } from '../ui/Reveal';
import { humanizeToken, formatPercent, formatInteger, formatDuration } from '../../utils/format';
import type { RouteResponse } from '../../types';

const bar = (v: number) => Math.max(0, Math.min(100, Math.round(v * 100)));

function formatConstraint(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (Array.isArray(value)) return value.length ? value.map(String).join(', ') : '—';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export function RoutingPipeline({ result }: { result: RouteResponse }) {
  const m = result.performance_metrics;
  const excluded = m.models_filtered ?? result.filtered_models.length;
  const steps = [
    { id: 'query', title: 'Query', value: `${result.query.length.toLocaleString()} characters` },
    { id: 'analysis', title: 'Analysis', value: `${humanizeToken(result.query_analysis.task_type)} · ${humanizeToken(result.query_analysis.domain)}` },
    { id: 'filter', title: 'Filtering', value: `${excluded} excluded` },
    { id: 'score', title: 'Scoring', value: `${m.candidates_evaluated ?? result.model_scores.length} scored` },
    { id: 'select', title: 'Selection', value: result.selected_model_name },
    { id: 'rec', title: 'Recommendation', value: result.final_model_name + (result.escalation_info.escalated ? ' (escalated)' : '') },
  ];
  return (
    <Reveal as="section" className="cx-card" ariaLabelledBy="pipe-title">
      <header className="cx-card-head">
        <div><p className="cx-kicker">Decision pipeline</p><h2 id="pipe-title">How this was decided</h2></div>
        <span className="cx-note-inline">Routing took {formatDuration(m.routing_latency_ms)}</span>
      </header>
      <ol className="cx-pipe">
        {steps.map((s, i) => (
          <li key={s.id} style={{ ['--i' as string]: i }}>
            <span className="cx-pipe-dot" aria-hidden="true">{i + 1}</span>
            <strong>{s.title}</strong>
            <span>{s.value}</span>
          </li>
        ))}
      </ol>
    </Reveal>
  );
}

export function QueryAnalysisCard({ result }: { result: RouteResponse }) {
  const q = result.query_analysis;
  const needs: [string, number][] = [
    ['Complexity', q.complexity],
    ['Quality requirement', q.quality_requirement],
    ['Reliability requirement', q.reliability_requirement],
    ['Risk level', q.risk_level],
    ['Latency requirement', q.latency_requirement],
    ['Cost sensitivity', q.cost_sensitivity],
    ['Context requirement', q.context_requirement],
  ];
  return (
    <Reveal as="section" className="cx-card" delay={1} ariaLabelledBy="qa-title">
      <header className="cx-card-head">
        <div><p className="cx-kicker">Query analysis</p><h2 id="qa-title">How the query was understood</h2></div>
        <ScanSearch aria-hidden="true" />
      </header>
      <p className="cx-chips">
        <span>Task · {humanizeToken(q.task_type)}</span>
        <span>Domain · {humanizeToken(q.domain)}</span>
        <span>≈ {formatInteger(q.estimated_tokens)} tokens</span>
        {typeof q.classification_confidence === 'number' ? <span>Confidence · {formatPercent(q.classification_confidence, 0)}</span> : null}
      </p>
      <ul className="cx-bars">
        {needs.map(([label, v]) => (
          <li className="cx-bar" key={label}>
            <span className="cx-bar-label">{label}</span>
            <span className="cx-bar-track" aria-hidden="true"><span className="cx-bar-fill" style={{ ['--w' as string]: `${bar(v)}%` }} /></span>
            <span className="cx-bar-value">{formatPercent(v, 0)}</span>
          </li>
        ))}
      </ul>
      {(q.required_modalities?.length || q.required_capabilities?.length) ? (
        <p className="cx-chips" aria-label="Detected requirements">
          {(q.required_modalities ?? []).map((x) => <span key={`m-${x}`}>Modality · {humanizeToken(x)}</span>)}
          {(q.required_capabilities ?? []).map((x) => <span key={`c-${x}`}>Needs · {humanizeToken(x)}</span>)}
        </p>
      ) : null}
      {q.uncertainty_notes?.length ? (
        <ul className="cx-notes">{q.uncertainty_notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
      ) : null}
      <p className="cx-note">Analysis method: {humanizeToken(q.analysis_method)}. Needs are scored 0–100%.</p>
    </Reveal>
  );
}

export function ConstraintsAndFilters({ result }: { result: RouteResponse }) {
  const constraints = Object.entries(result.routing_explanation.applied_constraints ?? {}).filter(([, v]) => v !== null && v !== undefined && !(Array.isArray(v) && v.length === 0) && v !== false);
  const filtered = result.filtered_models;
  return (
    <Reveal as="section" className="cx-card" delay={2} ariaLabelledBy="cf-title">
      <header className="cx-card-head">
        <div><p className="cx-kicker">Constraints</p><h2 id="cf-title">Applied constraints and exclusions</h2></div>
        <Filter aria-hidden="true" />
      </header>
      {constraints.length === 0 ? (
        <p className="cx-muted">No hard constraints were applied to this request.</p>
      ) : (
        <dl className="cx-kv">
          {constraints.map(([k, v]) => (<div key={k}><dt>{humanizeToken(k)}</dt><dd>{formatConstraint(v)}</dd></div>))}
        </dl>
      )}
      <details className="cx-details" open={filtered.length > 0 && filtered.length <= 5}>
        <summary><Ban aria-hidden="true" /> {filtered.length} candidate{filtered.length === 1 ? '' : 's'} excluded</summary>
        {filtered.length === 0 ? (
          <p className="cx-muted">Every candidate in the pool passed the filters.</p>
        ) : (
          <ul className="cx-rows">
            {filtered.map((f) => (
              <li key={f.model_id}><span className="cx-row-main"><strong>{f.model_id}</strong><span>{f.reason}</span></span></li>
            ))}
          </ul>
        )}
      </details>
    </Reveal>
  );
}

export function FallbackCard({ result }: { result: RouteResponse }) {
  const e = result.escalation_info;
  const fallback = result.routing_explanation.fallback_model_id ?? e.fallback_model_id;
  const reasons = result.routing_explanation.routing_reason ?? [];
  return (
    <Reveal as="section" className="cx-card" delay={3} ariaLabelledBy="fb-title">
      <header className="cx-card-head">
        <div><p className="cx-kicker">Safety net</p><h2 id="fb-title">Fallback and escalation</h2></div>
        <LifeBuoy aria-hidden="true" />
      </header>
      <dl className="cx-kv">
        <div><dt>Fallback model</dt><dd>{fallback ?? 'None recorded'}</dd></div>
        <div><dt>Escalated</dt><dd>{e.escalated ? 'Yes' : 'No'}</dd></div>
        <div><dt>Attempts</dt><dd>{e.attempts}</dd></div>
        <div><dt>Final status</dt><dd>{humanizeToken(e.final_status)}</dd></div>
        {e.escalated && e.escalation_reason ? <div><dt>Reason</dt><dd>{e.escalation_reason}</dd></div> : null}
      </dl>
      {reasons.length > 0 ? (
        <>
          <p className="cx-subhead"><ListChecks aria-hidden="true" /> Why it was chosen</p>
          <ul className="cx-notes">{reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
        </>
      ) : null}
      <Link to="/explanation" className="cx-link">Open the full explanation <ArrowRight aria-hidden="true" /></Link>
    </Reveal>
  );
}

export function RoutingInsights({ result }: { result: RouteResponse }) {
  return (
    <div className="cx-insights">
      <RoutingPipeline result={result} />
      <QueryAnalysisCard result={result} />
      <ConstraintsAndFilters result={result} />
      <FallbackCard result={result} />
    </div>
  );
}
