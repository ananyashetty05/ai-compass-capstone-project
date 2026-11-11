import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  BarChart3,
  CheckCircle2,
  CircleDollarSign,
  Info,
  ListOrdered,
  Loader2,
  ShieldCheck,
  Trophy,
} from 'lucide-react';
import { PageHeader } from '../components/layout/PageHeader';
import { Button, ButtonLink } from '../components/ui/Button';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { useRouteResult } from '../context/routeResultContext';
import { evaluateOffline } from '../services/evaluation.service';
import { describeError } from '../services/http';
import { formatDuration, formatPercent, formatUsd } from '../utils/format';
import type {
  OfflineEvaluationResponse,
  OfflineEvaluationStrategy,
  OfflineStrategyResult,
} from '../types';

const EMPTY_RESULTS: OfflineStrategyResult[] = [];

const STRATEGIES: Array<{
  key: OfflineEvaluationStrategy;
  title: string;
  description: string;
  icon: typeof BarChart3;
}> = [
  {
    key: 'aicompass',
    title: 'AI Compass Routing',
    description: 'Existing multi-objective router and configured user weights.',
    icon: BarChart3,
  },
  {
    key: 'strongest',
    title: 'Strongest Model Baseline',
    description: 'Highest available registry quality score after filtering.',
    icon: Trophy,
  },
  {
    key: 'cheapest',
    title: 'Cheapest Model Baseline',
    description: 'Lowest known input price; unknown prices are excluded.',
    icon: CircleDollarSign,
  },
  {
    key: 'static',
    title: 'Static Ranking Baseline',
    description: 'Fixed fallback priority, independent of user weights.',
    icon: ListOrdered,
  },
];

const METRICS = [
  { key: 'quality_score', label: 'Quality score', suffix: ' · registry estimate' },
  { key: 'estimated_cost_usd', label: 'Input cost', suffix: ' · estimated USD' },
  { key: 'latency_seconds', label: 'Latency', suffix: ' · registry estimate' },
  { key: 'reliability_score', label: 'Reliability', suffix: ' · registry metadata' },
] as const;

type MetricKey = (typeof METRICS)[number]['key'];

const TASK_CATEGORIES = [
  ['coding', 'Coding'],
  ['research', 'Research'],
  ['creative', 'Writing'],
  ['analysis', 'Analysis'],
  ['math', 'Mathematics'],
  ['image-generation', 'Image generation'],
  ['video-generation', 'Video generation'],
  ['presentation', 'Presentations'],
  ['audio-generation', 'Audio / music'],
  ['reasoning', 'General reasoning'],
  ['education', 'Learning'],
  ['summarization', 'Summarization'],
  ['design', 'Design'],
] as const;

function formatMetric(value: number | null, metric: MetricKey): string {
  if (value === null || !Number.isFinite(value)) return 'Unavailable';
  if (metric === 'quality_score' || metric === 'reliability_score') return formatPercent(value);
  if (metric === 'estimated_cost_usd') return formatUsd(value, 8);
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
  const [evaluation, setEvaluation] = useState<OfflineEvaluationResponse | null>(null);
  const [metric, setMetric] = useState<MetricKey>('quality_score');
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<{ message: string; hint?: string } | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const run = useCallback(async () => {
    const text = query.trim();
    if (text.length < 3 || running) return;
    if (maxInputPrice && (!Number.isFinite(Number(maxInputPrice)) || Number(maxInputPrice) <= 0)) {
      setError({ message: 'Maximum input price must be greater than zero.' });
      return;
    }
    if (maxLatency && (!Number.isFinite(Number(maxLatency)) || Number(maxLatency) <= 0)) {
      setError({ message: 'Maximum latency must be greater than zero.' });
      return;
    }
    const controller = new AbortController();
    controllerRef.current?.abort();
    controllerRef.current = controller;
    setRunning(true);
    setEvaluation(null);
    setError(null);
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
      if (!controller.signal.aborted) {
        setError(describeError(cause, 'Offline evaluation could not be completed.'));
      }
    } finally {
      if (!controller.signal.aborted) setRunning(false);
    }
  }, [query, running, taskTypeHint, maxInputPrice, maxLatency, requiredCapabilities]);

  const results = evaluation?.strategy_results ?? EMPTY_RESULTS;
  const resultsByKey = useMemo(
    () => new Map(results.map(row => [row.strategy, row])),
    [results],
  );
  const chartData = useMemo(() => results
    .filter(row => row.status === 'selected' && row[metric] !== null)
    .map(row => ({
      strategy: STRATEGIES.find(item => item.key === row.strategy)?.title ?? row.strategy,
      value: row[metric] as number,
      model: row.selected_model ?? 'Unavailable',
    })), [results, metric]);
  const selectedRows = results.filter(row => row.selected_model_id !== null);
  const uniqueSelections = new Set(selectedRows.map(row => row.selected_model_id));
  const metricDefinition = METRICS.find(item => item.key === metric) ?? METRICS[0];

  const setCapability = (capability: string) => {
    setRequiredCapabilities(current => current.includes(capability)
      ? current.filter(value => value !== capability)
      : [...current, capability]);
  };

  return (
    <>
      <PageHeader
        eyebrow="Research · routing policies"
        title="Evaluation Lab"
        description="Compare model-selection strategies using offline registry metadata. No provider inference is performed."
      />

      <div className="page-body evaluation-page offline-evaluation">
        <section className="evaluation-overview" aria-label="Offline evaluation status">
          <div className="evaluation-status-line">
            <div>
              <span className="evaluation-kicker">OFFLINE EVALUATION</span>
              <strong>{running ? 'Evaluating routing strategies' : evaluation ? 'Comparison complete' : 'Ready to evaluate'}</strong>
            </div>
            <span className="offline-status"><CheckCircle2 size={15} aria-hidden="true" /> No provider calls</span>
          </div>
          <div className="evaluation-strategy-grid">
            {STRATEGIES.map(({ key, title, description, icon: Icon }) => (
              <article
                key={key}
                className="evaluation-strategy"
                data-own={key === 'aicompass' || undefined}
                data-evaluated={resultsByKey.has(key) ? 'true' : undefined}
              >
                <span className="evaluation-strategy-icon"><Icon size={17} aria-hidden="true" /></span>
                <div className="evaluation-strategy-copy">
                  <h2>{title}</h2>
                  <p>{description}</p>
                </div>
                <span className="evaluation-strategy-state">
                  {resultsByKey.has(key) ? 'Evaluated' : 'Ready'}
                </span>
              </article>
            ))}
          </div>
        </section>

        <section className="offline-evaluation-controls" aria-label="Evaluation controls">
          <div className="offline-query-field">
            <label htmlFor="offline-query">Test query</label>
            <textarea
              id="offline-query"
              value={query}
              onChange={event => setQuery(event.target.value)}
              placeholder="Describe a task to compare routing decisions…"
              rows={3}
              maxLength={8000}
            />
            <span>{query.length.toLocaleString()} / 8,000 characters · only used for local query analysis</span>
          </div>
          <div className="offline-control-row">
            <label>
              Task category
              <select value={taskTypeHint} onChange={event => setTaskTypeHint(event.target.value)}>
                <option value="">Detect from query</option>
                {TASK_CATEGORIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <details className="offline-constraints">
              <summary>Hard constraints</summary>
              <div className="offline-constraint-fields">
                <label>
                  Max input price / 1K tokens (USD)
                  <input type="number" min="0.0001" step="0.0001" value={maxInputPrice} onChange={event => setMaxInputPrice(event.target.value)} placeholder="No limit" />
                </label>
                <label>
                  Max estimated latency (seconds)
                  <input type="number" min="0.1" step="0.5" value={maxLatency} onChange={event => setMaxLatency(event.target.value)} placeholder="No limit" />
                </label>
                <fieldset>
                  <legend>Required capability</legend>
                  {['coding', 'reasoning', 'math', 'research', 'image-generation'].map(capability => (
                    <label key={capability}>
                      <input type="checkbox" checked={requiredCapabilities.includes(capability)} onChange={() => setCapability(capability)} />
                      {capability.replaceAll('-', ' ')}
                    </label>
                  ))}
                </fieldset>
              </div>
            </details>
            <Button
              variant="primary"
              onClick={() => void run()}
              loading={running}
              disabled={query.trim().length < 3}
              leadingIcon={running ? <Loader2 className="spin" /> : <BarChart3 />}
            >
              {running ? 'Evaluating…' : evaluation ? 'Evaluate again' : 'Evaluate routing'}
            </Button>
          </div>
          {error && (
            <div className="offline-evaluation-error" role="alert">
              <Info size={16} aria-hidden="true" />
              <span>{error.message}{error.hint ? ` ${error.hint}` : ''}</span>
            </div>
          )}
        </section>

        {evaluation && (
          <>
            <section className="offline-selection-summary" aria-label="Model selection differences">
              <div>
                <span className="evaluation-kicker">SHARED ELIGIBLE POOL</span>
                <strong>{evaluation.candidate_count} model{evaluation.candidate_count === 1 ? '' : 's'}</strong>
                <small>after hard-constraint filtering</small>
              </div>
              <div>
                <span className="evaluation-kicker">SELECTIONS</span>
                <strong>{uniqueSelections.size} distinct model{uniqueSelections.size === 1 ? '' : 's'}</strong>
                <small>{selectedRows.length - uniqueSelections.size} repeated selection{selectedRows.length - uniqueSelections.size === 1 ? '' : 's'} across strategies</small>
              </div>
              <div>
                <span className="evaluation-kicker">FILTERED OUT</span>
                <strong>{evaluation.filtered_models.length}</strong>
                <small>ineligible registry entries</small>
              </div>
            </section>

            <section className="offline-results" aria-labelledby="offline-results-title">
              <div className="evaluation-section-heading">
                <div>
                  <span className="evaluation-kicker">SELECTION RESULTS</span>
                  <h2 id="offline-results-title">Strategy comparison</h2>
                </div>
                <span>Registry and benchmark metadata only</span>
              </div>
              <div className="offline-result-grid">
                {STRATEGIES.map(({ key, title, icon: Icon }) => {
                  const row = resultsByKey.get(key);
                  if (!row) return null;
                  return (
                    <article className="offline-result-card" key={key} data-own={key === 'aicompass' || undefined}>
                      <header>
                        <Icon size={17} aria-hidden="true" />
                        <h3>{title}</h3>
                        <span className={`offline-result-status${row.status === 'selected' ? '' : ' is-unavailable'}`}>
                          {row.status === 'selected' ? 'Selected' : 'Unavailable'}
                        </span>
                      </header>
                      <div className="offline-model-selection">
                        <span className="evaluation-kicker">SELECTED MODEL</span>
                        <strong>{row.selected_model ?? 'No model selected'}</strong>
                        {row.provider && <small>{row.provider} · {row.selected_model_id}</small>}
                      </div>
                      <p className="offline-rationale">{row.selection_rationale}</p>
                      {row.status === 'selected' && (
                        <>
                          {row.routing_score !== null && (
                            <div className="offline-routing-score">
                              <span>Routing score</span>
                              <strong>{formatPercent(row.routing_score)}</strong>
                            </div>
                          )}
                          <dl className="offline-metrics">
                            <div><dt>Quality score</dt><dd>{formatMetric(row.quality_score, 'quality_score')}</dd></div>
                            <div><dt>Estimated input cost</dt><dd>{formatMetric(row.estimated_cost_usd, 'estimated_cost_usd')}</dd></div>
                            <div><dt>Latency</dt><dd>{formatMetric(row.latency_seconds, 'latency_seconds')}</dd></div>
                            <div><dt>Reliability</dt><dd>{formatMetric(row.reliability_score, 'reliability_score')}</dd></div>
                            <div><dt>Risk / privacy</dt><dd>{formatMetric(row.risk_score, 'reliability_score')}</dd></div>
                            <div><dt>Context window</dt><dd>{row.context_window ? `${row.context_window.toLocaleString()} tokens` : 'Unavailable'}</dd></div>
                            <div><dt>Constraints</dt><dd>{row.constraint_satisfied ? 'Satisfied' : 'Not satisfied'}</dd></div>
                          </dl>
                        </>
                      )}
                      {row.quality_source && <p className="offline-source">Quality source: {row.quality_source}</p>}
                      {row.cost_basis && <p className="offline-source">{row.cost_basis}</p>}
                      {row.missing_data.length > 0 && (
                        <details className="offline-missing">
                          <summary>Metric availability · {row.missing_data.length} missing</summary>
                          <ul>{row.missing_data.map(item => <li key={item}>{item}</li>)}</ul>
                        </details>
                      )}
                    </article>
                  );
                })}
              </div>
            </section>

            <section className="offline-chart-section" aria-label="Metric comparison chart">
              <div className="evaluation-section-heading">
                <div><span className="evaluation-kicker">METADATA VISUALIZATION</span><h2>Compare available metrics</h2></div>
                <label className="offline-chart-select">
                  <span className="sr-only">Chart metric</span>
                  <select value={metric} onChange={event => setMetric(event.target.value as MetricKey)}>
                    {METRICS.map(item => <option key={item.key} value={item.key}>{item.label}</option>)}
                  </select>
                </label>
              </div>
              <p className="offline-chart-caption">
                {metricDefinition.label}{metricDefinition.suffix}. Missing values are omitted, not represented as zero.
              </p>
              {chartData.length ? (
                <div className="offline-chart">
                  <ResponsiveContainer width="100%" height={Math.max(180, chartData.length * 52)}>
                    <BarChart data={chartData} layout="vertical" margin={{ top: 8, right: 24, bottom: 8, left: 10 }}>
                      <CartesianGrid horizontal={false} stroke="var(--color-border)" />
                      <XAxis type="number" stroke="var(--color-text-muted)" tick={{ fill: 'var(--color-text-secondary)', fontSize: 11 }} />
                      <YAxis type="category" dataKey="strategy" width={210} stroke="var(--color-text-muted)" tick={{ fill: 'var(--color-text-secondary)', fontSize: 11 }} />
                      <Tooltip
                        formatter={(value) => [formatMetric(Number(value), metric), metricDefinition.label]}
                        labelFormatter={(label, payload) => {
                          const model = payload?.[0]?.payload?.model;
                          return model ? `${label} · ${model}` : label;
                        }}
                        contentStyle={{ background: 'var(--color-surface-raised)', borderColor: 'var(--color-border)', color: 'var(--color-text-primary)' }}
                      />
                      <Bar dataKey="value" name={metricDefinition.label} fill="var(--color-primary)" radius={[0, 5, 5, 0]} maxBarSize={24} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <p className="offline-no-chart">No strategies returned this metric from registry metadata.</p>
              )}
            </section>

            <section className="offline-table-section" aria-label="Detailed routing strategy table">
              <div className="evaluation-section-heading"><div><span className="evaluation-kicker">DETAIL</span><h2>Selection table</h2></div></div>
              <div className="table-wrap">
                <table className="data-table offline-comparison-table">
                  <thead>
                    <tr>
                      <th scope="col">Strategy</th>
                      <th scope="col">Selected model</th>
                      <th scope="col">Provider</th>
                      <th scope="col">Routing score</th>
                      <th scope="col">Quality</th>
                      <th scope="col">Input cost</th>
                      <th scope="col">Latency</th>
                      <th scope="col">Reliability</th>
                      <th scope="col">Constraints</th>
                    </tr>
                  </thead>
                  <tbody>
                    {results.map(row => (
                      <tr key={row.strategy}>
                        <th scope="row">{STRATEGIES.find(item => item.key === row.strategy)?.title ?? row.strategy}</th>
                        <td>{row.selected_model ?? 'Unavailable'}</td>
                        <td>{row.provider ?? '—'}</td>
                        <td>{row.routing_score === null ? '—' : formatPercent(row.routing_score)}</td>
                        <td>{row.quality_score === null ? 'Unavailable' : formatPercent(row.quality_score)}</td>
                        <td>{formatUsd(row.estimated_cost_usd, 8)}</td>
                        <td>{formatMetric(row.latency_seconds, 'latency_seconds')}</td>
                        <td>{formatMetric(row.reliability_score, 'reliability_score')}</td>
                        <td>{row.constraint_satisfied ? 'Satisfied' : 'Unavailable'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            {evaluation.filtered_models.length > 0 && (
              <details className="offline-filtered-models">
                <summary>Filtered models · {evaluation.filtered_models.length}</summary>
                <ul>
                  {evaluation.filtered_models.map(item => <li key={item.model_id}><strong>{item.model_id}</strong>: {item.reason}</li>)}
                </ul>
              </details>
            )}

            <details className="evaluation-methodology offline-methodology">
              <summary><ShieldCheck size={16} aria-hidden="true" /> Research validity and methodology</summary>
              <p>{evaluation.data_disclosure}</p>
              <p>
                All four strategies use the same analyzed query, registry catalog, and hard-constraint-filtered candidate pool.
                AI Compass uses the signed-in profile's routing weights. Quality is a registry estimate unless its source
                explicitly identifies a benchmark; it is not a measured response-quality score. Input cost uses the analyzer's
                estimated input-token count and known input pricing only, excluding output tokens. Latency, reliability, risk,
                capability, context-window, and availability fields are registry metadata, not measurements from this run.
              </p>
            </details>
          </>
        )}

        {!evaluation && !running && (
          <section className="offline-empty-state">
            <BarChart3 size={22} aria-hidden="true" />
            <strong>Evaluate routing decisions, not model responses</strong>
            <p>Run a comparison to see how adaptive and fixed selection strategies choose from the same eligible model pool.</p>
            {!lastRoute && <ButtonLink to="/route" variant="ghost">Open Route Query</ButtonLink>}
          </section>
        )}

        {running && (
          <div className="offline-running" role="status">
            <Loader2 className="spin" aria-hidden="true" />
            <span>Analyzing the query and scoring registry candidates locally…</span>
          </div>
        )}
      </div>
    </>
  );
}
