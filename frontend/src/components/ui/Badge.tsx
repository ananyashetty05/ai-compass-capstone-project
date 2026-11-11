import type { ReactNode } from 'react';
import {
  CheckCircle2,
  CircleDashed,
  CircleSlash,
  Clock,
  Info,
  Loader2,
  MinusCircle,
  ShieldAlert,
  XCircle,
  Zap,
} from 'lucide-react';
import { cn } from '../../utils/cn';

/* ------------------------------------------------------------------ *
 * Badge — compact, non-interactive label
 * ------------------------------------------------------------------ */

export type BadgeTone = 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info';

export interface BadgeProps {
  tone?: BadgeTone;
  size?: 'md' | 'lg';
  icon?: ReactNode;
  outline?: boolean;
  children: ReactNode;
  title?: string;
}

export function Badge({ tone = 'neutral', size = 'md', icon, outline, children, title }: BadgeProps) {
  return (
    <span
      className={cn('badge', outline && 'badge-outline')}
      data-tone={tone}
      data-size={size === 'lg' ? 'lg' : undefined}
      title={title}
    >
      {icon ? (
        <span aria-hidden="true" className="badge-icon">
          {icon}
        </span>
      ) : null}
      {children}
    </span>
  );
}

/* ------------------------------------------------------------------ *
 * Status — the accessible status system
 *
 * Every status carries visible text. The icon and colour are
 * supplementary, so meaning is never conveyed by colour alone.
 * ------------------------------------------------------------------ */

export type StatusTone = 'neutral' | 'success' | 'warning' | 'danger' | 'info' | 'primary';

const STATUS_ICONS = {
  online: CheckCircle2,
  success: CheckCircle2,
  passed: CheckCircle2,
  active: CheckCircle2,
  selected: CheckCircle2,
  offline: XCircle,
  failed: XCircle,
  danger: XCircle,
  connecting: Loader2,
  busy: Loader2,
  pending: Clock,
  warning: ShieldAlert,
  escalated: ShieldAlert,
  filtered: CircleSlash,
  inactive: MinusCircle,
  unavailable: CircleDashed,
  info: Info,
  draft: CircleDashed,
  primary: Zap,
} as const;

export type StatusName = keyof typeof STATUS_ICONS;

const STATUS_TONES: Record<StatusName, StatusTone> = {
  online: 'success',
  success: 'success',
  passed: 'success',
  active: 'success',
  selected: 'primary',
  offline: 'danger',
  failed: 'danger',
  danger: 'danger',
  connecting: 'info',
  busy: 'info',
  pending: 'neutral',
  warning: 'warning',
  escalated: 'warning',
  filtered: 'neutral',
  inactive: 'neutral',
  unavailable: 'neutral',
  info: 'info',
  draft: 'neutral',
  primary: 'primary',
};

export interface StatusProps {
  name: StatusName;
  /** Visible text. Required — this is the accessible source of truth. */
  children: ReactNode;
  /** Overrides the derived tone. */
  tone?: StatusTone;
  /** Marks the spinner icon as animating. */
  busy?: boolean;
  title?: string;
}

export function Status({ name, children, tone, busy, title }: StatusProps) {
  const Icon = STATUS_ICONS[name];
  return (
    <span className="status" data-tone={tone ?? STATUS_TONES[name]} data-busy={busy || undefined} title={title}>
      <span className="status-icon" aria-hidden="true">
        <Icon />
      </span>
      {children}
    </span>
  );
}

/* ------------------------------------------------------------------ *
 * Provenance — separates measured from estimated from unavailable
 * ------------------------------------------------------------------ */

export type ProvenanceKind = 'measured' | 'estimated' | 'unavailable';

const PROVENANCE_TEXT: Record<ProvenanceKind, string> = {
  measured: 'Measured',
  estimated: 'Estimated',
  unavailable: 'Unavailable',
};

export interface ProvenanceTagProps {
  kind: ProvenanceKind;
  /** Overrides the default label, e.g. "Measured (this run)". */
  label?: string;
}

export function ProvenanceTag({ kind, label }: ProvenanceTagProps) {
  return (
    <span className="provenance" data-kind={kind} title={`Data provenance: ${label ?? PROVENANCE_TEXT[kind].toLowerCase()}`}>
      {label ?? PROVENANCE_TEXT[kind]}
    </span>
  );
}

/* ------------------------------------------------------------------ *
 * Tag — capability / trait chip
 * ------------------------------------------------------------------ */

export function Tag({ tone = 'neutral', children, title }: { tone?: 'neutral' | 'primary'; children: ReactNode; title?: string }) {
  return (
    <span className="tag" data-tone={tone === 'primary' ? 'primary' : undefined} title={title}>
      {children}
    </span>
  );
}

export function TagList({ items, tone, max }: { items: readonly string[]; tone?: 'neutral' | 'primary'; max?: number }) {
  if (items.length === 0) {
    return <span className="text-muted text-xs">None reported</span>;
  }
  const visible = max ? items.slice(0, max) : items;
  const hidden = items.length - visible.length;
  return (
    <ul className="tag-list">
      {visible.map((item) => (
        <li key={item}>
          <Tag tone={tone}>{item}</Tag>
        </li>
      ))}
      {hidden > 0 ? (
        <li>
          <Tag title={items.slice(max).join(', ')}>+{hidden} more</Tag>
        </li>
      ) : null}
    </ul>
  );
}
