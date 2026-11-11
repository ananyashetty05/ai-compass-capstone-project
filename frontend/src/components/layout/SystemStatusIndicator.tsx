/**
 * System status control in the header.
 *
 * Reports only what `/health` returns: whether the backend is
 * reachable and whether each provider holds a server-side credential.
 * Provider keys are never exposed or requested.
 */
import { useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { Status } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Modal } from '../ui/Modal';
import { EmptyState } from '../ui/EmptyState';
import { useSystemStatus } from '../../context/systemStatusContext';
import { formatTimestamp } from '../../utils/format';

const STATE_LABEL = {
  online: 'Operational',
  degraded: 'Degraded',
  offline: 'Unreachable',
  unknown: 'Unknown',
} as const;

const STATE_NAME = {
  online: 'online',
  degraded: 'warning',
  offline: 'offline',
  unknown: 'unavailable',
} as const;

export function SystemStatusIndicator() {
  const { state, providers, isChecking, error, lastCheckedAt, refresh } = useSystemStatus();
  const [open, setOpen] = useState(false);

  return (
    <>
      <div className="header-status">
        <button
          type="button"
          className="status-button"
          onClick={() => setOpen(true)}
          aria-haspopup="dialog"
          title="View system status details"
        >
          <Status name={STATE_NAME[state]} busy={isChecking}>
            {STATE_LABEL[state]}
          </Status>
        </button>
      </div>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="System status"
        description="Live health of the routing backend and its configured providers."
        footer={
          <>
            <p className="text-xs text-muted">
              {lastCheckedAt ? `Last checked ${formatTimestamp(lastCheckedAt.toISOString())}` : 'Not yet checked'}
            </p>
            <Button variant="secondary" size="sm" leadingIcon={<RefreshCw />} onClick={() => void refresh()} loading={isChecking}>
              Refresh
            </Button>
          </>
        }
      >
        {error ? (
          <EmptyState
            iconName="offline"
            align="start"
            title="The backend could not be reached"
            description={error}
            action={
              <Button variant="secondary" size="sm" leadingIcon={<RefreshCw />} onClick={() => void refresh()}>
                Try again
              </Button>
            }
          />
        ) : providers.length === 0 ? (
          <EmptyState align="start" title="No provider data" description="The backend returned no provider configuration." />
        ) : (
          <ul className="status-list" data-layout="stacked">
            {providers.map((provider) => (
              <li key={provider.id}>
                <div className="status-list-name">
                  <span>{provider.label}</span>
                  <span className="sr-only">{provider.detail}</span>
                </div>
                <Status name={STATE_NAME[provider.state]}>{STATE_LABEL[provider.state]}</Status>
                <p className="status-list-detail">{provider.detail}</p>
              </li>
            ))}
          </ul>
        )}
      </Modal>
    </>
  );
}
