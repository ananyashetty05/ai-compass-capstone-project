/**
 * Three-icon theme switch: System, Dark, Light. Uses the app's existing
 * ThemeProvider, so the choice behaves exactly as in the rest of the site
 * (System is the default; it is saved to the account once signed in).
 */
import { Monitor, Moon, Sun } from 'lucide-react';
import { useTheme } from '../../context/themeContext';
import type { ThemePreference } from '../../types';

const OPTIONS: { id: ThemePreference; label: string; Icon: typeof Sun }[] = [
  { id: 'system', label: 'System', Icon: Monitor },
  { id: 'dark', label: 'Dark', Icon: Moon },
  { id: 'light', label: 'Light', Icon: Sun },
];

export function ThemeSwitch() {
  const { preference, setPreference } = useTheme();
  return (
    <div className="theme-switch" role="radiogroup" aria-label="Appearance">
      {OPTIONS.map(({ id, label, Icon }) => (
        <button
          key={id}
          type="button"
          role="radio"
          aria-checked={preference === id}
          aria-label={label}
          title={label}
          className="theme-switch-btn"
          data-active={preference === id || undefined}
          onClick={() => setPreference(id)}
        >
          <Icon aria-hidden="true" />
        </button>
      ))}
    </div>
  );
}
