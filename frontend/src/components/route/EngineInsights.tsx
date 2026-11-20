/**
 * Route Query Engine 2.0 — decision insights.
 *
 * Every value shown here comes from `RouteResponse.engine`. Nothing is estimated in the browser, and stages
 * that did not run are shown as skipped with the server's reason. Metrics keep their provenance label.
 */
import { AlertTriangle, Ban, CheckCircle2, CircleDashed, Gauge, ListChecks, Network, ScanSearch, Scale, Siren, XCircle } from 'lucide-react';
import { Reveal } from '../ui/Reveal';
import { RoutingJourney } from './RoutingJourney';
import { StageTimeline } from './StageTimeline';
import { humanizeToken, formatPercent, formatInteger, formatDuration, formatUsd } from '../../utils/format';
import type { EngineCandidate, EngineResult, EngineStage } from '../../types';

const GROUP_TEXT: Record<string, string> = { conversational: 'Conversational AI', developer_api: 'Developer & API', unclassified: 'Unclassified' };
const PRICE_TEXT: Record<string, string> = { completely_free: 'Free', free_tier_limited: 'Free tier with limits', pay_as_you_go: 'Pay-as-you-go', paid_subscription: 'Paid subscription', self_hosted_open_weight: 'Self-hosted (open weights)', unknown: 'Pricing not verified' };

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
        <span className="cx-note-inline">
          {engine.catalogue_summary?.category ? <>Pool: <strong>{engine.catalogue_summary.category === 'developer_api' ? 'Developer & API Models' : 'Conversational AI Models'}</strong>{engine.catalogue_summary.intent_ambiguous ? ' (intent unclear; not mixed)' : ''} · </> : null}{formatDuration(engine.routing_latency_ms)} total · engine {engine.version}</span>
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
      <p className="cx-muted">Weights from {humanizeToken(pr.weight_source)}{pr.adjustments.length ? `, adjusted by ${pr.adjustments.length} factor(s): inferred ones are capped at 1.5×, ones you asked for at 2.5×` : ''}.</p>
      <ul className="cx-bars">
        {DIMS.map((d) => (
          <li className="cx-bar" key={d}>
            <span className="cx-bar-label">{DIM_LABEL[d]}</span>
            <span className="cx-bar-track" aria-hidden="true"><span className="cx-bar-fill" style={{ ['--w' as string]: w(pr.weights[d]) }} /></span>
            <span className="cx-bar-value">{pct(pr.weights[d])}</span>
          </li>
        ))}
      </ul>
      {pr.adjustments.length > 0 && <ul className="cx-notes">{pr.adjustments.map((a, i) => <li key={i}>{DIM_LABEL[a.dimension] ?? a.dimension} ×{a.factor.toFixed(2)} — {a.reason} <small>({a.origin === 'inferred' ? 'inferred from the query' : 'you asked for this'})</small></li>)}</ul>}
      {pr.hard_constraints.length === 0
        ? <p className="cx-muted">No explicit hard constraints were set.</p>
        : <dl className="cx-kv">{pr.hard_constraints.map((c, i) => <div key={i}><dt>{humanizeToken(c.kind)}</dt><dd>{Array.isArray(c.value) ? c.value.join(', ') : String(c.value)} <small>({humanizeToken(c.source)})</small></dd></div>)}</dl>}
      {pr.warnings.length > 0 && <ul className="cx-notes">{pr.warnings.map((x, i) => <li key={i}>{x}</li>)}</ul>}
    </Reveal>
  );
}

const ACCESS_LABEL: Record<string, string> = {
  ready: 'Execution ready',
  credential_not_configured: 'API key not configured',
  no_adapter: 'Adapter unavailable',
  provider_disabled: 'Provider disabled',
  inference_not_verified: 'Not verified',
  open_at_destination: 'Open at provider',
};

/** Suitability and executability are different facts: a ranked model is always recommendable, and this says whether it can also be run. */
function AccessTag({ c }: { c: EngineCandidate }) {
  if (c.execution_status === undefined || c.execution_status === null) return <span className="eng-tag eng-tag--dim">Unknown</span>;
  const ready = c.execution_ready === true;
  const label = ACCESS_LABEL[c.execution_status] ?? humanizeToken(c.execution_status);
  const extra = [!ready ? label : null, c.metadata_status === 'incomplete' ? 'Metadata incomplete' : null].filter(Boolean).join(' · ');
  return (
    <span className="cmp-access" title={ready ? 'AI Compass can run this model with the current server configuration.' : 'Recommendation only: this model is still ranked on its merits; it cannot be run from AI Compass right now.'}>
      <span className={`cmp-status${ready ? ' cmp-status--ready' : ''}`}>{ready ? 'Execution ready' : 'Recommendation only'}</span>
      {extra ? <small>{extra}</small> : null}
    </span>
  );
}

function CandidateRow({ c, top }: { c: EngineCandidate; top: boolean }) {
  return (
    <tr className={top ? 'cmp-row cmp-row--top' : 'cmp-row'}>
      <th scope="row" className="cmp-model">
        <span className="cmp-rank" aria-label={`Rank ${c.rank}`}>{c.rank}</span>
        <span className="cmp-name">
          <strong>{c.model_name}</strong>
          <small>{c.provider}{c.pareto_optimal
            ? <span className="cmp-pareto" title="Not dominated by any other candidate"> · Pareto</span>
            : <span title={`Dominated by ${c.dominated_by.join(', ')}`}> · Dominated</span>}</small>
          {c.model_category ? <small className="cmp-sub" title="Recommendation group and verified pricing; neither affects the score">{GROUP_TEXT[c.model_category] ?? c.model_category} · {PRICE_TEXT[c.pricing_category ?? 'unknown']}</small> : null}
        </span>
      </th>
      <td className="cmp-score" title="Robust score: weighted utility with a penalty for low-confidence inputs">
        <span className="cmp-score-val">{c.robust_score.toFixed(3)}</span>
        <span className="cmp-score-bar" aria-hidden="true"><span style={{ width: `${Math.max(0, Math.min(1, c.robust_score)) * 100}%` }} /></span>
      </td>
      {DIMS.map((d) => {
        const v = c.utilities[d];
        const ev = c.evidence[d];
        const missing = v === null || v === undefined;
        return (
          <td key={d} className={`cmp-num${missing ? ' cmp-na' : ''}`}
            title={ev ? `${humanizeToken(ev.provenance)} · confidence ${pct(ev.confidence)}${ev.note ? ` · ${ev.note}` : ''}` : undefined}>
            {missing ? '–' : pct(v)}
          </td>
        );
      })}
      <td className="cmp-num">{pct(c.confidence)}</td>
      <td className="cmp-num">{c.estimated_cost_usd === null ? <span className="cmp-na">unknown</span> : formatUsd(c.estimated_cost_usd)}</td>
      <td className="cmp-cell"><AccessTag c={c} /></td>
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
        <span className="cx-note-inline">
          {engine.pool_summary && engine.pool_summary.unscored > 0
            ? `${engine.pool_summary.scored} scored · ${engine.pool_summary.unscored} more in the pool have no metadata to compare`
            : `${engine.candidates.length} eligible`} · pool: {humanizeToken(engine.candidate_pool)}
        </span>
      </header>
      <div className="cmp-wrap" role="region" aria-label="Candidate comparison" tabIndex={0}>
        <table className="cmp-table">
          <thead>
            <tr><th scope="col">Model</th><th scope="col">Score</th>{DIMS.map((d) => <th key={d} scope="col" className="cmp-h-num">{DIM_LABEL[d]}</th>)}<th scope="col" className="cmp-h-num">Confidence</th><th scope="col" className="cmp-h-num">$ / req</th><th scope="col">Access</th></tr>
          </thead>
          <tbody>{rows.map((c, i) => <CandidateRow key={c.model_id} c={c} top={i === 0} />)}</tbody>
        </table>
      </div>
      <p className="cx-note">
        Access shows whether a model can be run with the current configuration; it never affects rank. “n/a” means the registry has no value; it is never treated as zero or as best, and it lowers confidence. Hover a cell for its provenance.
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
      {s.decision_status && s.decision_status !== 'recommended' && (
        <p className="cx-note" role="status" data-decision-status={s.decision_status}><strong>{humanizeToken(s.decision_status)}.</strong> {s.decision_reason}</p>
      )}
      {(s.alternative_ids?.length ?? 0) > 0 && (
        <p className="cx-note">Equally suitable on the evidence: {s.alternative_ids!.map((id) => engine.candidates.find((c) => c.model_id === id)?.model_name ?? id).join(', ')}.</p>
      )}
      {e.why_selected.length > 0 && <ul className="cx-notes">{e.why_selected.map((x, i) => <li key={i}>{x}</li>)}</ul>}
      <dl className="cx-kv">
        <div><dt>Margin over runner-up</dt><dd>{s.score_margin === null || s.score_margin === undefined ? '—' : s.score_margin.toFixed(3)}</dd></div>
        <div><dt>Survives a 10% re-weighting</dt><dd>{pct(s.weight_stability)}</dd></div>
        {s.tie_break_applied ? <div><dt>Tie-break</dt><dd>{s.tie_break_applied}</dd></div> : null}
      </dl>
      {e.tradeoffs.length > 0 && (<><p className="cx-subhead"><ListChecks aria-hidden="true" /> Trade-offs</p><ul className="cx-notes">{e.tradeoffs.map((x, i) => <li key={i}>{x}</li>)}</ul></>)}
      {(e.unavailable_data.length > 0 || s.caveats.length > 0) && (
        <><p className="cx-subhead"><AlertTriangle aria-hidden="true" /> Limits of this decision</p>
          <ul className="cx-notes">{[...s.caveats, ...e.unavailable_data].map((x, i) => <li key={i}>{x}</li>)}</ul></>
      )}
      <p className="cx-note">{e.confidence_statement}</p>
      {engine.executable_alternative && <p className="cx-note" role="note"><strong>Best match vs best runnable.</strong> {engine.executable_alternative.statement}</p>}
      <ConfidenceBreakdown engine={engine} />
    </Reveal>
  );
}

function ConfidenceBreakdown({ engine }: { engine: EngineResult }) {
  const cr = engine.confidence_report;
  if (!cr) return null;
  return (
    <details className="cx-details">
      <summary>Confidence, by component</summary>
      <ul className="cx-notes">
        {cr.components.map((c) => (
          <li key={c.name}>
            <strong>{humanizeToken(c.name)}</strong>: {c.value === null ? (c.kind === 'not_applicable' ? 'not applicable' : 'not a number') : pct(c.value)}
            {' '}<small>({c.kind === 'heuristic_estimate' ? 'heuristic estimate, not a probability' : c.kind === 'deterministic' ? 'deterministic fact' : 'n/a'})</small> — {c.basis}
          </li>
        ))}
      </ul>
      <p className="cx-note">{cr.combined_note} {cr.calibration.statement}</p>
    </details>
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
        {engine.provenance && <>
          <div><dt>Decision fingerprint</dt><dd title={engine.provenance.fingerprint}><code>{engine.provenance.fingerprint.slice(0, 16)}</code></dd></div>
          <div><dt>Catalogue snapshot</dt><dd>{engine.provenance.catalogue.candidates} models · {humanizeToken(engine.provenance.catalogue.origin)}{engine.provenance.catalogue.version !== null ? ` · v${engine.provenance.catalogue.version}` : ''} · <code>{engine.provenance.catalogue.content_sha256.slice(0, 10)}</code></dd></div>
        </>}
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
      <RoutingJourney engine={engine} />
      <StageTimeline engine={engine} />
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
