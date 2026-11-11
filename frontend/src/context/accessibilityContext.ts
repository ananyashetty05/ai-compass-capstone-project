/**
 * Accessibility preferences contract.
 * Text size, reduced motion and high contrast are account-specific and
 * persist to the backend profile.
 */
import { createContext, useContext } from 'react';
import type { AccessibilityPreferences, FontSizePreference } from '../types';

export interface AccessibilityContextValue {
  preferences: AccessibilityPreferences;
  /** True when the user asked for reduced motion, or the OS does. */
  reducedMotion: boolean;
  setTextSize: (size: FontSizePreference) => void;
  setReducedMotion: (value: boolean) => void;
  setHighContrast: (value: boolean) => void;
  reset: () => void;
}

export const DEFAULT_ACCESSIBILITY: AccessibilityPreferences = {
  font_size: 'default',
  reduced_motion: false,
  high_contrast: false,
};

export const AccessibilityContext = createContext<AccessibilityContextValue | null>(null);

export function useAccessibility(): AccessibilityContextValue {
  const context = useContext(AccessibilityContext);
  if (!context) throw new Error('useAccessibility must be used inside <AccessibilityProvider>.');
  return context;
}
