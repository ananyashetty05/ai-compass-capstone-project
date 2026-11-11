import { ArrowRight, Clock3, Database, Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';
import { RoutingVisualization } from '../components/dashboard/RoutingVisualization';
import { ButtonLink } from '../components/ui/Button';
import { Status } from '../components/ui/Badge';
import { EmptyState, ErrorState } from '../components/ui/EmptyState';
import { useAsync } from '../hooks/useAsync';
import { useRouteResult } from '../context/routeResultContext';
import { useSystemStatus } from '../context/systemStatusContext';
import { listModels } from '../services/models.service';
import { fetchRoutingHistory } from '../services/history.service';
import { humanizeToken } from '../utils/format';
import type { ModelInfo, RoutingHistoryEntry } from '../types';

const PROVIDER_NAMES: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  google: 'Google',
  mistral: 'Mistral',
  meta: 'Meta',
  cohere: 'Cohere',
  together: 'Together AI',
};

function providerName(provider: string): string {
  return PROVIDER_NAMES[provider.toLowerCase()] ?? humanizeToken(provider);
}

function historyTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? 'Time unavailable'
    : new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

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
  const { result } = useRouteResult();
  const { state: healthState } = useSystemStatus();
  const models = useAsync((signal) => listModels(signal), []);
  const history = useAsync(() => fetchRoutingHistory(), []);

  const highlights = (models.data ?? [])
    .filter((model) => model.entry_type === 'inference_model' || model.entry_type === 'model')
    .slice()
    .sort((a, b) => a.fallback_priority - b.fallback_priority)
    .slice(0, 4);

  const historyEntries: RoutingHistoryEntry[] =
    history.data?.availability === 'available' ? history.data.entries : [];
  const visibleHistory = result
    ? historyEntries.filter((entry) => entry.id !== result.routing_id)
    : historyEntries;

  return (
    <div className="dashboard-redesign">
      <section className="dashboard-hero">
        <div className="dashboard-hero-copy">
          <p className="dashboard-eyebrow"><span /> AI routing intelligence</p>
          <h1>Find the right AI model<br />for any task.</h1>
          <p className="dashboard-hero-description">
            Adaptive, multi-objective, and personalized model routing — with clear explanations.
          </p>
          <ButtonLink to="/route" variant="primary" trailingIcon={<ArrowRight />}>
            Route a Query
          </ButtonLink>
        </div>
        <RoutingVisualization />
      </section>

      <div className="dashboard-status-line">
        <span><span className="dashboard-status-dot" data-state={healthState} /> Routing service</span>
        <strong>{healthState === 'online' ? 'Operational' : healthState === 'degraded' ? 'Partially available' : healthState === 'offline' ? 'Unreachable' : 'Checking status'}</strong>
      </div>

      <div className="dashboard-lower-grid">
        <section className="dashboard-section" aria-labelledby="recent-routing-title">
          <div className="dashboard-section-heading">
            <div>
              <p className="dashboard-section-kicker">Your workspace</p>
              <h2 id="recent-routing-title">Recent routing activity</h2>
            </div>
            <Link to="/route" className="dashboard-text-link">Route a query <ArrowRight aria-hidden="true" /></Link>
          </div>

          {history.isInitialLoad ? (
            <div className="dashboard-activity-state" role="status">Loading routing activity…</div>
          ) : history.data?.availability === 'error' ? (
            <ErrorState title="Activity unavailable" message={history.data.reason} compact />
          ) : null}

          {result ? (
            <Link to="/route" className="dashboard-activity-row dashboard-activity-current">
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
            <EmptyState
              icon={<Clock3 />}
              title="No routing activity yet"
              description="Your completed routing requests will appear here."
              align="start"
            />
          ) : null}

          {!history.isInitialLoad && history.data?.availability === 'unsupported' && !result ? (
            <div className="dashboard-activity-state">Routing history is not available in this backend. New recommendations remain available in the Route Query workspace.</div>
          ) : null}
        </section>

        <section className="dashboard-section" aria-labelledby="model-highlights-title">
          <div className="dashboard-section-heading">
            <div>
              <p className="dashboard-section-kicker">Registry</p>
              <h2 id="model-highlights-title">Model pool highlights</h2>
            </div>
            <Link to="/models" className="dashboard-text-link">View model pool <ArrowRight aria-hidden="true" /></Link>
          </div>

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
            <div className="dashboard-model-grid">
              {highlights.map((model) => <ModelHighlight key={model.model_id} model={model} />)}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
