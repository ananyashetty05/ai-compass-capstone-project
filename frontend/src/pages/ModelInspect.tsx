/**
 * Model inspect page.
 *
 * Read-only view of one registry record: identity, headline numbers,
 * specs, performance with provenance, routing compatibility, and the
 * lifecycle/provenance block. Nothing here contacts a provider.
 */
import { ArrowLeft, ArrowUpRight, Compass, Gauge, Layers, ShieldCheck } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { providerName } from '../components/dashboard/DistributionCards';
import { RegistryDetailBlock } from '../components/registry/LiveRegistry';
import { GenerationPill, LifecycleBlock, VerificationPill } from '../components/registry/Ecosystem';
import { CATEGORY_LABEL, KIND_LABEL } from '../components/registry/ModelCard';
import { ProvenanceTag, TagList } from '../components/ui/Badge';
import { ButtonLink } from '../components/ui/Button';
import { Grid, Meter, Page, PropertyList, SectionHeader, Stat, StatusPill, Surface } from '../components/ui/ds';
import { EmptyState, ErrorState, Notice } from '../components/ui/EmptyState';
import { Radar } from '../components/ui/Radar';
import { useAsync } from '../hooks/useAsync';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { getModelDetail, listModels } from '../services/models.service';
import { formatModelCostPerThousand, hasPublishedPrice, formatInteger, formatNumber, formatPercent, formatSeconds, humanizeToken } from '../utils/format';
import { UNAVAILABLE } from '../types';
import type { ModelInfo } from '../types';

const SOURCE_LABELS: Record<string, string> = {
  provider_config: 'Provider configuration',
  static_catalog: 'Bundled provider-documentation snapshot',
  application_catalog: 'Bundled application catalog snapshot',
  live_discovered: 'Live provider catalog discovery',
  catalog: 'Autonomous catalogue (see provenance per field)',
  routerbench: 'RouterBench import',
  measured: 'Measured in this environment',
};

const isApi = (m: ModelInfo) => m.entry_type === 'inference_model' || m.entry_type === 'model';

function Chips({ items }: { items: string[] }) {
  return items.length > 0 ? <TagList items={items.map(humanizeToken)} /> : <p className="text-muted">{UNAVAILABLE}</p>;
}

function Inspect({ model }: { model: ModelInfo }) {
  const sourceLabel = SOURCE_LABELS[model.source] ?? humanizeToken(model.source);
  const provenanceKind = model.source === 'measured' ? 'measured' : 'estimated';
  const eligibility = model.eligibility?.eligible;

  return (
    <>
      <Surface variant="glass" className="mi-hero" aria-labelledby="mi-title">
        <div className="mi-hero-main">
          <p className="ds-kicker">{providerName(model.provider)}</p>
          <h1 id="mi-title">{model.model_name}</h1>
          <p className="mi-id"><code>{model.model_id}</code></p>
          <div className="mi-pills">
            <StatusPill tone={model.active ? 'success' : 'neutral'}>{model.active ? 'Active' : 'Inactive'}</StatusPill>
            <StatusPill tone="primary">{isApi(model) ? 'API inference model' : humanizeToken(model.entry_type)}</StatusPill>
            {isApi(model) && eligibility !== undefined ? (
              <StatusPill tone={eligibility ? 'success' : 'warning'}>{eligibility ? 'Routing-eligible' : 'Not routing-eligible'}</StatusPill>
            ) : null}
            <StatusPill>{CATEGORY_LABEL[model.primary_category ?? 'unclassified']}{model.category_kind && model.category_kind !== 'unclassified' && model.category_kind !== 'consumer_app' ? ` · ${KIND_LABEL[model.category_kind] ?? humanizeToken(model.category_kind)}` : ''}</StatusPill>
            <GenerationPill catalog={model.catalog} />
            <VerificationPill catalog={model.catalog} />
            {model.lifecycle_status && model.lifecycle_status.toLowerCase() !== (model.active ? 'active' : 'inactive') ? <StatusPill>{humanizeToken(model.lifecycle_status)}</StatusPill> : null}
          </div>
          {model.description ? <p className="mi-desc">{model.description}</p> : null}
          {model.classification_reason ? <p className="mi-desc" style={{ fontSize: '0.8125rem', opacity: 0.8 }}>Classified as {CATEGORY_LABEL[model.primary_category ?? 'unclassified']} ({model.classification_basis ?? 'unverified'}): {model.classification_reason}.</p> : null}
        </div>
        <div className="mi-hero-actions">
          <ButtonLink to="/route" variant="primary" leadingIcon={<Compass />}>Route a query</ButtonLink>
          {model.external_url ? (
            <a className="btn" data-variant="secondary" href={model.external_url} target="_blank" rel="noreferrer noopener">Open destination <ArrowUpRight aria-hidden="true" /></a>
          ) : null}
        </div>
      </Surface>

      <Grid cols={4} className="mi-stats">
        <Stat label="Quality estimate" value={formatPercent(model.estimated_quality, 0)} hint={sourceLabel} />
        <Stat label="Cost / 1K tokens" value={formatModelCostPerThousand(model)} hint={hasPublishedPrice(model) ? 'Registry price' : 'No price in the registry'} />
        <Stat label="Latency estimate" value={formatSeconds(model.avg_latency_seconds)} hint="Registry estimate" />
        <Stat label="Context window" value={formatInteger(model.context_window)} hint="Tokens" />
      </Grid>

      <Grid ratio="2-1" className="mi-body">
        <div className="mi-col">
          <Surface className="mi-card" aria-labelledby="mi-perf">
            <SectionHeader id="mi-perf" level="h2" kicker="Performance" title="Scoring inputs"
              description="Higher is better. These are registry values used by the router, not benchmark results." actions={<ProvenanceTag kind={provenanceKind} label={sourceLabel} />} />
            <div className="mi-perf-grid">
            <Radar label="Registry scoring inputs" axes={[
              { label: 'Quality', value: model.estimated_quality, display: formatPercent(model.estimated_quality, 0) },
              { label: 'Reliability', value: model.reliability, display: formatPercent(model.reliability, 0) },
              { label: 'Safety', value: model.risk_level === null ? null : 1 - model.risk_level, display: model.risk_level === null ? UNAVAILABLE : formatPercent(1 - model.risk_level, 0) },
              { label: 'Cost', value: model.estimated_cost === null ? null : 1 - model.estimated_cost, display: model.estimated_cost === null ? UNAVAILABLE : formatPercent(1 - model.estimated_cost, 0) },
              { label: 'Speed', value: model.estimated_latency === null ? null : 1 - model.estimated_latency, display: model.estimated_latency === null ? UNAVAILABLE : formatPercent(1 - model.estimated_latency, 0) },
            ]} />
            <div className="mi-meters">
              <Meter label="Estimated quality" value={model.estimated_quality} display={formatPercent(model.estimated_quality, 0)} />
              <Meter label="Reliability (metadata)" value={model.reliability} display={formatPercent(model.reliability, 0)} />
              <Meter label="Risk suitability" value={model.risk_level === null ? null : 1 - model.risk_level} display={model.risk_level === null ? UNAVAILABLE : formatPercent(1 - model.risk_level, 0)} />
              <Meter label="Cost efficiency" value={model.estimated_cost === null ? null : 1 - model.estimated_cost} display={model.estimated_cost === null ? UNAVAILABLE : formatPercent(1 - model.estimated_cost, 0)} />
              <Meter label="Speed" value={model.estimated_latency === null ? null : 1 - model.estimated_latency} display={model.estimated_latency === null ? UNAVAILABLE : formatPercent(1 - model.estimated_latency, 0)} />
            </div>
            </div>
            <p className="ds-section-desc">Cost efficiency and speed are the inverted configured cost and latency, matching the routing score convention.</p>
          </Surface>

          <Surface className="mi-card" aria-labelledby="mi-compat">
            <SectionHeader id="mi-compat" level="h2" kicker="Routing compatibility" title="What it can be routed for" />
            <div className="mi-tags">
              <div><p className="field-label">Capabilities</p><Chips items={model.capabilities} /></div>
              <div><p className="field-label">Supported tasks</p><Chips items={model.supported_tasks} /></div>
              <div><p className="field-label">Supported domains</p><Chips items={model.supported_domains} /></div>
            </div>
            <RegistryDetailBlock model={model} adminToken="" />
          </Surface>
        </div>

        <div className="mi-col">
          {model.catalog ? (
            <Surface className="mi-card" aria-labelledby="mi-life">
              <SectionHeader id="mi-life" level="h2" kicker="Lifecycle" title="Generation, access and sources" />
              <LifecycleBlock model={model} />
            </Surface>
          ) : null}
          <Surface className="mi-card" aria-labelledby="mi-specs">
            <SectionHeader id="mi-specs" level="h2" kicker="Specifications" title="Registry record" />
            <PropertyList items={[
              { label: 'Provider', value: providerName(model.provider) },
              { label: 'Entry type', value: humanizeToken(model.entry_type) },
              { label: 'Availability', value: model.availability ? humanizeToken(model.availability) : UNAVAILABLE },
              { label: 'Lifecycle', value: model.lifecycle_status ? humanizeToken(model.lifecycle_status) : UNAVAILABLE },
              { label: 'Fallback priority', value: `#${formatNumber(model.fallback_priority, 0)}`, hint: 'Order tried if the first choice fails' },
              { label: 'Cost per request', value: model.estimated_cost === null ? UNAVAILABLE : `$${model.estimated_cost.toFixed(6)}` },
              { label: 'Data source', value: sourceLabel },
            ]} />
          </Surface>
          <Notice tone="info" icon={<Gauge />} title="How the router uses this record">
            Quality, cost and latency are registry estimates used in per-model scoring after analysis. Reliability and risk are registry metadata, not measured provider outcomes. No provider is contacted while this page is open.
          </Notice>
        </div>
      </Grid>
    </>
  );
}

export function ModelInspect() {
  const [params] = useSearchParams();
  const provider = params.get('provider') ?? '';
  const modelId = params.get('model') ?? '';
  const models = useAsync((signal) => listModels(signal), []);
  const listed = (models.data ?? []).find((m) => m.model_id === modelId && (!provider || m.provider === provider)) ?? null;
  // A retired (superseded) model is not in the active list but must stay readable for history and earlier decisions.
  const historical = useAsync((signal) => getModelDetail(provider, modelId, signal), [provider, modelId],
    { enabled: !models.isInitialLoad && !listed && Boolean(provider && modelId) });
  const model = listed ?? historical.data?.entry ?? null;
  useDocumentTitle(model ? `${model.model_name} · Model` : 'Model');

  return (
    <Page className="mi-page">
      <nav aria-label="Breadcrumb" className="mi-crumbs">
        <Link to="/models"><ArrowLeft aria-hidden="true" /> Model pool</Link>
        <span aria-hidden="true">/</span>
        <span>{model?.model_name ?? 'Model'}</span>
      </nav>
      {models.isInitialLoad || (!listed && historical.isInitialLoad) ? (
        <div className="mi-loading" role="status" aria-busy="true"><Layers aria-hidden="true" /> Loading model record…</div>
      ) : models.error ? (
        <ErrorState title="Model record unavailable" message={models.error.message} hint={models.error.hint} onRetry={models.reload} />
      ) : model ? (
        <Inspect model={model} />
      ) : (
        <EmptyState
          icon={<ShieldCheck />} title="Model not found"
          description="This model is not in the registry. It may have been removed or renamed."
          action={<ButtonLink to="/models" variant="secondary">Back to model pool</ButtonLink>}
        />
      )}
    </Page>
  );
}
