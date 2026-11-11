export * from './api';

/* ------------------------------------------------------------------ *
 * UI-level view models
 * ------------------------------------------------------------------ */

/** Where a numeric value came from. Never conflate these. */
export type Provenance = 'measured' | 'estimated' | 'unavailable';

export interface MetricValue {
  /** null means "not reported by the backend" — never substitute 0. */
  value: number | null;
  provenance: Provenance;
  unit?: string;
  /** Where this number came from, shown in the UI. */
  source: string;
}

export const UNAVAILABLE = 'Unavailable';
