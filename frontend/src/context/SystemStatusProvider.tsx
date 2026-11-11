/**
 * SystemStatusProvider — a single shared `/health` probe.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { SystemStatusContext } from './systemStatusContext';
import type { SystemStatusValue } from './systemStatusContext';
import { getHealth, summariseHealth, toProviderHealth } from '../services/health.service';
import type { ProviderHealth } from '../services/health.service';
import { describeError } from '../services/http';
import type { HealthResponse, HealthState } from '../types';

const POLL_INTERVAL_MS = 60_000;

export function SystemStatusProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [state, setState] = useState<HealthState>('unknown');
  const [providers, setProviders] = useState<ProviderHealth[]>([]);
  const [isChecking, setIsChecking] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastCheckedAt, setLastCheckedAt] = useState<Date | null>(null);

  const probe = useCallback((signal?: AbortSignal) => {
    setIsChecking(true);
    return getHealth(signal)
      .then((response) => {
        if (signal?.aborted) return;
        setHealth(response);
        setState(summariseHealth(response).state);
        setProviders(toProviderHealth(response));
        setError(null);
        setLastCheckedAt(new Date());
      })
      .catch((cause: unknown) => {
        if (signal?.aborted) return;
        setHealth(null);
        setState('offline');
        setProviders([]);
        setError(describeError(cause, 'The backend could not be reached.').message);
        setLastCheckedAt(new Date());
      })
      .finally(() => {
        if (!signal?.aborted) setIsChecking(false);
      });
  }, []);

  // Initial health probe. Polling an external service on mount is the
  // canonical use of an effect; the state it sets is the response.
  useEffect(() => {
    const controller = new AbortController();
    // oxlint-disable-next-line react/set-state-in-effect
    void probe(controller.signal);
    return () => controller.abort();
  }, [probe]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      if (document.visibilityState === 'visible') void probe();
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(interval);
  }, [probe]);

  const value = useMemo<SystemStatusValue>(
    () => ({ state, health, providers, isChecking, error, lastCheckedAt, refresh: () => void probe() }),
    [state, health, providers, isChecking, error, lastCheckedAt, probe],
  );

  return <SystemStatusContext.Provider value={value}>{children}</SystemStatusContext.Provider>;
}
