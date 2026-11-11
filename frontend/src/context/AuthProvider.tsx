/**
 * AuthProvider — session bootstrap and profile persistence.
 *
 * Security notes:
 *  - The bearer token is stored by `tokenStore` in services/http and is
 *    never logged, rendered or included in a URL.
 *  - A 401 from any request clears the token and drops the session.
 *  - Provider credentials and routing internals stay server-side; this
 *    layer only ever holds what `/auth/me` returns.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { AuthContext } from './authContext';
import type { AuthContextValue, AuthStatus } from './authContext';
import * as authService from '../services/auth.service';
import type { RegisterPayload } from '../services/auth.service';
import { UNAUTHORIZED_EVENT, describeError, tokenStore } from '../services/http';
import type { UserProfile } from '../types';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  // The token is read once: the bootstrap is a one-time side effect,
  // and a token appearing later arrives through `adoptSession`.
  const [initialToken] = useState(() => tokenStore.get());
  const [bootstrapped, setBootstrapped] = useState<AuthStatus | null>(null);
  const mounted = useRef(true);

  // Derived during render, so an anonymous visitor never renders a
  // loading state and no effect has to correct it afterwards.
  const status: AuthStatus = bootstrapped ?? (initialToken ? 'initialising' : 'anonymous');

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // Restore an existing session on first load.
  useEffect(() => {
    if (status !== 'initialising') return;
    const controller = new AbortController();
    authService
      .getMe(controller.signal)
      .then((profile) => {
        if (controller.signal.aborted || !mounted.current) return;
        setUser(profile);
        setBootstrapped('authenticated');
      })
      .catch(() => {
        if (controller.signal.aborted || !mounted.current) return;
        tokenStore.clear();
        setUser(null);
        setBootstrapped('anonymous');
      });
    return () => controller.abort();
  }, [status]);

  // Global 401 handling: drop the session and let the router redirect.
  useEffect(() => {
    const handle = () => {
      tokenStore.clear();
      setUser(null);
      setBootstrapped('anonymous');
    };
    window.addEventListener(UNAUTHORIZED_EVENT, handle);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handle);
  }, []);

  const adoptSession = useCallback((token: string, profile: UserProfile) => {
    tokenStore.set(token);
    setUser(profile);
    setBootstrapped('authenticated');
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const result = await authService.login(email, password);
    adoptSession(result.token, result.profile);
  }, [adoptSession]);

  const signUp = useCallback(async (payload: RegisterPayload) => {
    const result = await authService.register(payload);
    adoptSession(result.token, result.profile);
  }, [adoptSession]);

  const signOut = useCallback(() => {
    tokenStore.clear();
    setUser(null);
    setBootstrapped('anonymous');
  }, []);

  const refreshProfile = useCallback(async () => {
    try {
      const profile = await authService.getMe();
      if (!mounted.current) return;
      setUser(profile);
      setBootstrapped('authenticated');
    } catch {
      // A failure here is non-fatal: the cached profile stays in place.
    }
  }, []);

  const patchProfile = useCallback<AuthContextValue['patchProfile']>(
    async (patch) => {
      const previous = user;
      // Optimistic update so sliders and toggles feel instant.
      setUser((current) => (current ? { ...current, ...patch } : current));

      try {
        let saved: UserProfile;
        if (patch.routing_preferences) {
          saved = await authService.updatePreferences(patch.routing_preferences);
        } else {
          saved = await authService.updateProfile(patch);
        }
        if (mounted.current) setUser(saved);
        return { ok: true };
      } catch (cause) {
        if (mounted.current) setUser(previous);
        const described = describeError(cause, 'Your changes could not be saved.');
        return { ok: false, message: described.message, hint: described.hint };
      }
    },
    [user],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      isAuthenticated: status === 'authenticated' && user !== null,
      adoptSession,
      signIn,
      signUp,
      signOut,
      patchProfile,
      refreshProfile,
    }),
    [status, user, adoptSession, signIn, signUp, signOut, patchProfile, refreshProfile],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
