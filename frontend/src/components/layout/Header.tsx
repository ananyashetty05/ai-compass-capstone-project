import { useState } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import { Menu, X } from 'lucide-react';
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

export function Header() {
  const { pathname } = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const current = PRIMARY_NAV.find((item) => item.to === pathname)
    ?? (pathname === '/' ? PRIMARY_NAV.find((item) => item.to === '/route') : undefined);

  useDocumentTitle(current?.label ?? resolveNavItem(pathname)?.label ?? 'AI Compass');

  return (
    <header className="app-topnav">
      <div className="topnav-inner">
        <Link to="/dashboard" className="topnav-brand" aria-label="AI Compass dashboard">
          <Brand tagline="" />
        </Link>

        <nav className="topnav-links" aria-label="Main navigation">
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
