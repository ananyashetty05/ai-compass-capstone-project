import { ArrowRight, Clock3, Database, GitCommitHorizontal, Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';
import { HeroOrbit } from '../components/dashboard/HeroOrbit';
import { AttentionCard } from '../components/dashboard/AttentionCard';
import { CapabilityOverview, ProviderDistribution, providerName } from '../components/dashboard/DistributionCards';
import { KpiIcons, KpiRow } from '../components/dashboard/KpiRow';
import type { Kpi } from '../components/dashboard/KpiRow';
import { PathsCard } from '../components/dashboard/PathsCard';
import { RegistryCard } from '../components/dashboard/RegistryCard';
import { deriveAttention, summariseModels, timeAgo, topBlockReason } from '../components/dashboard/insights';
import { ButtonLink } from '../components/ui/Button';
import { Status } from '../components/ui/Badge';
import { EmptyState, ErrorState } from '../components/ui/EmptyState';
import { Reveal } from '../components/ui/Reveal';
import { useAsync } from '../hooks/useAsync';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { useRouteResult } from '../context/routeResultContext';
import { useSystemStatus } from '../context/systemStatusContext';
import { getRegistryActivity, getRegistryStatus, listModels } from '../services/models.service';
import { fetchRoutingHistory } from '../services/history.service';
import { summariseHealth } from '../services/health.service';
import { humanizeToken } from '../utils/format';
import type { ModelInfo, RoutingHistoryEntry } from '../types';

function historyTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? 'Time unavailable'
    : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

const HEALTH_LABEL = { online: 'Operational', degraded: 'Partially available', offline: 'Unreachable', unknown: 'Checking status' } as const;

function ModelHighlight({ model }: { model: ModelInfo }) {
  return (
    <article className="dashboard-model-card">
      <div className="dashboard-model-card-heading">
        <div>
          <span className="dashboard-model-provider">{providerName(model.provider)}</span>
          <h3>{model.model_name}</h3>
        </div>
        <Status name={model.active ? 'active' : 'inactive'}>{model.active ? 'Active' : 'Inactive'}</Status>
      </div>
      <div className="dashboard-model-capabilities">
        {model.capabilities.slice(0, 3).map((capability) => (
          <span key={capability}>{humanizeToken(capability)}</span>
        ))}
        {model.capabilities.length === 0 ? <span>Capabilities not listed</span> : null}
      </div>
      <p className="dashboard-model-kind">
        {model.entry_type === 'inference_model' || model.entry_type === 'model' ? 'API inference model' : humanizeToken(model.entry_type)}
        {model.availability ? ` · ${humanizeToken(model.availability)}` : ''}
      </p>
    </article>
  );
}

export function Dashboard() {
  useDocumentTitle('Dashboard');
  const { result } = useRouteResult();
  const { state: healthState, health, providers, isChecking } = useSystemStatus();
  const models = useAsync((signal) => listModels(signal), []);
  const registry = useAsync((signal) => getRegistryStatus(signal), []);
  const activity = useAsync((signal) => getRegistryActivity(signal), []);
  const history = useAsync(() => fetchRoutingHistory(), []);

  const summary = models.data ? summariseModels(models.data) : null;
  const highlights = (summary?.inference ?? []).slice().sort((a, b) => a.fallback_priority - b.fallback_priority).slice(0, 4);
  const healthSummary = health ? summariseHealth(health) : null;
  const topBlock = summary ? topBlockReason(summary.inference) : null;

  const historyEntries: RoutingHistoryEntry[] = history.data?.availability === 'available' ? history.data.entries : [];
  const visibleHistory = result ? historyEntries.filter((entry) => entry.id !== result.routing_id) : historyEntries;

  const lastRefresh = (registry.data?.providers ?? [])
    .map((p) => p.last_success_at)
    .filter((v): v is string => Boolean(v))
    .sort()
    .at(-1);

  const kpis: Kpi[] = [
    {
      id: 'models', label: 'Registered models', icon: KpiIcons.models, loading: models.isInitialLoad,
      value: summary ? summary.inference.length : null,
      detail: summary
        ? `${summary.active} active${summary.inactive > 0 ? ` · ${summary.inactive} inactive` : ''}${summary.nonInference > 0 ? ` · ${summary.nonInference} tools & destinations` : ''}`
        : models.error?.message ?? 'Model list unavailable',
    },
    {
      id: 'eligible', label: 'Routing-eligible', icon: KpiIcons.routing, loading: models.isInitialLoad,
      value: summary?.eligible ?? null, of: summary && summary.eligible !== null ? summary.inference.length : null,
      detail: summary?.eligible !== null && summary ? (topBlock ? `${topBlock.count} blocked: ${topBlock.label}` : 'Models the router may currently choose') : 'This registry does not report eligibility per model',
    },
    {
      id: 'providers', label: 'Providers ready', icon: KpiIcons.providers, loading: isChecking && !health,
      value: healthSummary ? healthSummary.available : null, of: healthSummary?.total ?? null,
      detail: healthSummary ? `${healthSummary.configured} with a server credential` : 'Health check unavailable',
      tone: healthSummary && healthSummary.available === 0 ? 'warn' : undefined,
    },
    {
      id: 'registry', label: 'Last registry refresh', icon: KpiIcons.registry, loading: registry.isInitialLoad,
      value: null, text: lastRefresh ? timeAgo(lastRefresh) : registry.error ? null : 'Never',
      detail: lastRefresh
        ? `${registry.data?.providers.length ?? 0} provider${registry.data?.providers.length === 1 ? '' : 's'} tracked`
        : registry.error ? 'Registry status unavailable' : 'No live refresh recorded — built-in catalog in use',
    },
  ];

  const attention = deriveAttention({ health: healthState, providers, summary, registry: registry.data });

  return (
    <div className="dashboard-redesign">
      <section className="dashboard-hero cx-hero">
        <div className="dashboard-hero-copy">
          <p className="dashboard-eyebrow"><span /> AI routing intelligence</p>
          <h1>Find the right AI model<br />for any task.</h1>
          <p className="dashboard-hero-description">
            Adaptive, multi-objective, and personalized model routing — with clear explanations.
          </p>
          <div className="cx-hero-actions">
            <ButtonLink to="/route" variant="primary" trailingIcon={<ArrowRight />}>Route a Query</ButtonLink>
            <span className="cx-status-pill" data-state={healthState}>
              <span className="dashboard-status-dot" data-state={healthState} /> Routing service · <strong>{HEALTH_LABEL[healthState]}</strong>
            </span>
          </div>
        </div>
        <HeroOrbit />
      </section>

      <KpiRow kpis={kpis} />

      <div className="cx-grid cx-grid--2">
        <AttentionCard items={attention} loading={(isChecking && !health) || models.isInitialLoad} />
        <Reveal as="section" className="cx-card" delay={1} ariaLabelledBy="recent-routing-title">
          <header className="cx-card-head">
            <div><p className="cx-kicker">Your workspace</p><h2 id="recent-routing-title">Recent routing activity</h2></div>
            <Link to="/route" className="cx-link">Route a query <ArrowRight aria-hidden="true" /></Link>
          </header>

          {history.isInitialLoad ? (
            <div className="dashboard-activity-state" role="status">Loading routing activity…</div>
          ) : history.data?.availability === 'error' ? (
            <ErrorState title="Activity unavailable" message={history.data.reason} compact />
          ) : null}

          {result ? (
            <Link to="/explanation" className="dashboard-activity-row dashboard-activity-current">
              <span className="dashboard-activity-icon"><Sparkles aria-hidden="true" /></span>
              <span className="dashboard-activity-main">
                <strong>{result.query}</strong>
                <span>{humanizeToken(result.query_analysis.task_type)} · {result.final_model_name}</span>
              </span>
              <span className="dashboard-activity-time">This session</span>
              <ArrowRight className="dashboard-activity-arrow" aria-hidden="true" />
            </Link>
          ) : null}

          {visibleHistory.map((entry) => (
            <article key={entry.id} className="dashboard-activity-row">
              <span className="dashboard-activity-icon"><Clock3 aria-hidden="true" /></span>
              <span className="dashboard-activity-main">
                <strong>{entry.query_summary}</strong>
                <span>Category unavailable · {entry.final_model_name}</span>
              </span>
              <time className="dashboard-activity-time" dateTime={entry.timestamp}>{historyTime(entry.timestamp)}</time>
            </article>
          ))}

          {!history.isInitialLoad && history.data?.availability === 'available' && visibleHistory.length === 0 && !result ? (
            <EmptyState icon={<Clock3 />} title="No routing activity yet" description="Your completed routing requests will appear here." align="start" />
          ) : null}

          {!history.isInitialLoad && history.data?.availability === 'unsupported' && !result ? (
            <EmptyState
              icon={<Clock3 />}
              title="No routing run in this session"
              description="This backend does not store routing history, so only the latest run of this session is shown. Route a query to see it here."
              align="start"
              action={<ButtonLink to="/route" variant="secondary" size="sm">Route a query</ButtonLink>}
            />
          ) : null}
        </Reveal>
      </div>

      {summary ? (
        <div className="cx-grid cx-grid--3">
          <ProviderDistribution summary={summary} />
          <CapabilityOverview summary={summary} />
          <RegistryCard status={registry.data} error={registry.error?.message ?? null} loading={registry.isInitialLoad} onRetry={registry.reload} />
        </div>
      ) : models.error ? (
        <ErrorState title="Model ecosystem unavailable" message={models.error.message} hint={models.error.hint} compact onRetry={models.reload} />
      ) : (
        <div className="cx-grid cx-grid--3" aria-busy="true">{[0, 1, 2].map((i) => <div key={i} className="cx-card cx-card--loading" />)}</div>
      )}

      <div className="cx-grid cx-grid--2">
        <Reveal as="section" className="cx-card" ariaLabelledBy="model-highlights-title">
          <header className="cx-card-head">
            <div><p className="cx-kicker">Registry</p><h2 id="model-highlights-title">Model pool highlights</h2></div>
            <Link to="/models" className="cx-link">View model pool <ArrowRight aria-hidden="true" /></Link>
          </header>
          {models.isInitialLoad ? (
            <div className="dashboard-activity-state" role="status">Loading registered models…</div>
          ) : models.error ? (
            <ErrorState title="Model highlights unavailable" message={models.error.message} hint={models.error.hint} compact onRetry={models.reload} />
          ) : highlights.length === 0 ? (
            <EmptyState
              icon={<Database />}
              title="No inference models registered"
              description="The registry returned no API models to highlight."
              align="start"
              action={<ButtonLink to="/models" variant="secondary" size="sm">Open model pool</ButtonLink>}
            />
          ) : (
            <div className="dashboard-model-grid">{highlights.map((model) => <ModelHighlight key={model.model_id} model={model} />)}</div>
          )}
          <p className="cx-note">Ordered by fallback priority — the order models are tried if the first choice fails.</p>
        </Reveal>

        <Reveal as="section" className="cx-card" delay={1} ariaLabelledBy="reg-activity-title">
          <header className="cx-card-head">
            <div><p className="cx-kicker">Registry</p><h2 id="reg-activity-title">Recent registry changes</h2></div>
            <GitCommitHorizontal aria-hidden="true" />
          </header>
          {activity.isInitialLoad ? (
            <div className="dashboard-activity-state" role="status">Loading registry activity…</div>
          ) : activity.error ? (
            <EmptyState iconName="info" title="Registry activity unavailable" description="Lifecycle events are recorded only when live registry persistence is available." align="start" />
          ) : (activity.data ?? []).length === 0 ? (
            <EmptyState title="No registry changes recorded" description="Model lifecycle changes and failed refreshes will be listed here." align="start" />
          ) : (
            <ul className="cx-rows">
              {(activity.data ?? []).slice(0, 6).map((item, i) => (
                <li key={`${item.occurred_at}-${i}`}>
                  <span className="cx-row-main">
                    <strong>{item.model_id ?? providerName(item.provider)}</strong>
                    <span>{item.kind === 'refresh_failure' ? 'Refresh failed' : humanizeToken(item.event_type)}{item.new_status ? ` → ${humanizeToken(item.new_status)}` : ''}{item.reason ? ` · ${item.reason}` : ''}</span>
                  </span>
                  <time className="cx-row-time" dateTime={item.occurred_at}>{timeAgo(item.occurred_at) ?? ''}</time>
                </li>
              ))}
            </ul>
          )}
        </Reveal>
      </div>

      <PathsCard />
    </div>
  );
}
