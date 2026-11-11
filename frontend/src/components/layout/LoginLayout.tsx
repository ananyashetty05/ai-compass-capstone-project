/**
 * Split-screen sign-in shell.
 *
 * A full-viewport two-panel surface: the credential form on the left, a
 * dark routing hero on the right. The single `<h1>` lives in the form
 * column so the document outline is correct — the hero headline is an
 * `<h2>` that labels the visual region.
 *
 * This is intentionally separate from `AuthLayout`, which still serves
 * the multi-step onboarding flow.
 */
import type { ReactNode } from 'react';
import { Brand } from './Brand';
import { RoutingVisual } from '../auth/RoutingVisual';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';

export interface LoginLayoutProps {
  eyebrow: string;
  title: string;
  subtitle: ReactNode;
  children: ReactNode;
  /** Rendered under the hero copy — the account-creation path. */
  footer?: ReactNode;
}

export function LoginLayout({ eyebrow, title, subtitle, children, footer }: LoginLayoutProps) {
  useDocumentTitle(`${title} · AI Compass`);

  return (
    <div className="login-page">
      <div className="login-panel">
        <div className="login-panel-inner">
          <Brand className="login-brand" />

          <p className="eyebrow">{eyebrow}</p>
          <h1 className="login-heading">{title}</h1>
          <p className="login-subtitle">{subtitle}</p>

          {children}
        </div>
      </div>

      <div className="login-hero">
        <div className="login-hero-content">
          <p className="eyebrow login-hero-eyebrow">AI Compass</p>
          <h2 className="login-hero-title">
            Every query
            <br />
            routed on its own terms.
          </h2>
          <p className="login-hero-lede">
            Intelligent model routing that balances quality, cost, latency, reliability, risk and your preferences — so you
            get the right model for every request.
          </p>
        </div>

        <RoutingVisual />

        {footer}
      </div>
    </div>
  );
}
