/**
 * AI Compass — Routing history API.
 *
 * The current backend does not expose a history endpoint. This module
 * is the frontend's forward-compatible contract for one: it probes the
 * documented path and reports availability, so a future backend change
 * needs no UI work.
 *
 * IMPORTANT: this module never synthesises history entries. When the
 * endpoint is missing, callers render an explicit "not available"
 * state rather than placeholder rows.
 */
import { ApiError, get } from './http';
import type { RoutingHistoryEntry } from '../types';

export const ROUTING_HISTORY_ENDPOINT = '/routing-history';

export type RoutingHistoryResult =
  | { availability: 'available'; entries: RoutingHistoryEntry[] }
  | { availability: 'unsupported'; reason: string }
  | { availability: 'error'; reason: string };

let cachedProbe: Promise<RoutingHistoryResult> | null = null;

async function probe(): Promise<RoutingHistoryResult> {
  try {
    const entries = await get<RoutingHistoryEntry[]>(ROUTING_HISTORY_ENDPOINT);
    return { availability: 'available', entries: Array.isArray(entries) ? entries : [] };
  } catch (error) {
    if (error instanceof ApiError && (error.isNotFound || error.status === 405)) {
      return {
        availability: 'unsupported',
        reason: `This backend build does not expose ${ROUTING_HISTORY_ENDPOINT}.`,
      };
    }
    if (error instanceof ApiError && error.kind === 'canceled') {
      return { availability: 'error', reason: 'The history request was cancelled.' };
    }
    return { availability: 'error', reason: error instanceof Error ? error.message : 'History could not be loaded.' };
  }
}

/**
 * Fetch routing history, probing once per page load. The result —
 * including a negative "unsupported" result — is memoised so the
 * dashboard, query page and history section do not each re-probe.
 */
export function fetchRoutingHistory(): Promise<RoutingHistoryResult> {
  if (!cachedProbe) {
    // This request is shared across page consumers, so a single component
    // unmount (including StrictMode's development remount) must not cancel
    // the cached result for every consumer.
    cachedProbe = probe().finally(() => {
      /* Keep the negative result cached: a missing endpoint stays missing. */
    });
  }
  return cachedProbe;
}

export function resetRoutingHistoryProbe(): void {
  cachedProbe = null;
}
