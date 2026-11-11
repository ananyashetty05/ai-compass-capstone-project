import { useId, useState } from 'react';
import type { ReactNode } from 'react';
import { cn } from '../../utils/cn';

export interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  radius?: 'sm' | 'pill' | 'circle';
  className?: string;
  /** Announced to screen readers when the skeleton stands in for content. */
  label?: string;
}

export function Skeleton({ width = '100%', height = '1rem', radius = 'sm', className, label }: SkeletonProps) {
  return (
    <span
      className={cn('skeleton', className)}
      style={{ width, height }}
      data-radius={radius === 'sm' ? undefined : radius}
      role={label ? 'status' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : 'true'}
    />
  );
}

/** Placeholder block with an accessible loading announcement. */
export function SkeletonBlock({ label, lines = 3, className }: { label: string; lines?: number; className?: string }) {
  const id = useId();
  return (
    <div className={className} role="status" aria-live="polite" aria-labelledby={id}>
      <span id={id} className="sr-only">
        {label}
      </span>
      <div className="skeleton-stack" aria-hidden="true">
        {Array.from({ length: lines }, (_, index) => (
          <Skeleton key={index} height={index === lines - 1 ? '0.75rem' : '1rem'} width={index === lines - 1 ? '60%' : '100%'} />
        ))}
      </div>
    </div>
  );
}

export function SkeletonCard({ label, lines = 3 }: { label: string; lines?: number }) {
  return (
    <div className="card">
      <SkeletonBlock label={label} lines={lines} />
    </div>
  );
}

/** Skeleton shaped like a metric tile. */
export function SkeletonMetric() {
  return (
    <div className="metric" aria-hidden="true">
      <Skeleton width="45%" height="0.625rem" />
      <Skeleton width="65%" height="1.5rem" />
      <Skeleton width="85%" height="0.75rem" />
    </div>
  );
}
export function SkeletonMetrics({ count = 6 }: { count?: number }) {
  return (
    <div className="metric-grid" role="status" aria-live="polite">
      <span className="sr-only">Loading system metrics…</span>
      {Array.from({ length: count }, (_, index) => (
        <SkeletonMetric key={index} />
      ))}
    </div>
  );
}

/** Skeleton shaped like a data table, for the model pool and evaluation. */
export function SkeletonTable({ rows = 6, columns = 7 }: { rows?: number; columns?: number }) {
  return (
    <div role="status" aria-live="polite">
      <span className="sr-only">Loading table data…</span>
      <div className="table-wrap" aria-hidden="true">
        <table className="data-table">
          <thead>
            <tr>
              {Array.from({ length: columns }, (_, index) => (
                <th key={index} scope="col">
                  <Skeleton width="60%" height="0.625rem" />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: rows }, (_, rowIndex) => (
              <tr key={rowIndex}>
                {Array.from({ length: columns }, (_, columnIndex) => (
                  <td key={columnIndex}>
                    <Skeleton width={columnIndex === 0 ? '85%' : '55%'} height="1rem" />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Generic indeterminate loading indicator for long-running requests. */
export function LoadingIndicator({ label, detail }: { label: string; detail?: string }) {
  const id = useId();
  return (
    <div role="status" aria-live="polite" aria-labelledby={id}>
      <div className="row">
        <span className="spinner" data-size="lg" aria-hidden="true" />
        <div className="loading-indicator-text">
          <p id={id} className="loading-indicator-title">
            {label}
          </p>
          {detail ? <p className="text-sm text-muted">{detail}</p> : null}
        </div>
      </div>
      <div className="indeterminate loading-indicator-track" aria-hidden="true" />
    </div>
  );
}

export interface SegmentedOption<T extends string> {
  value: T;
  label: string;
  icon?: ReactNode;
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
  size,
}: {
  options: readonly SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  label: string;
  size?: 'sm' | 'md' | 'lg';
}) {
  const [focusIndex, setFocusIndex] = useState(0);

  const move = (delta: number) => {
    const next = (focusIndex + delta + options.length) % options.length;
    setFocusIndex(next);
    onChange(options[next].value);
  };

  return (
    <div
      className="segmented"
      role="radiogroup"
      aria-label={label}
      onKeyDown={(event) => {
        if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
          event.preventDefault();
          move(1);
        } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
          event.preventDefault();
          move(-1);
        }
      }}
    >
      {options.map((option, index) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          className="segmented-item"
          aria-checked={option.value === value}
          tabIndex={option.value === value ? 0 : -1}
          data-size={size === 'md' ? undefined : size}
          onClick={() => {
            setFocusIndex(index);
            onChange(option.value);
          }}
        >
          {option.icon ? (
            <span aria-hidden="true" className="btn-icon">
              {option.icon}
            </span>
          ) : null}
          {option.label}
        </button>
      ))}
    </div>
  );
}
