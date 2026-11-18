/**
 * AI Compass — Model pool API.
 */
import { get } from './http';
import type { ModelInfo, RegistryStatus } from '../types';

export function listModels(signal?: AbortSignal): Promise<ModelInfo[]> {
  return get<ModelInfo[]>('/models', { signal });
}

export function getModel(modelId: string, signal?: AbortSignal): Promise<ModelInfo> {
  return get<ModelInfo>(`/models/${modelId}`, { signal });
}

export function getRegistryStatus(signal?: AbortSignal): Promise<RegistryStatus> {
  return get<RegistryStatus>('/models/registry-status', { signal });
}
