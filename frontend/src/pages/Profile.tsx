/**
 * Profile.
 *
 * The account's user group is fixed at registration and is shown as
 * read-only context — the router reads it from the session, so it
 * cannot be changed here. Routing preferences are the only values this
 * page writes, through `PUT /profile/preferences`. Appearance and
 * accessibility are owned by their own providers and live in Settings.
 */
import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import { Info, Lock, SlidersHorizontal, UserCog } from 'lucide-react';
import { PageHeader } from '../components/layout/PageHeader';
import { Button, ButtonLink } from '../components/ui/Button';
import { Badge, Status } from '../components/ui/Badge';
import { Card, CardBody, CardHeader } from '../components/ui/Card';
import { MetadataEntry, MetadataRow } from '../components/ui/Metadata';
import { TextInput } from '../components/ui/Input';
import { Slider } from '../components/ui/Slider';
import { SaveStateBar } from '../components/ui/Controls';
import type { SaveState } from '../components/ui/Controls';
import { AppLoading } from '../components/ui/Spinner';
import { Notice } from '../components/ui/EmptyState';
import { useAuth } from '../context/authContext';
import { useToast } from '../context/toastContext';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { OBJECTIVES, groupDescription, groupLabel } from '../utils/domain';
import { formatPercent } from '../utils/format';
import type { RoutingPreferences } from '../types';

export function Profile() {
  useDocumentTitle('Profile · AI Compass');
  const { user, patchProfile } = useAuth();
  const { push } = useToast();

  // Seed from the profile we already have. `seededFrom` below starts out
  // equal to `user`, so the re-seed branch only runs for *later* changes;
  // without this initialiser the editor would never be seeded and the
  // page would render nothing.
  const [preferences, setPreferences] = useState<RoutingPreferences | null>(
    user ? { ...user.routing_preferences } : null,
  );
  const [name, setName] = useState(user?.name ?? '');
  const [saveState, setSaveState] = useState<SaveState>('idle');
  const [message, setMessage] = useState<string>('');
  const [nameError, setNameError] = useState<string | null>(null);

  // Re-seed the editor whenever the server profile changes. Adjusting
  // state during render (rather than in an effect) means the form never
  // shows a frame of stale values after a save from another surface.
  const [seededFrom, setSeededFrom] = useState(user);
  if (user && user !== seededFrom) {
    setSeededFrom(user);
    const incoming = user.routing_preferences;
    const moved =
      preferences === null || OBJECTIVES.some((objective) => preferences[objective.key] !== incoming[objective.key]);
    setPreferences({ ...incoming });
    setName(user.name);
    // Our own successful save also replaces the profile object, but it
    // does not move the priorities — so only reset the form's save state
    // when the values genuinely differ, and keep the confirmation the
    // user just earned.
    if (moved) {
      setSaveState('idle');
      setMessage('');
    }
  }

  const nameDirty = (user?.name ?? '') !== name.trim();
  const nameChanged = nameDirty && name.trim().length > 0;
  const busy = saveState === 'saving';

  const update = useCallback((key: keyof RoutingPreferences, value: number) => {
    setPreferences((current) => (current ? { ...current, [key]: value } : current));
    setSaveState('dirty');
  }, []);

  const save = useCallback(async () => {
    if (!user || !preferences || busy) return;
    setSaveState('saving');
    setMessage('');
    // `patchProfile` updates the shared profile the moment the request
    // succeeds, so every other surface sees the new priorities without a
    // refresh, and a rejection rolls the shared copy back on its own.
    const result = await patchProfile({ routing_preferences: preferences });
    if (result.ok === true) {
      setSaveState('saved');
      setMessage('Routing priorities saved. They apply to your next query.');
      push({ tone: 'success', title: 'Priorities saved' });
    } else {
      setSaveState('error');
      setMessage(result.message);
    }
  }, [busy, patchProfile, preferences, push, user]);

  const saveName = useCallback(async () => {
    if (!nameChanged || busy) return;
    if (name.trim().length < 1) {
      setNameError('Enter a name.');
      return;
    }
    setNameError(null);
    const result = await patchProfile({ name: name.trim() });
    if (result.ok === true) {
      push({ tone: 'success', title: 'Name updated' });
    } else {
      push({ tone: 'danger', title: 'Name not saved', description: result.message });
    }
  }, [busy, name, nameChanged, patchProfile, push]);

  const reset = useCallback(() => {
    if (!user) return;
    setPreferences({ ...user.routing_preferences });
    setSaveState('idle');
    setMessage('');
  }, [user]);

  // `RequireAuth` already guarantees a profile, but never render an
  // empty document if that ever stops being true.
  if (!user || !preferences) return <AppLoading label="Loading your profile…" />;

  return (
    <>
      <PageHeader
        eyebrow="Account"
        title="Your routing profile"
        description="Your user group and routing priorities are resolved from your session on every query, so they are never part of a routing request."
      />

      <div className="page-body">
        <div className="split">
          <Card>
            <CardHeader
              title="Account"
              compact
              description="Your name is stored with your account; your email cannot be changed here."
            />
            <CardBody>
              <MetadataRow label="Account details" columns="2">
                <MetadataEntry label="Name" value={name.trim().length > 0 ? name : 'Unavailable'} />
                <MetadataEntry label="Email" value={user.email} />
                <MetadataEntry
                  label="Account"
                  value="Active"
                  suffix={<Status name="active">Verified</Status>}
                />
                <MetadataEntry
                  label="Priorities"
                  value={user.preferences_customized ? 'Customised' : 'Group defaults'}
                />
              </MetadataRow>

              <div className="field">
                <TextInput
                  label="Display name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  error={nameError}
                  hint="Shown in the header and in routing explanations."
                  autoComplete="name"
                  disabled={busy}
                />
                <div className="row">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => void saveName()}
                    disabled={!nameChanged || busy}
                    loading={busy}
                  >
                    Save name
                  </Button>
                </div>
              </div>
            </CardBody>
          </Card>

          <Card tone="primary">
            <CardHeader
              title="User group"
              compact
              description="Fixed when the account was created."
              icon={<Lock />}
            />
            <CardBody>
              <p className="eyebrow">Routing as</p>
              <p className="account-group-name">{groupLabel(user.user_group)}</p>
              <p className="text-secondary">{groupDescription(user.user_group)}</p>
              <Notice tone="neutral" icon={<Info />} title="Why this cannot be changed here">
                The backend treats the user group as the source of truth for every routing request and rejects a group
                supplied per query. Changing it would mean creating a new account.
              </Notice>
            </CardBody>
          </Card>
        </div>

        <Card>
          <CardHeader
            title="Routing priorities"
            compact
            description="How much each objective matters to you. The router normalises these into weights before scoring, so their relative order is what counts."
            icon={<SlidersHorizontal />}
            actions={
              user.preferences_customized ? (
                <Badge tone="neutral" outline>
                  Customised
                </Badge>
              ) : (
                <Badge tone="neutral" outline>
                  Group defaults
                </Badge>
              )
            }
          />
          <CardBody>
            <div className="stack">
              {OBJECTIVES.map((objective) => (
                <Slider
                  key={objective.key}
                  label={objective.label}
                  value={preferences[objective.key]}
                  onChange={(value) => update(objective.key, value)}
                  description={objective.description}
                  formatValue={(value) => formatPercent(value, 0)}
                  disabled={busy}
                />
              ))}
            </div>

            <p className="inline-note">
              Currently saved for {groupLabel(user.user_group)}:{' '}
              {OBJECTIVES.map((objective) => `${objective.shortLabel.toLowerCase()} ${formatPercent(user.routing_preferences[objective.key], 0)}`).join(
                ' · ',
              )}
              . Discarding your changes restores these values, which are your group's defaults until you save a change.
            </p>

            <SaveStateBar
              state={saveState}
              message={message || undefined}
              onSave={() => void save()}
              onReset={reset}
              saveLabel="Save priorities"
            />
          </CardBody>
        </Card>

        <Card tone="muted">
          <CardHeader
            title="Session"
            compact
            description="Tokens and provider credentials are never displayed in this interface."
            icon={<UserCog />}
          />
          <CardBody>
            <p className="inline-note">
              This page shows the profile the backend returned for your session. It does not display the session token,
              and provider credentials stay on the server. Appearance, text size, contrast and motion settings live in{' '}
              <Link to="/settings" className="text-link">
                Settings
              </Link>
              .
            </p>
            <div className="row row-wrap">
              <ButtonLink to="/settings" variant="secondary" size="sm">
                Open settings
              </ButtonLink>
              <ButtonLink to="/route" variant="ghost" size="sm">
                Route a request
              </ButtonLink>
            </div>
          </CardBody>
        </Card>
      </div>
    </>
  );
}
