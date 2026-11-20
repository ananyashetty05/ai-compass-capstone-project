/**
 * Explainable-AI decision trace.
 *
 * Every element renders recorded data from the routing run (`EngineResult`): the real filtering
 * outcomes, the real score decomposition, counterfactuals recomputed by the router, and the checks that
 * actually ran. Unknown values stay unknown; stages that did not run say so and why.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, Check, ChevronDown, ExternalLink, Gauge, Info, Layers, Loader2, Minus, Scale, Tag, X } from 'lucide-react';
import { useRouteResult } from '../../context/routeResultContext';
import { fetchRoutingHistory } from '../../services/history.service';
import { getDecisionTrace } from '../../services/trace.service';
import { describeError } from '../../services/http';
import { formatPercent, humanizeToken } from '../../utils/format';
import type { EngineCandidate, EngineResult, RoutingHistoryEntry } from '../../types';
import { DIMS, DIM_LABEL, buildFlow, buildReport, fmtMs, groupRejections, provenanceLabel, selectedCandidate, tieNote, whyHeadline } from './traceModel';
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

type Panel = 'why' | 'models' | 'evidence';
const PANELS: { id: Panel; label: string }[] = [
  { id: 'why', label: 'Why this match' }, { id: 'models', label: 'Candidates & scoring' }, { id: 'evidence', label: 'Evidence & report' },
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
        {panel === 'evidence' ? <><EvidenceSection e={e} /><ReportSection e={e} /></> : null}
      </div>
    </div>
  );
}

/* ── Outcome ──────────────────────────────────────────────────────────────── */
function Hero({ e, query }: { e: EngineResult; query?: string }) {
  const top = selectedCandidate(e);
  const headline = useMemo(() => whyHeadline(e), [e]);
  const tie = useMemo(() => tieNote(e), [e]);
  const cat = e.profile.category;
  const rows = top ? [top, ...e.candidates.filter((c) => c.model_id !== top.model_id).slice(0, 2)] : [];
  const conf = e.selection.confidence_value;
  const kpis: { icon: React.ReactNode; k: string; v: string; s: string }[] = [
    { icon: <Gauge />, k: 'Confidence', v: `${humanizeToken(e.selection.confidence_level)} · ${conf.toFixed(2)}`, s: 'from the ranking, not an answer' },
    { icon: <Scale />, k: 'Category', v: cat ? cat.label : '—', s: cat ? `rule confidence ${cat.confidence.toFixed(2)}` : 'not recorded' },
    { icon: <Layers />, k: 'Compared', v: String(e.candidates.length), s: `${e.exclusions.length} outside the category or constraints` },
    { icon: <Tag />, k: 'Scoring version', v: `v${e.scoring_version}`, s: `engine ${e.version}` },
  ];
  return (
    <section className="xh" data-tone="route" aria-label="Decision summary">
      <div className="xh-grid">
        <div className="xh-main">
          <div className="xh-chips">
            <span className="xai-chip" data-tone="route">Recommendation</span>
            {cat ? <span className="xai-chip" data-tone="neutral">{cat.label}</span> : null}
            {e.recommendation_only ? <span className="xai-chip" data-tone="neutral">Nothing was run</span> : null}
          </div>
          <h3 className="xh-title">{top ? top.model_name : 'No product selected'}{top ? <span>{top.provider}</span> : null}</h3>
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
          <div className="xh-compare-head"><h4>How it compares</h4><span className="xh-compare-note">Fit score inside {cat ? cat.label : 'the category'}</span></div>
          <ul>
            {rows.map((c, i) => (
              <li key={c.model_id} data-sel={i === 0}>
                <span className="xh-rowname"><b>{c.model_name}</b><small>{i === 0 ? 'Best Match' : `Rank ${c.rank}`}</small></span>
                <span className="xh-track"><Meter value={top && top.robust_score > 0 ? Math.min(1, c.robust_score / top.robust_score) : 0} tone={i === 0 ? 'ok' : 'primary'} /></span>
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
  const cur = flow.find((n) => n.id === node) ?? flow[flow.length - 1];
  return (
    <Card id="xai-flow-title" title="Query to recommendation" sub="The path this query took to reach its Best Match. Select a stage for its recorded detail."
      right={<ul className="xf-key" aria-label="Stage states"><li data-state="done">Completed</li><li data-state="warn">Needs attention</li><li data-state="skipped">Not run</li></ul>}>
      <ol className="xf-steps" aria-label="Recommendation pipeline">
        {flow.map((n, i) => (
          <li key={n.id} data-state={n.state} style={{ ['--i' as string]: i }}>
            <button type="button" className="xf-node" data-state={n.state} aria-pressed={n.id === cur.id} onClick={() => onNode(n.id)}>
              <StateIcon state={n.state} n={i + 1} />
              <span className="xf-t">{n.label}</span>
              <span className="xf-s">{STATE_TEXT[n.state]}{n.ms !== undefined && n.state === 'done' ? <em>{fmtMs(n.ms)}</em> : null}</span>
            </button>
          </li>
        ))}
      </ol>
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
    case 'category': {
      const c = p.category;
      if (!c) return <p className="xai-muted">This decision was recorded before category routing existed.</p>;
      const ranked = Object.entries(c.scores).sort((a, b) => b[1] - a[1]).filter(([, v]) => v > 0).slice(0, 4);
      return (
        <>
          <Tiles rows={[
            ['Resolved category', c.label], ['Rule confidence', c.confidence.toFixed(2)],
            ['Rules that fired', c.signals.map(humanizeToken).join(', ') || 'None, so the general Conversational AI category is used', true],
            ['Runner-up category', c.runner_up ? `${humanizeToken(c.runner_up)} (${c.runner_up_score.toFixed(1)})` : 'None'],
            ['Required sub-type', c.required_subtype ? humanizeToken(c.required_subtype) : 'None'],
            ['Features asked for', c.features.map((f) => humanizeToken(f.feature)).join(', ') || 'None. Products are separated by category fit only.', true],
          ]} />
          {ranked.length ? <ul className="xd-catscores" aria-label="Category scores">{ranked.map(([k, v]) => <li key={k} data-win={k === c.category}><span>{humanizeToken(k)}</span><b>{v.toFixed(1)}</b></li>)}</ul> : null}
        </>
      );
    }
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
      return <Tiles rows={[['Approved pool', cs ? String(cs.catalogue_total) : '—'], ['Serve the category', cs?.category_members != null ? String(cs.category_members) : '—'], ['Compared', cs ? String(cs.eligible) : String(e.candidates.length)], ['Outside the category or constraints', String(e.exclusions.length)], ['API keys used', cs?.credentials_used_for_comparison === false ? 'No. Keys never affect the comparison.' : 'Not recorded']]} />;
    }
    case 'score': {
      const eco = !!top?.ecosystem_category;
      return eco ? <Tiles rows={[
        ['Method', 'Fit score: how well each product\'s documented strengths cover what the query asks for, plus category membership', true],
        ['Weights inside the fit score', 'Features asked for 50% · detected task 30% (conversational, coding and API categories) · category role 20%', true],
        ['Not scored', 'Quality, latency, reliability and risk: no measured value exists for any approved product, so they are excluded for all, never estimated', true],
        ['Cost', e.normalization ? humanizeToken(e.normalization.cost_basis) : '—'],
        ['Ties', 'Resolved by the approved-list order and labelled as such'],
      ]} /> : <Tiles rows={[
        ['Method', 'Weighted sum of per-objective utilities, ranked by a pessimistic robust score', true],
        ['Missing-data policy', e.scoring_config ? `${humanizeToken(e.scoring_config.missing_policy)} · unknown scores 0, never an average` : '—'],
        ['Uncertainty penalty', fmt(e.scoring_config?.uncertainty_penalty ?? e.normalization?.uncertainty_penalty, 2)],
        ['Cost basis', e.normalization ? `${humanizeToken(e.normalization.cost_basis)}` : '—'], ['Latency basis', e.normalization ? humanizeToken(e.normalization.latency_basis) : '—'],
      ]} />;
    }
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
          {stab != null ? (
            <div className="xd-metric">
              <span className="xd-k">Stable under weight changes</span>
              <strong>{formatPercent(stab, 0)}</strong>
              <Meter value={stab} tone={stab >= 0.75 ? 'ok' : stab >= 0.5 ? 'warn' : 'bad'} />
              <small>Share of a 10% re-weighting (worst direction) this winner survives</small>
            </div>
          ) : (
            <div className="xd-metric">
              <span className="xd-k">Selection confidence</span>
              <strong>{humanizeToken(e.selection.confidence_level)} · {e.selection.confidence_value.toFixed(2)}</strong>
              <Meter value={e.selection.confidence_value} tone={e.selection.confidence_value >= 0.75 ? 'ok' : e.selection.confidence_value >= 0.5 ? 'warn' : 'bad'} />
              <small>Category {fmt(e.selection.confidence_components?.category_confidence, 2)} · margin {fmt(e.selection.confidence_components?.ranking_margin, 2)} · features {fmt(e.selection.confidence_components?.feature_support, 2)}</small>
            </div>
          )}
          {e.selection.caveats.length ? (
            <ul className="xd-caveats" aria-label="Caveats">{e.selection.caveats.map((c) => <li key={c}><AlertTriangle aria-hidden="true" />{c}</li>)}</ul>
          ) : null}
        </div>
      );
    }
    default:
      return <p className="xai-muted">No further detail was recorded for this stage.</p>;
  }
}

/* ── Candidates & scoring ─────────────────────────────────────────────────── */
function FunnelSection({ e }: { e: EngineResult }) {
  const cs = e.catalogue_summary;
  const groups = groupRejections(e);
  const [open, setOpen] = useState<string | null>(null);
  const eco = cs?.pool_source === 'approved_ecosystem';
  const steps = cs ? (eco ? [
    { k: 'Approved pool', v: cs.catalogue_total, note: 'Every approved product, key or no key' },
    { k: 'Serve the category', v: cs.category_members ?? cs.eligible, note: `Category: ${e.profile.category?.label ?? 'unknown'}` },
    { k: 'Compared', v: cs.eligible, note: 'Passed every hard constraint' },
    { k: 'Selected', v: cs.selected, note: 'Highest fit score' },
  ] : [
    { k: 'In catalogue', v: cs.catalogue_total, note: 'Every known model, key or no key' },
    { k: 'Considered', v: cs.considered, note: 'After lifecycle checks' },
    { k: 'Eligible', v: cs.eligible, note: 'Passed every hard constraint' },
    { k: 'Scored', v: cs.scored, note: 'Ranked on the objectives' },
    { k: 'Selected', v: cs.selected, note: 'Highest robust score' },
  ]) : [];
  const max = Math.max(1, ...steps.map((s) => s.v));
  return (
    <Card id="xai-funnel-title" title="Category gate & filtering" sub="A product outside the query's category is never ranked against it, and a hard constraint removes a product outright. A missing credential never removes anything.">
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
      <div className="xai-sub-head"><h4>Why products were left out</h4><span>{e.exclusions.length} removed</span></div>
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

function EcosystemRanking({ e }: { e: EngineResult }) {
  const [all, setAll] = useState(false);
  const rows = all ? e.candidates : e.candidates.slice(0, 7);
  const selId = e.selection.selected_model_id;
  const asked = e.profile.category?.features ?? [];
  return (
    <Card id="xai-rank-title" title="Fit scoring" sub="Every product here serves the resolved category. The score is how well its documented strengths cover what the query asks for.">
      <div className="xai-table-wrap">
        <table className="xai-table">
          <caption className="sr-only">Products in the resolved category ranked by fit score</caption>
          <thead><tr><th>#</th><th>Product</th><th className="num">Features</th><th className="num">Task</th><th className="num">Category role</th><th>Matched</th><th className="num">Fit score</th></tr></thead>
          <tbody>
            {rows.map((c) => {
              const f = c.fit_breakdown ?? {};
              return (
                <tr key={c.model_id} data-selected={c.model_id === selId}>
                  <td className="rank">{c.rank}</td>
                  <td><strong>{c.model_name}</strong><small>{c.provider}{c.model_id === selId ? ' · Best Match' : ''}{c.category_role === 'secondary' ? ' · also serves this category' : ''}</small></td>
                  <td className="num">{asked.length ? fmt(f.feature_fit, 2) : '—'}</td>
                  <td className="num">{f.intent_fit != null ? fmt(f.intent_fit, 2) : '—'}</td>
                  <td className="num">{fmt(f.category_fit, 2)}</td>
                  <td>{(c.matched_features ?? []).length ? (c.matched_features ?? []).map(humanizeToken).join(', ') : <span className="xai-muted">{asked.length ? 'none' : 'nothing specific asked'}</span>}{(c.unmet_features ?? []).length ? <small>Not documented: {(c.unmet_features ?? []).map(humanizeToken).join(', ')}</small> : null}</td>
                  <td className="num score"><strong>{fmt(c.robust_score)}</strong></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="xai-table-foot">
        {e.candidates.length > 7 ? <button type="button" className="xai-btn" onClick={() => setAll(!all)}>{all ? 'Show top 7' : `Show all ${e.candidates.length} products`}</button> : <span />}
        <p>{e.normalization?.notes?.[0] ?? ''}</p>
      </div>
    </Card>
  );
}

function RankingSection({ e }: { e: EngineResult }) {
  const [all, setAll] = useState(false);
  if (e.candidates[0]?.ecosystem_category) return <EcosystemRanking e={e} />;
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
        <Card id="xai-why-title" title="Why it is the Best Match" sub={top ? `${top.model_name} against ${Math.max(0, e.candidates.length - 1)} other products in the same category` : undefined}>
          {e.explanation.why_selected.length ? <ul className="xai-rows">{e.explanation.why_selected.map((w) => <li key={w}><span className="xai-ico" data-tone="ok"><Check aria-hidden="true" /></span><p>{w}</p></li>)}</ul> : <p className="xai-muted">No supporting reasons were recorded.</p>}
          {e.explanation.tradeoffs.length ? (
            <>
              <div className="xai-sub-head"><h4>Trade-offs</h4></div>
              <ul className="xai-rows">{e.explanation.tradeoffs.map((w) => <li key={w}><span className="xai-ico" data-tone="warn"><Scale aria-hidden="true" /></span><p>{w}</p></li>)}</ul>
            </>
          ) : null}
          <div className="xai-confidence">
            <div><span>Confidence</span><b>{humanizeToken(e.selection.confidence_level)} · {e.selection.confidence_value.toFixed(2)}</b></div>
            {stab != null ? <div><span>Survives a 10% re-weighting</span><b>{formatPercent(stab, 0)}</b><Meter value={stab} tone={stab >= 0.75 ? 'ok' : stab >= 0.5 ? 'warn' : 'bad'} /></div> : null}
            <div><span>Margin over runner-up</span><b>{e.selection.score_margin == null ? '—' : fmt(e.selection.score_margin)}</b></div>
          </div>
          {e.selection.confidence_formula ? (
            <details className="xai-reveal">
              <summary>How confidence is computed</summary>
              <p className="xai-muted">{e.selection.confidence_formula}</p>
              <ul className="xai-notrun">{e.confidence_report?.components.map((c) => <li key={c.name}><strong>{humanizeToken(c.name)} · {c.value == null ? '—' : c.value.toFixed(2)}</strong><small>{c.basis}</small></li>)}</ul>
            </details>
          ) : null}
        </Card>
        <Card id="xai-alt-title" title="Suggested alternatives" sub="Ranks 2 to 4 of the same ranking, and where they fell short.">
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
  if (top.ecosystem_category) {
    const match = e.ranking?.find((r) => r.model_id === top.model_id);
    return (
      <Card id="xai-ev-title" title="Where the fit comes from" sub={`Evidence for ${top.model_name}. Strengths are taken from the vendor's published positioning; they are not benchmark results.`}>
        <Tiles rows={[
          ['Documented strengths', (top.strengths ?? []).map(humanizeToken).join(', ') || 'None recorded', true],
          ['Matched what you asked for', (top.matched_features ?? []).map(humanizeToken).join(', ') || (e.profile.category?.features.length ? 'None' : 'Nothing specific was asked'), true],
          ['Not documented for this product', (top.unmet_features ?? []).map(humanizeToken).join(', ') || 'None'],
          ['Measured quality, price, latency', 'Unavailable for every approved product. Never estimated.'],
        ]} />
        {match?.external_url ? <p className="xai-muted"><a className="xai-link" href={match.external_url} target="_blank" rel="noopener noreferrer">Open {top.model_name}<ExternalLink aria-hidden="true" /></a></p> : null}
        {e.explanation.unavailable_data.length ? <ul className="xai-rows xai-rows-tight">{e.explanation.unavailable_data.map((u) => <li key={u}><span className="xai-ico" data-tone="neutral"><Info aria-hidden="true" /></span><p>{u}</p></li>)}</ul> : null}
      </Card>
    );
  }
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
