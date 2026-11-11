/**
 * Page header.
 *
 * Each page inside the shell owns exactly one `<h2>` (the shell owns the
 * `<h1>` in the header), so the document outline stays flat and
 * predictable. Pages rendered *outside* the shell — the 404 — pass
 * `as="h1"` so they still own exactly one top-level heading.
 */
import type { ReactNode } from 'react';

export interface PageHeaderProps {
  title: string;
  description?: ReactNode;
  /** Small label above the title, e.g. "Registry". */
  eyebrow?: string;
  actions?: ReactNode;
  id?: string;
  /** Heading element. Defaults to `h2`; use `h1` outside the shell. */
  as?: 'h1' | 'h2';
}

export function PageHeader({ title, description, eyebrow, actions, id, as: Heading = 'h2' }: PageHeaderProps) {
  const headingId = id ?? `page-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;

  return (
    <header className="page-header">
      <div className="page-header-text">
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <Heading className="page-title" id={headingId}>
          {title}
        </Heading>
        {description ? <p className="page-description">{description}</p> : null}
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </header>
  );
}
