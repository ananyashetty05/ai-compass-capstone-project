/**
 * Command palette (Ctrl/⌘ + K, or "/" outside inputs): jump to any page or run a quick action from the keyboard.
 * Dialog pattern: focus trap, Escape closes, ↑/↓ move, Enter runs, focus returns to the trigger.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { ArrowUp, CornerDownLeft, Monitor, Moon, Search, Sun } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { NAV_ITEMS } from './navigation';
import { useFocusTrap } from '../../hooks/useFocusTrap';
import { useTheme } from '../../context/themeContext';
import { scrollToTop } from '../../utils/scroll';

interface Command { id: string; label: string; hint: string; group: string; icon: LucideIcon; run: () => void; keywords?: string }

export function useCommandPalette() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing = !!target && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName));
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setOpen((v) => !v); return; }
      if (event.key === '/' && !typing && !event.metaKey && !event.ctrlKey && !event.altKey) { event.preventDefault(); setOpen(true); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);
  return { open, setOpen };
}

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const { setPreference } = useTheme();
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const panel = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  useFocusTrap(open, panel, onClose);

  const commands = useMemo<Command[]>(() => [
    ...NAV_ITEMS.map((item) => ({ id: `go:${item.to}`, label: item.label, hint: item.description, group: 'Go to', icon: item.icon, run: () => navigate(item.to), keywords: item.shortLabel })),
    { id: 'theme:light', label: 'Appearance: Light', hint: 'Use the light theme', group: 'Actions', icon: Sun, run: () => setPreference('light'), keywords: 'theme' },
    { id: 'theme:dark', label: 'Appearance: Dark', hint: 'Use the dark theme', group: 'Actions', icon: Moon, run: () => setPreference('dark'), keywords: 'theme' },
    { id: 'theme:system', label: 'Appearance: System', hint: 'Follow the operating system', group: 'Actions', icon: Monitor, run: () => setPreference('system'), keywords: 'theme' },
    { id: 'top', label: 'Scroll to top', hint: 'Return to the top of this page', group: 'Actions', icon: ArrowUp, run: () => scrollToTop() },
  ], [navigate, setPreference]);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    const score = (c: Command) => (c.label.toLowerCase().startsWith(q) ? 0 : c.label.toLowerCase().includes(q) ? 1 : (c.keywords ?? '').toLowerCase().includes(q) ? 2 : c.hint.toLowerCase().includes(q) ? 3 : 9);
    return commands.filter((c) => score(c) < 9).sort((a, b) => score(a) - score(b));
  }, [commands, query]);

  useEffect(() => { if (open) { setQuery(''); setActive(0); window.requestAnimationFrame(() => input.current?.focus()); } }, [open]);
  useEffect(() => { setActive(0); }, [query]);
  useEffect(() => { panel.current?.querySelector('[data-active="true"]')?.scrollIntoView({ block: 'nearest' }); }, [active, results]);

  if (!open) return null;
  const run = (c?: Command) => { if (!c) return; onClose(); window.setTimeout(c.run, 0); };
  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'ArrowDown') { event.preventDefault(); setActive((i) => Math.min(results.length - 1, i + 1)); }
    else if (event.key === 'ArrowUp') { event.preventDefault(); setActive((i) => Math.max(0, i - 1)); }
    else if (event.key === 'Enter') { event.preventDefault(); run(results[active]); }
  };
  let lastGroup = '';
  return createPortal(
    <div className="cp-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="cp" role="dialog" aria-modal="true" aria-label="Command palette" ref={panel} onKeyDown={onKeyDown}>
        <label className="cp-search">
          <Search aria-hidden="true" />
          <input ref={input} value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Jump to a page or run an action…" aria-label="Search commands"
            role="combobox" aria-expanded="true" aria-controls="cp-list" aria-activedescendant={results[active] ? `cp-${results[active].id}` : undefined} />
          <kbd>Esc</kbd>
        </label>
        <ul className="cp-list" id="cp-list" role="listbox">
          {results.length === 0 ? <li className="cp-empty">No matching pages or actions</li> : results.map((c, i) => {
            const header = c.group !== lastGroup ? (lastGroup = c.group) : null;
            return (
              <li key={c.id} role="presentation">
                {header ? <p className="cp-group">{header}</p> : null}
                <button type="button" id={`cp-${c.id}`} role="option" aria-selected={i === active} data-active={i === active} className="cp-item" onMouseMove={() => setActive(i)} onClick={() => run(c)}>
                  <c.icon aria-hidden="true" />
                  <span className="cp-item-text"><strong>{c.label}</strong><small>{c.hint}</small></span>
                  {i === active ? <CornerDownLeft aria-hidden="true" className="cp-enter" /> : null}
                </button>
              </li>
            );
          })}
        </ul>
        <p className="cp-foot"><span><kbd>↑</kbd><kbd>↓</kbd> move</span><span><kbd>↵</kbd> open</span><span><kbd>Ctrl</kbd>/<kbd>⌘</kbd><kbd>K</kbd> toggle</span></p>
      </div>
    </div>,
    document.body,
  );
}
