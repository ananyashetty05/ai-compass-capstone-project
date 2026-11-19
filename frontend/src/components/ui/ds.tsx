/**
 * AI Compass design-system primitives.
 *
 * Small, dependency-free building blocks shared by every page. Visual rules live in `styles/ds.css`
 * and use the global tokens, so a change there restyles the whole product consistently.
 */
import { useId } from 'react';
import type { CSSProperties, ElementType, ReactNode } from 'react';
import { cn } from '../../utils/cn';

/* ── Layout ───────────────────────────────────────────────────────── */

/** Consistent page container: width, gutters and vertical rhythm come from tokens. */
export function Page({ children, className, width = 'wide' }: { children: ReactNode; className?: string; width?: 'wide' | 'narrow' | 'full' }) {
  return <div className={cn('ds-page', className)} data-width={width}>{children}</div>;
}

/** Responsive grid. `ratio` picks a column proportion that collapses to one column on small screens. */
export function Grid({ children, cols = 3, ratio, gap = 'md', className, as: El = 'div', style }: {
  children: ReactNode; cols?: 1 | 2 | 3 | 4; ratio?: '2-1' | '3-2' | '1-2' | '3-1'; gap?: 'sm' | 'md' | 'lg'; className?: string; as?: ElementType; style?: CSSProperties;
}) {
  return <El className={cn('ds-grid', className)} data-cols={ratio ? undefined : cols} data-ratio={ratio} data-gap={gap} style={style}>{children}</El>;
}

export function SectionHeader({ title, description, kicker, actions, id, level = 'h2' }: {
  title: ReactNode; description?: ReactNode; kicker?: string; actions?: ReactNode; id?: string; level?: 'h2' | 'h3';
}) {
  const H = level;
  return (
    <header className="ds-section-head">
      <div>
        {kicker ? <p className="ds-kicker">{kicker}</p> : null}
        <H className="ds-section-title" id={id}>{title}</H>
        {description ? <p className="ds-section-desc">{description}</p> : null}
      </div>
      {actions ? <div className="ds-section-actions">{actions}</div> : null}
    </header>
  );
}

/** Surface used for grouped content. `glass` is reserved for floating or hero surfaces. */
export function Surface({ children, className, variant = 'solid', interactive, as: El = 'section', ...rest }: {
  children: ReactNode; className?: string; variant?: 'solid' | 'glass' | 'quiet'; interactive?: boolean; as?: ElementType; 'aria-labelledby'?: string; 'aria-label'?: string; id?: string;
}) {
  return <El className={cn('ds-surface', className)} data-variant={variant} data-interactive={interactive || undefined} {...rest}>{children}</El>;
}

/* ── Controls ─────────────────────────────────────────────────────── */

export interface SegmentOption<T extends string> { value: T; label: string; hint?: string; icon?: ReactNode }

export function SegmentedControl<T extends string>({ value, onChange, options, label, disabled, className }: {
  value: T; onChange: (v: T) => void; options: SegmentOption<T>[]; label: string; disabled?: boolean; className?: string;
}) {
  return (
    <div className={cn('ds-seg', className)} role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={value === o.value} title={o.hint} disabled={disabled}
          className={value === o.value ? 'is-on' : ''} onClick={() => onChange(o.value)}>
          {o.icon ? <span aria-hidden="true" className="ds-seg-icon">{o.icon}</span> : null}{o.label}
        </button>
      ))}
    </div>
  );
}

/** A selectable card (radio- or checkbox-like). Keyboard operable and announced with the right role. */
export function SelectCard({ selected, onSelect, icon, title, description, disabled, kind = 'radio', className }: {
  selected: boolean; onSelect: () => void; icon?: ReactNode; title: string; description?: string; disabled?: boolean; kind?: 'radio' | 'checkbox'; className?: string;
}) {
  return (
    <button type="button" role={kind} aria-checked={selected} disabled={disabled} onClick={onSelect} className={cn('ds-select-card', className)} data-selected={selected || undefined}>
      {icon ? <span className="ds-select-icon" aria-hidden="true">{icon}</span> : null}
      <span className="ds-select-text"><strong>{title}</strong>{description ? <small>{description}</small> : null}</span>
      <span className="ds-select-mark" aria-hidden="true" />
    </button>
  );
}

/* ── Data display ─────────────────────────────────────────────────── */

export type Tone = 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info';

export function StatusPill({ tone = 'neutral', children, icon, title }: { tone?: Tone; children: ReactNode; icon?: ReactNode; title?: string }) {
  return <span className="ds-pill" data-tone={tone} title={title}>{icon ? <span aria-hidden="true" className="ds-pill-icon">{icon}</span> : null}{children}</span>;
}

export function Stat({ label, value, hint, icon, tone = 'neutral', className }: { label: string; value: ReactNode; hint?: ReactNode; icon?: ReactNode; tone?: Tone; className?: string }) {
  return (
    <div className={cn('ds-stat', className)} data-tone={tone}>
      <p className="ds-stat-label">{icon ? <span aria-hidden="true" className="ds-stat-icon">{icon}</span> : null}{label}</p>
      <p className="ds-stat-value">{value}</p>
      {hint ? <p className="ds-stat-hint">{hint}</p> : null}
    </div>
  );
}

export function PropertyList({ items, columns = 1, className }: { items: { label: string; value: ReactNode; hint?: ReactNode }[]; columns?: 1 | 2 | 3; className?: string }) {
  return (
    <dl className={cn('ds-props', className)} data-cols={columns}>
      {items.map((i) => (
        <div key={i.label} className="ds-prop">
          <dt>{i.label}</dt>
          <dd>{i.value}{i.hint ? <small>{i.hint}</small> : null}</dd>
        </div>
      ))}
    </dl>
  );
}

/** A labelled proportion bar. `value` is 0–1; `null` renders as unavailable rather than empty. */
export function Meter({ label, value, display, tone = 'primary' }: { label: string; value: number | null; display?: string; tone?: Tone }) {
  const id = useId();
  const pct = value === null ? 0 : Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className="ds-meter" data-tone={tone} data-missing={value === null || undefined}>
      <span className="ds-meter-label" id={id}>{label}</span>
      <span className="ds-meter-track" role="meter" aria-labelledby={id} aria-valuemin={0} aria-valuemax={100} aria-valuenow={value === null ? undefined : Math.round(pct)}>
        <span className="ds-meter-fill" style={{ width: `${pct}%` }} />
      </span>
      <span className="ds-meter-value">{value === null ? 'n/a' : display ?? `${Math.round(pct)}%`}</span>
    </div>
  );
}

export function Chip({ children, tone = 'neutral' }: { children: ReactNode; tone?: Tone }) {
  return <span className="ds-chip" data-tone={tone}>{children}</span>;
}
