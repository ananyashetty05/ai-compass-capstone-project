/**
 * Cinematic entry experience. The story plays first; the existing sign-in
 * form is revealed at the end (or immediately via "Skip to sign in").
 * Creating an account continues to use the existing /onboarding flow.
 */
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Brand } from '../layout/Brand';
import { SignInForm } from '../auth/SignInForm';
import { AuroraBackground } from './AuroraBackground';
import { AuthVisual } from './AuthVisual';
import { Story } from './Story';
import { ThemeSwitch } from './ThemeSwitch';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';

function useInView<T extends Element>() {
  const ref = useRef<T>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || seen) return;
    if (typeof IntersectionObserver === 'undefined') { setSeen(true); return; }
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setSeen(true); io.disconnect(); } }, { threshold: 0.25 });
    io.observe(el);
    return () => io.disconnect();
  }, [seen]);
  return [ref, seen] as const;
}

export function Landing() {
  useDocumentTitle('Sign in');
  const [cardRef, seen] = useInView<HTMLDivElement>();
  const [onAuth, setOnAuth] = useState(false);

  // Hide the brand and skip link once the sign-in section is on screen.
  useEffect(() => {
    const el = document.getElementById('signin');
    if (!el || typeof IntersectionObserver === 'undefined') return;
    const io = new IntersectionObserver(([e]) => setOnAuth(e.isIntersecting), { threshold: 0.35 });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <div className="landing">
      <header className={onAuth ? 'landing-bar is-auth' : 'landing-bar'}>
        <span className="landing-bar-brand"><Brand tagline="Routing intelligence" /></span>
        <div className="landing-bar-actions">
          <a className="story-skip" href="#signin">Skip to sign in</a>
          <ThemeSwitch />
        </div>
      </header>
      <Story />
      <section className="landing-auth" id="signin" aria-labelledby="signin-title">
        <AuroraBackground />
        <div className="la-grid">
          <AuthVisual>
            <p className="story-kicker">AI Compass</p>
            <p className="la-headline">Pick up where your routing left off.</p>
            <p className="story-text">Your priorities and preferences are saved to your account.</p>
          </AuthVisual>
          <div
            className={seen ? 'landing-card is-in' : 'landing-card'}
            ref={cardRef}
            onPointerMove={(e) => {
              const r = e.currentTarget.getBoundingClientRect();
              e.currentTarget.style.setProperty('--mx', `${e.clientX - r.left}px`);
              e.currentTarget.style.setProperty('--my', `${e.clientY - r.top}px`);
            }}
          >
            <Brand tagline="Routing intelligence" />
            <header className="auth-header">
              <h2 className="auth-title" id="signin-title">Sign in</h2>
              <p className="auth-subtitle">Welcome back. Continue to your routing workspace.</p>
            </header>
            <SignInForm />
            <div className="auth-footer">
              <p>New to AI Compass? <Link to="/onboarding" className="text-link">Create an account</Link></p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
