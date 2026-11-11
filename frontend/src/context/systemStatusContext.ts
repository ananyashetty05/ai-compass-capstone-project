/**
 * System status contract.
 *
 * One health probe is shared by the header, dashboard and settings so
 * the app does not poll `/health` on every page.
 */
import { createContext, useContext } from 'react';
import type { HealthState, HealthResponse } from '../types';
import type { ProviderHealth } from '../services/health.service';

export interface SystemStatusValue {
  state: HealthState;
  /** null while unknown or when the probe failed. */
  health: HealthResponse | null;
  providers: ProviderHealth[];
  /** True during the first probe and after a manual refresh. */
  isChecking: boolean;
  /** Present when the probe failed; drives the offline messaging. */
  error: string | null;
  lastCheckedAt: Date | null;
  refresh: () => void;
}

export const SystemStatusContext = createContext<SystemStatusValue | null>(null);

export function useSystemStatus(): SystemStatusValue {
  const context = useContext(SystemStatusContext);
  if (!context) throw new Error('useSystemStatus must be used inside <SystemStatusProvider>.');
  return context;
}
