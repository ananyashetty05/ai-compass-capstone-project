/**
 * Primary navigation.
 *
 * Renders as a persistent sidebar on wide viewports and as a modal
 * drawer below the `--layout` breakpoint. `NavLink` supplies
 * `aria-current="page"`, which is the only signal used to highlight the
 * active route.
 */
import { useEffect, useRef } from 'react';
import { NavLink } from 'react-router-dom';
import { X } from 'lucide-react';
import { NAV_SECTIONS } from './navigation';
import { Brand } from './Brand';
import { IconButton } from '../ui/Button';
import { Avatar } from '../ui/Controls';
import { useAuth } from '../../context/authContext';
import { groupLabel } from '../../utils/domain';
import { useFocusTrap } from '../../hooks/useFocusTrap';

export interface SidebarProps {
  /** Mobile drawer state. Ignored on wide viewports. */
  open: boolean;
  onClose: () => void;
  /** True when the sidebar is rendered inside the mobile drawer. */
  variant: 'fixed' | 'drawer';
}

export function Sidebar({ open, onClose, variant }: SidebarProps) {
  const { user } = useAuth();
  const panelRef = useRef<HTMLElement>(null);
  const isDrawer = variant === 'drawer';

  useFocusTrap(isDrawer && open, panelRef, onClose);

  // Prevent background scrolling while the drawer is open.
  useEffect(() => {
    if (!isDrawer || !open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previous;
    };
  }, [isDrawer, open]);

  return (
    <aside
      ref={panelRef}
      className="sidebar"
      data-variant={variant}
      data-open={isDrawer ? (open ? 'true' : 'false') : undefined}
      aria-label="Primary"
      {...(isDrawer ? { role: 'dialog', 'aria-modal': open ? true : undefined } : {})}
      {...(isDrawer && !open ? { inert: true } : {})}
    >
      <div className="drawer-header">
        <Brand to="/" />
        {isDrawer ? <IconButton label="Close navigation" onClick={onClose} icon={<X />} /> : null}
      </div>

      <nav className="sidebar-nav" aria-label="Main">
        {NAV_SECTIONS.map((section) => (
          <section className="nav-section" aria-label={section.title} key={section.id}>
            {/* A visual group label, not a heading: the document `<h1>`
                lives in the topbar, which follows this nav in DOM order,
                and the `<nav>` is already named for assistive technology.
                Promoting these to `<h2>` would put a level-2 heading above
                the level-1 and break the document outline. */}
            <p className="nav-section-title">{section.title}</p>
            <ul className="nav-list">
              {section.items.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.end}
                    onClick={isDrawer ? onClose : undefined}
                    className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
                  >
                    <item.icon aria-hidden="true" />
                    <span className="nav-link-text">{item.label}</span>
                    {item.badge ? (
                      <span className="nav-badge badge" data-tone="primary">{item.badge}</span>
                    ) : null}
                  </NavLink>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </nav>

      {user ? (
        <div className="sidebar-footer">
          <NavLink to="/profile" onClick={isDrawer ? onClose : undefined} className="profile-summary">
            <Avatar name={user.name} size="sm" />
            <span className="profile-summary-text">
              <span className="profile-summary-name">{user.name}</span>
              <span className="profile-summary-group">{groupLabel(user.user_group)}</span>
            </span>
          </NavLink>
        </div>
      ) : null}
    </aside>
  );
}
