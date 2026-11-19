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
import { Info, Lock } from 'lucide-react';
import { Grid, Page, SectionHeader, StatusPill, Surface } from '../components/ui/ds';
import { Button, ButtonLink } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { TextInput } from '../components/ui/Input';
import { Slider } from '../components/ui/Slider';
import { Avatar, SaveStateBar } from '../components/ui/Controls';
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

  const total = OBJECTIVES.reduce((sum, objective) => sum + preferences[objective.key], 0);
  const share = (key: keyof RoutingPreferences) => (total > 0 ? preferences[key] / total : 0);
  const customised = user.preferences_customized;

  return (
    <Page className="pf">
      <Surface variant="glass" className="pf-hero" aria-labelledby="pf-title">
        <Avatar name={user.name} />
        <div className="pf-hero-main">
          <p className="ds-kicker">Account</p>
          <h1 id="pf-title">{name.trim().length > 0 ? name : user.name}</h1>
          <p className="pf-email">{user.email}</p>
          <div className="pf-pills">
            <StatusPill tone="primary" icon={<Lock />}>{groupLabel(user.user_group)}</StatusPill>
            <StatusPill tone="success">Verified</StatusPill>
            <StatusPill>{customised ? 'Custom priorities' : 'Group default priorities'}</StatusPill>
          </div>
        </div>
        <p className="pf-hero-note">Your user group and priorities are resolved from your session on every query, so they are never part of a routing request.</p>
      </Surface>

      <Grid ratio="2-1" className="pf-grid">
        <Surface className="pf-card" aria-labelledby="pf-priorities">
          <SectionHeader
            id="pf-priorities" kicker="Routing" title="Routing priorities"
            description="How much each objective matters to you. The router normalises these into weights before scoring, so their relative order is what counts."
            actions={<Badge tone="neutral" outline>{customised ? 'Customised' : 'Group defaults'}</Badge>}
          />
          <div className="pf-split" role="img" aria-label={`Resulting weight split: ${OBJECTIVES.map((o) => `${o.shortLabel} ${Math.round(share(o.key) * 100)}%`).join(', ')}`}>
            {OBJECTIVES.map((objective, i) => (
              <i key={objective.key} style={{ flex: `${Math.max(share(objective.key) * 100, 0.1)} 1 0` }} data-i={i} title={`${objective.shortLabel}: ${Math.round(share(objective.key) * 100)}% of total weight`} />
            ))}
          </div>
          <ul className="pf-split-legend" aria-hidden="true">
            {OBJECTIVES.map((objective, i) => (
              <li key={objective.key}><span data-i={i} />{objective.shortLabel} <b>{Math.round(share(objective.key) * 100)}%</b></li>
            ))}
          </ul>
          <div className="slider-grid pf-sliders">
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
            {OBJECTIVES.map((objective) => `${objective.shortLabel.toLowerCase()} ${formatPercent(user.routing_preferences[objective.key], 0)}`).join(' · ')}
            . Discarding your changes restores these values.
          </p>
          <SaveStateBar
            state={saveState}
            message={message || undefined}
            onSave={() => void save()}
            onReset={reset}
            saveLabel="Save priorities"
          />
        </Surface>

        <div className="pf-col">
          <Surface className="pf-card" aria-labelledby="pf-account">
            <SectionHeader id="pf-account" kicker="Account" title="Display name" description="Shown in the header and in routing explanations. Your email cannot be changed here." />
            <TextInput
              label="Display name"
              hideLabel
              value={name}
              onChange={(event) => setName(event.target.value)}
              error={nameError}
              autoComplete="name"
              disabled={busy}
            />
            <div className="row">
              <Button variant="secondary" size="sm" onClick={() => void saveName()} disabled={!nameChanged || busy} loading={busy}>
                Save name
              </Button>
            </div>
          </Surface>

          <Surface className="pf-card" aria-labelledby="pf-group">
            <SectionHeader id="pf-group" kicker="Fixed at sign-up" title={groupLabel(user.user_group)} description={groupDescription(user.user_group)} />
            <Notice tone="neutral" icon={<Info />} title="Why this cannot be changed here">
              The backend treats the user group as the source of truth for every routing request and rejects a group supplied per query. Changing it would mean creating a new account.
            </Notice>
          </Surface>

          <Surface className="pf-card" variant="quiet" aria-labelledby="pf-session">
            <SectionHeader id="pf-session" kicker="Session" title="Where things live" />
            <p className="inline-note">
              Tokens and provider credentials are never displayed here. Appearance, text size, contrast and motion are in{' '}
              <Link to="/settings" className="text-link">Settings</Link>.
            </p>
            <div className="row row-wrap">
              <ButtonLink to="/settings" variant="secondary" size="sm">Open settings</ButtonLink>
              <ButtonLink to="/route" variant="ghost" size="sm">Route a request</ButtonLink>
            </div>
          </Surface>
        </div>
      </Grid>
    </Page>
  );
}
