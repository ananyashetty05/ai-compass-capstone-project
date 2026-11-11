/**
 * Theme contract. The resolved appearance is derived from the
 * persisted profile preference plus the OS setting, so switching
 * devices keeps the same choice.
 */
import { createContext, useContext } from 'react';
import type { ThemePreference } from '../types';

export interface ThemeContextValue {
  /** What the user selected: light | dark | system. */
  preference: ThemePreference;
  /** What is actually rendered: light | dark. */
  resolved: 'light' | 'dark';
  setPreference: (next: ThemePreference) => void;
  /** Cycles light → dark → system, for the header control. */
  cycle: () => void;
}

export const ThemeContext = createContext<ThemeContextValue | null>(null);

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) throw new Error('useTheme must be used inside <ThemeProvider>.');
  return context;
}
