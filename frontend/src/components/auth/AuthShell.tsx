/**
 * Shared shell for the sign-up flow, visually matched to the sign-in
 * section of the landing page: live background, orbit illustration, and a
 * glass card with the same reveal, border light and field effects.
 */
import { useEffect, useState } from 'react';
import type { ReactNode, Ref } from 'react';
import { Gauge, Scale, ShieldCheck } from 'lucide-react';
import { Brand } from '../layout/Brand';
import { AuroraBackground } from '../landing/AuroraBackground';
import { AuthVisual } from '../landing/AuthVisual';
import { ThemeSwitch } from '../landing/ThemeSwitch';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';

export interface AuthShellProps {
  title: string;
  subtitle?: ReactNode;
  documentTitle: string;
  children: ReactNode;
  footer?: ReactNode;
  /** Optional element rendered above the heading (e.g. the stepper). */
  progress?: ReactNode;
  headingRef?: Ref<HTMLHeadingElement>;
}

const POINTS = [
  { icon: Scale, title: 'Balanced by your priorities', text: 'Quality, cost, speed, reliability and risk are weighed the way you choose.' },
  { icon: Gauge, title: 'One model per query', text: 'Each prompt goes to the best model in the pool, with a fallback if needed.' },
  { icon: ShieldCheck, title: 'Every decision explained', text: 'See why a model was picked and why the others were not.' },
];

export function AuthShell({ title, subtitle, documentTitle, children, footer, progress, headingRef }: AuthShellProps) {
  useDocumentTitle(documentTitle);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const t = window.setTimeout(() => setReady(true), 40);
    return () => window.clearTimeout(t);
  }, []);

  return (
    <div className="landing al-page">
      <AuroraBackground />
      <header className="landing-bar">
        <span />
        <div className="landing-bar-actions"><ThemeSwitch /></div>
      </header>
      <main className="la-grid al-grid" id="main">
        <AuthVisual>
          <p className="story-kicker">AI Compass</p>
          <p className="la-headline">The right model for every query, with the reasoning shown.</p>
          <ul className="al-points">
            {POINTS.map(({ icon: Icon, title: t, text }) => (
              <li key={t}>
                <span className="al-point-icon" aria-hidden="true"><Icon /></span>
                <span><strong>{t}</strong><span className="al-point-text">{text}</span></span>
              </li>
            ))}
          </ul>
        </AuthVisual>
        <div
          className={ready ? 'landing-card landing-card--wide is-in' : 'landing-card landing-card--wide'}
          onPointerMove={(e) => {
            const r = e.currentTarget.getBoundingClientRect();
            e.currentTarget.style.setProperty('--mx', `${e.clientX - r.left}px`);
            e.currentTarget.style.setProperty('--my', `${e.clientY - r.top}px`);
          }}
        >
          <Brand tagline="Routing intelligence" />
          {progress}
          <header className="auth-header">
            <h1 className="auth-title" ref={headingRef} tabIndex={-1}>{title}</h1>
            {subtitle ? <p className="auth-subtitle">{subtitle}</p> : null}
          </header>
          {children}
          {footer ? <div className="auth-footer">{footer}</div> : null}
        </div>
      </main>
    </div>
  );
}
