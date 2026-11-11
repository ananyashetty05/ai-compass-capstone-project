import type { ReactNode } from 'react';
import { AlertTriangle, CheckCircle2, Inbox, Info, PlugZap, RefreshCw, SearchX, ServerCrash, ShieldOff } from 'lucide-react';
import { Button } from './Button';

export type StateIconName = 'empty' | 'search' | 'error' | 'offline' | 'blocked' | 'info';

const ICONS: Record<StateIconName, typeof Inbox> = {
  empty: Inbox,
  search: SearchX,
  error: AlertTriangle,
  offline: ServerCrash,
  blocked: ShieldOff,
  info: PlugZap,
};

export interface EmptyStateProps {
  icon?: ReactNode;
  iconName?: StateIconName;
  title: string;
  /** Explains what happened. */
  description: ReactNode;
  /** Explains what the user can do next. */
  action?: ReactNode;
  secondaryAction?: ReactNode;
  align?: 'center' | 'start';
}

export function EmptyState({ icon, iconName = 'empty', title, description, action, secondaryAction, align = 'center' }: EmptyStateProps) {
  const Icon = ICONS[iconName];
  return (
    <div className="state-block" data-align={align === 'start' ? 'start' : undefined}>
      <span className="state-icon" aria-hidden="true">
        {icon ?? <Icon />}
      </span>
      <p className="state-title">{title}</p>
      <p className="state-description">{description}</p>
      {action || secondaryAction ? (
        <div className="state-actions">
          {action}
          {secondaryAction}
        </div>
      ) : null}
    </div>
  );
}

export interface ErrorStateProps {
  title?: string;
  message: string;
  hint?: string;
  onRetry?: () => void;
  retryLabel?: string;
  /** Extra guidance rendered below the retry control. */
  children?: ReactNode;
  compact?: boolean;
}

/**
 * Explicit error surface. Always shows the backend's own message —
 * the UI never substitutes a fabricated result for a failed request.
 */
export function ErrorState({
  title = 'Something went wrong',
  message,
  hint,
  onRetry,
  retryLabel = 'Try again',
  children,
  compact,
}: ErrorStateProps) {
  const body = (
    <>
      <span className="state-icon" aria-hidden="true">
        <AlertTriangle />
      </span>
      <p className="state-title">{title}</p>
      <p className="state-description">{message}</p>
      {hint ? <p className="state-description state-description-sm">{hint}</p> : null}
      {onRetry || children ? (
        <div className="state-actions">
          {onRetry ? (
            <Button variant="secondary" size="sm" leadingIcon={<RefreshCw />} onClick={onRetry}>
              {retryLabel}
            </Button>
          ) : null}
          {children}
        </div>
      ) : null}
    </>
  );

  if (compact) {
    return (
      <div className="notice" data-tone="danger" role="alert">
        <AlertTriangle aria-hidden="true" />
        <div className="notice-body">
          <p className="notice-title">{title}</p>
          <p>{message}</p>
          {hint ? <p className="text-xs">{hint}</p> : null}
          {onRetry ? (
            <div className="notice-actions">
              <Button variant="danger-ghost" size="sm" leadingIcon={<RefreshCw />} onClick={onRetry}>
                {retryLabel}
              </Button>
            </div>
          ) : null}
          {children}
        </div>
      </div>
    );
  }

  return (
    <div className="state-block" data-align="start" role="alert">
      {body}
    </div>
  );
}

export interface NoticeProps {
  tone?: 'neutral' | 'primary' | 'success' | 'warning' | 'danger' | 'info';
  title?: string;
  children: ReactNode;
  icon?: ReactNode;
  /** `status` for polite updates, `alert` for errors. */
  live?: 'status' | 'alert' | 'none';
  actions?: ReactNode;
}

export function Notice({ tone = 'neutral', title, children, icon, live = 'none', actions }: NoticeProps) {
  const fallbackIcon = (
    <>
      {tone === 'success' ? <CheckCircle2 /> : null}
      {tone === 'warning' || tone === 'danger' ? <AlertTriangle /> : null}
      {tone === 'info' || tone === 'primary' ? <Info /> : null}
    </>
  );

  return (
    <div
      className="notice"
      data-tone={tone === 'neutral' ? undefined : tone}
      role={live === 'none' ? undefined : live === 'status' ? 'status' : 'alert'}
    >
      <span aria-hidden="true">{icon ?? fallbackIcon}</span>
      <div className="notice-body">
        {title ? <p className="notice-title">{title}</p> : null}
        <div>{children}</div>
        {actions ? <div className="notice-actions">{actions}</div> : null}
      </div>
    </div>
  );
}
