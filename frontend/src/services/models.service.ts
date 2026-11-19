/**
 * AI Compass — Model pool API.
 */
import { get, http } from './http';
import type {
  CatalogPage, CatalogQuery, ModelDetailResponse, ModelInfo, RefreshHistoryItem, RefreshResult,
  PoolStats, RegistryActivityItem, RegistryStatus, VerifyResult,
} from '../types';

export function listModels(signal?: AbortSignal): Promise<ModelInfo[]> {
  return get<ModelInfo[]>('/models', { signal });
}

export function getPoolStats(signal?: AbortSignal): Promise<PoolStats> {
  return get<PoolStats>('/models/pool-stats', { signal });
}

export function getModel(modelId: string, signal?: AbortSignal): Promise<ModelInfo> {
  return get<ModelInfo>(`/models/${modelId}`, { signal });
}

export function getRegistryStatus(signal?: AbortSignal): Promise<RegistryStatus> {
  return get<RegistryStatus>('/models/registry-status', { signal });
}

export async function getCatalog(query: CatalogQuery, signal?: AbortSignal): Promise<CatalogPage> {
  const params: Record<string, string> = {};
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== '' && value !== 'all') params[key] = String(value);
  }
  return get<CatalogPage>('/models/catalog', { signal, params });
}

export function getModelDetail(provider: string, modelId: string, signal?: AbortSignal): Promise<ModelDetailResponse> {
  return get<ModelDetailResponse>('/models/detail', { signal, params: { provider, model_id: modelId } });
}

export function getRegistryActivity(signal?: AbortSignal): Promise<RegistryActivityItem[]> {
  return get<RegistryActivityItem[]>('/models/activity', { signal, params: { limit: '30' } });
}

export function getRefreshHistory(signal?: AbortSignal): Promise<RefreshHistoryItem[]> {
  return get<RefreshHistoryItem[]>('/models/refresh-history', { signal, params: { limit: '20' } });
}

/* Administrator operations. The token is supplied per call from component memory;
 * it is never persisted, logged or placed in a URL. */
const adminHeaders = (token: string) => ({ 'X-Registry-Admin-Token': token });

export async function refreshRegistry(token: string, provider: string | null, onlyIfStale: boolean): Promise<RefreshResult[]> {
  const response = await http.post<{ results: RefreshResult[] }>(
    '/models/registry/refresh', { provider, only_if_stale: onlyIfStale }, { headers: adminHeaders(token) },
  );
  return response.data.results;
}

export async function verifyModelInference(token: string, provider: string, modelId: string): Promise<VerifyResult> {
  const response = await http.post<VerifyResult>(
    '/models/registry/verify', { provider, model_id: modelId }, { headers: adminHeaders(token) },
  );
  return response.data;
}
