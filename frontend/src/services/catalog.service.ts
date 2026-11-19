/**
 * AI Compass — autonomous catalogue API (read-only). Discovery itself runs server-side on a schedule;
 * nothing here triggers it.
 */
import { get } from './http';
import type { CatalogEcosystem, CatalogFamily } from '../types';

export function getCatalogEcosystem(signal?: AbortSignal): Promise<CatalogEcosystem> {
  return get<CatalogEcosystem>('/catalog/summary', { signal });
}

export function getCatalogFamilies(signal?: AbortSignal): Promise<CatalogFamily[]> {
  return get<CatalogFamily[]>('/catalog/families', { signal });
}
