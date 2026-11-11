import type { CSSProperties, ElementType, ReactNode } from 'react';
import { cn } from '../../utils/cn';

export type CardTone = 'default' | 'muted' | 'primary' | 'success' | 'warning' | 'danger' | 'info';
export type CardPadding = 'default' | 'lg' | 'compact' | 'none';

export interface CardProps {
  tone?: CardTone;
  padding?: CardPadding;
  /** Adds a hover affordance for clickable cards. */
  interactive?: boolean;
  /** `raised` lifts the card out of the page. */
  elevation?: 'flat' | 'raised';
  as?: ElementType;
  className?: string;
  style?: CSSProperties;
  /** Heading level owned by the consumer — keeps the document outline correct. */
  ariaLabelledBy?: string;
  children: ReactNode;
}

export function Card({
  tone = 'default',
  padding = 'default',
  interactive,
  elevation = 'flat',
  as: Element = 'div',
  className,
  style,
  ariaLabelledBy,
  children,
}: CardProps) {
  return (
    <Element
      className={cn('card', className)}
      data-tone={tone === 'default' ? undefined : tone}
      data-padding={padding === 'default' ? undefined : padding}
      data-emphasis={elevation === 'raised' ? 'raised' : undefined}
      data-interactive={interactive ? 'true' : undefined}
      style={style}
      aria-labelledby={ariaLabelledBy}
    >
      {children}
    </Element>
  );
}

export interface CardHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  compact?: boolean;
  /** Renders the title at the correct level for the surrounding outline. */
  as?: 'h2' | 'h3' | 'h4';
  id?: string;
}

export function CardHeader({ title, description, icon, actions, compact, as: Heading = 'h3', id }: CardHeaderProps) {
  return (
    <div className="card-header" data-compact={compact || undefined}>
      <div className="card-header-main">
        <Heading className="card-title" id={id}>
          {icon ? (
            <span aria-hidden="true" className="card-title-icon">
              {icon}
            </span>
          ) : null}
          {title}
        </Heading>
        {description ? <p className="card-description">{description}</p> : null}
      </div>
      {actions ? <div className="card-header-actions">{actions}</div> : null}
    </div>
  );
}

export function CardBody({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('card-body', className)}>{children}</div>;
}

export function CardFooter({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('card-footer', className)}>{children}</div>;
}

export interface StatCardProps {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
  tone?: CardTone;
  /** Row header element for a card inside a list. */
  as?: 'div' | 'li';
}

/** Compact label/value card used for headline numbers. */
export function StatCard({ label, value, hint, icon, tone = 'default', as = 'div' }: StatCardProps) {
  return (
    <Card as={as} tone={tone} padding="compact" className="stat-card">
      <p className="stat-card-label">{label}</p>
      <p className="stat-card-value">
        {icon ? (
          <span aria-hidden="true" className="stat-card-icon">
            {icon}
          </span>
        ) : null}
        {value}
      </p>
      {hint ? <p className="stat-card-hint">{hint}</p> : null}
    </Card>
  );
}
