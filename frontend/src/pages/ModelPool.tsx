/**
 * Model pool.
 *
 * A read-only view of `GET /models`: whatever the registry returns is
 * what is shown, including inactive models. Cost, latency and quality
 * figures are registry metadata from the configured `source`, so every
 * table carries a provenance label rather than implying a benchmark.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { LiveCatalogBrowser, LiveRegistryPanel } from '../components/registry/LiveRegistry';
import { EcosystemPanel } from '../components/registry/Ecosystem';
import { KIND_LABEL, ModelCard, PRICING_LABEL, ACCESS_LABEL, cardKey } from '../components/registry/ModelCard';
import { Boxes, Check, Filter, GitCompareArrows, LayoutGrid, List, Search, SlidersHorizontal } from 'lucide-react';
import { PageHeader } from '../components/layout/PageHeader';
import { CapabilityOverview, ProviderDistribution } from '../components/dashboard/DistributionCards';
import { KpiIcons, KpiRow } from '../components/dashboard/KpiRow';
import { summariseModels } from '../components/dashboard/insights';
import { Button } from '../components/ui/Button';
import { Status } from '../components/ui/Badge';
import { DataTable } from '../components/ui/DataTable';
import type { ColumnDef } from '../components/ui/DataTable';
import { Modal } from '../components/ui/Modal';
import { TextInput } from '../components/ui/Input';
import { EmptyState, ErrorState } from '../components/ui/EmptyState';
import { Segmented, SkeletonMetrics, SkeletonTable } from '../components/ui/Skeleton';
import { useAsync } from '../hooks/useAsync';
import { EcosystemMap } from '../components/registry/EcosystemMap';
import { ApprovedEcosystem, type EcoFilter } from '../components/registry/ApprovedEcosystem';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { getPoolStats, getRegistryStatus, listModels } from '../services/models.service';
import {
  formatModelCostPerThousand,
  hasPublishedPrice,
  formatInteger,
  formatNumber,
  formatPercent,
  formatSeconds,
  humanizeToken,
} from '../utils/format';
import { UNAVAILABLE } from '../types';
import type { ModelGroup, ModelInfo, PoolStats, PricingCategory } from '../types';

type StatusFilter = 'all' | 'active' | 'inactive';
type RegistryView = 'cards' | 'table';
type UseCategory = 'all' | ModelGroup;
type PricingFilter = 'all' | PricingCategory;
type AccessFilter = 'all' | 'consumer_chat' | 'provider_api' | 'hosted_inference' | 'aggregator_api' | 'self_hosted';
type ContextFilter = 'all' | '32000' | '128000' | '1000000';
type FreeFilter = 'all' | 'free_any' | 'free_download' | 'paid';
type WeightsFilter = 'all' | 'open_weights' | 'proprietary';
const MAX_COMPARE = 3;

type SortKey = 'default' | 'name' | 'provider' | 'quality' | 'cost' | 'latency';
const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: 'default', label: 'Registry order' },
  { value: 'name', label: 'Name (A–Z)' },
  { value: 'provider', label: 'Provider (A–Z)' },
  { value: 'quality', label: 'Quality estimate (high first)' },
  { value: 'cost', label: 'Cost (low first)' },
  { value: 'latency', label: 'Latency estimate (low first)' },
];

const GROUP_LABEL: Record<ModelGroup, string> = {
  conversational: 'Conversational AI Models',
  developer_api: 'Developer & API Models',
  unclassified: 'Unclassified',
};
const GROUP_DETAIL: Record<ModelGroup, string> = {
  conversational: 'AI assistants and chat models you talk to directly: questions, research, writing, coding help and analysis.',
  developer_api: 'Models and API providers for integrating AI into your own applications, projects and workflows.',
  unclassified: 'Provider role or model type not verified yet; shown, never guessed.',
};
const PRICING_OPTIONS: Array<{ value: PricingFilter; label: string }> = [
  { value: 'all', label: 'Any pricing' },
  { value: 'completely_free', label: 'Free' },
  { value: 'free_tier_limited', label: 'Free tier with limits' },
  { value: 'pay_as_you_go', label: 'Pay-as-you-go' },
  { value: 'self_hosted_open_weight', label: 'Self-hosted (open weights)' },
  { value: 'unknown', label: 'Pricing not verified' },
];
const ACCESS_OPTIONS: Array<{ value: AccessFilter; label: string }> = [
  { value: 'all', label: 'Any access route' },
  { value: 'consumer_chat', label: 'Consumer chat' },
  { value: 'provider_api', label: 'Provider API' },
  { value: 'hosted_inference', label: 'Hosted inference' },
  { value: 'aggregator_api', label: 'Aggregator API' },
  { value: 'self_hosted', label: 'Self-hosted' },
];
const PAGE_SIZE = 48;
function isFreeAny(m: ModelInfo): boolean { return m.free_download === true || m.free_access === 'free' || m.free_access === 'limited_free'; }

const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  google: 'Google',
  mistral: 'Mistral',
  meta: 'Meta',
  cohere: 'Cohere',
  together: 'Together AI',
};

const SOURCE_LABELS: Record<string, string> = {
  provider_config: 'Provider configuration',
  static_catalog: 'Bundled provider-documentation snapshot',
  application_catalog: 'Bundled application catalog snapshot',
  live_discovered: 'Live provider catalog discovery',
  catalog: 'Autonomous catalogue',
  routerbench: 'RouterBench import',
  measured: 'Measured in this environment',
};

function providerLabel(provider: string): string {
  const known = PROVIDER_LABELS[provider.toLowerCase()];
  if (known) return known;
  // A catalogue display name ("DeepSeek", "xAI", "Perplexity AI") must not be re-cased; only machine ids ("together_ai") are humanised.
  return /[\sA-Z]/.test(provider) ? provider : humanizeToken(provider);
}

function entryTypeLabel(type: string): string {
  if (type === 'inference_model' || type === 'model') return 'API model';
  if (type === 'application_integration') return 'AI application';
  if (type === 'specialized_ai_tool') return 'Specialized tool';
  return humanizeToken(type);
}

function availabilityLabel(value: string): string {
  if (value === 'api_configured') return 'API configured';
  return humanizeToken(value);
}

export function ModelPool() {
  const navigate = useNavigate();
  const setSelected = useCallback((m: ModelInfo) => navigate(`/models/inspect?provider=${encodeURIComponent(m.provider)}&model=${encodeURIComponent(m.model_id)}`), [navigate]);
  useDocumentTitle('Model registry · AI Compass');
  const models = useAsync((signal) => listModels(signal));
  const poolStats = useAsync((signal) => getPoolStats(signal));
  const registryStatus = useAsync((signal) => getRegistryStatus(signal));
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<StatusFilter>('all');
  const [provider, setProvider] = useState<string>('all');
  const [availability, setAvailability] = useState<string>('all');
  const [lifecycle, setLifecycle] = useState<string>('all');
  const [useCat, setUseCat] = useState<UseCategory>('all');
  const [ecoCat, setEcoCat] = useState<EcoFilter>('all');
  const [pricingFilter, setPricingFilter] = useState<PricingFilter>('all');
  const [accessFilter, setAccessFilter] = useState<AccessFilter>('all');
  const [contextFilter, setContextFilter] = useState<ContextFilter>('all');
  const [kind, setKind] = useState('all');
  const [freeFilter, setFreeFilter] = useState<FreeFilter>('all');
  const [weightsFilter, setWeightsFilter] = useState<WeightsFilter>('all');
  const [capability, setCapability] = useState('all');
  const [view, setView] = useState<RegistryView>('cards');
  const [sortKey, setSortKey] = useState<SortKey>('default');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [compareOpen, setCompareOpen] = useState(false);
  const [adminToken, setAdminToken] = useState('');
  const [catalogRefresh, setCatalogRefresh] = useState(0);

  const providers = useMemo(() => {
    const ids = new Set((models.data ?? []).map((model) => model.provider));
    return Array.from(ids).sort((a, b) => providerLabel(a).localeCompare(providerLabel(b)));
  }, [models.data]);

  const capabilities = useMemo(() => {
    const values = new Set((models.data ?? []).flatMap((model) => model.capability_tags ?? []));
    return Array.from(values).sort((a, b) => humanizeToken(a).localeCompare(humanizeToken(b)));
  }, [models.data]);

  const availabilityOptions = useMemo(() => {
    const values = new Set((models.data ?? []).map((model) => model.availability).filter((value): value is string => Boolean(value)));
    return Array.from(values).sort((a, b) => humanizeToken(a).localeCompare(humanizeToken(b)));
  }, [models.data]);

  const lifecycleOptions = useMemo(() => {
    const values = new Set((models.data ?? []).map((model) => model.lifecycle_status).filter((value): value is string => Boolean(value)));
    return Array.from(values).sort((a, b) => humanizeToken(a).localeCompare(humanizeToken(b)));
  }, [models.data]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const rows = (models.data ?? []).filter((model) => {
      if (ecoCat !== 'all' && model.ecosystem_category !== ecoCat && !(model.secondary_categories ?? []).includes(ecoCat)) return false;
      if (useCat !== 'all' && (model.model_category ?? 'unclassified') !== useCat) return false;
      if (pricingFilter !== 'all' && (model.pricing_category ?? 'unknown') !== pricingFilter) return false;
      if (accessFilter !== 'all' && (model.access_type ?? 'unknown') !== accessFilter) return false;
      if (contextFilter !== 'all' && (model.context_window ?? 0) < Number(contextFilter)) return false;
      if (kind !== 'all' && (model.category_kind ?? 'unclassified') !== kind) return false;
      if (freeFilter === 'free_any' && !isFreeAny(model)) return false;
      if (freeFilter === 'free_download' && model.free_download !== true) return false;
      if (freeFilter === 'paid' && model.free_access !== 'paid') return false;
      if (weightsFilter !== 'all' && (model.weights_status ?? 'unknown') !== weightsFilter) return false;
      if (status === 'active' && !model.active) return false;
      if (status === 'inactive' && model.active) return false;
      if (provider !== 'all' && model.provider !== provider) return false;
      if (availability !== 'all' && model.availability !== availability) return false;
      if (lifecycle !== 'all' && model.lifecycle_status !== lifecycle) return false;
      if (capability !== 'all' && !(model.capability_tags ?? []).includes(capability)) return false;
      if (needle.length === 0) return true;
      return (
        model.model_id.toLowerCase().includes(needle) ||
        model.model_name.toLowerCase().includes(needle) ||
        model.provider.toLowerCase().includes(needle) ||
        (model.developer ?? '').toLowerCase().includes(needle) ||
        (model.model_family ?? '').toLowerCase().includes(needle) ||
        (model.category_kind ?? '').toLowerCase().includes(needle) ||
        model.capabilities.some((value) => value.toLowerCase().includes(needle)) ||
        (model.capability_tags ?? []).some((value) => value.toLowerCase().includes(needle))
      );
    });
    // Missing numbers sort last so unknown values never look "best".
    const num = (v: number | null | undefined, missing: number) => (typeof v === 'number' && Number.isFinite(v) ? v : missing);
    const by: Record<SortKey, ((a: ModelInfo, b: ModelInfo) => number) | null> = {
      default: null,
      name: (a, b) => a.model_name.localeCompare(b.model_name),
      provider: (a, b) => providerLabel(a.provider).localeCompare(providerLabel(b.provider)) || a.model_name.localeCompare(b.model_name),
      quality: (a, b) => num(b.estimated_quality, -1) - num(a.estimated_quality, -1),
      cost: (a, b) => {
        const ca = num(hasPublishedPrice(a) ? a.cost_per_1k_tokens : null, Infinity);
        const cb = num(hasPublishedPrice(b) ? b.cost_per_1k_tokens : null, Infinity);
        return ca === cb ? 0 : ca - cb;
      },
      latency: (a, b) => {
        const la = num(a.avg_latency_seconds, Infinity);
        const lb = num(b.avg_latency_seconds, Infinity);
        return la === lb ? 0 : la - lb;
      },
    };
    const compare = by[sortKey];
    return compare ? rows.slice().sort(compare) : rows;
  }, [accessFilter, availability, capability, contextFilter, freeFilter, kind, lifecycle, models.data, pricingFilter, provider, query, status, sortKey, useCat, ecoCat, weightsFilter]);

  // Page size resets whenever the result set changes; the visible slice never hides records (the count always shows the full total).
  useEffect(() => { setLimit(PAGE_SIZE); }, [filtered]);
  const visible = useMemo(() => filtered.slice(0, limit), [filtered, limit]);

  const total = (models.data ?? []).length;
  // Headline numbers come from the server (`/models/pool-stats`); this is only a fallback if that call fails, computed with the same rules.
  const stats: PoolStats | null = poolStats.data ?? null;
  const fallbackCounts = useMemo(() => {
    const out: Record<ModelGroup, number> = { conversational: 0, developer_api: 0, unclassified: 0 };
    for (const model of models.data ?? []) out[model.model_category ?? 'unclassified'] += 1;
    return out;
  }, [models.data]);
  const groups = stats?.categories?.counts ?? fallbackCounts;
  const approvedMode = !!stats?.ecosystem || (models.data ?? []).some((m) => !!m.ecosystem_category);
  const ecoLabels = useMemo(() => Object.fromEntries((stats?.ecosystem?.categories ?? []).map((c) => [c.id, c.label])), [stats]);
  const ecoMapModels = useMemo(() => (models.data ?? []).map((m) => ({ ...m, provider: m.ecosystem_category ?? m.provider })), [models.data]);
  const mismatch = stats !== null && stats.pool_total !== total;
  const kindOptions = useMemo(() => {
    if (useCat === 'all') return [];
    const counts = new Map<string, number>();
    for (const model of models.data ?? []) if ((model.model_category ?? 'unclassified') === useCat) counts.set(model.category_kind ?? 'unclassified', (counts.get(model.category_kind ?? 'unclassified') ?? 0) + 1);
    return Array.from(counts, ([k, count]) => ({ kind: k, label: KIND_LABEL[k] ?? humanizeToken(k), count })).sort((a, b) => b.count - a.count);
  }, [models.data, useCat]);

  const advancedActive = [status !== 'all', availability !== 'all', lifecycle !== 'all', capability !== 'all', freeFilter !== 'all', weightsFilter !== 'all', pricingFilter !== 'all', accessFilter !== 'all', contextFilter !== 'all'].filter(Boolean).length;
  const filtersActive = ecoCat !== 'all' || query.trim().length > 0 || provider !== 'all' || useCat !== 'all' || kind !== 'all' || advancedActive > 0;

  const clearFilters = useCallback(() => {
    setQuery(''); setStatus('all'); setProvider('all'); setAvailability('all'); setLifecycle('all'); setUseCat('all'); setEcoCat('all'); setKind('all');
    setFreeFilter('all'); setWeightsFilter('all'); setCapability('all'); setPricingFilter('all'); setAccessFilter('all'); setContextFilter('all');
  }, []);

  const toggleCompare = useCallback((model: ModelInfo) => {
    const key = cardKey(model);
    setCompareIds((current) => {
      if (current.includes(key)) return current.filter((id) => id !== key);
      if (current.length >= MAX_COMPARE) return current;
      return [...current, key];
    });
  }, []);

  const columns: ColumnDef<ModelInfo>[] = useMemo(
    () => [
      {
        id: 'model',
        header: 'Model',
        cell: (row) => (
          <div>
            <span className="cell-primary">{row.model_name}</span>
            <p className="cell-sub">{row.model_id}</p>
          </div>
        ),
        sortValue: (row) => row.model_name,
      },
      {
        id: 'provider',
        header: 'Provider',
        cell: (row) => providerLabel(row.provider),
        sortValue: (row) => providerLabel(row.provider),
        secondary: true,
      },
      {
        id: 'group',
        header: 'Group · access',
        cell: (row) => (
          <div>
            <span className="cell-primary">{GROUP_LABEL[row.model_category ?? 'unclassified']}</span>
            <p className="cell-sub">{ACCESS_LABEL[row.access_type ?? 'unknown']}</p>
          </div>
        ),
        sortValue: (row) => row.model_category ?? 'unclassified',
      },
      {
        id: 'pricing',
        header: 'Pricing (verified)',
        cell: (row) => <span title={row.free_access_note ?? undefined}>{PRICING_LABEL[row.pricing_category ?? 'unknown']}</span>,
        sortValue: (row) => row.pricing_category ?? 'unknown',
        secondary: true,
      },
      {
        id: 'status',
        header: 'Status',
        cell: (row) => (
          <Status name={row.active ? 'active' : 'inactive'}>{row.entry_type === 'inference_model' ? 'Recommendation-ready' : row.entry_type === 'specialized_ai_tool' ? 'Specialized tool' : 'Application'}</Status>
        ),
        sortValue: (row) => (row.active ? 0 : 1),
      },
      {
        id: 'quality',
        header: 'Quality estimate',
        numeric: true,
        cell: (row) => <span className="text-numeric">{formatPercent(row.estimated_quality, 0)}</span>,
        sortValue: (row) => row.estimated_quality,
      },
      {
        id: 'cost',
        header: 'Cost / 1K',
        numeric: true,
        cell: (row) => <span className="text-numeric">{formatModelCostPerThousand(row)}</span>,
        sortValue: (row) => (hasPublishedPrice(row) ? row.cost_per_1k_tokens : null),
      },
      {
        id: 'latency',
        header: 'Latency estimate',
        numeric: true,
        cell: (row) => <span className="text-numeric">{formatSeconds(row.avg_latency_seconds)}</span>,
        sortValue: (row) => row.avg_latency_seconds,
        secondary: true,
      },
      {
        id: 'reliability',
        header: 'Reliability metadata',
        numeric: true,
        cell: (row) => <span className="text-numeric">{formatPercent(row.reliability, 0)}</span>,
        sortValue: (row) => row.reliability,
        secondary: true,
      },
      {
        id: 'context',
        header: 'Context',
        numeric: true,
        cell: (row) => <span className="text-numeric">{formatInteger(row.context_window)}</span>,
        sortValue: (row) => row.context_window,
        secondary: true,
      },
      {
        id: 'fallback',
        header: 'Fallback',
        numeric: true,
        cell: (row) => <span className="text-numeric">#{formatNumber(row.fallback_priority, 0)}</span>,
        sortValue: (row) => row.fallback_priority,
        secondary: true,
      },
      {
        id: 'details',
        header: 'Details',
        cell: (row) => (
          <div className="registry-row-actions">
            <Button size="sm" variant="ghost" onClick={() => setSelected(row)}>
              Inspect
              <span className="sr-only"> {row.model_name}</span>
            </Button>
            <Button
              size="sm"
              variant={compareIds.includes(cardKey(row)) ? 'subtle' : 'secondary'}
              disabled={!compareIds.includes(cardKey(row)) && compareIds.length >= MAX_COMPARE}
              onClick={() => toggleCompare(row)}
            >
              {compareIds.includes(cardKey(row)) ? <Check aria-hidden="true" /> : <GitCompareArrows aria-hidden="true" />}
              <span className="sr-only">{compareIds.includes(cardKey(row)) ? 'Remove from comparison' : 'Add to comparison'} </span>
            </Button>
          </div>
        ),
        sortValue: () => null,
      },
    ],
    [compareIds, toggleCompare],
  );

  const catalogueSummary = useMemo(() => (models.data ? summariseModels(models.data) : null), [models.data]);
  const compareModels = (models.data ?? []).filter((model) => compareIds.includes(cardKey(model)));
  const chooseCategory = (next: UseCategory) => { setUseCat(next); setKind('all'); };
  const categoryTabs: Array<{ key: UseCategory; label: string; detail: string; count: number }> = [
    { key: 'all', label: 'All entries', detail: 'Everything in the active pool, in both groups', count: stats?.pool_total ?? total },
    { key: 'conversational', label: GROUP_LABEL.conversational, detail: GROUP_DETAIL.conversational, count: groups.conversational },
    { key: 'developer_api', label: GROUP_LABEL.developer_api, detail: GROUP_DETAIL.developer_api, count: groups.developer_api },
    ...(groups.unclassified > 0 ? [{ key: 'unclassified' as UseCategory, label: GROUP_LABEL.unclassified, detail: GROUP_DETAIL.unclassified, count: groups.unclassified }] : []),
  ];

  return (
    <>
      <PageHeader
        eyebrow="Registry"
        title="Model registry"
        description={approvedMode ? 'The approved ecosystem AI Compass recommends from, grouped into seven categories. Recommendation only: every entry opens at its own site.' : 'Two recommendation groups: Conversational AI Models for assistants you talk to, and Developer & API Models for building with AI. Each entry is in exactly one group; capabilities overlap and are filtered separately.'}
        actions={(
          <div className="row row-wrap">
            {compareIds.length > 0 && (
              <Button variant="secondary" size="sm" leadingIcon={<GitCompareArrows />} disabled={compareIds.length < 2} onClick={() => setCompareOpen(true)}>
                Compare ({compareIds.length})
              </Button>
            )}
            <Button variant="secondary" size="sm" onClick={() => { models.reload(); poolStats.reload(); }} loading={models.isLoading}>Reload catalog</Button>
          </div>
        )}
      />

      {models.isInitialLoad ? (
        <div className="page-body">
          <SkeletonMetrics count={4} />
          <SkeletonTable rows={8} />
        </div>
      ) : models.error ? (
        <ErrorState title="The model registry could not be loaded" message={models.error.message} hint={models.error.hint} onRetry={models.reload} />
      ) : (
        <div className="page-body registry-page-body mp">
          {approvedMode && stats?.ecosystem ? <ApprovedEcosystem stats={stats} selected={ecoCat} onSelect={setEcoCat} /> : (
          <section className="mp-overview" aria-labelledby="mp-overview-title">
            <h2 id="mp-overview-title" className="sr-only">Catalogue overview</h2>
            <KpiRow
              kpis={[
                { id: 'canonical', label: 'Active canonical models', icon: KpiIcons.models, value: stats?.canonical_models ?? catalogueSummary?.inference.length ?? 0, detail: `One per model identity · plus ${formatInteger(stats?.applications ?? 0)} AI applications` },
                { id: 'offerings', label: 'Provider offerings', icon: KpiIcons.providers, value: stats?.provider_offerings.count ?? null, detail: stats ? `Access routes across ${stats.provider_offerings.providers} providers, not extra models` : 'Offering count unavailable' },
                { id: 'pending', label: 'Awaiting verification', icon: KpiIcons.registry, value: stats?.pending_verification ?? null, detail: 'Discovered but not yet published; excluded from the pool' },
                { id: 'retired', label: 'Retired generations', icon: KpiIcons.routing, value: stats?.retired ?? null, detail: 'Older generations kept as history; excluded from the pool' },
              ]}
            />
            {stats?.access ? (
              <section aria-labelledby="mp-access-title">
                <h3 id="mp-access-title" className="sr-only">Recommendation and execution access</h3>
                <KpiRow
                  kpis={[
                    { id: 'rec', label: 'Recommendation-eligible', icon: KpiIcons.routing, value: stats.access.recommendation_eligible, detail: `Of ${formatInteger(stats.access.catalog_models)} catalogue models · credentials never affect this` },
                    { id: 'exec', label: 'Execution-ready', icon: KpiIcons.providers, value: stats.access.execution_ready, detail: 'Adapter and server credential both present' },
                    { id: 'reconly', label: 'Recommendation only', icon: KpiIcons.models, value: stats.access.recommendation_only, detail: `${formatInteger(stats.access.provider_not_configured)} lack a provider credential · ${formatInteger(stats.access.adapter_unavailable)} have no adapter` },
                    { id: 'meta', label: 'Incomplete metadata', icon: KpiIcons.registry, value: stats.access.metadata_incomplete, detail: `${formatInteger(stats.access.metadata_stale)} more are stale; unknown values stay unknown` },
                  ]}
                />
                <p className="mp-math" role="note">AI Compass recommends from the whole catalogue. A provider credential only decides whether it can also run the model.</p>
              </section>
            ) : null}
            <div className="mp-cats" role="group" aria-label="Primary category">
              {categoryTabs.map((tab) => (
                <button type="button" className="mp-cat" key={tab.key} aria-pressed={useCat === tab.key} onClick={() => chooseCategory(tab.key)}>
                  <span className="mp-cat-count">{formatNumber(tab.count, 0)}</span>
                  <span className="mp-cat-label">{tab.label}</span>
                  <span className="mp-cat-detail">{tab.detail}</span>
                </button>
              ))}
            </div>
            <p className="mp-math" role="status">
              <span>Recommendation groups are exclusive:
                {' '}<strong>{formatNumber(groups.conversational, 0)}</strong> <span className="mp-sep">+</span> <strong>{formatNumber(groups.developer_api, 0)}</strong>
                {groups.unclassified > 0 ? <> <span className="mp-sep">+</span> <strong>{formatNumber(groups.unclassified, 0)}</strong></> : null}
                {' '}<span className="mp-sep">=</span> <strong>{formatNumber(stats?.pool_total ?? total, 0)}</strong></span>
              {stats ? (
                <span className="mp-audit" data-ok={stats.integrity.ok && !mismatch} title={stats.integrity.checks.map((c) => `${c.ok ? '✓' : '✗'} ${c.check.replace(/_/g, ' ')}`).join('\n')}>
                  {stats.integrity.ok && !mismatch ? 'Counts reconcile · integrity audit passed' : 'Count audit found a problem — see tooltip'}
                </span>
              ) : poolStats.isLoading ? <span className="mp-audit" data-ok="true">Loading server counts…</span> : <span className="mp-audit" data-ok="false">Server counts unavailable; showing counts from the loaded list</span>}
            </p>
            {kindOptions.length > 0 ? (
              <div className="mp-kinds" role="group" aria-label={`${GROUP_LABEL[useCat as ModelGroup]} types`}>
                <button type="button" className="mp-kind" aria-pressed={kind === 'all'} onClick={() => setKind('all')}>All types</button>
                {kindOptions.map((option) => (
                  <button type="button" className="mp-kind" key={option.kind} aria-pressed={kind === option.kind} onClick={() => setKind(option.kind)}>{option.label}<b>{formatNumber(option.count, 0)}</b></button>
                ))}
              </div>
            ) : null}
          </section>
          )}

          {!approvedMode && poolStats.isLoading ? null : approvedMode
            ? <EcosystemMap models={ecoMapModels} selected={ecoCat} onSelect={(id) => setEcoCat(id as EcoFilter)} labelOf={(id) => ecoLabels[id] ?? humanizeToken(id)} title="Categories feeding the router" unit="categories" />
            : <EcosystemMap models={models.data ?? []} selected={provider} onSelect={setProvider} labelOf={providerLabel} />}

          <div className="table-surface">
            <div className="mp-toolbar">
              <TextInput className="toolbar-search" label="Search" hideLabel type="search" placeholder="Search models, developers, capabilities" value={query} onChange={(event) => setQuery(event.target.value)} leadingIcon={<Search />} />
              <label className="mp-field">
                <span>Provider</span>
                <select className="registry-filter-select" aria-label="Filter by provider" value={provider} onChange={(event) => setProvider(event.target.value)}>
                  <option value="all">All providers</option>
                  {providers.map((id) => <option key={id} value={id}>{providerLabel(id)}</option>)}
                </select>
              </label>
              <label className="mp-field">
                <span>Sort by</span>
                <select className="registry-filter-select" aria-label="Sort models" value={sortKey} onChange={(event) => setSortKey(event.target.value as SortKey)}>
                  {SORT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </label>
              <Button variant="secondary" size="sm" leadingIcon={<SlidersHorizontal />} aria-expanded={showAdvanced} onClick={() => setShowAdvanced((v) => !v)}>
                Filters{advancedActive > 0 ? ` (${advancedActive})` : ''}
              </Button>
              <Segmented<RegistryView> size="sm" label="Registry display" value={view} onChange={setView}
                options={[{ value: 'cards', label: 'Cards', icon: <LayoutGrid /> }, { value: 'table', label: 'Table', icon: <List /> }]} />
            </div>

            {showAdvanced ? (
              <div className="mp-adv" role="group" aria-label="More filters">
                <label className="mp-field"><span>Capability (overlapping)</span>
                  <select className="registry-filter-select" aria-label="Filter by capability" value={capability} onChange={(event) => setCapability(event.target.value)}>
                    <option value="all">Any capability</option>
                    {capabilities.map((value) => <option key={value} value={value}>{humanizeToken(value)}{stats?.capabilities.counts[value] ? ` (${stats.capabilities.counts[value]})` : ''}</option>)}
                  </select></label>
                <label className="mp-field"><span>Weights</span>
                  <select className="registry-filter-select" aria-label="Filter by weights availability" value={weightsFilter} onChange={(event) => setWeightsFilter(event.target.value as WeightsFilter)}>
                    <option value="all">Any</option><option value="open_weights">Open weights</option><option value="proprietary">Proprietary</option>
                  </select></label>
                <label className="mp-field"><span>Cost to use</span>
                  <select className="registry-filter-select" aria-label="Filter by free access" value={freeFilter} onChange={(event) => setFreeFilter(event.target.value as FreeFilter)}>
                    <option value="all">Any</option><option value="free_any">Free download or free tier</option><option value="free_download">Free to download (weights)</option><option value="paid">Paid only</option>
                  </select></label>
                <label className="mp-field"><span>Pricing (verified)</span>
                  <select className="registry-filter-select" aria-label="Filter by pricing category" value={pricingFilter} onChange={(event) => setPricingFilter(event.target.value as PricingFilter)}>
                    {PRICING_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select></label>
                <label className="mp-field"><span>Access route</span>
                  <select className="registry-filter-select" aria-label="Filter by access route" value={accessFilter} onChange={(event) => setAccessFilter(event.target.value as AccessFilter)}>
                    {ACCESS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select></label>
                <label className="mp-field"><span>Context window</span>
                  <select className="registry-filter-select" aria-label="Filter by minimum context window" value={contextFilter} onChange={(event) => setContextFilter(event.target.value as ContextFilter)}>
                    <option value="all">Any</option><option value="32000">32K or more</option><option value="128000">128K or more</option><option value="1000000">1M or more</option>
                  </select></label>
                <label className="mp-field"><span>Availability</span>
                  <select className="registry-filter-select" aria-label="Filter by availability" value={availability} onChange={(event) => setAvailability(event.target.value)}>
                    <option value="all">All availability</option>
                    {availabilityOptions.map((value) => <option key={value} value={value}>{availabilityLabel(value)}</option>)}
                  </select></label>
                <label className="mp-field"><span>Lifecycle</span>
                  <select className="registry-filter-select" aria-label="Filter by lifecycle" value={lifecycle} onChange={(event) => setLifecycle(event.target.value)}>
                    <option value="all">All lifecycle states</option>
                    {lifecycleOptions.map((value) => <option key={value} value={value}>{humanizeToken(value)}</option>)}
                  </select></label>
                <div className="mp-field"><span>Status</span>
                  <Segmented<StatusFilter> size="sm" label="Filter by status" value={status} onChange={setStatus}
                    options={[{ value: 'all', label: 'All' }, { value: 'active', label: 'Active' }, { value: 'inactive', label: 'Inactive' }]} /></div>
              </div>
            ) : null}

            <div className="mp-resultbar">
              <p className="toolbar-count" role="status" style={{ margin: 0 }}>
                {view === 'cards' ? `Showing ${formatInteger(visible.length)} of ${formatInteger(filtered.length)}` : `${formatInteger(filtered.length)}`} matching · {formatInteger(total)} in the active pool
              </p>
              {filtersActive ? <Button variant="ghost" size="sm" onClick={clearFilters} leadingIcon={<Filter />}>Clear all filters</Button> : null}
            </div>

            {view === 'cards' ? (
              filtered.length > 0 ? (
                <>
                  <div className="mp-grid" role="list" aria-label="Models">
                    {visible.map((model) => (
                      <div role="listitem" key={cardKey(model)} style={{ display: 'contents' }}>
                        <ModelCard
                          model={model}
                          providerLabel={providerLabel(model.provider)}
                          compared={compareIds.includes(cardKey(model))}
                          compareDisabled={compareIds.length >= MAX_COMPARE}
                          onInspect={setSelected}
                          onToggleCompare={toggleCompare}
                        />
                      </div>
                    ))}
                  </div>
                  {visible.length < filtered.length ? (
                    <div className="mp-more">
                      <Button variant="secondary" onClick={() => setLimit((n) => n + PAGE_SIZE)}>
                        Show {formatInteger(Math.min(PAGE_SIZE, filtered.length - visible.length))} more ({formatInteger(filtered.length - visible.length)} not yet shown)
                      </Button>
                    </div>
                  ) : null}
                </>
              ) : (
                <EmptyState icon={<Boxes />} title="No models match these filters"
                  description={filtersActive ? 'Clear the filters to see the whole active pool.' : 'The registry returned no models, so there is nothing for the router to select.'}
                  action={filtersActive ? <Button variant="secondary" onClick={clearFilters}>Clear filters</Button> : undefined} />
              )
            ) : (
              <DataTable
                flush
                caption="Models available to the router, with the registry metadata used for scoring"
                columns={columns}
                rows={filtered}
                rowKey={(row) => cardKey(row)}
                initialSort={{ columnId: 'quality', direction: 'desc' }}
                renderCard={(row) => (
                  <div>
                    <div className="record-head">
                      <div><p className="record-title">{row.model_name}</p><p className="record-subtitle">{row.model_id}</p></div>
                      <Status name={row.active ? 'active' : 'inactive'}>{row.active ? 'Active' : 'Inactive'}</Status>
                    </div>
                    <dl className="record-metrics">
                      <div className="record-metric"><dt className="record-metric-label">Category</dt><dd className="record-metric-value">{GROUP_LABEL[row.model_category ?? 'unclassified']}</dd></div>
                      <div className="record-metric"><dt className="record-metric-label">Provider</dt><dd className="record-metric-value">{providerLabel(row.provider)}</dd></div>
                      <div className="record-metric"><dt className="record-metric-label">Quality estimate</dt><dd className="record-metric-value">{formatPercent(row.estimated_quality, 0)}</dd></div>
                      <div className="record-metric"><dt className="record-metric-label">Cost / 1K</dt><dd className="record-metric-value">{formatModelCostPerThousand(row)}</dd></div>
                      <div className="record-metric"><dt className="record-metric-label">Latency estimate</dt><dd className="record-metric-value">{formatSeconds(row.avg_latency_seconds)}</dd></div>
                      <div className="record-metric"><dt className="record-metric-label">Context</dt><dd className="record-metric-value">{formatInteger(row.context_window)}</dd></div>
                    </dl>
                    <div className="registry-row-actions">
                      <Button size="sm" variant="secondary" onClick={() => setSelected(row)}>Inspect<span className="sr-only"> {row.model_name}</span></Button>
                      <Button size="sm" variant={compareIds.includes(cardKey(row)) ? 'subtle' : 'ghost'} disabled={!compareIds.includes(cardKey(row)) && compareIds.length >= MAX_COMPARE} onClick={() => toggleCompare(row)}>
                        {compareIds.includes(cardKey(row)) ? 'Selected' : 'Compare'}
                      </Button>
                    </div>
                  </div>
                )}
                emptyState={<EmptyState icon={<Boxes />} title="No models match these filters" description={filtersActive ? 'Clear the filters to see the whole active pool.' : 'The registry returned no models.'}
                  action={filtersActive ? <Button variant="secondary" onClick={clearFilters}>Clear filters</Button> : undefined} />}
              />
            )}
          </div>

          {approvedMode ? null : (
            <>
          <section className="cx-overview" aria-label="Catalogue distribution">
            {catalogueSummary ? (
              <div className="cx-grid cx-grid--2">
                <ProviderDistribution summary={catalogueSummary} />
                <CapabilityOverview summary={catalogueSummary} />
              </div>
            ) : null}
          </section>
          <EcosystemPanel />
          <LiveRegistryPanel
            status={registryStatus.data}
            adminToken={adminToken}
            onAdminToken={setAdminToken}
            onChanged={() => { registryStatus.reload(); models.reload(); poolStats.reload(); setCatalogRefresh((value) => value + 1); }}
          />
          <LiveCatalogBrowser refreshKey={catalogRefresh} onInspect={setSelected} />
            </>
          )}

          <p className="inline-note">
            Filters apply to this list only and never change routing, which is driven by the live registry at query time. Cost, latency and quality are registry metadata
            from the source shown on each model, not benchmarks run here.
          </p>
        </div>
      )}

      <Modal
        open={compareOpen}
        onClose={() => setCompareOpen(false)}
        title="Compare registry entries"
        description="A side-by-side view of the selected registry metadata."
        size="lg"
        footer={(
          <div className="row row-wrap">
            <Button variant="ghost" size="sm" onClick={() => setCompareIds([])}>Clear selection</Button>
            <Button variant="secondary" size="sm" onClick={() => setCompareOpen(false)}>Done</Button>
          </div>
        )}
      >
        <ModelComparison models={compareModels} />
      </Modal>
    </>
  );
}

function ModelComparison({ models: entries }: { models: ModelInfo[] }) {
  const rows: { label: string; value: (model: ModelInfo) => string }[] = [
    { label: 'Type', value: (model) => entryTypeLabel(model.entry_type) },
    { label: 'Provider', value: (model) => providerLabel(model.provider) },
    { label: 'Status', value: (model) => model.active ? 'Active' : 'Inactive' },
    { label: 'Quality estimate', value: (model) => formatPercent(model.estimated_quality, 0) },
    { label: 'Cost / 1K tokens', value: (model) => formatModelCostPerThousand(model) },
    { label: 'Latency estimate', value: (model) => formatSeconds(model.avg_latency_seconds) },
    { label: 'Reliability metadata', value: (model) => formatPercent(model.reliability, 0) },
    { label: 'Context window', value: (model) => formatInteger(model.context_window) },
    { label: 'Capabilities', value: (model) => model.capabilities.length ? model.capabilities.map(humanizeToken).join(', ') : UNAVAILABLE },
    { label: 'Data source', value: (model) => SOURCE_LABELS[model.source] ?? humanizeToken(model.source) },
  ];

  if (entries.length < 2) {
    return <EmptyState title="Select at least two entries" description="Choose two or three models or applications from the registry to compare their reported metadata." />;
  }

  return (
    <div className="registry-comparison">
      {rows.map((row) => (
        <div className="registry-comparison-row" key={row.label}>
          <strong>{row.label}</strong>
          {entries.map((model) => (
            <span key={cardKey(model)} title={row.value(model)}>{row.value(model)}</span>
          ))}
        </div>
      ))}
    </div>
  );
}
