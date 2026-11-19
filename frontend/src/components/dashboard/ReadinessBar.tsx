import { Reveal } from '../ui/Reveal';
import type { ModelSummary } from './insights';

/**
 * Registry readiness as one stacked bar, built only from counts the
 * registry reports: routing-eligible, other active, inactive.
 */
export function ReadinessBar({ summary }: { summary: ModelSummary }) {
  const total = summary.inference.length;
  if (total === 0) return null;
  const eligible = summary.eligible ?? 0;
  const activeOther = Math.max(0, summary.active - eligible);
  const parts = [
    { key: 'eligible', label: 'Routing-eligible', value: eligible, color: 'var(--color-primary)' },
    { key: 'active', label: summary.eligible === null ? 'Active' : 'Active, not eligible', value: activeOther, color: 'color-mix(in srgb, var(--color-primary) 35%, var(--color-surface))' },
    { key: 'inactive', label: 'Inactive', value: summary.inactive, color: 'var(--color-border-strong)' },
  ].filter((p) => p.value > 0);

  return (
    <Reveal as="section" className="cx-card ready-card" ariaLabelledBy="ready-title">
      <header className="cx-card-head">
        <div><p className="cx-kicker">Model ecosystem</p><h2 id="ready-title">Routing readiness</h2></div>
        <span className="cx-note-inline">{total} API models</span>
      </header>
      <div className="ready-bar" role="img" aria-label={parts.map((p) => `${p.label}: ${p.value}`).join(', ')}>
        {parts.map((p) => <i key={p.key} style={{ flexGrow: p.value, background: p.color }} title={`${p.label}: ${p.value}`} />)}
      </div>
      <ul className="ready-legend">
        {parts.map((p) => (
          <li key={p.key}><span style={{ background: p.color }} aria-hidden="true" />{p.label} <b>{p.value}</b></li>
        ))}
      </ul>
    </Reveal>
  );
}
