/**
 * AppShell — the persistent application frame.
 *
 * Provides the skip link, the responsive sidebar/drawer, the header and
 * a focus-managed `<main>` landmark. Route changes move focus into the
 * main region so keyboard and screen-reader users are not left at the
 * top of the document with no announcement of the new page.
 */
import { useEffect, useLayoutEffect, useRef } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Header } from './Header';
import { scrollToTop } from '../../utils/scroll';
import { BackToTop, ScrollProgress, useAutoReveal } from './MotionLayer';
import { CommandPalette, useCommandPalette } from './CommandPalette';

export function AppShell() {
  const { pathname } = useLocation();
  const mainRef = useRef<HTMLElement>(null);
  const firstRender = useRef(true);
  const palette = useCommandPalette();
  useAutoReveal(pathname);

  // The browser must not restore a remembered offset on its own; every route change starts at the top.
  useEffect(() => {
    if ('scrollRestoration' in window.history) window.history.scrollRestoration = 'manual';
  }, []);
  useLayoutEffect(() => { scrollToTop(); }, [pathname]);

  // Move focus to the main region on navigation (skip the first render,
  // so initial page load does not steal focus).
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    mainRef.current?.focus({ preventScroll: true });
  }, [pathname]);

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>

      <ScrollProgress />
      <div className="app-frame" data-route={pathname}>
        <Header onOpenPalette={() => palette.setOpen(true)} />
        <main
          id="main-content"
          className="app-main"
          data-route={pathname}
          data-wide={pathname === '/' || pathname === '/route' ? 'true' : undefined}
          ref={mainRef}
          tabIndex={-1}
        >
          <div className="app-page-transition" key={pathname}>
            <Outlet />
          </div>
        </main>
      </div>
      <BackToTop />
      <CommandPalette open={palette.open} onClose={() => palette.setOpen(false)} />
    </div>
  );
}
