import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import {
  ArrowRight,
  BarChart3,
  ChevronDown,
  CornerDownLeft,
  FlaskConical,
  Info,
  Layers,
  Loader2,
  ShieldCheck,
  SlidersHorizontal,
  Table2,
  Tag,
  X,
} from 'lucide-react';
import { PageHeader } from '../components/layout/PageHeader';
import { EvaluationPipeline } from '../components/evaluation/EvaluationPipeline';
import { MetricGuide, ResultReading } from '../components/evaluation/EvaluationInsights';
import { StrategyCard } from '../components/evaluation/StrategyCard';
import { STRATEGIES, strategyShort, strategyTitle } from '../components/evaluation/strategies';
import { SegmentedControl } from '../components/ui/ds';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { useRouteResult } from '../context/routeResultContext';
import { evaluateOffline } from '../services/evaluation.service';
import { describeError } from '../services/http';
import { formatDuration, formatPercent, formatUsd } from '../utils/format';
import { scrollToElement } from '../utils/scroll';
import type { OfflineEvaluationResponse, OfflineStrategyResult } from '../types';

const EMPTY_RESULTS: OfflineStrategyResult[] = [];
const MAX_QUERY = 8000;

const METRICS = [
  { key: 'quality_score', label: 'Quality', suffix: 'registry estimate' },
  { key: 'estimated_cost_usd', label: 'Input cost', suffix: 'estimated USD' },
  { key: 'latency_seconds', label: 'Latency', suffix: 'registry estimate' },
  { key: 'reliability_score', label: 'Reliability', suffix: 'registry metadata' },
] as const;
type MetricKey = (typeof METRICS)[number]['key'];

const TASK_CATEGORIES = [
  ['coding', 'Coding'], ['research', 'Research'], ['creative', 'Writing'], ['analysis', 'Analysis'],
  ['math', 'Mathematics'], ['image-generation', 'Image generation'], ['video-generation', 'Video generation'],
  ['presentation', 'Presentations'], ['audio-generation', 'Audio / music'], ['reasoning', 'General reasoning'],
  ['education', 'Learning'], ['summarization', 'Summarization'], ['design', 'Design'],
] as const;

const CAPABILITIES = ['coding', 'reasoning', 'math', 'research', 'image-generation'];

const STRATEGY_COLOR: Record<string, string> = {
  aicompass: 'var(--color-primary)',
  strongest: 'var(--ev-c-strong)',
  cheapest: 'var(--ev-c-cheap)',
  static: 'var(--ev-c-static)',
};

function formatMetric(value: number | null, metric: MetricKey): string {
  if (value === null || !Number.isFinite(value)) return '—';
  if (metric === 'quality_score' || metric === 'reliability_score') return formatPercent(value);
  if (metric === 'estimated_cost_usd') return formatUsd(value, 6);
  return formatDuration(value * 1000);
}

export function Evaluation() {
  useDocumentTitle('Evaluation · AI Compass');
  const { result: lastRoute } = useRouteResult();
  const [query, setQuery] = useState(lastRoute?.query ?? '');
  const [taskTypeHint, setTaskTypeHint] = useState('');
  const [maxInputPrice, setMaxInputPrice] = useState('');
  const [maxLatency, setMaxLatency] = useState('');
  const [requiredCapabilities, setRequiredCapabilities] = useState<string[]>([]);
  const [constraintsOpen, setConstraintsOpen] = useState(false);
  const [evaluation, setEvaluation] = useState<OfflineEvaluationResponse | null>(null);
  const [metric, setMetric] = useState<MetricKey>('quality_score');
  const [view, setView] = useState<'chart' | 'table'>('chart');
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<{ message: string; hint?: string } | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  const revealRef = useRef(false);
  const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const constraintCount = (maxInputPrice ? 1 : 0) + (maxLatency ? 1 : 0) + requiredCapabilities.length;

  const run = useCallback(async () => {
    const text = query.trim();
    if (text.length < 3 || running) return;
    if (maxInputPrice && (!Number.isFinite(Number(maxInputPrice)) || Number(maxInputPrice) <= 0)) {
      setError({ message: 'Maximum input price must be greater than zero.' });
      setConstraintsOpen(true);
      return;
    }
    if (maxLatency && (!Number.isFinite(Number(maxLatency)) || Number(maxLatency) <= 0)) {
      setError({ message: 'Maximum latency must be greater than zero.' });
      setConstraintsOpen(true);
      return;
    }
    const controller = new AbortController();
    controllerRef.current?.abort();
    controllerRef.current = controller;
    setRunning(true);
    setEvaluation(null);
    setError(null);
    revealRef.current = true;
    requestAnimationFrame(() => { if (resultsRef.current) scrollToElement(resultsRef.current); });
    try {
      const response = await evaluateOffline({
        query: text,
        ...(taskTypeHint ? { task_type_hint: taskTypeHint } : {}),
        ...(maxInputPrice ? { max_cost: Number(maxInputPrice) } : {}),
        ...(maxLatency ? { max_latency: Number(maxLatency) } : {}),
        ...(requiredCapabilities.length ? { require_capabilities: requiredCapabilities } : {}),
      }, controller.signal);
      setEvaluation(response);
    } catch (cause) {
      if (!controller.signal.aborted) setError(describeError(cause, 'Offline evaluation could not be completed.'));
    } finally {
      if (!controller.signal.aborted) setRunning(false);
    }
  }, [query, running, taskTypeHint, maxInputPrice, maxLatency, requiredCapabilities]);

  // Settle onto the results once they land.
  useEffect(() => {
    if (!revealRef.current || running || !evaluation) return;
    revealRef.current = false;
    const raf = requestAnimationFrame(() => { if (resultsRef.current) scrollToElement(resultsRef.current); });
    return () => cancelAnimationFrame(raf);
  }, [evaluation, running]);

  const results = evaluation?.strategy_results ?? EMPTY_RESULTS;
  const resultsByKey = useMemo(() => new Map(results.map((row) => [row.strategy, row])), [results]);
  const ordered = STRATEGIES.flatMap(({ key }) => { const r = resultsByKey.get(key); return r ? [r] : []; });
  const selectedRows = results.filter((row) => row.selected_model_id !== null);
  const uniqueSelections = new Set(selectedRows.map((row) => row.selected_model_id));
  const compassPick = resultsByKey.get('aicompass')?.selected_model_id ?? null;
  const baselinesPicked = selectedRows.filter((r) => r.strategy !== 'aicompass');
  const agreeing = compassPick ? baselinesPicked.filter((r) => r.selected_model_id === compassPick).length : 0;
  const metricDefinition = METRICS.find((item) => item.key === metric) ?? METRICS[0];
  const chartData = useMemo(() => results
    .filter((row) => row.status === 'selected' && row[metric] !== null)
    .map((row) => ({ key: row.strategy, strategy: strategyShort(row.strategy), value: row[metric] as number, model: row.selected_model ?? '—' })), [results, metric]);

  const toggleCapability = (c: string) =>
    setRequiredCapabilities((cur) => (cur.includes(c) ? cur.filter((v) => v !== c) : [...cur, c]));
  const clearConstraints = () => { setMaxInputPrice(''); setMaxLatency(''); setRequiredCapabilities([]); };
  const canUseLast = !!lastRoute?.query && lastRoute.query !== query;

  return (
    <>
      <PageHeader
        eyebrow="Research · routing policies"
        title="Evaluation Lab"
        description="See how AI Compass and three fixed baselines choose from the same eligible models. Offline, from registry metadata. No model is run."
      />

      <div className="page-body ev">
        {/* ── Test bench ─────────────────────────────────────────── */}
        <section className="ev-bench" aria-labelledby="ev-bench-title">
          <header className="ev-bench-head">
            <span className="ev-bench-icon" aria-hidden="true"><FlaskConical /></span>
            <div>
              <h2 id="ev-bench-title">Test a query</h2>
              <p>Describe a task. All four strategies pick a model for it from the same filtered pool.</p>
            </div>
            <span className="ev-offline-pill"><ShieldCheck aria-hidden="true" />Offline · no cost</span>
          </header>

          <div className="ev-input">
            <textarea
              id="offline-query"
              value={query}
              onChange={(e) => setQuery(e.target.value.slice(0, MAX_QUERY))}
              onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); void run(); } }}
              placeholder="e.g. Write a Python function that merges overlapping intervals and explain its complexity…"
              rows={3}
              aria-label="Test query"
              disabled={running}
            />
            <div className="ev-input-foot">
              <span className="ev-count">{query.length.toLocaleString()} / {MAX_QUERY.toLocaleString()}</span>
              {canUseLast ? (
                <button type="button" className="ev-link-btn" onClick={() => setQuery(lastRoute!.query)}>
                  <CornerDownLeft aria-hidden="true" />Use last routed query
                </button>
              ) : null}
              <span className="ev-input-actions">
                <kbd className="rq-kbd" aria-hidden="true">{isMac ? '⌘ ↵' : 'Ctrl ↵'}</kbd>
                <button type="button" className="ev-run" onClick={() => void run()} disabled={running || query.trim().length < 3} aria-keyshortcuts={isMac ? 'Meta+Enter' : 'Control+Enter'}>
                  {running ? <><Loader2 className="spin" aria-hidden="true" />Evaluating…</> : <>{evaluation ? 'Evaluate again' : 'Evaluate'}<ArrowRight aria-hidden="true" /></>}
                </button>
              </span>
            </div>
          </div>

          <div className="ev-options">
            <label className="ev-select">
              <Tag aria-hidden="true" />
              <span className="sr-only">Task category</span>
              <select value={taskTypeHint} onChange={(e) => setTaskTypeHint(e.target.value)} disabled={running}>
                <option value="">Category: detect from query</option>
                {TASK_CATEGORIES.map(([value, label]) => <option key={value} value={value}>Category: {label}</option>)}
              </select>
              <ChevronDown aria-hidden="true" className="ev-select-chev" />
            </label>
            <button type="button" className="ev-toggle" aria-expanded={constraintsOpen} aria-controls="ev-constraints" onClick={() => setConstraintsOpen((o) => !o)}>
              <SlidersHorizontal aria-hidden="true" />Hard constraints
              {constraintCount > 0 ? <span className="ev-badge">{constraintCount}</span> : null}
              <ChevronDown aria-hidden="true" className="ev-toggle-chev" />
            </button>
            {constraintCount > 0 ? (
              <button type="button" className="ev-link-btn" onClick={clearConstraints}><X aria-hidden="true" />Clear</button>
            ) : null}
          </div>

          <div id="ev-constraints" className="ev-constraints" data-open={constraintsOpen || undefined} inert={!constraintsOpen || undefined}>
            <div className="ev-constraints-inner">
              <label className="ev-field">
                <span>Max input price / 1K tokens</span>
                <span className="ev-field-input"><em>$</em><input type="number" min="0.0001" step="0.0001" value={maxInputPrice} onChange={(e) => setMaxInputPrice(e.target.value)} placeholder="No limit" /></span>
              </label>
              <label className="ev-field">
                <span>Max estimated latency</span>
                <span className="ev-field-input"><input type="number" min="0.1" step="0.5" value={maxLatency} onChange={(e) => setMaxLatency(e.target.value)} placeholder="No limit" /><em>sec</em></span>
              </label>
              <fieldset className="ev-caps">
                <legend>Required capabilities</legend>
                <div>
                  {CAPABILITIES.map((c) => (
                    <button key={c} type="button" className="ev-cap" aria-pressed={requiredCapabilities.includes(c)} onClick={() => toggleCapability(c)}>
                      {c.replaceAll('-', ' ')}
                    </button>
                  ))}
                </div>
              </fieldset>
            </div>
          </div>

          {error ? (
            <div className="ev-error" role="alert"><Info aria-hidden="true" /><span>{error.message}{error.hint ? ` ${error.hint}` : ''}</span></div>
          ) : null}
        </section>

        {/* ── Results ────────────────────────────────────────────── */}
        <div ref={resultsRef} className="ev-results-anchor">
          {running ? (
            <section className="ev-section" aria-busy="true" aria-label="Evaluating">
              <div className="ev-running" role="status"><Loader2 className="spin" aria-hidden="true" />Analysing the query and scoring registry candidates…</div>
              <div className="ev-grid">
                {STRATEGIES.map((s, i) => <div key={s.key} className="ev-card ev-card--skeleton" style={{ ['--i' as string]: i }} aria-hidden="true"><i /><i /><i /><i /></div>)}
              </div>
            </section>
          ) : null}

          {evaluation && !running ? (
            <div className="ev-results">
              <section className="ev-stats" aria-label="Run summary">
                <div className="ev-stat"><span>Eligible pool</span><strong>{evaluation.candidate_count}</strong><small>model{evaluation.candidate_count === 1 ? '' : 's'} after filtering</small></div>
                <div className="ev-stat"><span>Distinct picks</span><strong>{uniqueSelections.size}</strong><small>across {selectedRows.length} selecting strateg{selectedRows.length === 1 ? 'y' : 'ies'}</small></div>
                <div className="ev-stat"><span>Agree with AI Compass</span><strong>{compassPick ? `${agreeing}/${baselinesPicked.length}` : '—'}</strong><small>{compassPick ? 'baselines chose the same model' : 'AI Compass made no pick'}</small></div>
                <div className="ev-stat"><span>Filtered out</span><strong>{evaluation.filtered_models.length}</strong><small>ineligible registry entries</small></div>
              </section>

              <section className="ev-section" aria-labelledby="ev-cmp-title">
                <header className="ev-section-head">
                  <div><p className="ev-kicker">Results</p><h2 id="ev-cmp-title">Strategy comparison</h2></div>
                  <p className="ev-section-note">Figures are registry metadata; “—” means the registry has no value.</p>
                </header>
                <div className="ev-grid">
                  {ordered.map((row, i) => <StrategyCard key={row.strategy} row={row} compassPick={compassPick} index={i} />)}
                </div>
              </section>

              <ResultReading rows={ordered.map((row) => ({ ...row, title: strategyShort(row.strategy) }))} />

              <section className="ev-section" aria-labelledby="ev-metrics-title">
                <header className="ev-section-head">
                  <div><p className="ev-kicker">Metrics</p><h2 id="ev-metrics-title">Compare side by side</h2></div>
                  <SegmentedControl
                    label="View"
                    value={view}
                    onChange={setView}
                    options={[{ value: 'chart', label: 'Chart', icon: <BarChart3 /> }, { value: 'table', label: 'Table', icon: <Table2 /> }]}
                  />
                </header>

                {view === 'chart' ? (
                  <div className="ev-chart-wrap">
                    <div className="ev-chart-bar">
                      <SegmentedControl
                        label="Chart metric"
                        value={metric}
                        onChange={setMetric}
                        options={METRICS.map((m) => ({ value: m.key, label: m.label }))}
                      />
                      <span className="ev-section-note">{metricDefinition.label} · {metricDefinition.suffix}. Missing values are left out, not shown as zero.</span>
                    </div>
                    {chartData.length ? (
                      <div className="ev-chart">
                        <ResponsiveContainer width="100%" height={Math.max(170, chartData.length * 56)}>
                          <BarChart data={chartData} layout="vertical" margin={{ top: 4, right: 28, bottom: 4, left: 4 }}>
                            <CartesianGrid horizontal={false} stroke="var(--color-border-subtle)" />
                            <XAxis type="number" stroke="var(--color-text-muted)" tick={{ fill: 'var(--color-text-secondary)', fontSize: 11 }}
                              tickFormatter={(v) => (metric === 'quality_score' || metric === 'reliability_score' ? `${Math.round(Number(v) * 100)}%` : String(v))} />
                            <YAxis type="category" dataKey="strategy" width={96} stroke="var(--color-text-muted)" tick={{ fill: 'var(--color-text-secondary)', fontSize: 12 }} />
                            <Tooltip
                              cursor={{ fill: 'var(--color-primary-subtle)' }}
                              formatter={(value) => [formatMetric(Number(value), metric), metricDefinition.label]}
                              labelFormatter={(label, payload) => { const m = payload?.[0]?.payload?.model; return m ? `${label} · ${m}` : label; }}
                              contentStyle={{ background: 'var(--color-surface-raised)', borderColor: 'var(--color-border)', borderRadius: 10, color: 'var(--color-text-primary)' }}
                            />
                            <Bar dataKey="value" name={metricDefinition.label} radius={[0, 6, 6, 0]} maxBarSize={26}>
                              {chartData.map((d) => <Cell key={d.key} fill={STRATEGY_COLOR[d.key] ?? 'var(--color-primary)'} />)}
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    ) : (
                      <p className="ev-chart-empty">No strategy’s model has a {metricDefinition.label.toLowerCase()} value in the registry.</p>
                    )}
                  </div>
                ) : (
                  <div className="table-wrap ev-table-wrap">
                    <table className="data-table ev-table">
                      <thead>
                        <tr>
                          <th scope="col">Strategy</th><th scope="col">Selected model</th><th scope="col">Routing score</th>
                          <th scope="col">Quality</th><th scope="col">Input cost</th><th scope="col">Latency</th>
                          <th scope="col">Reliability</th><th scope="col">Constraints</th>
                        </tr>
                      </thead>
                      <tbody>
                        {ordered.map((row) => (
                          <tr key={row.strategy}>
                            <th scope="row"><span className="ev-dot" style={{ background: STRATEGY_COLOR[row.strategy] }} aria-hidden="true" />{strategyTitle(row.strategy)}</th>
                            <td>{row.selected_model ?? <span className="ev-na">No pick</span>}{row.provider ? <small>{row.provider}</small> : null}</td>
                            <td>{row.routing_score === null ? '—' : formatPercent(row.routing_score)}</td>
                            <td>{formatMetric(row.quality_score, 'quality_score')}</td>
                            <td>{formatMetric(row.estimated_cost_usd, 'estimated_cost_usd')}</td>
                            <td>{formatMetric(row.latency_seconds, 'latency_seconds')}</td>
                            <td>{formatMetric(row.reliability_score, 'reliability_score')}</td>
                            <td>{row.status !== 'selected' ? '—' : row.constraint_satisfied ? 'Satisfied' : 'Not met'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              <div className="ev-notes">
                {evaluation.filtered_models.length > 0 ? (
                  <details className="ev-note">
                    <summary><Layers aria-hidden="true" />Filtered models <span className="ev-badge">{evaluation.filtered_models.length}</span><ChevronDown aria-hidden="true" className="ev-note-chev" /></summary>
                    <ul className="ev-filtered">
                      {evaluation.filtered_models.map((item) => <li key={item.model_id}><code>{item.model_id}</code><span>{item.reason}</span></li>)}
                    </ul>
                  </details>
                ) : null}
                <details className="ev-note">
                  <summary><ShieldCheck aria-hidden="true" />Research validity and methodology<ChevronDown aria-hidden="true" className="ev-note-chev" /></summary>
                  <div className="ev-note-body">
                    <p>{evaluation.data_disclosure}</p>
                    <p>
                      All four strategies use the same analysed query, registry catalog and hard-constraint-filtered pool.
                      AI Compass uses the signed-in profile’s routing weights. Quality is a registry estimate unless its source
                      names a benchmark; it is not a measured response-quality score. Input cost uses the estimated input-token
                      count and known input pricing only, excluding output tokens. Latency, reliability, risk, capability,
                      context-window and availability fields are registry metadata, not measurements from this run.
                    </p>
                  </div>
                </details>
              </div>
            </div>
          ) : null}
        </div>

        {/* ── Method ─────────────────────────────────────────────── */}
        <EvaluationPipeline evaluation={running ? null : evaluation} />
        <MetricGuide />
      </div>
    </>
  );
}
