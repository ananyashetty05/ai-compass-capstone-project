/**
 * Pure derivations for the dashboard. Everything here is computed from
 * data the API actually returned; nothing is estimated or invented.
 */
import type { HealthState, ModelInfo, RegistryStatus } from '../../types';
import type { ProviderHealth } from '../../services/health.service';
import { humanizeToken } from '../../utils/format';

export const isInference = (m: ModelInfo) => m.entry_type === 'inference_model' || m.entry_type === 'model';

export interface ModelSummary {
  inference: ModelInfo[];
  nonInference: number;
  active: number;
  inactive: number;
  /** null when the backend does not report eligibility on any entry. */
  eligible: number | null;
  stale: number;
  providers: { provider: string; total: number; active: number }[];
  capabilities: { name: string; count: number }[];
  modalities: { name: string; count: number }[];
}

export function summariseModels(models: ModelInfo[]): ModelSummary {
  const inference = models.filter(isInference);
  const byProvider = new Map<string, { total: number; active: number }>();
  const caps = new Map<string, number>();
  const mods = new Map<string, number>();
  for (const m of inference) {
    const p = byProvider.get(m.provider) ?? { total: 0, active: 0 };
    p.total += 1;
    if (m.active) p.active += 1;
    byProvider.set(m.provider, p);
    for (const c of m.capabilities) caps.set(c, (caps.get(c) ?? 0) + 1);
    const modalities = m.modalities && m.modalities.length > 0 ? m.modalities : m.modality ? [m.modality] : [];
    for (const x of modalities) mods.set(x, (mods.get(x) ?? 0) + 1);
  }
  const reported = inference.filter((m) => typeof m.routing_eligible === 'boolean');
  const rank = (map: Map<string, number>) =>
    [...map.entries()].map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
  return {
    inference,
    nonInference: models.length - inference.length,
    active: inference.filter((m) => m.active).length,
    inactive: inference.filter((m) => !m.active).length,
    eligible: reported.length > 0 ? reported.filter((m) => m.routing_eligible).length : null,
    stale: inference.filter((m) => m.catalog_stale).length,
    providers: [...byProvider.entries()].map(([provider, v]) => ({ provider, ...v })).sort((a, b) => b.total - a.total),
    capabilities: rank(caps),
    modalities: rank(mods),
  };
}

export interface AttentionItem {
  id: string;
  tone: 'warning' | 'danger' | 'info';
  title: string;
  detail: string;
  to?: string;
  action?: string;
}

export function deriveAttention(input: {
  health: HealthState;
  providers: ProviderHealth[];
  summary: ModelSummary | null;
  registry: RegistryStatus | null;
}): AttentionItem[] {
  const items: AttentionItem[] = [];
  const { health, providers, summary, registry } = input;

  if (health === 'offline') {
    items.push({ id: 'offline', tone: 'danger', title: 'Routing service unreachable', detail: 'The backend health check failed, so routing and registry data may be out of date.' });
  } else if (health === 'degraded') {
    const routable = summary?.eligible ?? 0;
    items.push({
      id: 'degraded', tone: 'warning', title: 'Routing service partially available',
      detail: routable > 0
        ? `None of the providers in the health check has a server credential, but ${routable} registry model${routable === 1 ? ' is' : 's are'} still routing-eligible.`
        : 'The service responded, but no provider is currently configured and enabled.',
    });
  }

  const missing = providers.filter((p) => p.state === 'unknown');
  if (missing.length > 0) {
    items.push({
      id: 'credentials',
      tone: 'info',
      title: `${missing.length} provider${missing.length === 1 ? '' : 's'} without a server credential`,
      detail: `${missing.map((p) => p.label).join(', ')} cannot be used for generation until a credential is configured on the server.`,
    });
  }
  const disabled = providers.filter((p) => p.state === 'offline');
  if (disabled.length > 0) {
    items.push({ id: 'disabled', tone: 'warning', title: `${disabled.map((p) => p.label).join(', ')} disabled`, detail: 'Disabled by server configuration; its models are not routable.' });
  }

  if (registry) {
    if (!registry.persistence_available) {
      items.push({ id: 'persistence', tone: 'info', title: 'Static catalog in use', detail: 'Registry persistence is unavailable, so live model discovery is not being stored.', to: '/models', action: 'Open model pool' });
    } else if (registry.live_registry_enabled === false) {
      items.push({ id: 'live-off', tone: 'info', title: 'Live registry is switched off', detail: 'Models come from the built-in catalog until live discovery is enabled.', to: '/models', action: 'Open model pool' });
    }
    const failed = registry.providers.filter((p) => p.last_attempt_status === 'failed' || p.status === 'failed');
    if (failed.length > 0) {
      items.push({ id: 'refresh-failed', tone: 'warning', title: `Last refresh failed for ${failed.map((p) => p.display_name ?? humanizeToken(p.provider)).join(', ')}`, detail: 'The previous catalog data remains in use. Open the model pool for the error detail.', to: '/models', action: 'Review' });
    }
  }

  if (summary) {
    if (summary.stale > 0) {
      items.push({ id: 'stale', tone: 'warning', title: `${summary.stale} model${summary.stale === 1 ? '' : 's'} with stale catalog data`, detail: 'Their catalog data has not been confirmed by a live provider refresh.', to: '/models', action: 'Review models' });
    }
    if (summary.inference.length > 0 && summary.active === 0) {
      items.push({ id: 'none-active', tone: 'danger', title: 'No active inference models', detail: 'Routing has nothing to choose from until a model is active.', to: '/models', action: 'Open model pool' });
    }
  }
  return items;
}

/** "3 min ago" style label; falls back to the raw date for older values. */
export function timeAgo(value: string | null | undefined, now = Date.now()): string | null {
  if (!value) return null;
  const t = new Date(value).getTime();
  if (Number.isNaN(t)) return null;
  const s = Math.max(0, Math.round((now - t) / 1000));
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 86400 * 14) return `${Math.floor(s / 86400)} d ago`;
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(t));
}

/** Most common reason models are not routing-eligible, from the registry's own eligibility data. */
export function topBlockReason(models: ModelInfo[]): { label: string; count: number } | null {
  const counts = new Map<string, number>();
  for (const m of models) {
    if (m.eligibility && !m.eligibility.eligible) {
      const code = m.eligibility.reasons[0]?.code;
      if (code) counts.set(code, (counts.get(code) ?? 0) + 1);
    }
  }
  const top = [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
  if (!top) return null;
  const label = top[0] === 'provider_not_configured' ? 'provider has no credential' : humanizeToken(top[0]).toLowerCase();
  return { label, count: top[1] };
}
