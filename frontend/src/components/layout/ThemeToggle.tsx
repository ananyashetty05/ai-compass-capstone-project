/**
 * Theme switcher.
 *
 * Exposes the stored Light, Dark, or System preference as an explicit
 * choice; the icon reflects the currently selected preference.
 */
import { Monitor, Moon, Sun } from 'lucide-react';
import { useTheme } from '../../context/themeContext';
import type { ThemePreference } from '../../types';

const ICON = { light: Sun, dark: Moon, system: Monitor } as const;

const LABEL: Record<ThemePreference, string> = {
  light: 'Light',
  dark: 'Dark',
  system: 'System',
};

export function ThemeToggle() {
  const { preference, setPreference } = useTheme();
  const Icon = ICON[preference];

  return (
    <label className="theme-control" title="Choose appearance">
      <Icon aria-hidden="true" />
      <span className="sr-only">Appearance</span>
      <select
        aria-label="Appearance"
        value={preference}
        onChange={(event) => {
          const value = event.target.value;
          if (value === 'light' || value === 'dark' || value === 'system') {
            setPreference(value);
          }
        }}
      >
        {(Object.keys(LABEL) as ThemePreference[]).map((theme) => (
          <option key={theme} value={theme}>{LABEL[theme]}</option>
        ))}
      </select>
    </label>
  );
}
