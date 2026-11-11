/**
 * Brand lockup. Links to the dashboard so it doubles as a "home"
 * control inside the shell and on the authentication surfaces.
 */
import { Link } from 'react-router-dom';
import { Compass } from 'lucide-react';
import { cn } from '../../utils/cn';

export interface BrandProps {
  /** Renders as a link on the dashboard, static on auth surfaces. */
  to?: string;
  tagline?: string;
  className?: string;
}

export function Brand({ to, tagline = 'Routing intelligence', className }: BrandProps) {
  const content = (
    <>
      <span className="brand-mark" aria-hidden="true">
        <Compass />
      </span>
      <span className="brand-text">
        <span className="brand-name">AI Compass</span>
        <span className="brand-tagline">{tagline}</span>
      </span>
    </>
  );

  if (to) {
    return (
      <Link to={to} className={cn('brand', className)}>
        {content}
      </Link>
    );
  }

  return (
    <span className={cn('brand', className)}>
      {content}
    </span>
  );
}
