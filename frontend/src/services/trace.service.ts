/** Stored XAI decision traces (`GET /routing-history/{id}/trace`). Never synthesised: a 404 means "not stored". */
import { get } from './http';
import type { EngineResult } from '../types';

export function getDecisionTrace(routingId: string, signal?: AbortSignal): Promise<EngineResult> {
  return get<EngineResult>(`/routing-history/${encodeURIComponent(routingId)}/trace`, { signal });
}
