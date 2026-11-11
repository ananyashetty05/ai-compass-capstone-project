/**
 * Model pool.
 *
 * A read-only view of `GET /models`: whatever the registry returns is
 * what is shown, including inactive models. Cost, latency and quality
 * figures are registry metadata from the configured `source`, so every
 * table carries a provenance label rather than implying a benchmark.
 */
import { useCallback, useMemo, useState } from 'react';
import { ArrowUpRight, Boxes, Check, Filter, GitCompareArrows, LayoutGrid, List, Search, Server } from 'lucide-react';
import { PageHeader } from '../components/layout/PageHeader';
import { Button } from '../components/ui/Button';
import { Badge, ProvenanceTag, Status, Tag, TagList } from '../components/ui/Badge';
import { DimensionRow } from '../components/ui/ScoreBar';
import { DataTable } from '../components/ui/DataTable';
import type { ColumnDef } from '../components/ui/DataTable';
import { Modal } from '../components/ui/Modal';
import { TextInput } from '../components/ui/Input';
import { EmptyState, ErrorState, Notice } from '../components/ui/EmptyState';
import { MetadataEntry, MetadataRow } from '../components/ui/Metadata';
import { Segmented, SkeletonMetrics, SkeletonTable } from '../components/ui/Skeleton';
import { useAsync } from '../hooks/useAsync';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { listModels } from '../services/models.service';
import {
  formatCostPerThousand,
  formatInteger,
  formatNumber,
  formatPercent,
  formatSeconds,
  humanizeToken,
} from '../utils/format';
import { UNAVAILABLE } from '../types';
import type { ModelInfo } from '../types';

type StatusFilter = 'all' | 'active' | 'inactive';
type EntryFilter = 'all' | 'inference_model' | 'application_integration' | 'specialized_ai_tool';
type RegistryView = 'cards' | 'table';
const MAX_COMPARE = 3;

const REGISTRY_CATEGORIES: { key: EntryFilter; title: string; detail: string; countKey: keyof RegistryCategoryCounts }[] = [
  { key: 'all', title: 'All entries', detail: 'Everything in the registry', countKey: 'all' },
  { key: 'inference_model', title: 'API models', detail: 'Available for model routing', countKey: 'models' },
  { key: 'application_integration', title: 'AI applications', detail: 'Products opened at their destination', countKey: 'applications' },
  { key: 'specialized_ai_tool', title: 'Specialized tools', detail: 'Task-specific AI tools', countKey: 'tools' },
];

type RegistryCategoryCounts = {
  all: number;
  models: number;
  applications: number;
  tools: number;
};

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
  routerbench: 'RouterBench import',
  measured: 'Measured in this environment',
};

function providerLabel(provider: string): string {
  const known = PROVIDER_LABELS[provider.toLowerCase()];
  return known ?? humanizeToken(provider);
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
  useDocumentTitle('Model registry · AI Compass');
  const models = useAsync((signal) => listModels(signal));
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<StatusFilter>('all');
  const [provider, setProvider] = useState<string>('all');
  const [availability, setAvailability] = useState<string>('all');
  const [entryType, setEntryType] = useState<EntryFilter>('all');
  const [capability, setCapability] = useState('all');
  const [view, setView] = useState<RegistryView>('cards');
  const [selected, setSelected] = useState<ModelInfo | null>(null);
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [compareOpen, setCompareOpen] = useState(false);

  const providers = useMemo(() => {
    const ids = new Set((models.data ?? []).map((model) => model.provider));
    return Array.from(ids).sort((a, b) => providerLabel(a).localeCompare(providerLabel(b)));
  }, [models.data]);

  const capabilities = useMemo(() => {
    const values = new Set((models.data ?? []).flatMap((model) => model.capabilities));
    return Array.from(values).sort((a, b) => humanizeToken(a).localeCompare(humanizeToken(b)));
  }, [models.data]);

  const availabilityOptions = useMemo(() => {
    const values = new Set((models.data ?? []).map((model) => model.availability).filter((value): value is string => Boolean(value)));
    return Array.from(values).sort((a, b) => humanizeToken(a).localeCompare(humanizeToken(b)));
  }, [models.data]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (models.data ?? []).filter((model) => {
      if (status === 'active' && !model.active) return false;
      if (status === 'inactive' && model.active) return false;
      if (provider !== 'all' && model.provider !== provider) return false;
      if (availability !== 'all' && model.availability !== availability) return false;
      if (entryType === 'inference_model' && model.entry_type !== 'inference_model' && model.entry_type !== 'model') return false;
      if (entryType !== 'all' && entryType !== 'inference_model' && model.entry_type !== entryType) return false;
      if (capability !== 'all' && !model.capabilities.includes(capability)) return false;
      if (needle.length === 0) return true;
      return (
        model.model_id.toLowerCase().includes(needle) ||
        model.model_name.toLowerCase().includes(needle) ||
        model.provider.toLowerCase().includes(needle) ||
        model.capabilities.some((capability) => capability.toLowerCase().includes(needle))
      );
    });
  }, [availability, capability, entryType, models.data, provider, query, status]);

  const stats = useMemo(() => {
    const list = models.data ?? [];
    const active = list.filter((model) => model.active);
    return {
      total: list.length,
      active: active.length,
      inactive: list.length - active.length,
      providers: new Set(list.map((model) => model.provider)).size,
    };
  }, [models.data]);

  const categoryCounts = useMemo(() => {
    const list = models.data ?? [];
    return {
      all: list.length,
      models: list.filter((model) => model.entry_type === 'inference_model' || model.entry_type === 'model').length,
      applications: list.filter((model) => model.entry_type === 'application_integration').length,
      tools: list.filter((model) => model.entry_type === 'specialized_ai_tool').length,
    };
  }, [models.data]);

  const clearFilters = useCallback(() => {
    setQuery('');
    setStatus('all');
    setProvider('all');
    setAvailability('all');
    setEntryType('all');
    setCapability('all');
  }, []);

  const filtersActive = query.trim().length > 0 || status !== 'all' || provider !== 'all' || availability !== 'all' || entryType !== 'all' || capability !== 'all';

  const toggleCompare = useCallback((model: ModelInfo) => {
    setCompareIds((current) => {
      if (current.includes(model.model_id)) return current.filter((id) => id !== model.model_id);
      if (current.length >= MAX_COMPARE) return current;
      return [...current, model.model_id];
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
        id: 'status',
        header: 'Status',
        cell: (row) => (
          <Status name={row.active ? 'active' : 'inactive'}>{row.entry_type === 'inference_model' ? 'Recommendation-ready' : row.entry_type === 'specialized_ai_tool' ? 'Specialized tool' : 'Application'}</Status>
        ),
        sortValue: (row) => (row.active ? 0 : 1),
      },
      {
        id: 'quality',
        header: 'Quality',
        numeric: true,
        cell: (row) => <span className="text-numeric">{formatPercent(row.estimated_quality, 0)}</span>,
        sortValue: (row) => row.estimated_quality,
      },
      {
        id: 'cost',
        header: 'Cost / 1K',
        numeric: true,
        cell: (row) => <span className="text-numeric">{formatCostPerThousand(row.cost_per_1k_tokens)}</span>,
        sortValue: (row) => row.cost_per_1k_tokens,
      },
      {
        id: 'latency',
        header: 'Latency',
        numeric: true,
        cell: (row) => <span className="text-numeric">{formatSeconds(row.avg_latency_seconds)}</span>,
        sortValue: (row) => row.avg_latency_seconds,
        secondary: true,
      },
      {
        id: 'reliability',
        header: 'Reliability',
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
              variant={compareIds.includes(row.model_id) ? 'subtle' : 'secondary'}
              disabled={!compareIds.includes(row.model_id) && compareIds.length >= MAX_COMPARE}
              onClick={() => toggleCompare(row)}
            >
              {compareIds.includes(row.model_id) ? <Check aria-hidden="true" /> : <GitCompareArrows aria-hidden="true" />}
              <span className="sr-only">{compareIds.includes(row.model_id) ? 'Remove from comparison' : 'Add to comparison'} </span>
            </Button>
          </div>
        ),
        sortValue: () => null,
      },
    ],
    [compareIds, toggleCompare],
  );

  const compareModels = (models.data ?? []).filter((model) => compareIds.includes(model.model_id));

  return (
    <>
      <PageHeader
        eyebrow="Registry"
        title="Model registry"
        description="API inference models and consumer AI applications. Catalog estimates support routing; availability distinguishes direct applications from configured APIs."
        actions={(
          <div className="row row-wrap">
            {compareIds.length > 0 && (
              <Button
                variant="secondary"
                size="sm"
                leadingIcon={<GitCompareArrows />}
                disabled={compareIds.length < 2}
                onClick={() => setCompareOpen(true)}
              >
                Compare ({compareIds.length})
              </Button>
            )}
            <Button variant="secondary" size="sm" onClick={models.reload} loading={models.isLoading}>
              Refresh
            </Button>
          </div>
        )}
      />

      {models.isInitialLoad ? (
        <div className="page-body">
          <SkeletonMetrics count={4} />
          <SkeletonTable rows={8} />
        </div>
      ) : models.error ? (
        <ErrorState
          title="The model registry could not be loaded"
          message={models.error.message}
          hint={models.error.hint}
          onRetry={models.reload}
        />
      ) : (
        <div className="page-body registry-page-body">
          <section className="registry-discovery" aria-labelledby="registry-categories-title">
            <div className="registry-discovery-heading">
              <div>
                <p className="registry-eyebrow">Explore the catalog</p>
                <h2 id="registry-categories-title">Find a model for the work</h2>
                <p>Browse registered APIs and applications by how they’re available to your workflow.</p>
              </div>
              <span className="registry-discovery-count">{formatNumber(stats.total, 0)} entries</span>
            </div>
            <div className="registry-category-grid">
              {REGISTRY_CATEGORIES.map((category) => (
                <button
                  type="button"
                  className="registry-category"
                  data-selected={entryType === category.key}
                  key={category.key}
                  aria-pressed={entryType === category.key}
                  onClick={() => setEntryType(category.key)}
                >
                  <span className="registry-category-label">{category.title}</span>
                  <span className="registry-category-detail">{category.detail}</span>
                  <strong>{formatNumber(categoryCounts[category.countKey], 0)}</strong>
                </button>
              ))}
            </div>
          </section>

          {/* Toolbar and table share one surface: the controls act on
              the rows directly beneath them. */}
          <div className="table-surface">
            <div className="table-toolbar">
              <TextInput
                className="toolbar-search"
                label="Search"
                hideLabel
                type="search"
                placeholder="Model name, id, provider or capability"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                leadingIcon={<Search />}
              />

              <label className="toolbar-group registry-select-group">
                <span className="toolbar-label">Provider</span>
                <select
                  className="registry-filter-select"
                  aria-label="Filter by provider"
                  value={provider}
                  onChange={(event) => setProvider(event.target.value)}
                >
                  <option value="all">All providers</option>
                  {providers.map((id) => (
                    <option key={id} value={id}>{providerLabel(id)}</option>
                  ))}
                </select>
              </label>

              <label className="toolbar-group registry-select-group">
                <span className="toolbar-label">Availability</span>
                <select
                  className="registry-filter-select"
                  aria-label="Filter by availability"
                  value={availability}
                  onChange={(event) => setAvailability(event.target.value)}
                >
                  <option value="all">All availability</option>
                  {availabilityOptions.map((value) => (
                    <option key={value} value={value}>{availabilityLabel(value)}</option>
                  ))}
                </select>
              </label>

              <div className="toolbar-group">
                <span className="toolbar-label">Status</span>
                <Segmented<StatusFilter>
                  size="sm"
                  label="Filter by status"
                  value={status}
                  onChange={setStatus}
                  options={[
                    { value: 'all', label: 'All' },
                    { value: 'active', label: 'Active' },
                    { value: 'inactive', label: 'Inactive' },
                  ]}
                />
              </div>

              <label className="toolbar-group registry-select-group">
                <span className="toolbar-label">Capability</span>
                <select
                  className="registry-filter-select"
                  aria-label="Filter by capability"
                  value={capability}
                  onChange={(event) => setCapability(event.target.value)}
                >
                  <option value="all">All capabilities</option>
                  {capabilities.map((value) => (
                    <option key={value} value={value}>{humanizeToken(value)}</option>
                  ))}
                </select>
              </label>

              {filtersActive ? (
                <Button variant="ghost" size="sm" onClick={clearFilters} leadingIcon={<Filter />}>
                  Clear
                </Button>
              ) : null}

              <p className="toolbar-count" role="status">
                {formatInteger(filtered.length)} of {formatInteger(stats.total)}
              </p>
              <Segmented<RegistryView>
                size="sm"
                label="Registry display"
                value={view}
                onChange={setView}
                options={[
                  { value: 'cards', label: 'Cards', icon: <LayoutGrid /> },
                  { value: 'table', label: 'Table', icon: <List /> },
                ]}
              />
            </div>

            {view === 'cards' ? (
              filtered.length > 0 ? (
                <div className="registry-card-grid">
                  {filtered.map((model) => {
                    const isCompared = compareIds.includes(model.model_id);
                    return (
                      <article className="registry-card" key={model.model_id}>
                        <div className="registry-card-top">
                          <div>
                            <p className="registry-card-provider">{providerLabel(model.provider)}</p>
                            <h2 className="registry-card-title">{model.model_name}</h2>
                            <p className="registry-card-id">{model.model_id}</p>
                          </div>
                          <Status name={model.active ? 'active' : 'inactive'}>
                            {model.active ? 'Active' : 'Inactive'}
                          </Status>
                        </div>
                        <div className="registry-card-badges">
                          <Badge tone={model.entry_type === 'inference_model' || model.entry_type === 'model' ? 'primary' : 'neutral'}>
                            {entryTypeLabel(model.entry_type)}
                          </Badge>
                          {model.availability ? <Tag>{model.entry_type === 'application_integration' ? 'App' : 'API'}: {availabilityLabel(model.availability)}</Tag> : null}
                          <ProvenanceTag
                            kind={model.source === 'measured' ? 'measured' : 'estimated'}
                            label={SOURCE_LABELS[model.source] ?? humanizeToken(model.source)}
                          />
                        </div>
                        {model.description && <p className="registry-card-description">{model.description}</p>}
                        <dl className="registry-card-metrics">
                          <div><dt>Quality</dt><dd>{formatPercent(model.estimated_quality, 0)}</dd></div>
                          <div><dt>Cost / 1K</dt><dd>{formatCostPerThousand(model.cost_per_1k_tokens)}</dd></div>
                          <div><dt>Latency</dt><dd>{formatSeconds(model.avg_latency_seconds)}</dd></div>
                          <div><dt>Reliability</dt><dd>{formatPercent(model.reliability, 0)}</dd></div>
                        </dl>
                        <div className="registry-card-capabilities" aria-label="Reported capabilities">
                          {model.capabilities.length > 0
                            ? model.capabilities.slice(0, 5).map((value) => <Tag key={value}>{humanizeToken(value)}</Tag>)
                            : <span className="text-muted text-xs">No capabilities reported</span>}
                          {model.capabilities.length > 5 && <span className="text-muted text-xs">+{model.capabilities.length - 5}</span>}
                        </div>
                        <div className="registry-card-actions">
                          {model.external_url && (
                            <a className="btn" data-size="sm" data-variant="ghost" href={model.external_url} target="_blank" rel="noreferrer noopener">
                              Open destination <ArrowUpRight aria-hidden="true" />
                            </a>
                          )}
                          <Button size="sm" variant="secondary" onClick={() => setSelected(model)}>
                            Inspect
                          </Button>
                          <Button
                            size="sm"
                            variant={isCompared ? 'subtle' : 'ghost'}
                            disabled={!isCompared && compareIds.length >= MAX_COMPARE}
                            onClick={() => toggleCompare(model)}
                            leadingIcon={isCompared ? <Check /> : <GitCompareArrows />}
                          >
                            {isCompared ? 'Selected' : 'Compare'}
                          </Button>
                        </div>
                      </article>
                    );
                  })}
                </div>
              ) : (
                <EmptyState
                  icon={<Boxes />}
                  title="No models match these filters"
                  description={filtersActive
                    ? 'Clear the filters to see the whole registry.'
                    : 'The registry returned no models, so there is nothing for the router to select.'}
                  action={filtersActive ? <Button variant="secondary" onClick={clearFilters}>Clear filters</Button> : undefined}
                />
              )
            ) : <DataTable
              flush
              caption="Models available to the router, with the registry metadata used for scoring"
              columns={columns}
              rows={filtered}
              rowKey={(row) => row.model_id}
              initialSort={{ columnId: 'quality', direction: 'desc' }}
              renderCard={(row) => (
                <div>
                  <div className="record-head">
                    <div>
                      <p className="record-title">{row.model_name}</p>
                      <p className="record-subtitle">{row.model_id}</p>
                    </div>
                    <Status name={row.active ? 'active' : 'inactive'}>{row.active ? 'Active' : 'Inactive'}</Status>
                  </div>
                  <dl className="record-metrics">
                    <div className="record-metric">
                      <dt className="record-metric-label">Type</dt>
                      <dd className="record-metric-value">{entryTypeLabel(row.entry_type)}</dd>
                    </div>
                    <div className="record-metric">
                      <dt className="record-metric-label">Provider</dt>
                      <dd className="record-metric-value">{providerLabel(row.provider)}</dd>
                    </div>
                    <div className="record-metric">
                      <dt className="record-metric-label">Quality</dt>
                      <dd className="record-metric-value">{formatPercent(row.estimated_quality, 0)}</dd>
                    </div>
                    <div className="record-metric">
                      <dt className="record-metric-label">Cost / 1K</dt>
                      <dd className="record-metric-value">{formatCostPerThousand(row.cost_per_1k_tokens)}</dd>
                    </div>
                    <div className="record-metric">
                      <dt className="record-metric-label">Latency</dt>
                      <dd className="record-metric-value">{formatSeconds(row.avg_latency_seconds)}</dd>
                    </div>
                    <div className="record-metric">
                      <dt className="record-metric-label">Reliability</dt>
                      <dd className="record-metric-value">{formatPercent(row.reliability, 0)}</dd>
                    </div>
                    <div className="record-metric">
                      <dt className="record-metric-label">Context</dt>
                      <dd className="record-metric-value">{formatInteger(row.context_window)}</dd>
                    </div>
                  </dl>
                  <div className="registry-row-actions">
                    <Button size="sm" variant="secondary" onClick={() => setSelected(row)}>
                      Inspect
                      <span className="sr-only"> {row.model_name}</span>
                    </Button>
                    <Button
                      size="sm"
                      variant={compareIds.includes(row.model_id) ? 'subtle' : 'ghost'}
                      disabled={!compareIds.includes(row.model_id) && compareIds.length >= MAX_COMPARE}
                      onClick={() => toggleCompare(row)}
                    >
                      {compareIds.includes(row.model_id) ? 'Selected' : 'Compare'}
                    </Button>
                  </div>
                </div>
              )}
              emptyState={
                <EmptyState
                  icon={<Boxes />}
                  title="No models match these filters"
                  description={
                    filtersActive
                      ? 'Clear the filters to see the whole registry.'
                      : 'The registry returned no models, so there is nothing for the router to select.'
                  }
                  action={
                    filtersActive ? (
                      <Button variant="secondary" onClick={clearFilters}>
                        Clear filters
                      </Button>
                    ) : undefined
                  }
                />
              }
            />
            }
          </div>

          <p className="inline-note">
            Filters apply to this list only. They do not change routing behaviour, which is driven by the live
            registry at query time.
          </p>
        </div>
      )}

      <Modal
        open={selected !== null}
        onClose={() => setSelected(null)}
        title={selected?.model_name ?? 'Model'}
        description={selected ? `Registry record for ${selected.model_id}` : undefined}
        size="lg"
      >
        {selected ? <ModelDetail model={selected} /> : null}
      </Modal>

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
    { label: 'Cost / 1K tokens', value: (model) => formatCostPerThousand(model.cost_per_1k_tokens) },
    { label: 'Average latency', value: (model) => formatSeconds(model.avg_latency_seconds) },
    { label: 'Reliability', value: (model) => formatPercent(model.reliability, 0) },
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
            <span key={model.model_id} title={row.value(model)}>{row.value(model)}</span>
          ))}
        </div>
      ))}
    </div>
  );
}

function ModelDetail({ model }: { model: ModelInfo }) {
  return (
    <div className="stack">
      <div className="row row-wrap">
        <Status name={model.active ? 'active' : 'inactive'}>{model.active ? 'Active' : 'Inactive'}</Status>
        <Badge tone="neutral" outline>
          {providerLabel(model.provider)}
        </Badge>
        <ProvenanceTag kind={model.source === 'measured' ? 'measured' : 'estimated'} label={SOURCE_LABELS[model.source] ?? humanizeToken(model.source)} />
        <Tag>Fallback priority #{formatNumber(model.fallback_priority, 0)}</Tag>
      </div>

      <div className="dimension-list">
        <DimensionRow label="Estimated quality" value={model.estimated_quality} />
        <DimensionRow label="Reliability" value={model.reliability} />
        <DimensionRow label="Risk level" value={1 - model.risk_level} description="Inverted so that higher is safer." />
        <DimensionRow
          label="Cost efficiency"
          value={1 - model.estimated_cost}
          description="Inverted configured cost, matching the routing score convention."
        />
        <DimensionRow
          label="Speed"
          value={1 - model.estimated_latency}
          description="Inverted configured latency, matching the routing score convention."
        />
      </div>

      <MetadataRow label="Registry record" columns="2">
        <MetadataEntry label="Cost / 1K" value={formatCostPerThousand(model.cost_per_1k_tokens)} />
        <MetadataEntry label="Per request" value={formatUsdSafe(model.estimated_cost)} />
        <MetadataEntry label="Latency" value={formatSeconds(model.avg_latency_seconds)} />
        <MetadataEntry label="Context window" value={formatInteger(model.context_window)} />
        <MetadataEntry label="Source" value={SOURCE_LABELS[model.source] ?? humanizeToken(model.source)} />
        <MetadataEntry label="Fallback priority" value={`#${formatNumber(model.fallback_priority, 0)}`} />
      </MetadataRow>

      <div>
        <p className="field-label">Capabilities</p>
        {model.capabilities.length > 0 ? (
          <TagList items={model.capabilities.map(humanizeToken)} />
        ) : (
          <p className="text-muted">{UNAVAILABLE}</p>
        )}
      </div>

      <div>
        <p className="field-label">Supported domains</p>
        {model.supported_domains.length > 0 ? (
          <TagList items={model.supported_domains.map(humanizeToken)} />
        ) : (
          <p className="text-muted">{UNAVAILABLE}</p>
        )}
      </div>

      <div>
        <p className="field-label">Supported tasks</p>
        {model.supported_tasks.length > 0 ? (
          <TagList items={model.supported_tasks.map(humanizeToken)} />
        ) : (
          <p className="text-muted">{UNAVAILABLE}</p>
        )}
      </div>

      <Notice tone="info" icon={<Server />} title="How the router uses this record">
        Estimated quality, cost and latency feed the per-model scores once a query has been analysed. Reliability and
        risk come straight from the registry. No provider is contacted while this page is open.
      </Notice>
    </div>
  );
}

function formatUsdSafe(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return UNAVAILABLE;
  return `$${value.toFixed(6)}`;
}
