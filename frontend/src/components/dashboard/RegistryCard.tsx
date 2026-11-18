import { RefreshCw } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Reveal } from '../ui/Reveal';
import { Status } from '../ui/Badge';
import { ErrorState } from '../ui/EmptyState';
import { humanizeToken } from '../../utils/format';
import type { RegistryProviderRefresh, RegistryStatus } from '../../types';
import { timeAgo } from './insights';
import { providerName } from './DistributionCards';

function refreshState(p: RegistryProviderRefresh): { name: 'active' | 'inactive'; label: string } {
  if (p.disabled) return { name: 'inactive', label: 'Disabled' };
  if (p.configured === false) return { name: 'inactive', label: 'Not configured' };
  if (p.last_attempt_status === 'failed' || p.status === 'failed') return { name: 'inactive', label: 'Last refresh failed' };
  if (p.last_success_at) return { name: 'active', label: p.stale ? 'Stale' : 'Fresh' };
  return { name: 'inactive', label: 'Never refreshed' };
}

export function RegistryCard({ status, error, loading, onRetry }: { status: RegistryStatus | null; error: string | null; loading: boolean; onRetry: () => void }) {
  return (
    <Reveal as="section" className="cx-card" delay={3} ariaLabelledBy="reg-title">
      <header className="cx-card-head">
        <div><p className="cx-kicker">Registry</p><h2 id="reg-title">Provider refresh status</h2></div>
        <Link to="/models" className="cx-link">Model pool</Link>
      </header>
      {loading ? (
        <p className="cx-muted" role="status">Loading registry status…</p>
      ) : error ? (
        <ErrorState title="Registry status unavailable" message={error} compact onRetry={onRetry} />
      ) : status ? (
        <>
          <p className="cx-pills">
            <span data-on={status.live_registry_enabled ? 'true' : 'false'}>Live registry {status.live_registry_enabled ? 'on' : 'off'}</span>
            <span data-on={status.persistence_available ? 'true' : 'false'}>Persistence {status.persistence_available ? 'available' : 'unavailable'}</span>
            {typeof status.refresh_ttl_minutes === 'number' ? <span data-on="true">TTL {status.refresh_ttl_minutes} min</span> : null}
          </p>
          {status.providers.length === 0 ? (
            <p className="cx-muted">No provider refresh has been recorded yet.</p>
          ) : (
            <ul className="cx-rows">
              {status.providers.map((p) => {
                const s = refreshState(p);
                const when = timeAgo(p.last_success_at);
                return (
                  <li key={p.provider}>
                    <span className="cx-row-main"><strong>{p.display_name ?? providerName(p.provider)}</strong><span>{when ? `Last success ${when}` : p.error_code ? humanizeToken(p.error_code) : 'No successful refresh yet'}</span></span>
                    <Status name={s.name}>{s.label}</Status>
                  </li>
                );
              })}
            </ul>
          )}
        </>
      ) : null}
      <p className="cx-note"><RefreshCw aria-hidden="true" /> Refreshes are run from the model pool by an administrator.</p>
    </Reveal>
  );
}
