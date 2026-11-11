/**
 * Session-scoped routing results — context contract.
 *
 * `POST /route-and-generate` returns a complete routing decision, and
 * the Route Query, Explanation and Evaluation surfaces all read from
 * that same payload. Holding it here means the three pages always show
 * the same run, and a refresh cannot silently swap in a different one.
 *
 * The result is in memory only: it is never persisted and no history is
 * synthesised, because the backend exposes no routing-history endpoint.
 */
import { createContext, useContext } from 'react';
import type { RouteResponse } from '../types';

export interface RouteResultValue {
  /** The most recent completed routing run, or null if none yet. */
  result: RouteResponse | null;
  /** True while `/route-and-generate` is in flight. */
  isRouting: boolean;
  setResult: (result: RouteResponse) => void;
  clearResult: () => void;
  setRouting: (value: boolean) => void;
}

export const RouteResultContext = createContext<RouteResultValue | null>(null);

export function useRouteResult(): RouteResultValue {
  const context = useContext(RouteResultContext);
  if (!context) throw new Error('useRouteResult must be used inside <RouteResultProvider>.');
  return context;
}

/** Convenience for surfaces that only render when a result exists. */
export function useActiveResult(): RouteResponse | null {
  return useRouteResult().result;
}
