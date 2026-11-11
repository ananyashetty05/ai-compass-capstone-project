/**
 * AI Compass — Model pool API.
 */
import { get } from './http';
import type { ModelInfo } from '../types';

export function listModels(signal?: AbortSignal): Promise<ModelInfo[]> {
  return get<ModelInfo[]>('/models', { signal });
}

export function getModel(modelId: string, signal?: AbortSignal): Promise<ModelInfo> {
  return get<ModelInfo>(`/models/${modelId}`, { signal });
}
