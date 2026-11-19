import { useId, useMemo, useState } from 'react';
import { AlertTriangle, ChevronDown, Search, Shield, ShieldCheck, SlidersHorizontal, X } from 'lucide-react';
import { providerName } from '../dashboard/DistributionCards';
import type { ModelInfo } from '../../types';

export type PrivacyLevel = 'standard' | 'strict';

export const CAPABILITY_OPTIONS = ['coding', 'reasoning', 'math', 'research', 'image-generation'] as const;

interface Props {
  models: ModelInfo[];
  loading: boolean;
  error: string | null;
  disabled?: boolean;
  maxCost: string; onMaxCost: (v: string) => void;
  maxLatency: string; onMaxLatency: (v: string) => void;
  capabilities: string[]; onCapabilities: (v: string[]) => void;
  privacy: PrivacyLevel; onPrivacy: (v: PrivacyLevel) => void;
  excludedProviders: string[]; onExcludedProviders: (v: string[]) => void;
  selectedModelIds: string[]; onSelectedModelIds: (v: string[]) => void;
}

const toggle = <T,>(list: T[], item: T): T[] => (list.includes(item) ? list.filter((x) => x !== item) : [...list, item]);

/**
 * Hard constraints are pass/fail rules the routing engine applies before
 * scoring (backend `routing_engine/filtering.py`). Everything shown here is
 * sent to the backend as-is; nothing is simulated. The candidate count only
 * reflects the two rules the browser can evaluate exactly: provider
 * exclusion and the chosen model pool.
 *
 * Collapsed by default (they are optional); active constraints stay visible
 * as removable chips even when the panel is closed.
 */
export function ConstraintsPanel(p: Props) {
  const uid = useId();
  const [filter, setFilter] = useState('');
  const providers = useMemo(() => {
    const counts = new Map<string, number>();
    p.models.forEach((m) => counts.set(m.provider, (counts.get(m.provider) ?? 0) + 1));
    return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  }, [p.models]);

  const shown = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return q ? p.models.filter((m) => `${m.model_name} ${m.provider}`.toLowerCase().includes(q)) : p.models;
  }, [p.models, filter]);

  const excludedLower = p.excludedProviders.map((x) => x.toLowerCase());
  const candidates = p.models.filter(
    (m) => !excludedLower.includes(m.provider.toLowerCase()) && (p.selectedModelIds.length === 0 || p.selectedModelIds.includes(m.model_id)),
  ).length;

  const documented = p.models.filter((m) => m.data_handling_status === 'provider_documented_restricted' || m.data_handling_status === 'customer_controlled').length;
  const hasHandlingData = p.models.some((m) => m.data_handling_status !== undefined);

  const active: { key: string; label: string; clear: () => void }[] = [];
  if (p.maxCost.trim()) active.push({ key: 'cost', label: `Cost ≤ $${p.maxCost}`, clear: () => p.onMaxCost('') });
  if (p.maxLatency.trim()) active.push({ key: 'lat', label: `Latency ≤ ${p.maxLatency}s`, clear: () => p.onMaxLatency('') });
  p.capabilities.forEach((c) => active.push({ key: `cap-${c}`, label: `Needs ${c.replace('-', ' ')}`, clear: () => p.onCapabilities(p.capabilities.filter((x) => x !== c)) }));
  if (p.privacy === 'strict') active.push({ key: 'privacy', label: 'Strict privacy', clear: () => p.onPrivacy('standard') });
  p.excludedProviders.forEach((x) => active.push({ key: `ex-${x}`, label: `Excluding ${providerName(x)}`, clear: () => p.onExcludedProviders(p.excludedProviders.filter((y) => y !== x)) }));
  if (p.selectedModelIds.length) active.push({ key: 'pool', label: `Pool: ${p.selectedModelIds.length} model${p.selectedModelIds.length === 1 ? '' : 's'}`, clear: () => p.onSelectedModelIds([]) });

  const [open, setOpen] = useState(active.length > 0);

  const clearAll = () => {
    p.onMaxCost(''); p.onMaxLatency(''); p.onCapabilities([]); p.onPrivacy('standard'); p.onExcludedProviders([]); p.onSelectedModelIds([]);
  };

  const bodyId = `${uid}-body`;

  return (
    <section className="cp" data-open={open || undefined} aria-labelledby={`${uid}-title`}>
      <button type="button" className="cp-head" aria-expanded={open} aria-controls={bodyId} onClick={() => setOpen((o) => !o)}>
        <span className="cp-head-icon" aria-hidden="true"><SlidersHorizontal /></span>
        <span className="cp-head-text">
          <strong id={`${uid}-title`}>Hard constraints</strong>
          <small>Pass/fail limits applied before scoring. A model that breaks one can never be chosen.</small>
        </span>
        {active.length > 0 ? <span className="cp-head-badge">{active.length} active</span> : <span className="cp-head-tag">Optional</span>}
        <ChevronDown className="cp-head-chev" aria-hidden="true" />
      </button>

      {active.length > 0 ? (
        <div className="cp-active" aria-live="polite">
          <ul className="cp-chips">
            {active.map((a) => (
              <li key={a.key}>
                <button type="button" className="cp-chip" onClick={a.clear} disabled={p.disabled} aria-label={`Remove constraint: ${a.label}`}>
                  {a.label}<X aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
          <button type="button" className="cp-link" onClick={clearAll} disabled={p.disabled}>Clear all</button>
        </div>
      ) : null}

      <div id={bodyId} className="cp-body" inert={!open || undefined}>
        <fieldset className="cp-fieldset" disabled={p.disabled}>
          <legend className="sr-only">Hard constraints</legend>
          <div className="cp-row">
            <section className="cp-card" aria-labelledby={`${uid}-budget`}>
              <h4 id={`${uid}-budget`}>Cost and speed</h4>
              <p>Removes models over the limit, or whose cost or latency the registry can’t verify.</p>
              <label className="cp-field">
                <span>Max cost per request</span>
                <span className="cp-input"><em>$</em><input type="number" min="0" step="0.001" inputMode="decimal" placeholder="No limit" value={p.maxCost} onChange={(e) => p.onMaxCost(e.target.value)} /></span>
              </label>
              <label className="cp-field">
                <span>Max latency</span>
                <span className="cp-input"><input type="number" min="0" step="0.5" inputMode="decimal" placeholder="No limit" value={p.maxLatency} onChange={(e) => p.onMaxLatency(e.target.value)} /><em>sec</em></span>
              </label>
            </section>

            <section className="cp-card" aria-labelledby={`${uid}-caps`}>
              <h4 id={`${uid}-caps`}>Required capabilities</h4>
              <p>Removes models missing any selected capability. The query’s detected needs are always added.</p>
              <div className="cp-toggles" role="group" aria-labelledby={`${uid}-caps`}>
                {CAPABILITY_OPTIONS.map((c) => (
                  <button key={c} type="button" className="cp-pill" aria-pressed={p.capabilities.includes(c)} onClick={() => p.onCapabilities(toggle(p.capabilities, c))}>
                    {c.replace('-', ' ')}
                  </button>
                ))}
              </div>
            </section>

            <section className="cp-card" aria-labelledby={`${uid}-privacy`}>
              <h4 id={`${uid}-privacy`}>Privacy</h4>
              <p>Choose whether a model must document how it handles your data.</p>
              <div className="cp-options" role="radiogroup" aria-labelledby={`${uid}-privacy`}>
                <label className="cp-option">
                  <input type="radio" name={`${uid}-privacy-level`} checked={p.privacy === 'standard'} onChange={() => p.onPrivacy('standard')} />
                  <span className="cp-option-icon" aria-hidden="true"><Shield /></span>
                  <span className="cp-option-text"><strong>Standard</strong><small>No privacy filter</small></span>
                </label>
                <label className="cp-option">
                  <input type="radio" name={`${uid}-privacy-level`} checked={p.privacy === 'strict'} onChange={() => p.onPrivacy('strict')} />
                  <span className="cp-option-icon" aria-hidden="true"><ShieldCheck /></span>
                  <span className="cp-option-text"><strong>Strict</strong><small>Documented data handling only</small></span>
                </label>
              </div>
              {hasHandlingData ? (
                documented === 0 ? (
                  <p className="cp-warn"><AlertTriangle aria-hidden="true" />None of the {p.models.length} registry models document data handling, so Strict would exclude all of them.</p>
                ) : (
                  <p className="cp-note">{documented} of {p.models.length} registry models document data handling.</p>
                )
              ) : null}
            </section>
          </div>

          <section className="cp-card" aria-labelledby={`${uid}-providers`}>
            <div className="cp-card-head">
              <div>
                <h4 id={`${uid}-providers`}>Exclude providers</h4>
                <p>Models from a selected provider are removed. Numbers are registry models per provider.</p>
              </div>
            </div>
            {p.loading ? <p className="cp-note">Loading the model registry…</p> : p.error ? <p className="cp-error">{p.error}</p> : (
              <div className="cp-toggles" role="group" aria-labelledby={`${uid}-providers`}>
                {providers.map(([name, n]) => (
                  <button key={name} type="button" className="cp-pill" aria-pressed={p.excludedProviders.includes(name)} onClick={() => p.onExcludedProviders(toggle(p.excludedProviders, name))}>
                    {providerName(name)} <small>{n}</small>
                  </button>
                ))}
              </div>
            )}
          </section>

          <section className="cp-card" aria-labelledby={`${uid}-pool`}>
            <div className="cp-card-head">
              <div>
                <h4 id={`${uid}-pool`}>Model pool</h4>
                <p>Optional. Pick specific API models to compare; everything outside the pool is excluded.</p>
              </div>
              <div className="cp-pool-meta">
                <span className="cp-count"><strong>{candidates}</strong> of {p.models.length} candidates</span>
                {p.selectedModelIds.length > 0 ? <button type="button" className="cp-link" onClick={() => p.onSelectedModelIds([])}>Clear selection</button> : null}
              </div>
            </div>
            <label className="cp-search"><Search aria-hidden="true" />
              <input type="search" placeholder="Filter models by name or provider" aria-label="Filter models" value={filter} onChange={(e) => setFilter(e.target.value)} />
            </label>
            {p.loading ? <p className="cp-note">Loading the model registry…</p> : p.error ? <p className="cp-error">{p.error}</p> : shown.length === 0 ? (
              <p className="cp-note">{p.models.length === 0 ? 'No API inference models are available in the registry.' : 'No models match that filter.'}</p>
            ) : (
              <div className="cp-pool-list">
                {shown.map((m) => (
                  <label key={m.model_id} className="cp-pool-item" data-checked={p.selectedModelIds.includes(m.model_id) || undefined}>
                    <input type="checkbox" checked={p.selectedModelIds.includes(m.model_id)} onChange={() => p.onSelectedModelIds(toggle(p.selectedModelIds, m.model_id))} />
                    <span><strong>{m.model_name}</strong><small>{providerName(m.provider)}</small></span>
                  </label>
                ))}
              </div>
            )}
          </section>

          <p className="cp-always">
            Always applied: the model must be active and routable, support the query’s modalities and detected capabilities, and have a large enough context window. After routing, every excluded model is listed with its reason.
          </p>
        </fieldset>
      </div>
    </section>
  );
}
