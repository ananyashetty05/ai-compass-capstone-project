/**
 * Interpretation aids for the Evaluation Lab.
 *
 * Both components are derived from what the offline evaluation actually
 * returned. They never turn registry metadata into a measured result,
 * and they say plainly when a figure is missing.
 */
import { Gauge, Info, Medal, ShieldAlert } from 'lucide-react';
import { Reveal } from '../ui/Reveal';
import { formatDuration, formatPercent, formatUsd } from '../../utils/format';
import type { OfflineStrategyResult } from '../../types';

const GUIDE = [
  { name: 'Routing score', basis: 'Computed', text: 'Weighted blend of the objectives using the signed-in profile’s weights. Only AI Compass uses your weights; baselines ignore them.' },
  { name: 'Quality', basis: 'Registry estimate', text: 'A catalog estimate unless its source names a benchmark. It is not a measured response-quality score.' },
  { name: 'Input cost', basis: 'Estimated', text: 'Known input price × the analyzer’s estimated input tokens. Output tokens are excluded; models with no known price are excluded from the cheapest baseline.' },
  { name: 'Latency', basis: 'Registry estimate', text: 'Average response time recorded in registry metadata, not measured in this run.' },
  { name: 'Reliability', basis: 'Registry metadata', text: 'A catalog reliability figure; no uptime or error rate was observed here.' },
  { name: 'Risk', basis: 'Registry metadata', text: 'Lower is better. A catalog risk indicator used by the router.' },
];

export function MetricGuide() {
  return (
    <Reveal as="details" className="cx-card cx-guide">
      <summary><Info aria-hidden="true" /> How to read these metrics <span className="cx-guide-hint">Measured, estimated or registry-derived?</span></summary>
      <p className="cx-muted">This lab runs offline against registry metadata. Nothing below is a response measured from a provider.</p>
      <dl className="cx-guide-grid">
        {GUIDE.map((g) => (
          <div key={g.name}>
            <dt>{g.name}<span data-basis={g.basis === 'Computed' ? 'computed' : 'registry'}>{g.basis}</span></dt>
            <dd>{g.text}</dd>
          </div>
        ))}
      </dl>
    </Reveal>
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
  const items = [
    { label: 'Highest quality estimate', ...leaders(selected, (r) => r.quality_score, 'max'), fmt: (v: number) => formatPercent(v) },
    { label: 'Lowest input cost', ...leaders(selected, (r) => r.estimated_cost_usd, 'min'), fmt: (v: number) => formatUsd(v, 8) },
    { label: 'Lowest latency estimate', ...leaders(selected, (r) => r.latency_seconds, 'min'), fmt: (v: number) => formatDuration(v * 1000) },
    { label: 'Highest reliability metadata', ...leaders(selected, (r) => r.reliability_score, 'max'), fmt: (v: number) => formatPercent(v) },
    { label: 'Lowest risk indicator', ...leaders(selected, (r) => r.risk_score, 'min'), fmt: (v: number) => formatPercent(v) },
  ];
  const unavailable = rows.filter((r) => r.status === 'unavailable');
  const missing = [...new Set(selected.flatMap((r) => r.missing_data).map((m) => m.replace(/\.+$/, '')))];
  return (
    <Reveal as="section" className="cx-card" ariaLabelledBy="reading-title">
      <header className="cx-card-head">
        <div><p className="cx-kicker">Interpretation</p><h2 id="reading-title">Reading these results</h2></div>
        <Medal aria-hidden="true" />
      </header>
      <ul className="cx-leaders">
        {items.map((it) => (
          <li key={it.label}>
            <span className="cx-leader-label">{it.label}</span>
            {it.value === null ? (
              <strong data-na="true">Not reported by any strategy’s model</strong>
            ) : (
              <strong>{it.names.join(' · ')} <span>{it.fmt(it.value)}</span></strong>
            )}
            <small>{it.value === null ? 'Cannot be compared' : `Reported for ${it.have} of ${selected.length} selected strateg${selected.length === 1 ? 'y' : 'ies'}`}</small>
          </li>
        ))}
      </ul>
      {unavailable.length > 0 ? (
        <p className="cx-flag"><ShieldAlert aria-hidden="true" /> {unavailable.map((r) => r.title).join(', ')} could not select a model for this query, so {unavailable.length === 1 ? 'it is' : 'they are'} left out of the comparisons above.</p>
      ) : null}
      {missing.length > 0 ? (
        <p className="cx-flag"><Gauge aria-hidden="true" /> Missing registry data for at least one selection: {missing.join('; ')}. Comparisons on those fields are incomplete.</p>
      ) : null}
      <p className="cx-note"><span>A leader here means the best recorded value among the selected models. It is not evidence that the model answers better.</span></p>
    </Reveal>
  );
}
