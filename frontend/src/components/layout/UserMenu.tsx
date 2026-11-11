/**
 * Account menu.
 *
 * Implements the ARIA menu-button pattern: `aria-expanded` reflects
 * state, arrow keys move between items, Home/End jump to the ends,
 * Escape closes and returns focus to the trigger.
 */
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { LogOut, Settings, UserRound } from 'lucide-react';
import { useAuth } from '../../context/authContext';
import { groupLabel } from '../../utils/domain';
import { Avatar } from '../ui/Controls';
import { useDismissable } from '../../hooks/useDismissable';

export function UserMenu() {
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  const close = useCallback(() => {
    setOpen(false);
    triggerRef.current?.focus();
  }, []);

  // Escape and outside clicks dismiss without stealing focus back.
  useDismissable(open, [triggerRef, menuRef], () => setOpen(false));

  useEffect(() => {
    if (!open) return;
    // Focus the first item so keyboard users land inside the menu.
    window.requestAnimationFrame(() => {
      menuRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    });
  }, [open]);

  const onMenuKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    // Escape closes and returns focus to the trigger, per the ARIA
    // menu-button pattern.
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
      return;
    }
    const items = Array.from(menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? []);
    if (items.length === 0) return;
    const index = items.indexOf(document.activeElement as HTMLElement);
    const move = (next: number) => {
      event.preventDefault();
      items[(next + items.length) % items.length].focus();
    };
    if (event.key === 'ArrowDown') move(index + 1);
    else if (event.key === 'ArrowUp') move(index - 1);
    else if (event.key === 'Home') move(0);
    else if (event.key === 'End') move(items.length - 1);
  };

  if (!user) return null;

  return (
    <div className="user-menu">
      <button
        ref={triggerRef}
        type="button"
        className="avatar-button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-controls={menuId}
      >
        <Avatar name={user.name} />
        <span className="avatar-button-text">
          <span className="avatar-button-name">{user.name}</span>
          <span className="avatar-button-meta">{groupLabel(user.user_group)}</span>
        </span>
      </button>

      {open ? (
        <div
          ref={menuRef}
          id={menuId}
          className="menu"
          data-placement="bottom-end"
          role="menu"
          aria-label="Account"
          onKeyDown={onMenuKeyDown}
        >
          <div className="menu-header">
            <strong>{user.name}</strong>
            <span>{user.email}</span>
          </div>
          <Link role="menuitem" className="menu-item" to="/profile" onClick={() => setOpen(false)}>
            <UserRound aria-hidden="true" />
            Profile &amp; preferences
          </Link>
          <Link role="menuitem" className="menu-item" to="/settings" onClick={() => setOpen(false)}>
            <Settings aria-hidden="true" />
            Settings
          </Link>
          <div className="menu-separator" role="separator" />
          <button
            role="menuitem"
            type="button"
            className="menu-item"
            data-tone="danger"
            onClick={() => {
              setOpen(false);
              signOut();
            }}
          >
            <LogOut aria-hidden="true" />
            Sign out
          </button>
        </div>
      ) : null}
    </div>
  );
}
