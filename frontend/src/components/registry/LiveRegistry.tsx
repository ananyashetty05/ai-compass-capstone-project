/**
 * Live Model Pool building blocks for the existing Model Pool page.
 *
 * Everything shown here comes from the backend registry. Catalog visibility is
 * kept separate from inference access and routing eligibility, and unknown
 * metadata is displayed as unavailable — never as a placeholder score.
 */
import { useEffect, useMemo, useState } from 'react';
import { History, RefreshCw, Search, ShieldCheck } from 'lucide-react';
import { Button } from '../ui/Button';
import { Status, Tag } from '../ui/Badge';
import type { StatusName } from '../ui/Badge';
import { EmptyState, ErrorState, Notice } from '../ui/EmptyState';
import { TextInput } from '../ui/Input';
import { MetadataEntry, MetadataRow } from '../ui/Metadata';
import { SkeletonTable } from '../ui/Skeleton';
import { useAsync } from '../../hooks/useAsync';
import { useDebouncedValue } from '../../hooks/useDebouncedValue';
import {
  getCatalog, getModelDetail, getRegistryActivity, refreshRegistry, verifyModelInference,
} from '../../services/models.service';
import { describeError } from '../../services/http';
import { formatInteger, formatTimestamp, humanizeToken } from '../../utils/format';
import { UNAVAILABLE } from '../../types';
import type { ModelInfo, RefreshResult, RegistryProviderRefresh, RegistryStatus } from '../../types';

const LIFECYCLE_STATES = ['newly_discovered', 'pending_validation', 'active', 'deprecated', 'unavailable', 'retired', 'incompatible'];
const ORIGIN_LABELS: Record<string, string> = { static: 'Curated catalog', live: 'Live-discovered', application: 'AI application' };
const PAGE_SIZE = 24;

function lifecycleTone(value: string | undefined): StatusName {
  if (value === 'active') return 'active';
  if (value === 'deprecated') return 'warning';
  if (value === 'unavailable' || value === 'retired' || value === 'incompatible') return 'unavailable';
  return 'pending';
}

function freshness(provider: RegistryProviderRefresh): { label: string; tone: StatusName } {
  if (!provider.last_success_at) return { label: 'Never refreshed', tone: 'unavailable' };
  return provider.stale ? { label: 'Stale', tone: 'warning' } : { label: 'Fresh', tone: 'success' };
}

function attemptTone(status: string | null | undefined): StatusName {
  if (status === 'success') return 'success';
  if (status === 'failed' || status === 'abandoned') return 'failed';
  if (status === 'running') return 'busy';
  return 'unavailable';
}

/* ------------------------------------------------------------------ *
 * Provider health, refresh controls, activity
 * ------------------------------------------------------------------ */

export function LiveRegistryPanel({
  status, adminToken, onAdminToken, onChanged,
}: {
  status: RegistryStatus | null;
  adminToken: string;
  onAdminToken: (token: string) => void;
  onChanged: () => void;
}) {
  const activity = useAsync((signal) => getRegistryActivity(signal), [status?.persistence_available], { enabled: Boolean(status?.persistence_available) });
  const [busy, setBusy] = useState<string | null>(null);
  const [results, setResults] = useState<RefreshResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [onlyIfStale, setOnlyIfStale] = useState(false);

  if (!status) return null;

  const run = async (provider: string | null) => {
    setBusy(provider ?? 'all');
    setError(null);
    try {
      setResults(await refreshRegistry(adminToken, provider, onlyIfStale));
      onChanged();
      activity.reload();
    } catch (cause) {
      setError(describeError(cause, 'The refresh could not be started.').message);
    } finally {
      setBusy(null);
    }
  };

  const canRefresh = Boolean(status.live_registry_enabled && status.admin_configured && adminToken.trim().length > 0);

  return (
    <section className="live-panel" aria-labelledby="live-panel-title">
      <div className="live-panel-heading">
        <div>
          <p className="registry-eyebrow">Live model pool</p>
          <h2 id="live-panel-title">Provider catalog health</h2>
        </div>
        {status.persistence_available ? <Tag>TTL {formatInteger(status.refresh_ttl_minutes)} min</Tag> : null}
      </div>

      {!status.live_registry_enabled ? (
        <Notice tone="neutral" title="Static catalog in use">
          Live discovery is switched off for this deployment. Curated provider-documentation snapshots remain available, and routing is unchanged.
          Enabling it requires the approved registry migration and <code>LIVE_REGISTRY_ENABLED</code>.
        </Notice>
      ) : !status.persistence_available ? (
        <Notice tone="warning" title="Live registry storage is unreachable" live="status">
          The static catalog is being used. Refresh history will return once the registry database is reachable.
        </Notice>
      ) : null}

      <div className="live-table-wrap">
        <table className="live-table">
          <caption className="sr-only">Provider catalog refresh status</caption>
          <thead>
            <tr><th scope="col">Provider</th><th scope="col">Credentials</th><th scope="col">Catalog</th><th scope="col">Last success</th>
              <th scope="col">Last attempt</th><th scope="col">Last result</th><th scope="col"><span className="sr-only">Actions</span></th></tr>
          </thead>
          <tbody>
            {status.providers.map((provider) => {
              const fresh = freshness(provider);
              return (
                <tr key={provider.provider}>
                  <th scope="row">{provider.display_name ?? humanizeToken(provider.provider)}</th>
                  <td>{provider.disabled ? <Status name="inactive">Disabled</Status> : provider.configured ? <Status name="success">Configured</Status> : <Status name="unavailable">Not configured</Status>}</td>
                  <td>{status.persistence_available ? <Status name={fresh.tone}>{fresh.label}</Status> : <span className="text-muted">{UNAVAILABLE}</span>}</td>
                  <td className="text-numeric">{formatTimestamp(provider.last_success_at)}</td>
                  <td>{provider.last_attempt_status ? <Status name={attemptTone(provider.last_attempt_status)}>{humanizeToken(provider.last_attempt_status)}</Status> : <span className="text-muted">None yet</span>}</td>
                  <td className="live-result">
                    {provider.error_message ?? (provider.entries_seen != null
                      ? `${formatInteger(provider.entries_seen)} listed · ${formatInteger(provider.entries_new)} new · ${formatInteger(provider.entries_changed)} changed · ${formatInteger(provider.entries_missing)} missing`
                      : UNAVAILABLE)}
                  </td>
                  <td>
                    <Button size="sm" variant="ghost" disabled={!canRefresh || !provider.configured || Boolean(provider.disabled)}
                      loading={busy === provider.provider} onClick={() => run(provider.provider)}>
                      Refresh<span className="sr-only"> {provider.display_name ?? provider.provider}</span>
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <details className="live-admin">
        <summary>Refresh controls</summary>
        <div className="live-admin-body">
          {!status.admin_configured ? (
            <p className="text-muted">Registry administration is not configured on this deployment (<code>REGISTRY_ADMIN_TOKEN</code> is unset), so refresh and verification are disabled.</p>
          ) : (
            <>
              <TextInput label="Registry administrator token" type="password" autoComplete="off" value={adminToken}
                onChange={(event) => onAdminToken(event.target.value)}
                hint="Held in memory for this tab only; never stored or shown again." />
              <label className="live-check">
                <input type="checkbox" checked={onlyIfStale} onChange={(event) => setOnlyIfStale(event.target.checked)} />
                Skip providers refreshed within the TTL
              </label>
              <Button size="sm" variant="secondary" leadingIcon={<RefreshCw />} disabled={!canRefresh} loading={busy === 'all'} onClick={() => run(null)}>
                Refresh all configured providers
              </Button>
            </>
          )}
          {error ? <Notice tone="danger" live="alert">{error}</Notice> : null}
          {results.length > 0 ? (
            <ul className="live-results" aria-live="polite">
              {results.map((result) => (
                <li key={result.provider}>
                  <strong>{humanizeToken(result.provider)}</strong>: {humanizeToken(result.status)}
                  {result.status === 'success' ? ` — ${formatInteger(result.entries_seen)} listed, ${formatInteger(result.entries_new)} new, ${formatInteger(result.entries_changed)} changed, ${formatInteger(result.entries_missing)} missing` : ''}
                  {result.status === 'failed' && result.error_code ? ` (${humanizeToken(result.error_code)})` : ''}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </details>

      {status.persistence_available ? (
        <div className="live-activity">
          <h3><History aria-hidden="true" /> Recent registry activity</h3>
          {activity.isInitialLoad ? <SkeletonTable rows={3} columns={3} /> : activity.error ? (
            <ErrorState compact title="Activity could not be loaded" message={activity.error.message} onRetry={activity.reload} />
          ) : (activity.data ?? []).length === 0 ? (
            <p className="text-muted">No registry activity has been recorded yet.</p>
          ) : (
            <ol className="live-activity-list">
              {(activity.data ?? []).slice(0, 12).map((item, index) => (
                <li key={`${item.occurred_at}-${index}`} data-kind={item.kind}>
                  <time dateTime={item.occurred_at}>{formatTimestamp(item.occurred_at)}</time>
                  <span>
                    {item.kind === 'refresh_failure'
                      ? <><strong>{humanizeToken(item.provider)}</strong> refresh {humanizeToken(item.event_type).toLowerCase()}{item.reason ? ` — ${item.reason}` : ''}</>
                      : <><strong>{item.model_id}</strong> · {humanizeToken(item.event_type)}{item.new_status ? ` → ${humanizeToken(item.new_status)}` : ''}{item.reason ? ` — ${item.reason}` : ''}</>}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </div>
      ) : null}
    </section>
  );
}

/* ------------------------------------------------------------------ *
 * Server-paged live catalogue
 * ------------------------------------------------------------------ */

export function LiveCatalogBrowser({ refreshKey, onInspect }: { refreshKey: number; onInspect: (model: ModelInfo) => void }) {
  const [search, setSearch] = useState('');
  const [provider, setProvider] = useState('all');
  const [origin, setOrigin] = useState('all');
  const [lifecycle, setLifecycle] = useState('all');
  const [eligible, setEligible] = useState('all');
  const [sort, setSort] = useState('provider');
  const [page, setPage] = useState(1);
  const debounced = useDebouncedValue(search, 250);

  useEffect(() => { setPage(1); }, [debounced, provider, origin, lifecycle, eligible, sort]);

  const catalog = useAsync(
    (signal) => getCatalog({
      search: debounced.trim(), provider, origin, lifecycle, sort, page, page_size: PAGE_SIZE,
      eligible: eligible === 'all' ? undefined : eligible === 'yes',
    }, signal),
    [debounced, provider, origin, lifecycle, eligible, sort, page, refreshKey],
  );

  const data = catalog.data;
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const providerOptions = useMemo(() => data?.providers ?? [], [data?.providers]);

  return (
    <section className="live-catalog" aria-labelledby="live-catalog-title">
      <div className="live-panel-heading">
        <div>
          <p className="registry-eyebrow">Unified catalogue</p>
          <h2 id="live-catalog-title">Search every registry entry</h2>
        </div>
        {data ? <span className="registry-discovery-count">{formatInteger(data.total)} match</span> : null}
      </div>

      {data ? (
        <dl className="live-summary">
          <div><dt>Total entries</dt><dd>{formatInteger(data.summary.total)}</dd></div>
          <div><dt>Curated</dt><dd>{formatInteger(data.summary.by_origin.static)}</dd></div>
          <div><dt>Live-discovered</dt><dd>{formatInteger(data.summary.by_origin.live)}</dd></div>
          <div><dt>Applications</dt><dd>{formatInteger(data.summary.by_origin.application)}</dd></div>
          <div><dt>Routing-eligible</dt><dd>{formatInteger(data.summary.routing_eligible)}</dd></div>
        </dl>
      ) : null}

      <div className="table-toolbar live-toolbar">
        <TextInput className="toolbar-search" label="Search catalogue" hideLabel type="search" placeholder="Name, id, provider or family"
          value={search} onChange={(event) => setSearch(event.target.value)} leadingIcon={<Search />} />
        <label className="toolbar-group registry-select-group"><span className="toolbar-label">Provider</span>
          <select className="registry-filter-select" value={provider} onChange={(event) => setProvider(event.target.value)}>
            <option value="all">All providers</option>{providerOptions.map((name) => <option key={name} value={name}>{name}</option>)}
          </select></label>
        <label className="toolbar-group registry-select-group"><span className="toolbar-label">Origin</span>
          <select className="registry-filter-select" value={origin} onChange={(event) => setOrigin(event.target.value)}>
            <option value="all">All origins</option>{Object.entries(ORIGIN_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select></label>
        <label className="toolbar-group registry-select-group"><span className="toolbar-label">Lifecycle</span>
          <select className="registry-filter-select" value={lifecycle} onChange={(event) => setLifecycle(event.target.value)}>
            <option value="all">All states</option>{LIFECYCLE_STATES.map((value) => <option key={value} value={value}>{humanizeToken(value)}</option>)}
          </select></label>
        <label className="toolbar-group registry-select-group"><span className="toolbar-label">Routing</span>
          <select className="registry-filter-select" value={eligible} onChange={(event) => setEligible(event.target.value)}>
            <option value="all">Any</option><option value="yes">Eligible</option><option value="no">Not eligible</option>
          </select></label>
        <label className="toolbar-group registry-select-group"><span className="toolbar-label">Sort</span>
          <select className="registry-filter-select" value={sort} onChange={(event) => setSort(event.target.value)}>
            <option value="provider">Provider</option><option value="name">Name</option><option value="context">Context window</option>
            <option value="lifecycle">Lifecycle</option><option value="eligibility">Routing eligibility</option>
          </select></label>
      </div>

      {catalog.isInitialLoad ? <SkeletonTable rows={6} columns={6} /> : catalog.error ? (
        <ErrorState title="The catalogue could not be loaded" message={catalog.error.message} hint={catalog.error.hint} onRetry={catalog.reload} />
      ) : data && data.items.length === 0 ? (
        <EmptyState iconName="search" title="No registry entries match" description="Adjust the search or filters. Live-discovered entries appear after an authorized provider refresh." />
      ) : data ? (
        <>
          <div className="live-table-wrap" aria-busy={catalog.isLoading || undefined}>
            <table className="live-table">
              <caption className="sr-only">Registry catalogue</caption>
              <thead><tr><th scope="col">Model</th><th scope="col">Origin</th><th scope="col">Lifecycle</th><th scope="col">Catalog</th>
                <th scope="col">Inference</th><th scope="col">Routing</th><th scope="col">Context</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>
                {data.items.map((model) => (
                  <tr key={`${model.provider}:${model.model_id}`}>
                    <th scope="row"><span className="cell-primary">{model.model_name}</span><p className="cell-sub">{model.provider} · {model.model_id}</p></th>
                    <td>{ORIGIN_LABELS[model.catalog_origin ?? 'static']}</td>
                    <td><Status name={lifecycleTone(model.lifecycle_status)}>{humanizeToken(model.lifecycle_status ?? 'unknown')}</Status></td>
                    <td>{humanizeToken(model.availability ?? 'unknown')}</td>
                    <td>{model.entry_type !== 'inference_model' ? <span className="text-muted">Not applicable</span>
                      : model.verification ? humanizeToken(model.verification.status) : 'Unverified'}</td>
                    <td>{model.entry_type !== 'inference_model' ? <span className="text-muted">Opened directly</span>
                      : model.eligibility?.eligible ? <Status name="success">Eligible</Status>
                        : <span title={model.eligibility?.reasons.map((reason) => reason.message).join(' ')}><Status name="inactive">Excluded</Status></span>}</td>
                    <td className="text-numeric">{model.context_window > 0 ? formatInteger(model.context_window) : UNAVAILABLE}</td>
                    <td><Button size="sm" variant="ghost" onClick={() => onInspect(model)}>Inspect<span className="sr-only"> {model.model_name}</span></Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <nav className="live-pager" aria-label="Catalogue pages">
            <Button size="sm" variant="secondary" disabled={page <= 1 || catalog.isLoading} onClick={() => setPage((value) => value - 1)}>Previous</Button>
            <span role="status">Page {formatInteger(page)} of {formatInteger(pages)}</span>
            <Button size="sm" variant="secondary" disabled={page >= pages || catalog.isLoading} onClick={() => setPage((value) => value + 1)}>Next</Button>
          </nav>
        </>
      ) : null}
    </section>
  );
}

/* ------------------------------------------------------------------ *
 * Registry section of the model detail modal
 * ------------------------------------------------------------------ */

export function RegistryDetailBlock({ model, adminToken }: { model: ModelInfo; adminToken: string }) {
  const isApi = model.entry_type === 'inference_model';
  const detail = useAsync((signal) => getModelDetail(model.provider, model.model_id, signal), [model.provider, model.model_id], { enabled: isApi });
  const [verifying, setVerifying] = useState(false);
  const [verifyMessage, setVerifyMessage] = useState<{ tone: 'success' | 'danger' | 'warning'; text: string } | null>(null);

  const entry = detail.data?.entry ?? model;
  const verify = async () => {
    setVerifying(true);
    setVerifyMessage(null);
    try {
      const result = await verifyModelInference(adminToken, model.provider, model.model_id);
      setVerifyMessage(result.status === 'validated'
        ? { tone: 'success', text: `Inference verified in ${formatInteger(result.latency_ms)} ms.` }
        : { tone: 'danger', text: `Verification failed (${humanizeToken(result.error_code ?? 'unknown')}).` });
      detail.reload();
    } catch (cause) {
      setVerifyMessage({ tone: 'warning', text: describeError(cause, 'Verification could not run.').message });
    } finally {
      setVerifying(false);
    }
  };

  if (!isApi) {
    return (
      <Notice tone="neutral" title="Not an API routing candidate">
        Applications and tools are opened at their destination. They are shown for discovery and are never selected for API inference.
      </Notice>
    );
  }

  const provenance = Object.entries(entry.metric_provenance ?? {});
  return (
    <div className="stack">
      <div>
        <p className="field-label">Routing eligibility</p>
        {entry.eligibility?.eligible ? (
          <Status name="success">Eligible for the routing pool</Status>
        ) : (
          <>
            <Status name="inactive">Excluded from the routing pool</Status>
            <ul className="live-reasons">
              {(entry.eligibility?.reasons ?? []).map((reason) => <li key={reason.code}><code>{reason.code}</code> — {reason.message}</li>)}
            </ul>
          </>
        )}
        {(entry.eligibility?.warnings ?? []).map((warning) => <p className="text-muted text-xs" key={warning.code}>{warning.message}</p>)}
      </div>

      <MetadataRow label="Lifecycle and access" columns="2">
        <MetadataEntry label="Lifecycle" value={humanizeToken(entry.lifecycle_status ?? 'unknown')} />
        <MetadataEntry label="Reason" value={entry.lifecycle_reason ?? UNAVAILABLE} />
        <MetadataEntry label="Catalog visibility" value={humanizeToken(entry.availability ?? 'unknown')} />
        <MetadataEntry label="Adapter compatible" value={entry.adapter_compatible ? 'Yes' : 'No'} />
        <MetadataEntry label="Inference verification" value={entry.verification ? `${humanizeToken(entry.verification.status)} · ${formatTimestamp(entry.verification.verified_at)}` : 'Not verified'} />
        <MetadataEntry label="Catalog last confirmed" value={formatTimestamp(entry.catalog_last_confirmed_at)} />
        <MetadataEntry label="First seen" value={formatTimestamp(entry.first_seen_at)} />
        <MetadataEntry label="Provider retirement" value={entry.retires_at ? formatTimestamp(entry.retires_at) : UNAVAILABLE} />
      </MetadataRow>

      {provenance.length > 0 ? (
        <div>
          <p className="field-label">Metadata provenance</p>
          <div className="row row-wrap">{provenance.map(([field, source]) => <Tag key={field}>{humanizeToken(field)}: {humanizeToken(source)}</Tag>)}</div>
        </div>
      ) : null}

      <div>
        <p className="field-label">Lifecycle history</p>
        {detail.isInitialLoad ? <p className="text-muted">Loading history…</p>
          : (detail.data?.lifecycle_history ?? []).length === 0 ? <p className="text-muted">No lifecycle events recorded.</p>
            : (
              <ol className="live-activity-list">
                {(detail.data?.lifecycle_history ?? []).map((event, index) => (
                  <li key={`${event.occurred_at}-${index}`}>
                    <time dateTime={event.occurred_at}>{formatTimestamp(event.occurred_at)}</time>
                    <span>{humanizeToken(event.event_type)}{event.previous_status ? ` · ${humanizeToken(event.previous_status)} →` : ' ·'} {humanizeToken(event.new_status)}{event.reason ? ` — ${event.reason}` : ''}</span>
                  </li>
                ))}
              </ol>
            )}
      </div>

      {adminToken.trim() ? (
        <div>
          <Button size="sm" variant="secondary" leadingIcon={<ShieldCheck />} loading={verifying} onClick={verify}>Verify inference access</Button>
          <p className="text-muted text-xs">Makes one minimal provider call for this model only. It is never run automatically.</p>
          {verifyMessage ? <Notice tone={verifyMessage.tone} live="status">{verifyMessage.text}</Notice> : null}
        </div>
      ) : null}
    </div>
  );
}
