/**
 * Interpretation aids for the Evaluation Lab.
 *
 * Both components are derived from what the offline evaluation actually
 * returned. They never turn registry metadata into a measured result,
 * and they say plainly when a figure is missing.
 */
import { ChevronDown, Clock, DollarSign, Gauge, Info, ShieldAlert, ShieldCheck, Sparkles } from 'lucide-react';
import type { ReactNode } from 'react';
import { formatDuration, formatPercent, formatUsd } from '../../utils/format';
import type { OfflineStrategyResult } from '../../types';

const GUIDE = [
  { name: 'Routing score', basis: 'Computed', text: 'Weighted blend of the objectives using your profile’s weights. Only AI Compass uses your weights.' },
  { name: 'Quality', basis: 'Registry estimate', text: 'A catalog estimate unless its source names a benchmark. Not a measured response-quality score.' },
  { name: 'Input cost', basis: 'Estimated', text: 'Known input price × estimated input tokens. Output tokens excluded; unknown prices are left out.' },
  { name: 'Latency', basis: 'Registry estimate', text: 'Average response time from registry metadata, not measured in this run.' },
  { name: 'Reliability', basis: 'Registry metadata', text: 'A catalog reliability figure; no uptime or error rate was observed here.' },
  { name: 'Risk', basis: 'Registry metadata', text: 'Lower is better. A catalog risk indicator used by the router.' },
];

export function MetricGuide() {
  return (
    <details className="ev-guide">
      <summary>
        <span className="ev-guide-icon" aria-hidden="true"><Info /></span>
        <span className="ev-guide-label"><strong>How to read these metrics</strong><small>Which figures are computed, estimated or taken from the registry</small></span>
        <ChevronDown className="ev-guide-chev" aria-hidden="true" />
      </summary>
      <dl className="ev-guide-grid">
        {GUIDE.map((g) => (
          <div key={g.name}>
            <dt>{g.name}<span data-basis={g.basis === 'Computed' ? 'computed' : 'registry'}>{g.basis}</span></dt>
            <dd>{g.text}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

type Row = OfflineStrategyResult & { title: string };

function leaders(rows: Row[], pick: (r: Row) => number | null, best: 'max' | 'min') {
  const have = rows.filter((r) => pick(r) !== null && Number.isFinite(pick(r) as number));
  if (have.length === 0) return { names: [] as string[], value: null as number | null, have: 0 };
  const target = best === 'max' ? Math.max(...have.map((r) => pick(r) as number)) : Math.min(...have.map((r) => pick(r) as number));
  return { names: have.filter((r) => pick(r) === target).map((r) => r.title), value: target, have: have.length };
}

export function ResultReading({ rows }: { rows: Row[] }) {
  const selected = rows.filter((r) => r.status === 'selected');
  if (selected.length === 0) return null;
  const items: Array<{ label: string; icon: ReactNode; fmt: (v: number) => string } & ReturnType<typeof leaders>> = [
    { label: 'Highest quality', icon: <Sparkles />, ...leaders(selected, (r) => r.quality_score, 'max'), fmt: (v) => formatPercent(v) },
    { label: 'Lowest input cost', icon: <DollarSign />, ...leaders(selected, (r) => r.estimated_cost_usd, 'min'), fmt: (v) => formatUsd(v, 6) },
    { label: 'Lowest latency', icon: <Clock />, ...leaders(selected, (r) => r.latency_seconds, 'min'), fmt: (v) => formatDuration(v * 1000) },
    { label: 'Highest reliability', icon: <ShieldCheck />, ...leaders(selected, (r) => r.reliability_score, 'max'), fmt: (v) => formatPercent(v) },
    { label: 'Lowest risk', icon: <Gauge />, ...leaders(selected, (r) => r.risk_score, 'min'), fmt: (v) => formatPercent(v) },
  ];
  const unavailable = rows.filter((r) => r.status === 'unavailable');
  const missing = [...new Set(selected.flatMap((r) => r.missing_data).map((m) => m.replace(/\.+$/, '')))];
  return (
    <section className="ev-section" aria-labelledby="reading-title">
      <header className="ev-section-head">
        <div>
          <p className="ev-kicker">Interpretation</p>
          <h2 id="reading-title">Who leads on each metric</h2>
        </div>
        <p className="ev-section-note">Best recorded value among the selected models. Not evidence that a model answers better.</p>
      </header>
      <ul className="ev-leaders">
        {items.map((it) => (
          <li key={it.label} data-na={it.value === null || undefined}>
            <span className="ev-leader-icon" aria-hidden="true">{it.icon}</span>
            <span className="ev-leader-label">{it.label}</span>
            {it.value === null ? (
              <strong className="ev-leader-value">Not reported</strong>
            ) : (
              <strong className="ev-leader-value">{it.fmt(it.value)}</strong>
            )}
            <span className="ev-leader-who">
              {it.value === null ? 'No selected model has this figure' : it.names.join(' · ')}
            </span>
            {it.value !== null ? <small>Reported for {it.have} of {selected.length}</small> : null}
          </li>
        ))}
      </ul>
      {unavailable.length > 0 || missing.length > 0 ? (
        <div className="ev-flags">
          {unavailable.length > 0 ? (
            <p><ShieldAlert aria-hidden="true" />{unavailable.map((r) => r.title).join(', ')} could not select a model for this query, so {unavailable.length === 1 ? 'it is' : 'they are'} left out of these comparisons.</p>
          ) : null}
          {missing.length > 0 ? (
            <p><Info aria-hidden="true" />Missing registry data for at least one pick: {missing.join('; ')}.</p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
