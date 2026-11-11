/**
 * Authentication surface shell.
 *
 * Full-bleed two-column layout on wide viewports: a product explainer
 * beside the form, collapsing to a single column below 60rem. The
 * single `<h1>` lives in the form column so the heading order stays
 * correct for assistive technology.
 */
import type { ReactNode } from 'react';
import { Brand } from './Brand';
import { ARCHITECTURE_FLOW } from '../../utils/domain';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';

export interface AuthLayoutProps {
  title: string;
  subtitle: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  /** Widens the form column for multi-step onboarding. */
  wide?: boolean;
}

export function AuthLayout({ title, subtitle, children, footer, wide }: AuthLayoutProps) {
  useDocumentTitle(title);

  return (
    <div className="auth-layout">
      <div className="auth-main">
        <div className="auth-card" data-wide={wide || undefined}>
          <div className="auth-mobile-brand">
            <Brand tagline="" />
          </div>
          <h1 className="auth-title">{title}</h1>
          <p className="auth-subtitle">{subtitle}</p>
          {children}
          {footer ? <p className="auth-footer">{footer}</p> : null}
        </div>
      </div>

      <aside className="auth-aside" aria-label="How AI Compass routes a query">
        <div>
          <Brand />
          <h2 className="auth-aside-headline">Every query routed on its own terms.</h2>
          <p className="auth-aside-copy">
            AI Compass analyses each request, filters the model registry against your hard constraints, then scores the
            remaining candidates across quality, cost, latency, reliability, risk and how well they fit your profile.
            Responses are evaluated, and escalated to the next-best model when they fall short.
          </p>
        </div>

        <ol className="auth-flow">
          {ARCHITECTURE_FLOW.map((step, index) => (
            <li key={step.label} className="auth-flow-item">
              <span className="auth-flow-index" aria-hidden="true">
                {index + 1}
              </span>
              <span className="auth-flow-text">
                <span className="auth-flow-label">{step.label}</span>
                <span className="auth-flow-note">{step.note}</span>
              </span>
            </li>
          ))}
        </ol>

        <p className="auth-aside-footnote">
          Your provider credentials stay on the server. This interface only ever displays registry metadata and routing
          decisions returned by the backend.
        </p>
      </aside>
    </div>
  );
}
