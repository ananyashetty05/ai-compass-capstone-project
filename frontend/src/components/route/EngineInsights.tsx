/**
 * Route Query Engine 2.0 — decision insights.
 *
 * Every value shown here comes from `RouteResponse.engine`. Nothing is estimated in the browser, and stages
 * that did not run are shown as skipped with the server's reason. Metrics keep their provenance label.
 */
import { AlertTriangle, Ban, CheckCircle2, CircleDashed, Gauge, ListChecks, Network, ScanSearch, Scale, Siren, XCircle } from 'lucide-react';
import { Reveal } from '../ui/Reveal';
import { humanizeToken, formatPercent, formatInteger, formatDuration, formatUsd } from '../../utils/format';
import type { EngineCandidate, EngineResult, EngineStage } from '../../types';

const pct = (v: number | null | undefined) => (v === null || v === undefined ? '—' : formatPercent(v, 0));
const w = (v: number | null | undefined) => `${Math.max(0, Math.min(100, Math.round((v ?? 0) * 100)))}%`;
const DIMS = ['quality', 'cost', 'latency', 'reliability', 'risk', 'preference_alignment'] as const;
const DIM_LABEL: Record<string, string> = {
  quality: 'Quality', cost: 'Cost', latency: 'Latency', reliability: 'Reliability', risk: 'Safety', preference_alignment: 'Task fit',
};

function StageIcon({ status }: { status: EngineStage['status'] }) {
  if (status === 'completed') return <CheckCircle2 aria-hidden="true" className="eng-ok" />;
  if (status === 'failed') return <XCircle aria-hidden="true" className="eng-bad" />;
  return <CircleDashed aria-hidden="true" className="eng-muted" />;
}

export function PipelineTrace({ engine }: { engine: EngineResult }) {
  const total = engine.stages.reduce((sum, s) => (s.status === 'skipped' ? sum : sum + Math.max(0, s.duration_ms)), 0);
  return (
    <Reveal as="section" className="cx-card" ariaLabelledBy="eng-pipe-title">
      <header className="cx-card-head">
        <div><p className="cx-kicker">Decision pipeline</p><h2 id="eng-pipe-title">What actually ran</h2></div>
        <span className="cx-note-inline">{formatDuration(engine.routing_latency_ms)} total · engine {engine.version}</span>
      </header>
      <ol className="eng-stages">
        {engine.stages.map((s, i) => (
          <li key={s.name} className={`eng-stage eng-stage--${s.status}`} style={{ ['--i' as string]: i }}>
            <StageIcon status={s.status} />
            <span className="eng-stage-main"><strong>{s.label}</strong>{s.detail ? <span>{s.detail}</span> : null}</span>
            <span className="eng-stage-time">{s.status === 'skipped' ? 'skipped' : formatDuration(s.duration_ms)}</span>
            {s.status !== 'skipped' && total > 0 ? (
              <span className="eng-stage-bar" aria-hidden="true" title={`${Math.round((Math.max(0, s.duration_ms) / total) * 100)}% of measured stage time`}>
                <i style={{ width: `${Math.max(2, (Math.max(0, s.duration_ms) / total) * 100)}%` }} />
              </span>
            ) : null}
          </li>
        ))}
      </ol>
    </Reveal>
  );
}

export function QueryUnderstanding({ engine }: { engine: EngineResult }) {
  const p = engine.profile;
  const comps = Object.entries(p.complexity.components);
  return (
    <Reveal as="section" className="cx-card" delay={1} ariaLabelledBy="eng-qu-title">
      <header className="cx-card-head">
        <div><p className="cx-kicker">Query understanding</p><h2 id="eng-qu-title">How the request was read</h2></div>
        <ScanSearch aria-hidden="true" />
      </header>
      <p className="cx-chips">
        <span>Intent · {humanizeToken(p.primary_intent)}</span>
        {p.secondary_intents.map((i) => <span key={i.name}>+ {humanizeToken(i.name)}</span>)}
        <span>Domain · {humanizeToken(p.domain)}</span>
        <span>Complexity · {humanizeToken(p.complexity.category)} ({pct(p.complexity.score)})</span>
        <span>≈ {formatInteger(p.tokens.input_tokens)} in / {formatInteger(p.tokens.output_tokens)} out tokens (estimate)</span>
        {p.structured_output ? <span>Output · {p.structured_output}</span> : null}
        {p.risk.sensitivity !== 'none' ? <span>Sensitivity · {p.risk.sensitivity}</span> : null}
      </p>
      <ul className="cx-bars">
        {comps.map(([k, v]) => (
          <li className="cx-bar" key={k}>
            <span className="cx-bar-label">{humanizeToken(k)}</span>
            <span className="cx-bar-track" aria-hidden="true"><span className="cx-bar-fill" style={{ ['--w' as string]: w(v) }} /></span>
            <span className="cx-bar-value">{pct(v)}</span>
          </li>
        ))}
      </ul>
      {(p.explicit_requirements.length > 0 || p.inferred_requirements.length > 0) && (
        <p className="cx-chips" aria-label="Detected requirements">
          {p.explicit_requirements.map((r, i) => <span key={`e${i}`} title="Stated in your request">Stated · {humanizeToken(r.kind)}: {r.value}</span>)}
          {p.inferred_requirements.map((r, i) => <span key={`i${i}`} title={r.evidence || 'Inferred by the analyzer'}>Inferred · {humanizeToken(r.kind)}: {r.value}</span>)}
        </p>
      )}
      {p.ambiguities.length > 0 && (
        <ul className="cx-notes">
          {p.ambiguities.map((a, i) => (
            <li key={i}><strong>{a.severity === 'major' ? 'Needs clarification' : 'Note'}:</strong> {a.message}{a.clarifying_question ? ` ${a.clarifying_question}` : ''}</li>
          ))}
        </ul>
      )}
      {p.risk.indicators.length > 0 && (
        <ul className="cx-notes">
          {p.risk.indicators.map((r, i) => <li key={i}><AlertTriangle aria-hidden="true" className="eng-warn" /> {r.note} ({r.level}, {r.count} match{r.count === 1 ? '' : 'es'}; matched text is not stored)</li>)}
        </ul>
      )}
      <p className="cx-note">Method: {humanizeToken(p.analysis_method)}. This is a rule-based reading, not a model judgement, and token counts are estimates.</p>
    </Reveal>
  );
}

export function PreferencesPanel({ engine }: { engine: EngineResult }) {
  const pr = engine.preferences;
  return (
    <Reveal as="section" className="cx-card" delay={2} ariaLabelledBy="eng-pref-title">
      <header className="cx-card-head">
        <div><p className="cx-kicker">Preferences</p><h2 id="eng-pref-title">Weights and hard constraints</h2></div>
        <Scale aria-hidden="true" />
      </header>
      <p className="cx-muted">Weights from {humanizeToken(pr.weight_source)}{pr.adjustments.length ? `, adjusted by ${pr.adjustments.length} query-derived factor(s) (capped at 1.5×)` : ''}.</p>
      <ul className="cx-bars">
        {DIMS.map((d) => (
          <li className="cx-bar" key={d}>
            <span className="cx-bar-label">{DIM_LABEL[d]}</span>
            <span className="cx-bar-track" aria-hidden="true"><span className="cx-bar-fill" style={{ ['--w' as string]: w(pr.weights[d]) }} /></span>
            <span className="cx-bar-value">{pct(pr.weights[d])}</span>
          </li>
        ))}
      </ul>
      {pr.adjustments.length > 0 && <ul className="cx-notes">{pr.adjustments.map((a, i) => <li key={i}>{DIM_LABEL[a.dimension] ?? a.dimension} ×{a.factor.toFixed(2)} — {a.reason}</li>)}</ul>}
      {pr.hard_constraints.length === 0
        ? <p className="cx-muted">No explicit hard constraints were set.</p>
        : <dl className="cx-kv">{pr.hard_constraints.map((c, i) => <div key={i}><dt>{humanizeToken(c.kind)}</dt><dd>{Array.isArray(c.value) ? c.value.join(', ') : String(c.value)} <small>({humanizeToken(c.source)})</small></dd></div>)}</dl>}
      {pr.warnings.length > 0 && <ul className="cx-notes">{pr.warnings.map((x, i) => <li key={i}>{x}</li>)}</ul>}
    </Reveal>
  );
}

function CandidateRow({ c, top }: { c: EngineCandidate; top: boolean }) {
  return (
    <tr className={top ? 'eng-row-top' : undefined}>
      <th scope="row">
        <span className="eng-rank">#{c.rank}</span>
        <span className="eng-model"><strong>{c.model_name}</strong><small>{c.provider}</small></span>
      </th>
      <td className="eng-num" title="Robust score: weighted utility with a penalty for low-confidence inputs">{c.robust_score.toFixed(3)}</td>
      {DIMS.map((d) => {
        const v = c.utilities[d];
        const ev = c.evidence[d];
        return (
          <td key={d} className={`eng-num${v === null || v === undefined ? ' eng-missing' : ''}`}
            title={ev ? `${humanizeToken(ev.provenance)} · confidence ${pct(ev.confidence)}${ev.note ? ` · ${ev.note}` : ''}` : undefined}>
            {v === null || v === undefined ? 'n/a' : pct(v)}
          </td>
        );
      })}
      <td className="eng-num">{pct(c.confidence)}</td>
      <td className="eng-num">{c.estimated_cost_usd === null ? 'unknown' : formatUsd(c.estimated_cost_usd)}</td>
      <td>{c.pareto_optimal ? <span className="eng-tag">Pareto</span> : <span className="eng-tag eng-tag--dim" title={`Dominated by ${c.dominated_by.join(', ')}`}>dominated</span>}</td>
    </tr>
  );
}

export function CandidateComparison({ engine }: { engine: EngineResult }) {
  const rows = engine.candidates.slice(0, 12);
  if (!rows.length) return null;
  const n = engine.normalization;
  return (
    <Reveal as="section" className="cx-card" delay={2} ariaLabelledBy="eng-cand-title">
      <header className="cx-card-head">
        <div><p className="cx-kicker">Candidates</p><h2 id="eng-cand-title">Scored comparison</h2></div>
        <span className="cx-note-inline">{engine.candidates.length} eligible · pool: {humanizeToken(engine.candidate_pool)}</span>
      </header>
      <div className="eng-table-wrap" role="region" aria-label="Candidate comparison" tabIndex={0}>
        <table className="eng-table">
          <thead>
            <tr><th scope="col">Model</th><th scope="col">Score</th>{DIMS.map((d) => <th key={d} scope="col">{DIM_LABEL[d]}</th>)}<th scope="col">Data conf.</th><th scope="col">Est. $/req</th><th scope="col">Frontier</th></tr>
          </thead>
          <tbody>{rows.map((c, i) => <CandidateRow key={c.model_id} c={c} top={i === 0} />)}</tbody>
        </table>
      </div>
      <p className="cx-note">
        “n/a” means the registry has no value; it is never treated as zero or as best, and it lowers confidence. Hover a cell for its provenance.
        {n ? ` Cost: ${humanizeToken(n.cost_basis)}; latency: ${humanizeToken(n.latency_basis)}.` : ''}
      </p>
    </Reveal>
  );
}

export function ExclusionsPanel({ engine }: { engine: EngineResult }) {
  const ex = engine.exclusions;
  const guidance = engine.no_candidate_guidance as { suggestions?: string[] };
  return (
    <Reveal as="section" className="cx-card" delay={3} ariaLabelledBy="eng-ex-title">
      <header className="cx-card-head">
        <div><p className="cx-kicker">Hard-constraint filtering</p><h2 id="eng-ex-title">Excluded before scoring</h2></div>
        <Ban aria-hidden="true" />
      </header>
      {ex.length === 0 ? <p className="cx-muted">Every candidate passed the hard constraints.</p> : (
        <details className="cx-details" open={ex.length <= 5}>
          <summary>{ex.length} candidate{ex.length === 1 ? '' : 's'} excluded</summary>
          <ul className="cx-rows">
            {ex.map((e) => (
              <li key={`${e.model_id}-${e.code}`}>
                <span className="cx-row-main"><strong>{e.model_name ?? e.model_id}</strong><span>{e.reason}</span></span>
                <span className="eng-tag eng-tag--dim" title={e.requirement}>{humanizeToken(e.code)} · {e.permanence}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
      {guidance.suggestions?.length ? <ul className="cx-notes">{guidance.suggestions.map((s, i) => <li key={i}>{s}</li>)}</ul> : null}
    </Reveal>
  );
}

export function DecisionExplanation({ engine }: { engine: EngineResult }) {
  const e = engine.explanation;
  const s = engine.selection;
  return (
    <Reveal as="section" className="cx-card" delay={3} ariaLabelledBy="eng-exp-title">
      <header className="cx-card-head">
        <div><p className="cx-kicker">Selection</p><h2 id="eng-exp-title">Why this model</h2></div>
        <span className={`eng-conf eng-conf--${s.confidence_level}`}><Gauge aria-hidden="true" /> {humanizeToken(s.confidence_level)} confidence · {pct(s.confidence_value)}</span>
      </header>
      <p>{e.summary}</p>
      {e.why_selected.length > 0 && <ul className="cx-notes">{e.why_selected.map((x, i) => <li key={i}>{x}</li>)}</ul>}
      <dl className="cx-kv">
        <div><dt>Margin over runner-up</dt><dd>{s.score_margin === null || s.score_margin === undefined ? '—' : s.score_margin.toFixed(3)}</dd></div>
        <div><dt>Stable under ±20% weight changes</dt><dd>{pct(s.weight_stability)}</dd></div>
        {s.tie_break_applied ? <div><dt>Tie-break</dt><dd>{s.tie_break_applied}</dd></div> : null}
      </dl>
      {e.tradeoffs.length > 0 && (<><p className="cx-subhead"><ListChecks aria-hidden="true" /> Trade-offs</p><ul className="cx-notes">{e.tradeoffs.map((x, i) => <li key={i}>{x}</li>)}</ul></>)}
      {(e.unavailable_data.length > 0 || s.caveats.length > 0) && (
        <><p className="cx-subhead"><AlertTriangle aria-hidden="true" /> Limits of this decision</p>
          <ul className="cx-notes">{[...s.caveats, ...e.unavailable_data].map((x, i) => <li key={i}>{x}</li>)}</ul></>
      )}
      <p className="cx-note">{e.confidence_statement}</p>
    </Reveal>
  );
}

export function ExecutionPanel({ engine }: { engine: EngineResult }) {
  const x = engine.execution;
  const ev = engine.evaluation;
  const label: Record<string, string> = {
    not_requested: 'Recommendation only — no model was run', blocked: 'Blocked', succeeded: 'Executed', failed: 'Failed', budget_exhausted: 'Budget exhausted',
  };
  return (
    <Reveal as="section" className="cx-card" delay={4} ariaLabelledBy="eng-run-title">
      <header className="cx-card-head">
        <div><p className="cx-kicker">Execution</p><h2 id="eng-run-title">{label[x.status] ?? humanizeToken(x.status)}</h2></div>
        <Network aria-hidden="true" />
      </header>
      {x.blocked_reason && <p className="cx-muted"><Siren aria-hidden="true" className="eng-warn" /> {x.blocked_reason}</p>}
      {x.attempts.length > 0 && (
        <div className="eng-table-wrap" role="region" aria-label="Execution attempts" tabIndex={0}>
          <table className="eng-table">
            <thead><tr><th scope="col">#</th><th scope="col">Model</th><th scope="col">Outcome</th><th scope="col">Latency</th><th scope="col">Tokens in/out</th><th scope="col">Cost</th></tr></thead>
            <tbody>
              {x.attempts.map((a) => (
                <tr key={a.attempt}>
                  <td className="eng-num">{a.attempt}</td><td>{a.model_id}</td>
                  <td>{humanizeToken(a.outcome)}{a.error_kind ? ` (${humanizeToken(a.error_kind)}${a.retryable ? ', retryable' : ''})` : ''}{a.note ? ` — ${a.note}` : ''}</td>
                  <td className="eng-num">{a.latency_ms ? formatDuration(a.latency_ms) : '—'}</td>
                  <td className="eng-num">{a.input_tokens ?? '—'} / {a.output_tokens ?? '—'}</td>
                  <td className="eng-num">{a.cost_usd === null || a.cost_usd === undefined ? '—' : formatUsd(a.cost_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {x.escalated && <p className="cx-muted">Escalated to {x.final_model_name ?? x.final_model_id}: {humanizeToken(x.escalation_reason ?? 'unspecified')}.</p>}
      {x.notes.length > 0 && <ul className="cx-notes">{x.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>}
      <p className="cx-subhead">Response evaluation — {humanizeToken(ev.status)}</p>
      {ev.checks.length > 0 && (
        <ul className="cx-rows">
          {ev.checks.map((c) => (
            <li key={c.name}><span className="cx-row-main"><strong>{humanizeToken(c.name)}</strong><span>{c.detail}</span></span><span className={c.passed ? 'eng-ok' : 'eng-bad'}>{c.passed ? 'pass' : 'fail'}</span></li>
          ))}
        </ul>
      )}
      {ev.notes.map((n, i) => <p key={i} className="cx-note">{n}</p>)}
    </Reveal>
  );
}

export function EngineDetails({ engine }: { engine: EngineResult }) {
  const n = engine.normalization;
  return (
    <details className="cx-card cx-details eng-adv">
      <summary>Advanced details</summary>
      <dl className="cx-kv">
        <div><dt>Engine / scoring version</dt><dd>{engine.version} / {engine.scoring_version}</dd></div>
        <div><dt>Prompt submitted</dt><dd>{humanizeToken(engine.prompt_used_source)}</dd></div>
        {n && <><div><dt>Missing-data policy</dt><dd>{humanizeToken(n.missing_policy)}</dd></div>
          <div><dt>Uncertainty penalty</dt><dd>{n.uncertainty_penalty}</dd></div>
          <div><dt>Cost normalisation</dt><dd>{n.cost_method}</dd></div></>}
      </dl>
      {n && n.notes.length > 0 && <ul className="cx-notes">{n.notes.map((x, i) => <li key={i}>{x}</li>)}</ul>}
      <ul className="cx-notes">{engine.preferences.precedence.map((x, i) => <li key={i}>Precedence {i + 1}: {x}</li>)}</ul>
    </details>
  );
}

export function EngineInsights({ engine }: { engine: EngineResult }) {
  return (
    <div className="cx-insights eng-insights">
      <PipelineTrace engine={engine} />
      <QueryUnderstanding engine={engine} />
      <PreferencesPanel engine={engine} />
      <CandidateComparison engine={engine} />
      <ExclusionsPanel engine={engine} />
      <DecisionExplanation engine={engine} />
      <ExecutionPanel engine={engine} />
      <EngineDetails engine={engine} />
    </div>
  );
}
