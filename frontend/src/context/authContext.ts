/**
 * Authentication state contract.
 *
 * The user profile fetched from the backend is the single source of
 * truth for the user group, routing preferences, theme and
 * accessibility settings. Every other context reads from here.
 */
import { createContext, useContext } from 'react';
import type { ThemePreference, UserProfile } from '../types';
import type { RegisterPayload } from '../services/auth.service';

export type AuthStatus = 'initialising' | 'authenticated' | 'anonymous';

export interface ProfilePatch {
  name?: string;
  theme_preference?: ThemePreference;
  accessibility_preferences?: UserProfile['accessibility_preferences'];
  routing_preferences?: UserProfile['routing_preferences'];
}

export type PatchResult = { ok: true } | { ok: false; message: string; hint?: string };

export interface AuthContextValue {
  status: AuthStatus;
  user: UserProfile | null;
  isAuthenticated: boolean;
  /** Set credentials after a successful register/login. */
  adoptSession: (token: string, profile: UserProfile) => void;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (payload: RegisterPayload) => Promise<void>;
  signOut: () => void;
  /**
   * Optimistically applies a profile patch, persists it, and reverts
   * if the backend rejects the change.
   */
  patchProfile: (patch: ProfilePatch) => Promise<PatchResult>;
  /** Re-reads the profile from the backend. */
  refreshProfile: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>.');
  return context;
}

/** Convenience for components that only render inside the shell. */
export function useProfile(): UserProfile {
  const { user } = useAuth();
  if (!user) throw new Error('useProfile must be used on an authenticated route.');
  return user;
}
