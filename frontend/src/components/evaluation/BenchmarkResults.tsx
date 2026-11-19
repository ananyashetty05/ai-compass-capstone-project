/**
 * Strategy benchmark results.
 *
 * One head-to-head matrix replaces the repeated cards, leader tiles and table. Every figure is registry
 * metadata returned by the offline evaluation; a missing value stays "—" and is never drawn as zero.
 */
import { useMemo, useState } from 'react';
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Equal, Info, Layers, ShieldAlert, ShieldCheck } from 'lucide-react';
import { SegmentedControl } from '../ui/ds';
import { STRATEGIES, strategyShort } from './strategies';
import { formatDuration, formatPercent, formatUsd } from '../../utils/format';
import type { OfflineEvaluationResponse, OfflineStrategyResult } from '../../types';

type Key = 'routing_score' | 'quality_score' | 'reliability_score' | 'latency_seconds' | 'estimated_cost_usd' | 'risk_score';
interface Metric { key: Key; label: string; note: string; best: 'max' | 'min' | null; ratio: boolean; fmt: (v: number) => string }

const pct = (v: number) => formatPercent(v);
export const METRICS: Metric[] = [
  { key: 'routing_score', label: 'Routing score', note: 'Computed with your weights', best: null, ratio: true, fmt: pct },
  { key: 'quality_score', label: 'Quality', note: 'Registry estimate', best: 'max', ratio: true, fmt: pct },
  { key: 'reliability_score', label: 'Reliability', note: 'Registry metadata', best: 'max', ratio: true, fmt: pct },
  { key: 'latency_seconds', label: 'Latency', note: 'Registry estimate', best: 'min', ratio: false, fmt: (v) => formatDuration(v * 1000) },
  { key: 'estimated_cost_usd', label: 'Input cost', note: 'Estimated, input tokens only', best: 'min', ratio: false, fmt: (v) => formatUsd(v, 6) },
  { key: 'risk_score', label: 'Risk', note: 'Registry metadata, lower is better', best: 'min', ratio: true, fmt: pct },
];
const CHART_METRICS = METRICS.filter((m) => ['quality_score', 'estimated_cost_usd', 'latency_seconds', 'reliability_score'].includes(m.key));
const COLOR: Record<string, string> = { aicompass: 'var(--color-primary)', strongest: 'var(--ev-c-strong)', cheapest: 'var(--ev-c-cheap)', static: 'var(--ev-c-static)' };
const num = (v: number | null | undefined) => (typeof v === 'number' && Number.isFinite(v) ? v : null);

function bestSet(rows: OfflineStrategyResult[], m: Metric): Set<string> {
  if (!m.best) return new Set();
  const have = rows.filter((r) => num(r[m.key]) !== null);
  const vals = have.map((r) => r[m.key] as number);
  if (have.length < 2 || new Set(vals).size === 1) return new Set(); // a tie between everyone says nothing
  const target = m.best === 'max' ? Math.max(...vals) : Math.min(...vals);
  return new Set(have.filter((r) => r[m.key] === target).map((r) => r.strategy));
}

export function BenchmarkResults({ evaluation }: { evaluation: OfflineEvaluationResponse }) {
  const [metricKey, setMetricKey] = useState<Key>('quality_score');
  const byKey = useMemo(() => new Map(evaluation.strategy_results.map((r) => [r.strategy, r])), [evaluation]);
  const ordered = STRATEGIES.flatMap(({ key }) => { const r = byKey.get(key); return r ? [r] : []; });
  const picked = ordered.filter((r) => r.status === 'selected');
  const unavailable = ordered.filter((r) => r.status === 'unavailable');
  const compassPick = byKey.get('aicompass')?.selected_model_id ?? null;
  const baselines = picked.filter((r) => r.strategy !== 'aicompass');
  const agreeing = compassPick ? baselines.filter((r) => r.selected_model_id === compassPick).length : 0;
  const distinct = new Set(picked.map((r) => r.selected_model_id)).size;
  const missing = [...new Set(picked.flatMap((r) => r.missing_data).map((m) => m.replace(/\.+$/, '')))];
  const metric = CHART_METRICS.find((m) => m.key === metricKey) ?? CHART_METRICS[0];
  const chartData = picked.filter((r) => num(r[metric.key]) !== null).map((r) => ({ key: r.strategy, strategy: strategyShort(r.strategy), value: r[metric.key] as number, model: r.selected_model ?? '—' }));
  const best = useMemo(() => new Map(METRICS.map((m) => [m.key, bestSet(picked, m)])), [picked]);

  return (
    <div className="xai xb">
      <ul className="xb-stats" aria-label="Run summary">
        <li><span>Eligible pool</span><strong>{evaluation.candidate_count}</strong><small>model{evaluation.candidate_count === 1 ? '' : 's'} after filtering</small></li>
        <li><span>Distinct picks</span><strong>{distinct}</strong><small>across {picked.length} selecting strateg{picked.length === 1 ? 'y' : 'ies'}</small></li>
        <li><span>Agree with AI Compass</span><strong>{compassPick ? `${agreeing}/${baselines.length}` : '—'}</strong><small>{compassPick ? 'baselines chose the same model' : 'AI Compass made no pick'}</small></li>
        <li><span>Filtered out</span><strong>{evaluation.filtered_models.length}</strong><small>ineligible registry entries</small></li>
      </ul>

      <section className="xc" aria-labelledby="xb-matrix-title">
        <header className="xc-head">
          <div><h3 id="xb-matrix-title">Head to head</h3><p>Each strategy picks from the same filtered pool. The best value in a row is marked; “—” means the registry has no figure.</p></div>
        </header>
        <div className="xai-table-wrap xb-wrap">
          <table className="xb-matrix">
            <caption className="sr-only">Selected model and registry metrics for each strategy</caption>
            <thead>
              <tr>
                <th scope="col" className="xb-corner">Metric</th>
                {ordered.map((r) => {
                  const meta = STRATEGIES.find((s) => s.key === r.strategy);
                  const Icon = meta?.icon;
                  const own = r.strategy === 'aicompass';
                  const same = !own && r.status === 'selected' && compassPick !== null && r.selected_model_id === compassPick;
                  return (
                    <th scope="col" key={r.strategy} className="xb-col" data-strategy={r.strategy}>
                      <span className="xb-col-top"><span className="xb-col-ico" aria-hidden="true">{Icon ? <Icon /> : null}</span><b>{meta?.title ?? r.strategy}</b></span>
                      {r.status === 'selected' ? (
                        <>
                          <strong className="xb-model">{r.selected_model}</strong>
                          <small className="xb-prov">{r.provider ?? '—'}</small>
                          <span className="xb-tags">
                            {own ? <em data-k="accent">Uses your weights</em> : null}
                            {same ? <em><Equal aria-hidden="true" />Same as AI Compass</em> : null}
                            {!r.constraint_satisfied ? <em data-k="warn">Constraints not met</em> : null}
                          </span>
                        </>
                      ) : <span className="xb-none">No model selected</span>}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {METRICS.map((m) => (
                <tr key={m.key}>
                  <th scope="row"><b>{m.label}</b><small>{m.note}</small></th>
                  {ordered.map((r) => {
                    const v = r.status === 'selected' ? num(r[m.key]) : null;
                    const isBest = best.get(m.key)?.has(r.strategy);
                    return (
                      <td key={r.strategy} data-strategy={r.strategy} data-best={isBest || undefined} data-missing={v === null || undefined}>
                        {v === null ? <span className="xb-na" title={m.key === 'routing_score' ? 'Only AI Compass scores with your weights' : 'Not in registry'}>—</span> : (
                          <>
                            <span className="xb-val">{m.fmt(v)}{isBest ? <i className="xb-best">Best</i> : null}</span>
                            {m.ratio ? <span className="xb-bar" aria-hidden="true"><i style={{ width: `${Math.max(0, Math.min(1, v)) * 100}%` }} /></span> : null}
                          </>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {unavailable.length > 0 || missing.length > 0 ? (
          <div className="xb-flags">
            {unavailable.length > 0 ? <p><ShieldAlert aria-hidden="true" />{unavailable.map((r) => strategyShort(r.strategy)).join(', ')} could not select a model for this query, so {unavailable.length === 1 ? 'it is' : 'they are'} left out of the comparison.</p> : null}
            {missing.length > 0 ? <p><Info aria-hidden="true" />Missing registry data for at least one pick: {missing.join('; ')}.</p> : null}
          </div>
        ) : null}
      </section>

      <section className="xc" aria-labelledby="xb-why-title">
        <header className="xc-head"><div><h3 id="xb-why-title">Why each strategy chose its model</h3><p>The rule each policy applies, plus the registry details behind the pick.</p></div></header>
        <div className="xc-body xb-why-grid">
          {ordered.map((r) => {
            const meta = STRATEGIES.find((s) => s.key === r.strategy);
            return (
              <details key={r.strategy} className="xb-why" data-strategy={r.strategy} open={r.strategy === 'aicompass' || undefined}>
                <summary>
                  <span className="xb-dot" aria-hidden="true" />
                  <span><b>{meta?.title ?? r.strategy}</b><small>{r.selected_model ?? 'No model selected'}</small></span>
                </summary>
                <div className="xb-why-body">
                  <p>{r.selection_rationale}</p>
                  {r.status === 'selected' ? (
                    <dl>
                      <div><dt>Context window</dt><dd>{r.context_window ? `${r.context_window.toLocaleString()} tokens` : '—'}</dd></div>
                      <div><dt>Constraints</dt><dd>{r.constraint_satisfied ? 'Satisfied' : 'Not satisfied'}</dd></div>
                      {r.quality_source ? <div><dt>Quality source</dt><dd>{r.quality_source}</dd></div> : null}
                      {r.cost_basis ? <div><dt>Cost basis</dt><dd>{r.cost_basis}</dd></div> : null}
                    </dl>
                  ) : null}
                  {r.missing_data.length > 0 ? <ul className="xb-missing">{r.missing_data.map((m) => <li key={m}>{m}</li>)}</ul> : null}
                </div>
              </details>
            );
          })}
        </div>
      </section>

      <section className="xc" aria-labelledby="xb-chart-title">
        <header className="xc-head">
          <div><h3 id="xb-chart-title">Visual comparison</h3><p>{metric.label} · {metric.note.toLowerCase()}. Missing values are left out, not shown as zero.</p></div>
          <div className="xc-right"><SegmentedControl label="Chart metric" value={metricKey} onChange={setMetricKey} options={CHART_METRICS.map((m) => ({ value: m.key, label: m.label }))} /></div>
        </header>
        <div className="xc-body">
          {chartData.length ? (
            <ResponsiveContainer width="100%" height={Math.max(180, chartData.length * 60)}>
              <BarChart data={chartData} layout="vertical" margin={{ top: 4, right: 32, bottom: 4, left: 4 }}>
                <CartesianGrid horizontal={false} stroke="var(--color-border-subtle)" />
                <XAxis type="number" stroke="var(--color-text-muted)" tick={{ fill: 'var(--color-text-secondary)', fontSize: 11 }} tickFormatter={(v) => (metric.ratio ? `${Math.round(Number(v) * 100)}%` : String(v))} />
                <YAxis type="category" dataKey="strategy" width={96} stroke="var(--color-text-muted)" tick={{ fill: 'var(--color-text-secondary)', fontSize: 12 }} />
                <Tooltip cursor={{ fill: 'var(--color-primary-subtle)' }} formatter={(value) => [metric.fmt(Number(value)), metric.label]} labelFormatter={(label, payload) => { const m = payload?.[0]?.payload?.model; return m ? `${label} · ${m}` : label; }} contentStyle={{ background: 'var(--color-surface-raised)', borderColor: 'var(--color-border)', borderRadius: 10, color: 'var(--color-text-primary)' }} />
                <Bar dataKey="value" name={metric.label} radius={[0, 6, 6, 0]} maxBarSize={26}>
                  {chartData.map((d) => <Cell key={d.key} fill={COLOR[d.key] ?? 'var(--color-primary)'} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : <p className="xai-muted">No strategy’s model has a {metric.label.toLowerCase()} value in the registry.</p>}
        </div>
      </section>

      <div className="xb-notes">
        {evaluation.filtered_models.length > 0 ? (
          <details className="xc xb-note">
            <summary><Layers aria-hidden="true" />Filtered models <span className="xai-count">{evaluation.filtered_models.length}</span></summary>
            <ul className="xb-filtered">{evaluation.filtered_models.map((i) => <li key={i.model_id}><code>{i.model_id}</code><span>{i.reason}</span></li>)}</ul>
          </details>
        ) : null}
        <details className="xc xb-note">
          <summary><ShieldCheck aria-hidden="true" />Research validity and methodology</summary>
          <div className="xb-method">
            <p>{evaluation.data_disclosure}</p>
            <p>All four strategies use the same analysed query, registry catalog and hard-constraint-filtered pool. AI Compass uses the signed-in profile’s routing weights. Quality is a registry estimate unless its source names a benchmark; it is not a measured response-quality score. Input cost uses the estimated input-token count and known input pricing only, excluding output tokens. Latency, reliability, risk, capability, context-window and availability fields are registry metadata, not measurements from this run.</p>
          </div>
        </details>
      </div>
    </div>
  );
}
