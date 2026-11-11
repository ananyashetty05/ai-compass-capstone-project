/**
 * Panel — a titled surface with a hairline header band and internal
 * dividers.
 *
 * The structural sibling of `Card`. Use a Panel when the content needs
 * a header that reads as chrome (a result identifier, a status) and
 * internal rules that separate concerns — a Panel avoids nesting a card
 * inside a card to get those dividers.
 */
import type { ReactNode } from 'react';
import { cn } from '../../utils/cn';

export interface PanelProps {
  children: ReactNode;
  className?: string;
  /** Heading level owned by the consumer — keeps the outline correct. */
  ariaLabelledBy?: string;
  /** Visual weight. `primary` marks the surface as the page's answer. */
  tone?: 'default' | 'primary' | 'muted';
}

export function Panel({ children, className, ariaLabelledBy, tone = 'default' }: PanelProps) {
  return (
    <div className={cn('panel', className)} data-tone={tone === 'default' ? undefined : tone} aria-labelledby={ariaLabelledBy}>
      {children}
    </div>
  );
}

export interface PanelHeaderProps {
  title: ReactNode;
  /** Visible, non-interactive label rendered before the title. */
  eyebrow?: ReactNode;
  actions?: ReactNode;
  className?: string;
}

export function PanelHeader({ title, eyebrow, actions, className }: PanelHeaderProps) {
  return (
    <div className={cn('panel-header', className)}>
      <p className="panel-title">
        {eyebrow ? <span className="panel-title-eyebrow">{eyebrow} </span> : null}
        {title}
      </p>
      {actions ? <div className="panel-header-actions">{actions}</div> : null}
    </div>
  );
}

export interface PanelBodyProps {
  children: ReactNode;
  padding?: 'default' | 'sm' | 'none';
  className?: string;
}

export function PanelBody({ children, padding = 'default', className }: PanelBodyProps) {
  return (
    <div
      className={cn('panel-body', className)}
      data-padding={padding === 'default' ? undefined : padding}
    >
      {children}
    </div>
  );
}

/** A rule-separated region inside a Panel body. */
export function PanelSection({
  title,
  actions,
  children,
  className,
  as: Heading = 'h3',
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  /**
   * Heading level for the section title. Defaults to `h3`: a `Panel`
   * header is a `<p>`, not a heading, so a section inside a panel sits
   * directly beneath the page's `<h2>`. Pass `h4` when a panel is nested
   * inside a card that already owns an `h3`.
   */
  as?: 'h3' | 'h4';
}) {
  return (
    <section className={cn('panel-section', className)}>
      {title || actions ? (
        <div className="panel-section-head">
          {title ? <Heading className="panel-section-title">{title}</Heading> : <span />}
          {actions ? <div className="panel-header-actions">{actions}</div> : null}
        </div>
      ) : null}
      {children}
    </section>
  );
}

export function PanelFooter({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('panel-footer', className)}>{children}</div>;
}
