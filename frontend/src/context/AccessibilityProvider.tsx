/**
 * AccessibilityProvider.
 *
 * Applies the user's accessibility preferences to <html> as data
 * attributes so the token layer can respond without JS-driven styling.
 * Reduced motion is also honoured from the OS media query, and the OS
 * setting is overridden while the user preference is enabled.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { AccessibilityContext, DEFAULT_ACCESSIBILITY } from './accessibilityContext';
import type { AccessibilityContextValue } from './accessibilityContext';
import { useAuth } from './authContext';
import { useToast } from './toastContext';
import type { AccessibilityPreferences, FontSizePreference } from '../types';

const STORAGE_KEY = 'aicompass.accessibility';

function readCached(): AccessibilityPreferences {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_ACCESSIBILITY;
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return DEFAULT_ACCESSIBILITY;
    const record = parsed as Record<string, unknown>;
    return {
      font_size: record.font_size === 'small' || record.font_size === 'large' ? record.font_size : 'default',
      reduced_motion: record.reduced_motion === true,
      high_contrast: record.high_contrast === true,
    };
  } catch {
    return DEFAULT_ACCESSIBILITY;
  }
}

function writeCached(value: AccessibilityPreferences): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  } catch {
    /* non-fatal */
  }
}

function systemPrefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

export function AccessibilityProvider({ children }: { children: ReactNode }) {
  const { user, isAuthenticated, patchProfile } = useAuth();
  const { push } = useToast();
  const [preferences, setPreferences] = useState<AccessibilityPreferences>(readCached);
  const [systemReducedMotion, setSystemReducedMotion] = useState(systemPrefersReducedMotion);

  // Adopt the server-side preferences whenever the profile changes. This
  // is synchronising with an external system (the account), which is
  // exactly what an effect is for.
  useEffect(() => {
    if (!isAuthenticated || !user?.accessibility_preferences) return;
    const next: AccessibilityPreferences = {
      font_size: user.accessibility_preferences.font_size ?? 'default',
      reduced_motion: user.accessibility_preferences.reduced_motion === true,
      high_contrast: user.accessibility_preferences.high_contrast === true,
    };
    // oxlint-disable-next-line react/set-state-in-effect
    setPreferences(next);
    writeCached(next);
  }, [isAuthenticated, user?.accessibility_preferences]);

  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = (event: MediaQueryListEvent) => setSystemReducedMotion(event.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);

  const reducedMotion = preferences.reduced_motion || systemReducedMotion;

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.textScale = preferences.font_size;
    root.dataset.contrast = preferences.high_contrast ? 'high' : 'normal';
    root.dataset.reducedMotion = String(reducedMotion);
  }, [preferences.font_size, preferences.high_contrast, reducedMotion]);

  const commit = useCallback(
    (next: AccessibilityPreferences) => {
      setPreferences(next);
      writeCached(next);
      if (!isAuthenticated) return;
      void patchProfile({ accessibility_preferences: next }).then((result) => {
        if (result.ok === false) {
          push({ tone: 'danger', title: 'Accessibility setting not saved', description: result.message });
        }
      });
    },
    [isAuthenticated, patchProfile, push],
  );

  const setTextSize = useCallback((font_size: FontSizePreference) => commit({ ...preferences, font_size }), [commit, preferences]);
  const setReducedMotion = useCallback(
    (value: boolean) => commit({ ...preferences, reduced_motion: value }),
    [commit, preferences],
  );
  const setHighContrast = useCallback(
    (value: boolean) => commit({ ...preferences, high_contrast: value }),
    [commit, preferences],
  );
  const reset = useCallback(() => commit(DEFAULT_ACCESSIBILITY), [commit]);

  const value = useMemo<AccessibilityContextValue>(
    () => ({ preferences, reducedMotion, setTextSize, setReducedMotion, setHighContrast, reset }),
    [preferences, reducedMotion, setTextSize, setReducedMotion, setHighContrast, reset],
  );

  return <AccessibilityContext.Provider value={value}>{children}</AccessibilityContext.Provider>;
}
