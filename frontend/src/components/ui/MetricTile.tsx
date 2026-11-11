import type { ReactNode } from 'react';
import { ProvenanceTag } from './Badge';
import { cn } from '../../utils/cn';
import { UNAVAILABLE } from '../../types';
import type { Provenance } from '../../types';

export interface MetricTileProps {
  label: string;
  /** null renders "Unavailable" — never a fabricated 0. */
  value: number | null;
  format: (value: number) => string;
  unit?: string;
  icon?: ReactNode;
  /** Explains where the number comes from. Always shown. */
  source: string;
  provenance: Provenance;
  /** Optional sparkline or inline visualisation. */
  children?: ReactNode;
}

/**
 * A single key metric.
 *
 * When the backend does not report a value the tile reads
 * "Unavailable" and says why — it never shows 0 as a stand-in for
 * missing data.
 */
export function MetricTile({ label, value, format, unit, icon, source, provenance, children }: MetricTileProps) {
  const available = typeof value === 'number' && Number.isFinite(value);
  return (
    <div className="metric">
      <p className="metric-head">
        {icon ? (
          <span aria-hidden="true" className="metric-icon">
            {icon}
          </span>
        ) : null}
        {label}
      </p>
      <p className="metric-value" data-unavailable={!available || undefined}>
        {available ? (
          <>
            {format(value)}
            {unit ? <span className="metric-unit">{unit}</span> : null}
          </>
        ) : (
          UNAVAILABLE
        )}
      </p>
      {children}
      <p className="metric-foot">
        {source} <ProvenanceTag kind={provenance} />
      </p>
    </div>
  );
}

export interface MetricGridProps {
  children: ReactNode;
  label: string;
}

export function MetricGrid({ children, label }: MetricGridProps) {
  return (
    <section aria-label={label} className="metric-grid">
      {children}
    </section>
  );
}

/* ------------------------------------------------------------------ *
 * Stat strip — the dense counterpart to MetricTile
 * ------------------------------------------------------------------ */

export interface StatProps {
  label: string;
  /** Pre-formatted, or null when the API did not report the figure. */
  value: string | number | null | undefined;
  icon?: ReactNode;
  /** "Measured" or "estimated" — stated rather than implied. */
  provenance?: Provenance;
  /** Endpoint or registry field the figure comes from. */
  source?: string;
}

/**
 * One figure in a `StatStrip`.
 *
 * Reads as a single line of information rather than a bordered tile,
 * which lets a whole row of figures sit above content instead of
 * pushing it down. A missing value reads "Unavailable" — never 0.
 */
export function Stat({ label, value, icon, provenance, source }: StatProps) {
  const available = value !== null && value !== undefined && value !== '';
  return (
    <div className="metadata-pair" title={source}>
      <dt className="stat-label">
        {icon ? (
          <span aria-hidden="true" className="stat-icon">
            {icon}
          </span>
        ) : null}
        {label}
      </dt>
      <dd className="stat-value" data-unavailable={!available || undefined}>
        {available ? value : UNAVAILABLE}
      </dd>
      {provenance && source ? (
        <dd className="stat-source">
          {source} <ProvenanceTag kind={provenance} />
        </dd>
      ) : null}
    </div>
  );
}

export interface StatStripProps {
  /** Accessible name for the group, e.g. "Registry summary". */
  label: string;
  children: ReactNode;
  className?: string;
}

/** A single dense row of figures, separated by hairlines. */
export function StatStrip({ label, children, className }: StatStripProps) {
  return (
    <dl className={cn('stat-strip', className)} aria-label={label}>
      {children}
    </dl>
  );
}
