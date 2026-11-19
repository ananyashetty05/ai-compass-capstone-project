/**
 * Explainable-AI decision trace.
 *
 * Every element renders recorded data from the routing run (`EngineResult`): the real filtering
 * outcomes, the real score decomposition, counterfactuals recomputed by the router, and the checks that
 * actually ran. Unknown values stay unknown; stages that did not run say so and why.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, ArrowRight, Check, ChevronDown, Gauge, Info, Layers, ListChecks, Loader2, Minus, Scale, ShieldCheck, Tag, X } from 'lucide-react';
import { useRouteResult } from '../../context/routeResultContext';
import { fetchRoutingHistory } from '../../services/history.service';
import { getDecisionTrace } from '../../services/trace.service';
import { describeError } from '../../services/http';
import { formatDuration, formatPercent, formatUsd, humanizeToken } from '../../utils/format';
import type { EngineCandidate, EngineResult, RoutingHistoryEntry } from '../../types';
import { DIMS, DIM_LABEL, buildFlow, buildReport, decisiveFactor, fmtMs, groupRejections, provenanceLabel, selectedCandidate, tieNote, whyHeadline } from './traceModel';
import type { Dim, FlowNode, StepState } from './traceModel';

const STATE_TEXT: Record<StepState, string> = { done: 'Completed', skipped: 'Not run', failed: 'Failed', warn: 'Needs attention', idle: 'Not recorded' };
const fmt = (v: number | null | undefined, d = 3) => (typeof v === 'number' && Number.isFinite(v) ? v.toFixed(d) : '—');

export function DecisionTrace() {
  const { result: latest } = useRouteResult();
  const [history, setHistory] = useState<RoutingHistoryEntry[] | null>(null);
  const [historyNote, setHistoryNote] = useState<string | null>(null);
  const [pick, setPick] = useState<string>('latest');
  const [stored, setStored] = useState<EngineResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetchRoutingHistory().then((r) => {
      if (!alive) return;
      if (r.availability === 'available') setHistory(r.entries);
      else setHistoryNote(r.reason);
    });
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    if (pick === 'latest') { setStored(null); setError(null); return; }
    const c = new AbortController();
    setLoading(true); setError(null);
    getDecisionTrace(pick, c.signal)
      .then((t) => setStored(t))
      .catch((e) => { if (!c.signal.aborted) { setStored(null); setError(describeError(e, 'The stored trace could not be loaded.').message); } })
      .finally(() => { if (!c.signal.aborted) setLoading(false); });
    return () => c.abort();
  }, [pick]);

  const engine: EngineResult | null = pick === 'latest' ? (latest?.engine ?? null) : stored;
  const queryText = pick === 'latest' ? latest?.query : undefined;

  return (
    <div className="xai">
      <header className="xai-source">
        <label className="xai-pick">
          <span>Decision</span>
          <select value={pick} onChange={(e) => setPick(e.target.value)} aria-label="Choose a routing decision to inspect">
            <option value="latest">{latest?.engine ? 'Latest run in this session' : 'Latest run (none yet)'}</option>
            {(history ?? []).map((h) => (
              <option key={h.id} value={h.id}>{new Date(h.timestamp).toLocaleString()} · {h.selected_model_name || h.selected_model_id} · {h.mode ?? 'recommend'}</option>
            ))}
          </select>
        </label>
      </header>
      {historyNote ? <p className="xai-note"><Info aria-hidden="true" /> {historyNote} Stored decisions will appear here once history is available.</p> : null}

      {loading ? <div className="xai-empty" role="status"><Loader2 className="xai-spin" aria-hidden="true" /> Loading the stored decision…</div> : null}
      {error ? <div className="xai-empty" role="alert"><strong>No stored trace for this run.</strong><p>{error}</p><p>Decision traces are saved for runs made after trace storage is enabled. The latest run in this session is always available.</p></div> : null}
      {!loading && !error && !engine ? (
        <div className="xai-empty">
          <strong>No routing decision to explain yet.</strong>
          <p>Run a query on the Route Query page. This view will then show how AI Compass analysed it, which models were filtered out and why, how the remaining models scored, and what decided the outcome. No placeholder data is shown.</p>
        </div>
      ) : null}
      {engine && !loading && !error ? <TraceBody e={engine} query={queryText} /> : null}
    </div>
  );
}

/* ── Shared building blocks ───────────────────────────────────────────────── */
function Card({ id, title, sub, right, children, className }: { id?: string; title: string; sub?: string; right?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={`xc${className ? ` ${className}` : ''}`} aria-labelledby={id}>
      <header className="xc-head">
        <div><h3 id={id}>{title}</h3>{sub ? <p>{sub}</p> : null}</div>
        {right ? <div className="xc-right">{right}</div> : null}
      </header>
      <div className="xc-body">{children}</div>
    </section>
  );
}

function Meter({ value, tone = 'primary' }: { value: number; tone?: 'primary' | 'ok' | 'warn' | 'bad' }) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return <span className="xai-meter" data-tone={tone} role="img" aria-label={`${Math.round(pct)}%`}><i style={{ width: `${pct}%` }} /></span>;
}

function Legend({ small }: { small?: boolean }) {
  return <ul className="xai-legend" data-small={small || undefined} aria-label="Objectives">{DIMS.map((d) => <li key={d}><i data-dim={d} />{DIM_LABEL[d]}</li>)}</ul>;
}

type Panel = 'why' | 'models' | 'quality' | 'evidence';
const PANELS: { id: Panel; label: string }[] = [
  { id: 'why', label: 'Why this model' }, { id: 'models', label: 'Candidates & scoring' },
  { id: 'quality', label: 'Quality & escalation' }, { id: 'evidence', label: 'Evidence & report' },
];

function TraceBody({ e, query }: { e: EngineResult; query?: string }) {
  const [node, setNode] = useState<string>('select');
  const [panel, setPanel] = useState<Panel>('why');
  const flow = useMemo(() => buildFlow(e), [e]);
  useEffect(() => { setNode('select'); }, [e]);

  return (
    <div className="xai-body">
      <Hero e={e} query={query} />
      <FlowSection e={e} flow={flow} node={node} onNode={setNode} />
      <div className="xai-tabs" role="tablist" aria-label="Evaluation detail">
        {PANELS.map((t) => (
          <button key={t.id} type="button" role="tab" id={`xai-tab-${t.id}`} aria-selected={panel === t.id} aria-controls="xai-panel" onClick={() => setPanel(t.id)}>{t.label}</button>
        ))}
      </div>
      <div id="xai-panel" role="tabpanel" aria-labelledby={`xai-tab-${panel}`} className="xai-panel" key={panel}>
        {panel === 'why' ? <WhySection e={e} /> : null}
        {panel === 'models' ? <><FunnelSection e={e} /><RankingSection e={e} /></> : null}
        {panel === 'quality' ? <ExecutionSection e={e} /> : null}
        {panel === 'evidence' ? <><EvidenceSection e={e} /><ReportSection e={e} /></> : null}
      </div>
    </div>
  );
}

/* ── Outcome ──────────────────────────────────────────────────────────────── */
function Hero({ e, query }: { e: EngineResult; query?: string }) {
  const top = selectedCandidate(e);
  const factor = decisiveFactor(e);
  const headline = useMemo(() => whyHeadline(e), [e]);
  const tie = useMemo(() => tieNote(e), [e]);
  const executed = e.execution.status !== 'not_requested';
  const act = e.evaluation.decision?.action;
  const tone = !executed ? 'route' : act === 'accept' ? 'ok' : act === 'verify' ? 'warn' : act === 'escalate' ? 'bad' : 'route';
  const status = !executed ? 'Recommendation' : act === 'accept' ? 'Accepted' : act === 'verify' ? 'Needs verification' : act === 'escalate' ? 'Escalated' : 'Executed';
  const rows = top ? [top, ...e.candidates.filter((c) => c.model_id !== top.model_id).slice(0, 2)] : [];
  const kpis: { icon: React.ReactNode; k: string; v: string; s: string }[] = [
    { icon: <Gauge />, k: 'Confidence', v: humanizeToken(e.selection.confidence_level), s: 'uncalibrated estimate' },
    { icon: <Scale />, k: 'Decisive factor', v: factor ? DIM_LABEL[factor.dim] : '—', s: factor ? `${formatPercent(factor.share, 0)} of the score` : 'unavailable' },
    { icon: <Layers />, k: 'Candidates', v: String(e.candidates.length), s: `${e.exclusions.length} removed by constraints` },
    { icon: <Tag />, k: 'Scoring version', v: `v${e.scoring_version}`, s: `engine ${e.version}` },
  ];
  return (
    <section className="xh" data-tone={tone} aria-label="Decision summary">
      <div className="xh-grid">
        <div className="xh-main">
          <div className="xh-chips">
            <span className="xai-chip" data-tone={tone}>{status}</span>
            {executed && e.execution.escalated && e.execution.final_model_name ? <span className="xai-chip" data-tone="warn">Answered by {e.execution.final_model_name} after escalation</span> : null}
            {e.access ? <span className="xai-chip" data-tone={e.access.execution_available ? 'ok' : 'neutral'}>{e.access.execution_available ? 'Execution ready' : `Execution: ${humanizeToken(e.access.status ?? 'unknown').toLowerCase()}`}</span> : null}
          </div>
          <h3 className="xh-title">{top ? top.model_name : 'No model selected'}{top ? <span>{top.provider}</span> : null}</h3>
          {headline ? <p className="xh-why">{headline}</p> : <p className="xh-why">{e.explanation.summary}</p>}
          {tie ? <p className="xh-tie"><Info aria-hidden="true" />{tie}</p> : null}
          {query ? <blockquote className="xh-query"><small>Query</small>{query.length > 160 ? `${query.slice(0, 160)}…` : query}</blockquote> : null}
        </div>
        <dl className="xh-kpis">
          {kpis.map((x) => (
            <div key={x.k}><span className="xh-kpi-i" aria-hidden="true">{x.icon}</span><dt>{x.k}</dt><dd>{x.v}</dd><small>{x.s}</small></div>
          ))}
        </dl>
      </div>
      {rows.length ? (
        <div className="xh-compare">
          <div className="xh-compare-head"><h4>How it compares</h4><Legend small /></div>
          <ul>
            {rows.map((c, i) => (
              <li key={c.model_id} data-sel={i === 0}>
                <span className="xh-rowname"><b>{c.model_name}</b><small>{i === 0 ? 'Selected' : `Rank ${c.rank}`}</small></span>
                <span className="xh-track"><ContributionBar c={c} scale={top && top.robust_score > 0 ? Math.min(1, c.robust_score / Math.max(...rows.map((r) => r.robust_score))) : undefined} /></span>
                <span className="xh-rowscore">{fmt(c.robust_score)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

/* ── Decision flow ────────────────────────────────────────────────────────── */
function StateIcon({ state, n }: { state: StepState; n: number }) {
  return <span className="xf-i" data-state={state} aria-hidden="true">{state === 'done' ? <Check /> : state === 'failed' ? <X /> : state === 'warn' ? <AlertTriangle /> : state === 'skipped' || state === 'idle' ? <Minus /> : n}</span>;
}

function FlowSection({ e, flow, node, onNode }: { e: EngineResult; flow: FlowNode[]; node: string; onNode: (id: string) => void }) {
  const cur = flow.find((n) => n.id === node) ?? flow[0];
  const lanes: { id: 'route' | 'respond'; label: string; hint: string }[] = [
    { id: 'route', label: 'Routing', hint: 'Choosing the model' },
    { id: 'respond', label: 'Response', hint: 'Generating and checking the answer' },
  ];
  return (
    <Card id="xai-flow-title" title="Query to answer" sub="The path this query actually took. Dashed stages did not run. Select a stage for its recorded detail."
      right={<ul className="xf-key" aria-label="Stage states"><li data-state="done">Completed</li><li data-state="warn">Needs attention</li><li data-state="skipped">Not run</li></ul>}>
      <div className="xf">
        {lanes.map((lane) => {
          const items = flow.filter((n) => n.lane === lane.id);
          return (
            <div className="xf-lane" key={lane.id}>
              <div className="xf-lane-head"><b>{lane.label}</b><span>{lane.hint}</span></div>
              <ol className="xf-steps">
                {items.map((n, i) => (
                  <li key={n.id} data-state={n.state}>
                    <button type="button" className="xf-node" data-state={n.state} aria-pressed={n.id === cur.id} onClick={() => onNode(n.id)}>
                      <StateIcon state={n.state} n={(lane.id === 'respond' ? 6 : 0) + i + 1} />
                      <span className="xf-t">{n.label}</span>
                      <span className="xf-s">
                        {n.id === 'decision' ? (n.action ? <i className="xf-act" data-a={n.action}>{n.action}</i> : 'No decision') : STATE_TEXT[n.state]}
                        {n.ms !== undefined && n.state === 'done' ? <em>{fmtMs(n.ms)}</em> : null}
                      </span>
                    </button>
                  </li>
                ))}
              </ol>
            </div>
          );
        })}
      </div>
      <div className="xd" role="region" aria-live="polite" aria-label={`${cur.label} details`} key={cur.id}>
        <div className="xd-head">
          <StateIcon state={cur.state} n={0} />
          <h4>{cur.label}</h4>
          <span className="xai-chip" data-tone={cur.state}>{STATE_TEXT[cur.state]}</span>
          {cur.ms !== undefined ? <span className="xai-chip" data-tone="neutral">{fmtMs(cur.ms)}</span> : null}
        </div>
        {cur.summary ? <p className="xd-sum">{cur.summary}</p> : null}
        <NodeDetail e={e} id={cur.id} />
      </div>
    </Card>
  );
}

type Tile = [string, React.ReactNode, boolean?];
function Tiles({ rows }: { rows: Tile[] }) {
  return <dl className="xd-tiles">{rows.map(([k, v, wide]) => <div key={k} data-wide={wide || undefined}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>;
}

function NodeDetail({ e, id }: { e: EngineResult; id: string }) {
  const p = e.profile;
  const top = selectedCandidate(e);
  switch (id) {
    case 'query':
      return <Tiles rows={[['Input tokens', `${p.tokens.input_tokens} (${p.tokens.method.replace(/_/g, ' ')})`], ['Expected output', `${p.tokens.output_tokens} tokens (${(p.tokens.output_basis || 'estimate').replace(/_/g, ' ')})`], ['Prompt sent', humanizeToken(e.prompt_used_source)]]} />;
    case 'analysis':
      return <Tiles rows={[
        ['Task', humanizeToken(p.primary_intent)], ['Domain', `${humanizeToken(p.domain)} · confidence ${fmt(p.domain_confidence, 2)}`],
        ['Complexity', `${humanizeToken(p.complexity.category)} · ${fmt(p.complexity.score, 2)}`], ['Sensitivity', `${humanizeToken(p.risk.sensitivity)}${p.risk.recommends_strict_privacy ? ' · strict privacy' : ''}`],
        ['Audience', p.audience ? humanizeToken(p.audience.kind) : 'Not recorded'], ['Required capabilities', p.required_capabilities.join(', ') || 'None beyond the task'],
        ['Required modalities', p.required_modalities.join(', ')], ['Other intents', p.secondary_intents.map((i) => humanizeToken(i.name)).join(', ') || 'None'],
        ...(p.audience?.signals.length ? [['Audience rules fired', p.audience.signals.map(humanizeToken).join(', '), true] as Tile] : []),
        ['Method', `${humanizeToken(p.analysis_method)} · deterministic rules, no model call`, true],
      ]} />;
    case 'constraints':
      return (
        <>
          <div className="xd-weights" role="list" aria-label="Objective weights">
            {DIMS.map((d) => (
              <div role="listitem" key={d}><span><i data-dim={d} />{DIM_LABEL[d]}</span><b>{formatPercent(e.preferences.weights[d] ?? 0, 0)}</b><span className="xai-meter" data-dim={d}><i style={{ width: `${(e.preferences.weights[d] ?? 0) * 100 * 2.5}%` }} /></span></div>
            ))}
          </div>
          <Tiles rows={[
            ['Weights from', humanizeToken(e.preferences.weight_source)],
            ['Hard constraints', e.explanation.hard_constraints_applied.join('; ') || 'None set'],
            ['Query-based adjustments', e.preferences.adjustments.map((a) => `${DIM_LABEL[a.dimension as Dim] ?? a.dimension} ×${a.factor} (${a.reason})`).join('; ') || 'None', true],
          ]} />
        </>
      );
    case 'filter': {
      const cs = e.catalogue_summary;
      return <Tiles rows={[['Catalogue entries', cs ? String(cs.catalogue_total) : '—'], ['Eligible', cs ? String(cs.eligible) : String(e.candidates.length)], ['Removed', String(e.exclusions.length)], ['API credentials used', cs?.credentials_used_for_comparison === false ? 'No · published metadata only' : 'Not recorded']]} />;
    }
    case 'score':
      return <Tiles rows={[
        ['Method', 'Weighted sum of per-objective utilities, ranked by a pessimistic robust score', true],
        ['Missing-data policy', e.scoring_config ? `${humanizeToken(e.scoring_config.missing_policy)} · unknown scores 0, never an average` : '—'],
        ['Uncertainty penalty', fmt(e.scoring_config?.uncertainty_penalty ?? e.normalization?.uncertainty_penalty, 2)],
        ['Cost basis', e.normalization ? `${humanizeToken(e.normalization.cost_basis)}` : '—'], ['Latency basis', e.normalization ? humanizeToken(e.normalization.latency_basis) : '—'],
      ]} />;
    case 'select': {
      const stab = e.selection.weight_stability;
      const tie = tieNote(e);
      return (
        <div className="xd-select">
          <div className="xd-pick">
            <span className="xd-k">Selected model</span>
            <strong>{top?.model_name ?? 'None'}</strong>
            <small>{top ? `${top.provider} · ${top.model_id}` : ''}</small>
            {tie ? <p className="xd-tie"><Info aria-hidden="true" />{tie}</p> : null}
          </div>
          <div className="xd-metric">
            <span className="xd-k">Margin over runner-up</span>
            <strong>{e.selection.score_margin == null ? '—' : fmt(e.selection.score_margin)}</strong>
            <small>{e.selection.score_margin != null && e.selection.score_margin < 0 ? 'Runner-up scored slightly higher; tie rule applied' : 'Robust-score difference'}</small>
          </div>
          <div className="xd-metric">
            <span className="xd-k">Stable under weight changes</span>
            <strong>{stab != null ? formatPercent(stab, 0) : '—'}</strong>
            {stab != null ? <Meter value={stab} tone={stab >= 0.75 ? 'ok' : stab >= 0.5 ? 'warn' : 'bad'} /> : null}
            <small>Share of ±20% weight changes that keep this winner</small>
          </div>
          {e.selection.caveats.length ? (
            <ul className="xd-caveats" aria-label="Caveats">{e.selection.caveats.map((c) => <li key={c}><AlertTriangle aria-hidden="true" />{c}</li>)}</ul>
          ) : null}
        </div>
      );
    }
    case 'generate':
      return e.execution.attempts.length ? <AttemptList e={e} /> : <p className="xai-muted">{e.execution.mode === 'recommend' ? 'AI Compass recommended a model but did not call any provider. Run the query in Execute mode to record generation, measured latency and cost.' : (e.execution.blocked_reason ?? 'No attempt was made.')}</p>;
    case 'quality':
      return e.evaluation.checks.length ? <ChecksList e={e} /> : <p className="xai-muted">No response was produced, so no checks were run. Nothing is shown as passed.</p>;
    case 'decision':
      return e.evaluation.decision && e.evaluation.decision.action !== 'none'
        ? <><DecisionCard e={e} />{(e.execution.escalation_events ?? []).length === 0 ? <p className="xai-muted">No escalation was triggered.</p> : null}</>
        : <p className="xai-muted">An Accept / Verify / Escalate decision is made only for a generated response. None exists for this run, so no escalation was triggered.</p>;
    case 'escalate':
      return <EscalationTimeline e={e} />;
    default:
      return e.execution.final_model_name ? <Tiles rows={[['Answered by', e.execution.final_model_name], ['Escalated', e.execution.escalated ? 'Yes' : 'No'], ['Total latency (measured)', e.execution.total_latency_ms != null ? formatDuration(e.execution.total_latency_ms) : 'Unavailable'], ['Total cost (computed)', e.execution.total_cost_usd != null ? formatUsd(e.execution.total_cost_usd, 6) : 'Unavailable']]} /> : <p className="xai-muted">This run produced a recommendation, not an answer.</p>;
  }
}

/* ── Candidates & scoring ─────────────────────────────────────────────────── */
function FunnelSection({ e }: { e: EngineResult }) {
  const cs = e.catalogue_summary;
  const groups = groupRejections(e);
  const [open, setOpen] = useState<string | null>(null);
  const steps = cs ? [
    { k: 'In catalogue', v: cs.catalogue_total, note: 'Every known model, key or no key' },
    { k: 'Considered', v: cs.considered, note: 'After lifecycle checks' },
    { k: 'Eligible', v: cs.eligible, note: 'Passed every hard constraint' },
    { k: 'Scored', v: cs.scored, note: 'Ranked on the objectives' },
    { k: 'Selected', v: cs.selected, note: 'Highest robust score' },
  ] : [];
  const max = Math.max(1, ...steps.map((s) => s.v));
  return (
    <Card id="xai-funnel-title" title="Candidate filtering" sub="Hard constraints remove a model outright; a high score cannot buy it back. A missing credential never removes a model from comparison.">
      {steps.length ? (
        <ol className="xai-funnel">
          {steps.map((s, i) => (
            <li key={s.k} data-last={i === steps.length - 1}>
              <strong>{s.v}</strong><span className="xai-funnel-k">{s.k}</span>
              <span className="xai-funnel-track"><i style={{ width: `${Math.max(6, (s.v / max) * 100)}%` }} /></span>
              <small>{s.note}</small>
            </li>
          ))}
        </ol>
      ) : null}
      <div className="xai-sub-head"><h4>Why models were removed</h4><span>{e.exclusions.length} removed</span></div>
      {groups.length === 0 ? <p className="xai-muted">No candidate was removed.</p> : (
        <ul className="xai-rejects">
          {groups.map((g) => (
            <li key={g.code} data-open={open === g.code}>
              <button type="button" aria-expanded={open === g.code} onClick={() => setOpen(open === g.code ? null : g.code)}>
                <span className="xai-count">{g.count}</span>
                <span className="xai-rej-t"><strong>{humanizeToken(g.code)}</strong><small>{g.label}</small></span>
                <ChevronDown className="xai-chev" aria-hidden="true" />
              </button>
              {open === g.code ? <ul className="xai-rej-items">{g.items.map((i) => <li key={i.id}><strong>{i.name}</strong><span>{i.reason}</span><em>{i.permanence}</em></li>)}</ul> : null}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function ContributionBar({ c, scale }: { c: EngineCandidate; scale?: number }) {
  const total = DIMS.reduce((a, d) => a + (c.contributions[d] ?? 0), 0);
  if (total <= 0) return <span className="xai-muted">no contribution (all objectives unknown)</span>;
  return (
    <div className="xai-stack" style={scale ? { width: `${Math.max(8, scale * 100)}%` } : undefined} role="img" aria-label={DIMS.map((d) => `${DIM_LABEL[d]} ${fmt(c.contributions[d], 3)}`).join(', ')}>
      {DIMS.map((d) => ((c.contributions[d] ?? 0) > 0 ? <span key={d} data-dim={d} style={{ flexGrow: c.contributions[d] }} title={`${DIM_LABEL[d]}: ${fmt(c.contributions[d], 3)}`} /> : null))}
    </div>
  );
}

function RankingSection({ e }: { e: EngineResult }) {
  const [all, setAll] = useState(false);
  const rows = all ? e.candidates : e.candidates.slice(0, 6);
  const w = e.preferences.weights;
  const selId = e.selection.selected_model_id;
  return (
    <Card id="xai-rank-title" title="Multi-objective scoring" sub="Utilities are 0–1, higher is better. Ranking uses a pessimistic robust score that discounts weak evidence. A dash means unknown, never zero."
      right={<ul className="xai-weights-inline" aria-label="Objective weights">{DIMS.map((d) => <li key={d}><i data-dim={d} />{DIM_LABEL[d]} <b>{formatPercent(w[d] ?? 0, 0)}</b></li>)}</ul>}>
      <div className="xai-table-wrap">
        <table className="xai-table">
          <caption className="sr-only">Eligible candidates ranked by robust score with per-objective utilities</caption>
          <thead><tr><th>#</th><th>Model</th>{DIMS.map((d) => <th key={d} className="num">{DIM_LABEL[d]}</th>)}<th className="num">Robust score</th><th>Score composition</th></tr></thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.model_id} data-selected={c.model_id === selId}>
                <td className="rank">{c.rank}</td>
                <td><strong>{c.model_name}</strong><small>{c.provider}{c.model_id === selId ? ' · selected' : ''}{c.pareto_optimal ? ' · Pareto-optimal' : ''}</small></td>
                {DIMS.map((d) => (
                  <td key={d} className="num" data-missing={c.utilities[d] == null}>
                    {c.utilities[d] == null ? '—' : <><span>{fmt(c.utilities[d], 2)}</span><span className="xai-cell-bar" data-dim={d}><i style={{ width: `${(c.utilities[d] ?? 0) * 100}%` }} /></span></>}
                  </td>
                ))}
                <td className="num score"><strong>{fmt(c.robust_score)}</strong></td>
                <td><ContributionBar c={c} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="xai-table-foot">
        {e.candidates.length > 6 ? <button type="button" className="xai-btn" onClick={() => setAll(!all)}>{all ? 'Show top 6' : `Show all ${e.candidates.length} candidates`}</button> : <span />}
        {e.normalization ? <p>Cost: {e.normalization.cost_method}. Latency: {e.normalization.latency_basis.replace(/_/g, ' ')}.</p> : null}
      </div>
    </Card>
  );
}

/* ── Why this model ───────────────────────────────────────────────────────── */
const SCENARIO_SHORT: Record<string, string> = { 'weight.quality ×2': 'Quality ×2', 'weight.cost ×2': 'Cost ×2', 'weight.latency ×2': 'Speed ×2' };

function WhySection({ e }: { e: EngineResult }) {
  const top = selectedCandidate(e);
  const cfs = e.counterfactuals ?? [];
  const lower = e.explanation.why_alternatives_ranked_lower as { model_id?: string; model_name?: string; reason?: string; gap?: number }[];
  const stab = e.selection.weight_stability;
  const alts = e.candidates.filter((c) => c.model_id !== top?.model_id).slice(0, 3);
  const reasonFor = (id: string) => lower.find((l) => l.model_id === id)?.reason;
  return (
    <>
      <div className="xai-two">
        <Card id="xai-why-title" title="Why it won" sub={top ? `${top.model_name} against ${Math.max(0, e.candidates.length - 1)} other eligible models` : undefined}>
          {e.explanation.why_selected.length ? <ul className="xai-rows">{e.explanation.why_selected.map((w) => <li key={w}><span className="xai-ico" data-tone="ok"><Check aria-hidden="true" /></span><p>{w}</p></li>)}</ul> : <p className="xai-muted">No supporting reasons were recorded.</p>}
          {e.explanation.tradeoffs.length ? (
            <>
              <div className="xai-sub-head"><h4>Trade-offs</h4></div>
              <ul className="xai-rows">{e.explanation.tradeoffs.map((w) => <li key={w}><span className="xai-ico" data-tone="warn"><Scale aria-hidden="true" /></span><p>{w}</p></li>)}</ul>
            </>
          ) : null}
          <div className="xai-confidence">
            <div><span>Confidence</span><b>{humanizeToken(e.selection.confidence_level)}</b></div>
            <div><span>Stable under ±20% weight changes</span><b>{stab != null ? formatPercent(stab, 0) : '—'}</b>{stab != null ? <Meter value={stab} tone={stab >= 0.75 ? 'ok' : stab >= 0.5 ? 'warn' : 'bad'} /> : null}</div>
            <div><span>Margin over runner-up</span><b>{e.selection.score_margin == null ? '—' : fmt(e.selection.score_margin)}</b></div>
          </div>
        </Card>
        <Card id="xai-alt-title" title="Runners-up" sub="The strongest alternatives and where they fell short.">
          {alts.length ? (
            <div className="xai-table-wrap xai-flush">
              <table className="xai-table xai-compact">
                <thead><tr><th>#</th><th>Model</th><th className="num">Score</th><th className="num">Gap</th></tr></thead>
                <tbody>
                  {alts.map((c) => (
                    <tr key={c.model_id}>
                      <td className="rank">{c.rank}</td>
                      <td><strong>{c.model_name}</strong><small>{reasonFor(c.model_id) ?? c.provider}</small></td>
                      <td className="num score"><strong>{fmt(c.robust_score)}</strong></td>
                      <td className="num">{top ? fmt(c.robust_score - top.robust_score, 3) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <p className="xai-muted">Only one model satisfied the constraints, so there was nothing to compare it against.</p>}
        </Card>
      </div>

      <Card id="xai-cf-title" title="What would change the answer" sub="Each scenario re-runs the real filtering and scoring with one input changed. These are recomputed, not estimated.">
        {cfs.length ? (
          <ul className="xai-cf">
            {cfs.map((c) => (
              <li key={c.scenario} data-changed={c.changed}>
                <span className="xai-cf-tag">{SCENARIO_SHORT[c.changed_input] ?? c.changed_input}</span>
                <p className="xai-cf-s">{c.scenario}</p>
                <span className="xai-cf-out" data-changed={c.changed}>{c.changed ? 'Different winner' : 'Same winner'}</span>
                <strong>{c.winner.model_name}</strong>
                <small>{c.changed ? `${c.winner.model_name} would be chosen instead.` : 'The selected model still wins.'}</small>
              </li>
            ))}
          </ul>
        ) : <p className="xai-muted">No counterfactual could be computed for this run.</p>}
      </Card>
    </>
  );
}

/* ── Evidence & report ────────────────────────────────────────────────────── */
function EvidenceSection({ e }: { e: EngineResult }) {
  const top = selectedCandidate(e);
  if (!top) return null;
  return (
    <Card id="xai-ev-title" title="Where each number comes from" sub={`Evidence for ${top.model_name}. Measured, provider-reported and estimated values are labelled separately.`}>
      <div className="xai-table-wrap">
        <table className="xai-table">
          <thead><tr><th>Objective</th><th className="num">Value</th><th>Source</th><th className="num">Evidence confidence</th><th>Note</th></tr></thead>
          <tbody>
            {DIMS.map((d) => {
              const ev = top.evidence[d];
              const missing = !ev || ev.missing;
              return (
                <tr key={d}>
                  <td><strong>{DIM_LABEL[d]}</strong></td>
                  <td className="num">{missing || ev.raw_value == null ? 'Unavailable' : `${fmt(ev.raw_value, 3)} ${ev.unit}`}</td>
                  <td><span className="xai-src" data-kind={missing ? 'unavailable' : /measured|observed/.test(ev.provenance) ? 'measured' : ev.provenance === 'estimated' || /estimate/.test(ev.unit) ? 'estimated' : 'reported'}>{missing ? 'Unavailable' : provenanceLabel(ev.provenance)}</span></td>
                  <td className="num">{missing ? '—' : fmt(ev.confidence, 2)}</td>
                  <td className="muted">{ev?.note ?? ''}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {e.explanation.unavailable_data.length ? <ul className="xai-rows xai-rows-tight">{e.explanation.unavailable_data.map((u) => <li key={u}><span className="xai-ico" data-tone="neutral"><Info aria-hidden="true" /></span><p>{u}</p></li>)}</ul> : null}
    </Card>
  );
}

function ReportSection({ e }: { e: EngineResult }) {
  const report = useMemo(() => buildReport(e), [e]);
  const [copied, setCopied] = useState(false);
  const copyTimer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(copyTimer.current), []);
  const copy = async () => {
    try { await navigator.clipboard.writeText(report); setCopied(true); window.clearTimeout(copyTimer.current); copyTimer.current = window.setTimeout(() => setCopied(false), 1800); } catch { /* clipboard unavailable */ }
  };
  const download = () => {
    const url = URL.createObjectURL(new Blob([report], { type: 'text/markdown' }));
    const a = document.createElement('a'); a.href = url; a.download = 'ai-compass-explainability-report.md'; a.click(); URL.revokeObjectURL(url);
  };
  return (
    <Card id="xai-report-title" title="Explainability report" sub="A plain-text version of this page: what happened, why, and what is still uncertain."
      right={<div className="xai-actions"><button type="button" className="xai-btn" onClick={copy}>{copied ? 'Copied' : 'Copy Markdown'}</button><button type="button" className="xai-btn" data-primary="true" onClick={download}>Download .md</button></div>}>
      <details className="xai-reveal">
        <summary>Preview report</summary>
        <pre className="xai-report" tabIndex={0}>{report}</pre>
      </details>
    </Card>
  );
}

/* ── Quality & escalation ─────────────────────────────────────────────────── */
function AttemptList({ e }: { e: EngineResult }) {
  return (
    <ol className="xai-attempts">
      {e.execution.attempts.map((a) => (
        <li key={a.attempt} data-outcome={a.outcome}>
          <strong>Attempt {a.attempt} · {a.model_id}</strong>
          <span>{humanizeToken(a.outcome)}{a.error_kind ? ` (${humanizeToken(a.error_kind)})` : ''}</span>
          <small>{a.latency_ms != null ? `${Math.round(a.latency_ms)} ms measured` : 'latency not measured'}{a.cost_usd != null ? ` · ${formatUsd(a.cost_usd, 6)} computed from reported tokens` : ''}{a.note ? ` · ${a.note}` : ''}</small>
        </li>
      ))}
    </ol>
  );
}

function ChecksList({ e }: { e: EngineResult }) {
  const notRun = e.evaluation.checks_not_run ?? [];
  return (
    <>
      <ul className="xai-checks">{e.evaluation.checks.map((c) => <li key={c.name} data-pass={c.passed}><span aria-hidden="true">{c.passed ? <Check /> : <X />}</span><div><strong>{humanizeToken(c.name)}</strong><small>{c.detail}</small></div><em>{c.passed ? 'Passed' : 'Failed'}</em></li>)}</ul>
      {notRun.length ? (
        <details className="xai-reveal"><summary>{notRun.length} checks were not run</summary><ul className="xai-notrun">{notRun.map((n) => <li key={n.check}><strong>{humanizeToken(n.check)}</strong><small>{n.reason}</small></li>)}</ul></details>
      ) : null}
    </>
  );
}

function DecisionCard({ e }: { e: EngineResult }) {
  const d = e.evaluation.decision;
  if (!d) return null;
  return (
    <div className="xai-decision" data-action={d.action}>
      <span className="xai-decision-a">{humanizeToken(d.action)}</span>
      <div><strong>Rule: {humanizeToken(d.rule)}</strong><p>{d.reason}</p></div>
    </div>
  );
}

function EscalationTimeline({ e }: { e: EngineResult }) {
  const events = e.execution.escalation_events ?? [];
  if (!events.length) return <p className="xai-muted">Not triggered{e.execution.status === 'not_requested' ? ': no response was generated' : ''}.</p>;
  return (
    <ol className="xai-timeline">
      {events.map((ev) => (
        <li key={ev.sequence}>
          <strong>{ev.from_model_id} <ArrowRight aria-hidden="true" /> {ev.to_model_id ?? 'no further model'}</strong>
          <span>Trigger: {humanizeToken(ev.trigger)}</span><small>{ev.detail}</small><small>Original response: {humanizeToken(ev.original_response)} · Outcome: {ev.outcome || 'pending'}</small>
        </li>
      ))}
    </ol>
  );
}

function ExecutionSection({ e }: { e: EngineResult }) {
  const executed = e.execution.status !== 'not_requested';
  const conf = e.evaluation.confidence as { model_reported?: { note?: string }; evaluator_estimated?: { note?: string }; statement?: string } | undefined;
  if (!executed) {
    return (
      <Card id="xai-exec-title" title="After selection" sub="Response, quality checks and escalation">
        <div className="xai-empty-state">
          <span className="xai-ico" data-tone="neutral"><ShieldCheck aria-hidden="true" /></span>
          <div><strong>No model was run for this decision</strong><p>This was a recommendation, so there is no response, measured latency, cost or quality check to show. Switch Route Query to Execute mode to record generation, the checks that ran, the Accept / Verify / Escalate decision and any escalation.</p></div>
        </div>
      </Card>
    );
  }
  return (
    <div className="xai-exec">
      <Card id="xai-att-title" title="Attempts"><AttemptList e={e} />{e.execution.notes.map((n) => <p key={n} className="xai-muted">{n}</p>)}</Card>
      <Card id="xai-chk-title" title="Quality checks" right={<ListChecks className="xai-card-ico" aria-hidden="true" />}><ChecksList e={e} /></Card>
      <Card id="xai-dec-title" title="Decision">
        <DecisionCard e={e} />
        <div className="xai-sub-head"><h4>Confidence</h4></div>
        <ul className="xai-notrun"><li><strong>Model-reported</strong><small>{conf?.model_reported?.note ?? 'Unavailable'}</small></li><li><strong>Evaluator-estimated</strong><small>{conf?.evaluator_estimated?.note ?? 'Unavailable'}</small></li></ul>
        <p className="xai-muted">{conf?.statement ?? 'No calibrated confidence exists.'}</p>
      </Card>
      <Card id="xai-esc-title" title="Escalation"><EscalationTimeline e={e} /></Card>
    </div>
  );
}
