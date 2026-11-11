/**
 * ThemeProvider.
 *
 * Maps a three-state preference (light / dark / system) onto the
 * semantic token set. The preference is persisted to the user profile
 * through the existing backend endpoint, not to localStorage, so it
 * follows the account.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { ThemeContext } from './themeContext';
import type { ThemeContextValue } from './themeContext';
import { useAuth } from './authContext';
import { useToast } from './toastContext';
import type { ThemePreference } from '../types';

const VALID: ThemePreference[] = ['light', 'dark', 'system'];
const STORAGE_KEY = 'aicompass.theme.preference';

function normalise(value: string | undefined): ThemePreference {
  const lower = value?.toLowerCase();
  return VALID.includes(lower as ThemePreference) ? (lower as ThemePreference) : 'system';
}

function readCached(): ThemePreference {
  try {
    return normalise(window.localStorage.getItem(STORAGE_KEY) ?? undefined);
  } catch {
    return 'system';
  }
}

function writeCached(value: ThemePreference): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, value);
  } catch {
    /* non-fatal */
  }
}

function systemPrefersDark(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const { user, isAuthenticated, patchProfile } = useAuth();
  const { push } = useToast();
  // Cached preference renders immediately, avoiding a light-theme flash
  // while `/auth/me` is still in flight.
  const [preference, setPreference] = useState<ThemePreference>(readCached);
  const [systemDark, setSystemDark] = useState(systemPrefersDark);

  // Adopt the server-side preference whenever the profile changes. This
  // is synchronising with an external system (the account), which is
  // exactly what an effect is for.
  useEffect(() => {
    if (!isAuthenticated || !user) return;
    const next = normalise(user.theme_preference);
    // oxlint-disable-next-line react/set-state-in-effect
    setPreference(next);
    writeCached(next);
  }, [isAuthenticated, user?.theme_preference]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const update = (event: MediaQueryListEvent) => setSystemDark(event.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);

  const resolved: 'light' | 'dark' = preference === 'system' ? (systemDark ? 'dark' : 'light') : preference;

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = resolved;
    root.style.colorScheme = resolved;
  }, [resolved]);

  const setPreferenceAndPersist = useCallback(
    (next: ThemePreference) => {
      setPreference(next);
      writeCached(next);
      if (!isAuthenticated) return;
      void patchProfile({ theme_preference: next }).then((result) => {
        if (result.ok === false) {
          push({ tone: 'danger', title: 'Theme not saved', description: result.message });
        }
      });
    },
    [isAuthenticated, patchProfile, push],
  );

  const cycle = useCallback(() => {
    const order: ThemePreference[] = ['light', 'dark', 'system'];
    const index = order.indexOf(preference);
    setPreferenceAndPersist(order[(index + 1) % order.length]);
  }, [preference, setPreferenceAndPersist]);

  const value = useMemo<ThemeContextValue>(
    () => ({ preference, resolved, setPreference: setPreferenceAndPersist, cycle }),
    [preference, resolved, setPreferenceAndPersist, cycle],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
