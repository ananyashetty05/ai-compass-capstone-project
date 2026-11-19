/**
 * Pure derivations for the dashboard. Everything here is computed from
 * data the API actually returned; nothing is estimated or invented.
 */
import type { ModelInfo } from '../../types';
import { humanizeToken } from '../../utils/format';

export const isInference = (m: ModelInfo) => m.entry_type === 'inference_model' || m.entry_type === 'model';

export interface ModelSummary {
  inference: ModelInfo[];
  nonInference: number;
  active: number;
  inactive: number;
  /** null when the backend does not report eligibility on any entry. */
  eligible: number | null;
  /** Models AI Compass can run right now (provider credential + adapter); independent of comparison eligibility. */
  executable: number;
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
    /** Models AI Compass can run right now (provider credential + adapter). Independent of comparison eligibility. */
    executable: inference.filter((m) => m.execution_available === true).length,
    stale: inference.filter((m) => m.catalog_stale).length,
    providers: [...byProvider.entries()].map(([provider, v]) => ({ provider, ...v })).sort((a, b) => b.total - a.total),
    capabilities: rank(caps),
    modalities: rank(mods),
  };
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
