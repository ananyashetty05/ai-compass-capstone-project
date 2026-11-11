/**
 * Metadata — horizontal label/value strips.
 *
 * A dense alternative to a grid of stat cards for execution metadata
 * (model, provider, latency, cost, quality). Each pair reads as one
 * line of information rather than as a bordered box, which keeps a row
 * of figures from turning into a wall of cards.
 */
import type { ReactNode } from 'react';
import { UNAVAILABLE } from '../../types';
import { cn } from '../../utils/cn';

export interface MetadataItemProps {
  label: string;
  /** Already formatted, or the shared "Unavailable" string. */
  value: ReactNode;
  /** Renders the value in the mono face — for ids and identifiers. */
  mono?: boolean;
  /** Marks the value as not reported by the API. */
  unavailable?: boolean;
  /** Supplementary element after the value, e.g. a provenance tag. */
  suffix?: ReactNode;
  className?: string;
}

export function MetadataItem({
  label,
  value,
  mono,
  unavailable,
  suffix,
  className,
}: MetadataItemProps) {
  return (
    <div className={cn('metadata-item', className)}>
      <span className="metadata-label">{label}</span>
      <span
        className="metadata-value"
        data-mono={mono ? 'true' : undefined}
        data-unavailable={unavailable || undefined}
      >
        <span className="metadata-value-text">{value}</span>
        {suffix}
      </span>
    </div>
  );
}

export interface MetadataRowProps {
  /** Accessible name for the group, e.g. "Execution metadata". */
  label: string;
  columns?: 'auto' | '2';
  children: ReactNode;
  className?: string;
}

export function MetadataRow({ label, columns = 'auto', children, className }: MetadataRowProps) {
  return (
    <dl className={cn('metadata-row', className)} aria-label={label} data-columns={columns === '2' ? '2' : undefined}>
      {children}
    </dl>
  );
}

/**
 * Wraps each `MetadataItem` in the `<dt>`/`<dd>` pair a `MetadataRow`
 * (`<dl>`) requires, without every call site repeating the markup.
 */
export function MetadataEntry(props: Omit<MetadataItemProps, 'mono' | 'unavailable'>) {
  const { label, value, suffix } = props;
  // A field the API did not report must read "Unavailable" rather than
  // render as an empty, greyed-out cell that looks like a layout bug.
  const isUnavailable = value === UNAVAILABLE || value === null || value === undefined;
  return (
    <div className="metadata-pair">
      <dt className="metadata-label">{label}</dt>
      <dd className="metadata-value" data-unavailable={isUnavailable || undefined}>
        <span className="metadata-value-text">{isUnavailable ? UNAVAILABLE : value}</span>
        {suffix}
      </dd>
    </div>
  );
}
