/**
 * AI Compass — Evaluation API.
 */
import { post } from './http';
import type { OfflineEvaluationRequest, OfflineEvaluationResponse } from '../types';

export function evaluateOffline(
  payload: OfflineEvaluationRequest,
  signal?: AbortSignal,
): Promise<OfflineEvaluationResponse> {
  return post<OfflineEvaluationResponse>('/evaluate/offline', payload, signal);
}
