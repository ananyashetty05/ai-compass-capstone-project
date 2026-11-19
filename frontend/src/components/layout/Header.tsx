import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import { Menu, Search, X } from 'lucide-react';
import { IconButton } from '../ui/Button';
import { ThemeToggle } from './ThemeToggle';
import { UserMenu } from './UserMenu';
import { Brand } from './Brand';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { resolveNavItem } from './navigation';

const PRIMARY_NAV = [
  { to: '/dashboard', label: 'Dashboard', end: true },
  { to: '/route', label: 'Route Query' },
  { to: '/models', label: 'Model Pool' },
  { to: '/evaluation', label: 'Evaluation' },
  { to: '/personalization', label: 'Personalization' },
];

export function Header({ onOpenPalette }: { onOpenPalette?: () => void }) {
  const { pathname } = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const current = PRIMARY_NAV.find((item) => item.to === pathname)
    ?? (pathname === '/' ? PRIMARY_NAV.find((item) => item.to === '/route') : undefined);

  const linksRef = useRef<HTMLElement>(null);
  const [ind, setInd] = useState<{ x: number; w: number } | null>(null);
  // Sliding indicator under the active link; re-measured on route, resize and font load.
  useLayoutEffect(() => {
    const nav = linksRef.current;
    if (!nav) return;
    const measure = () => {
      const active = nav.querySelector<HTMLElement>('.topnav-link.is-active');
      setInd(active ? { x: active.offsetLeft, w: active.offsetWidth } : null);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(nav);
    document.fonts?.ready.then(measure).catch(() => undefined);
    return () => ro.disconnect();
  }, [pathname]);
  useEffect(() => { setMobileOpen(false); }, [pathname]);

  useDocumentTitle(current?.label ?? resolveNavItem(pathname)?.label ?? 'AI Compass');

  return (
    <header className="app-topnav">
      <div className="topnav-inner">
        <Link to="/dashboard" className="topnav-brand" aria-label="AI Compass dashboard">
          <Brand tagline="" />
        </Link>

        <nav className="topnav-links" aria-label="Main navigation" ref={linksRef}>
          <span className="topnav-indicator" aria-hidden="true" style={ind ? { transform: `translateX(${ind.x}px)`, width: ind.w, opacity: 1 } : { opacity: 0 }} />
          {PRIMARY_NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `topnav-link${isActive || (item.to === '/route' && pathname === '/') ? ' is-active' : ''}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="topnav-controls">
          {onOpenPalette ? (
            <button type="button" className="topnav-search" onClick={onOpenPalette} aria-label="Open command palette (Control or Command K)">
              <Search aria-hidden="true" /><span>Jump to…</span><kbd>⌘K</kbd>
            </button>
          ) : null}
          <ThemeToggle />
          <UserMenu />
          <IconButton
            className="topnav-mobile-toggle"
            label={mobileOpen ? 'Close navigation' : 'Open navigation'}
            onClick={() => setMobileOpen((open) => !open)}
            icon={mobileOpen ? <X /> : <Menu />}
            aria-expanded={mobileOpen}
            aria-controls="mobile-primary-navigation"
          />
        </div>
      </div>
      {mobileOpen ? (
        <nav id="mobile-primary-navigation" className="topnav-mobile-panel" aria-label="Main navigation">
          {PRIMARY_NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              onClick={() => setMobileOpen(false)}
              className={({ isActive }) => `topnav-mobile-link${isActive || (item.to === '/route' && pathname === '/') ? ' is-active' : ''}`}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      ) : null}
    </header>
  );
}
