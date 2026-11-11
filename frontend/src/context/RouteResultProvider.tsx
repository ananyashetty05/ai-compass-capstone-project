/**
 * RouteResultProvider — the single owner of the in-memory routing
 * result. The contract and hooks live in `routeResultContext` so this
 * file exports only a component.
 */
import { useCallback, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { RouteResultContext } from './routeResultContext';
import type { RouteResultValue } from './routeResultContext';
import type { RouteResponse } from '../types';

export function RouteResultProvider({ children }: { children: ReactNode }) {
  const [result, setResultState] = useState<RouteResponse | null>(null);
  const [isRouting, setRouting] = useState(false);

  const setResult = useCallback((next: RouteResponse) => {
    setResultState(next);
    setRouting(false);
  }, []);

  const clearResult = useCallback(() => {
    setResultState(null);
    setRouting(false);
  }, []);

  const value = useMemo<RouteResultValue>(
    () => ({ result, isRouting, setResult, clearResult, setRouting }),
    [result, isRouting, setResult, clearResult],
  );

  return <RouteResultContext.Provider value={value}>{children}</RouteResultContext.Provider>;
}
