/**
 * Settings.
 *
 * Appearance and accessibility settings write through to the account
 * immediately, so they are applied by their providers and reflected here
 * rather than staged behind a save button. Everything else on this page
 * is a read-only report of what the backend told us.
 *
 * The categories are listed on the left and the selected one shown on
 * the right. Each category is independent, so only one needs to be on
 * screen at a time — but the left rail keeps the whole configuration
 * discoverable without scrolling past a long page.
 */
import { useEffect, useState } from 'react';
import {
  Accessibility,
  Database,
  Info,
  LogOut,
  Monitor,
  Moon,
  Palette,
  PlugZap,
  RefreshCw,
  Server,
  Sun,
  Terminal,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { PageHeader } from '../components/layout/PageHeader';
import { Button } from '../components/ui/Button';
import { Badge, Status, Tag } from '../components/ui/Badge';
import type { StatusName } from '../components/ui/Badge';
import { Card, CardBody, CardHeader } from '../components/ui/Card';
import { MetadataEntry, MetadataRow } from '../components/ui/Metadata';
import { SwitchRow } from '../components/ui/Controls';
import { Segmented } from '../components/ui/Skeleton';
import { Notice } from '../components/ui/EmptyState';
import { useAccessibility } from '../context/accessibilityContext';
import { useTheme } from '../context/themeContext';
import { useSystemStatus } from '../context/systemStatusContext';
import { useAuth } from '../context/authContext';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { useToast } from '../context/toastContext';
import { API_BASE_URL, IS_DEVELOPMENT_FALLBACK } from '../services/http';
import { ROUTING_HISTORY_ENDPOINT } from '../services/history.service';
import { formatTimestamp } from '../utils/format';
import type { FontSizePreference, HealthState, ThemePreference } from '../types';

type SectionId = 'appearance' | 'accessibility' | 'status' | 'connection' | 'limits' | 'sources' | 'session';

const SECTIONS: { id: SectionId; label: string; description: string; icon: LucideIcon }[] = [
  { id: 'appearance', label: 'Appearance', description: 'Theme, applied immediately.', icon: Palette },
  { id: 'accessibility', label: 'Accessibility', description: 'Text size, motion and contrast.', icon: Accessibility },
  { id: 'status', label: 'Backend status', description: 'Provider connectivity from /health.', icon: PlugZap },
  { id: 'connection', label: 'API connection', description: 'The endpoint this build talks to.', icon: Server },
  { id: 'limits', label: 'Capabilities', description: 'What this interface can and cannot show.', icon: Info },
  { id: 'sources', label: 'Data sources', description: 'Registry figures and where they come from.', icon: Database },
  { id: 'session', label: 'Session', description: 'Sign out of this account.', icon: Terminal },
];

export function SettingsPage() {
  useDocumentTitle('Settings · AI Compass');
  const { preference, resolved, setPreference } = useTheme();
  const accessibility = useAccessibility();
  const { state, providers, isChecking, error, lastCheckedAt, refresh } = useSystemStatus();
  const { signOut } = useAuth();
  const { push } = useToast();
  const [section, setSection] = useState<SectionId>('appearance');
  const [confirmSignOut, setConfirmSignOut] = useState(false);

  // A short-lived confirmation for sign-out, since it is destructive
  // and immediately ends the session.
  useEffect(() => {
    if (!confirmSignOut) return;
    const timer = window.setTimeout(() => setConfirmSignOut(false), 6000);
    return () => window.clearTimeout(timer);
  }, [confirmSignOut]);

  const active = SECTIONS.find((entry) => entry.id === section) ?? SECTIONS[0];

  return (
    <>
      <PageHeader
        eyebrow="Configuration"
        title="Settings"
        description="Display and accessibility preferences are saved to your account. Everything else is reported by the backend."
        actions={
          <Button variant="secondary" size="sm" onClick={refresh} loading={isChecking} leadingIcon={<RefreshCw />}>
            Recheck status
          </Button>
        }
      />

      <div className="settings-layout">
        <nav className="settings-nav" aria-label="Settings categories">
          <ul className="nav-list">
            {SECTIONS.map((entry) => {
              const Icon = entry.icon;
              const current = entry.id === section;
              return (
                <li key={entry.id}>
                  <button
                    type="button"
                    className="nav-link"
                    aria-current={current ? 'page' : undefined}
                    onClick={() => setSection(entry.id)}
                  >
                    <Icon aria-hidden="true" />
                    <span className="settings-nav-text">
                      <span className="settings-nav-label">{entry.label}</span>
                      <span className="settings-nav-description">{entry.description}</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="settings-panel">
          <p className="settings-panel-intro">{active.description}</p>

          {section === 'appearance' ? (
            <Card>
              <CardHeader title="Theme" compact icon={<Palette />} description="Applied immediately and saved to your account." />
              <CardBody>
                <div className="field">
                  <Segmented<ThemePreference>
                    label="Theme"
                    value={preference}
                    onChange={(next) => setPreference(next)}
                    options={[
                      { value: 'light', label: 'Light', icon: <Sun /> },
                      { value: 'dark', label: 'Dark', icon: <Moon /> },
                      { value: 'system', label: 'System', icon: <Monitor /> },
                    ]}
                  />
                  <p className="field-hint">
                    Currently rendering in {resolved} mode
                    {preference === 'system' ? ', following your operating system setting.' : '.'}
                  </p>
                </div>
              </CardBody>
            </Card>
          ) : null}

          {section === 'accessibility' ? (
            <Card>
              <CardHeader
                title="Accessibility"
                compact
                icon={<Accessibility />}
                description="Also applied immediately and saved to your account."
              />
              <CardBody>
                <div className="field">
                  <span className="field-label" id="text-size-label">
                    Text size
                  </span>
                  <Segmented<FontSizePreference>
                    label="Text size"
                    value={accessibility.preferences.font_size}
                    onChange={accessibility.setTextSize}
                    options={[
                      { value: 'small', label: 'Small' },
                      { value: 'default', label: 'Default' },
                      { value: 'large', label: 'Large' },
                    ]}
                  />
                  <p className="field-hint">Scales all text through the interface. Your browser zoom still works too.</p>
                </div>
                <SwitchRow
                  checked={accessibility.preferences.reduced_motion}
                  onChange={accessibility.setReducedMotion}
                  label="Reduce motion"
                  description="Removes transitions and animation."
                />
                <SwitchRow
                  checked={accessibility.preferences.high_contrast}
                  onChange={accessibility.setHighContrast}
                  label="High contrast"
                  description="Increases the contrast between text, borders and surfaces."
                />
                <div className="row">
                  <Button size="sm" variant="ghost" onClick={accessibility.reset}>
                    Reset to defaults
                  </Button>
                </div>
              </CardBody>
            </Card>
          ) : null}

          {section === 'status' ? (
            <Card>
              <CardHeader
                title="Backend status"
                compact
                description="Reported by GET /health. This interface never requests, displays or stores provider credentials."
                icon={<PlugZap />}
                actions={<Status name={statusName(state)}>{stateLabel(state)}</Status>}
              />
              <CardBody>
                {error ? (
                  <Notice tone="danger" title="Status unavailable">
                    {error}
                  </Notice>
                ) : null}
                <div className="table-wrap">
                  <table className="data-table">
                    <caption className="sr-only">Provider connectivity as reported by the health endpoint</caption>
                    <thead>
                      <tr>
                        <th scope="col">Provider</th>
                        <th scope="col">State</th>
                        <th scope="col">Detail</th>
                        <th scope="col">Credential configured</th>
                      </tr>
                    </thead>
                    <tbody>
                      {providers.map((provider) => (
                        <tr key={provider.id}>
                          <th scope="row" className="cell-row-head">
                            {provider.label}
                          </th>
                          <td>
                            <Status name={statusName(provider.state)}>{stateLabel(provider.state)}</Status>
                          </td>
                          <td>{provider.detail}</td>
                          <td>
                            {provider.status.credential_configured ? (
                              <Badge tone="success" outline>
                                Yes
                              </Badge>
                            ) : (
                              <Badge tone="neutral" outline>
                                No
                              </Badge>
                            )}
                          </td>
                        </tr>
                      ))}
                      {providers.length === 0 ? (
                        <tr>
                          <td colSpan={4} className="text-muted">
                            No provider status was reported.
                          </td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
                <p className="inline-note">
                  Checked {lastCheckedAt ? formatTimestamp(lastCheckedAt.toISOString()) : 'not yet'}. A provider without a
                  configured credential cannot be selected, so routing reports an error rather than substituting another
                  model without telling you.
                </p>
              </CardBody>
            </Card>
          ) : null}

          {section === 'connection' ? (
            <Card>
              <CardHeader
                title="API connection"
                compact
                description="The endpoint this interface talks to."
                icon={<Server />}
              />
              <CardBody>
                <MetadataRow label="API connection">
                  <MetadataEntry label="Base URL" value={<span className="mono">{API_BASE_URL}</span>} />
                  <MetadataEntry
                    label="Source"
                    value={IS_DEVELOPMENT_FALLBACK ? 'VITE_API_BASE_URL not set — using the local default' : 'VITE_API_BASE_URL'}
                  />
                  <MetadataEntry
                    label="Interactive API docs"
                    value={
                      <a
                        className="text-link"
                        href={`${API_BASE_URL.replace(/\/api\/v1\/?$/, '')}/docs`}
                        target="_blank"
                        rel="noreferrer noopener"
                      >
                        Open in a new tab
                      </a>
                    }
                  />
                </MetadataRow>
                {IS_DEVELOPMENT_FALLBACK ? (
                  <Notice tone="info" title="Development default in use">
                    Set <code>VITE_API_BASE_URL</code> in a <code>.env</code> file to point this build at another backend.
                  </Notice>
                ) : null}
              </CardBody>
            </Card>
          ) : null}

          {section === 'limits' ? (
            <Card>
              <CardHeader
                title="Capabilities and limits"
                compact
                description="What this interface can and cannot show, stated plainly."
                icon={<Info />}
              />
              <CardBody>
                <ul className="reason-list">
                  <li>
                    Routing history: this backend build does not expose{' '}
                    <code className="mono">{ROUTING_HISTORY_ENDPOINT}</code>, so no history is listed. A result stays
                    available in this session only.
                  </li>
                  <li>Model quality, cost and latency come from registry metadata, not from live benchmarks.</li>
                  <li>Evaluation Lab compares routing decisions offline using registry metadata and does not call providers.</li>
                  <li>Provider credentials are never sent to the browser.</li>
                </ul>
              </CardBody>
            </Card>
          ) : null}

          {section === 'sources' ? (
            <Card>
              <CardHeader
                title="Data sources"
                compact
                description="Registry figures are derived from the locally stored RouterBench data. The figures below describe the dataset, not a benchmark run."
                icon={<Database />}
              />
              <CardBody>
                <div className="grid grid-3">
                  {DATASETS.map((dataset) => (
                    <div key={dataset.name} className="record-card">
                      <p className="record-title">{dataset.name}</p>
                      <p className="inline-note">{dataset.shape}</p>
                      <p className="inline-note">{dataset.note}</p>
                    </div>
                  ))}
                </div>
                <p className="inline-note">
                  Stored under <code className="mono">data/</code> in the backend. The interface reads these figures
                  through <code className="mono">GET /models</code> only.
                </p>
              </CardBody>
            </Card>
          ) : null}

          {section === 'session' ? (
            <Card>
              <CardHeader
                title="Session"
                compact
                description="Signing out discards the in-memory routing result for this session."
                icon={<Terminal />}
              />
              <CardBody>
                <div className="row row-wrap">
                  {confirmSignOut ? (
                    <>
                      <Button
                        variant="danger"
                        leadingIcon={<LogOut />}
                        onClick={() => {
                          setConfirmSignOut(false);
                          signOut();
                          push({ tone: 'info', title: 'Signed out' });
                        }}
                      >
                        Confirm sign out
                      </Button>
                      <Button variant="ghost" onClick={() => setConfirmSignOut(false)}>
                        Cancel
                      </Button>
                    </>
                  ) : (
                    <Button variant="secondary" leadingIcon={<LogOut />} onClick={() => setConfirmSignOut(true)}>
                      Sign out
                    </Button>
                  )}
                  <Tag>Token stored under aicompass.auth.token</Tag>
                </div>
              </CardBody>
            </Card>
          ) : null}
        </div>
      </div>
    </>
  );
}

const DATASETS = [
  { name: 'RouterBench raw', shape: '401,467 rows × 8 columns', note: '11 models, prompt/response pairs' },
  { name: 'RouterBench 0-shot', shape: '36,497 rows × 37 columns', note: 'Per-model performance and cost' },
  { name: 'RouterBench 5-shot', shape: '36,511 rows × 37 columns', note: 'Per-model performance and cost' },
];

/**
 * The health endpoint reports `degraded`, which has no matching status
 * glyph, so it is presented as a warning rather than silently
 * downgraded to an online or offline state.
 */
function statusName(state: HealthState): StatusName {
  if (state === 'degraded') return 'warning';
  if (state === 'unknown') return 'unavailable';
  return state;
}

function stateLabel(state: HealthState): string {
  switch (state) {
    case 'online':
      return 'Reachable';
    case 'degraded':
      return 'Degraded';
    case 'offline':
      return 'Offline';
    default:
      return 'Unknown';
  }
}
