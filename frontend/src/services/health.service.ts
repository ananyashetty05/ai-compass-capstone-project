/**
 * AI Compass — System health API.
 *
 * `/health` never returns provider secrets; it reports only whether a
 * server-side credential is configured and whether the provider is
 * administratively disabled.
 */
import { get } from './http';
import type { HealthResponse, HealthState, ProviderId, ProviderStatus } from '../types';

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return get<HealthResponse>('/health', { signal });
}

export interface ProviderHealth {
  id: ProviderId;
  label: string;
  state: HealthState;
  detail: string;
  status: ProviderStatus;
}

const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  google: 'Google Gemini',
  groq: 'Groq',
};

export function providerLabel(id: ProviderId): string {
  return PROVIDER_LABELS[id] ?? id.charAt(0).toUpperCase() + id.slice(1);
}

export function providerState(status: ProviderStatus): { state: HealthState; detail: string } {
  if (status.disabled) return { state: 'offline', detail: 'Disabled by server configuration' };
  if (status.credential_configured) return { state: 'online', detail: 'Credential configured server-side' };
  return { state: 'unknown', detail: 'No server-side credential configured' };
}

export function summariseHealth(health: HealthResponse): {
  state: HealthState;
  configured: number;
  available: number;
  total: number;
} {
  const entries = Object.values(health.providers);
  const configured = entries.filter((p) => p.credential_configured).length;
  const available = entries.filter((p) => p.credential_configured && !p.disabled).length;
  const state: HealthState = health.status === 'ok' ? (available > 0 ? 'online' : 'degraded') : 'degraded';
  return { state, configured, available, total: entries.length };
}

export function toProviderHealth(health: HealthResponse): ProviderHealth[] {
  return Object.entries(health.providers).map(([id, status]) => {
    const { state, detail } = providerState(status);
    return { id, label: providerLabel(id), state, detail, status };
  });
}
