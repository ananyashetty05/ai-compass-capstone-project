/**
 * Onboarding — account creation in three steps.
 *
 * 1. Account details.
 * 2. User group, loaded from `GET /profile/groups`. The group is fixed
 *    here and is never selectable again: the backend treats it as the
 *    source of truth and the router resolves it from the JWT.
 * 3. Routing preferences, seeded from
 *    `GET /profile/group-defaults/{group}` and adjustable before the
 *    account is created. Weights are normalised by the router, so the
 *    user is told they are relative priorities rather than percentages
 *    of a budget.
 */
import { useCallback, useId, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, ArrowRight, Check, UserCog } from 'lucide-react';
import { AuthLayout } from '../components/layout/AuthLayout';
import { Button } from '../components/ui/Button';
import { Card, CardBody, CardHeader } from '../components/ui/Card';
import { TextInput } from '../components/ui/Input';
import { Slider } from '../components/ui/Slider';
import { SkeletonBlock } from '../components/ui/Skeleton';
import { ErrorState, Notice } from '../components/ui/EmptyState';
import { useAsync } from '../hooks/useAsync';
import { useAuth } from '../context/authContext';
import { getGroupDefaults, getGroupOptions } from '../services/auth.service';
import { describeError } from '../services/http';
import { OBJECTIVES, groupDescription, groupLabel } from '../utils/domain';
import { formatPercent } from '../utils/format';
import type { GroupDefaults, RoutingPreferences, UserGroup } from '../types';

type Step = 'account' | 'group' | 'preferences';

const STEPS: { id: Step; label: string }[] = [
  { id: 'account', label: 'Account' },
  { id: 'group', label: 'User group' },
  { id: 'preferences', label: 'Priorities' },
];

export function Onboarding() {
  const { signUp } = useAuth();
  const navigate = useNavigate();

  const [step, setStep] = useState<Step>('account');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [group, setGroup] = useState<UserGroup | null>(null);
  const [preferences, setPreferences] = useState<RoutingPreferences | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<{ message: string; hint?: string } | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [loadingDefaults, setLoadingDefaults] = useState(false);
  const [defaultsError, setDefaultsError] = useState<{ message: string; hint?: string } | null>(null);
  const headingId = useId();

  const groups = useAsync((signal) => getGroupOptions(signal), [], { enabled: step === 'group' });

  // `chooseGroup` fetches the group's defaults and seeds the sliders
  // directly, so no second request is made and no effect is needed to
  // copy the result into state.
  const chooseGroup = useCallback(async (next: UserGroup) => {
    setGroup(next);
    setLoadingDefaults(true);
    setDefaultsError(null);
    try {
      const loaded: GroupDefaults = await getGroupDefaults(next);
      setPreferences(loaded.default_preferences);
    } catch (cause) {
      setDefaultsError(describeError(cause, 'The default priorities for that group could not be loaded.'));
    } finally {
      setLoadingDefaults(false);
      setStep('preferences');
    }
  }, []);

  const validateAccount = useCallback((): boolean => {
    const errors: Record<string, string> = {};
    if (name.trim().length < 1) errors.name = 'Enter your name.';
    if (!email.includes('@')) errors.email = 'Enter a valid email address.';
    if (password.length < 1) errors.password = 'Enter a password.';
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  }, [email, name, password]);

  const submit = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      if (submitting) return;
      if (!group) {
        setError({ message: 'Choose a user group before creating the account.' });
        return;
      }
      setSubmitting(true);
      setError(null);
      try {
        await signUp({
          name: name.trim(),
          email: email.trim(),
          password,
          user_group: group,
          routing_preferences: preferences ?? undefined,
        });
        navigate('/route', { replace: true });
      } catch (cause) {
        setError(describeError(cause, 'The account could not be created.'));
      } finally {
        setSubmitting(false);
      }
    },
    [email, group, name, navigate, password, preferences, signUp, submitting],
  );

  const stepIndex = STEPS.findIndex((s) => s.id === step);

  return (
    <AuthLayout
      wide
      title="Create your account"
      subtitle="Two steps after this one: choose the user group that will govern your routing, and tune the priorities it starts from."
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="text-link">
            Sign in
          </Link>
        </>
      }
    >
      <nav className="stepper" aria-label="Onboarding progress">
        <ol>
          {STEPS.map((entry, index) => {
            const state = index < stepIndex ? 'complete' : index === stepIndex ? 'current' : 'upcoming';
            return (
              <li key={entry.id} data-state={state}>
                <span className="stepper-item">
                  <span className="stepper-marker" aria-hidden="true">
                    {state === 'complete' ? <Check /> : index + 1}
                  </span>
                  <span className="stepper-text">
                    {entry.label}
                    {state === 'current' ? <span className="sr-only"> (current step)</span> : null}
                  </span>
                </span>
              </li>
            );
          })}
        </ol>
      </nav>

      <form className="auth-form" onSubmit={submit} noValidate>
        {error ? <ErrorState compact title="Registration failed" message={error.message} hint={error.hint} /> : null}

        {/* ---------------------------------------------- Step 1 */}
        {step === 'account' ? (
          <section aria-labelledby={headingId}>
            <h2 className="auth-section-title" id={headingId}>
              Account details
            </h2>
            <TextInput
              label="Full name"
              autoComplete="name"
              placeholder="Ada Lovelace"
              value={name}
              onChange={(event) => setName(event.target.value)}
              error={fieldErrors.name}
              required
            />
            <TextInput
              label="Email address"
              type="email"
              autoComplete="email"
              inputMode="email"
              placeholder="you@company.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              error={fieldErrors.email}
              required
            />
            <TextInput
              label="Password"
              type="password"
              autoComplete="new-password"
              hint="Stored hashed by the backend. A longer passphrase is stronger than a short password."
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              error={fieldErrors.password}
              required
            />
            <Button
              type="button"
              variant="primary"
              size="lg"
              block
              trailingIcon={<ArrowRight />}
              onClick={() => {
                if (validateAccount()) setStep('group');
              }}
            >
              Continue
            </Button>
          </section>
        ) : null}

        {/* ---------------------------------------------- Step 2 */}
        {step === 'group' ? (
          <section aria-labelledby={headingId}>
            <h2 className="auth-section-title" id={headingId}>
              Choose your user group
            </h2>
            <p className="auth-section-copy">
              The group fixes the default routing priorities the backend applies to every query. It is chosen once and
              cannot be changed per query — the router reads it from your account.
            </p>

            {groups.isInitialLoad ? (
              <div className="stack">
                <SkeletonBlock label="Loading the available user groups." lines={1} />
                <SkeletonBlock label="Loading the available user groups." lines={1} />
                <SkeletonBlock label="Loading the available user groups." lines={1} />
              </div>
            ) : groups.error ? (
              <ErrorState
                compact
                title="The group list could not be loaded"
                message={groups.error.message}
                hint={groups.error.hint}
                onRetry={groups.reload}
              />
            ) : (
              <div className="choice-grid" role="radiogroup" aria-labelledby={headingId}>
                {groups.data?.map((option) => {
                  const selected = option.group === group;
                  return (
                    <button
                      key={option.group}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      className="choice-card"
                      onClick={() => void chooseGroup(option.group)}
                    >
                      <span className="choice-indicator" aria-hidden="true">
                        <Check />
                      </span>
                      <span>
                        <span className="choice-title">{groupLabel(option.group)}</span>
                        <span className="choice-description">{option.description}</span>
                      </span>
                    </button>
                  );
                })}
                {groups.data && groups.data.length === 0 ? (
                  <Notice tone="warning" title="No groups were returned">
                    The backend reported an empty group list, so an account cannot be created yet.
                  </Notice>
                ) : null}
              </div>
            )}

            <Button type="button" variant="ghost" size="lg" block leadingIcon={<ArrowLeft />} onClick={() => setStep('account')}>
              Back
            </Button>
          </section>
        ) : null}

        {/* ---------------------------------------------- Step 3 */}
        {step === 'preferences' && group ? (
          <section aria-labelledby={headingId}>
            <h2 className="auth-section-title" id={headingId}>
              Routing priorities
            </h2>
            <p className="auth-section-copy">
              Starting from the {groupLabel(group)} defaults — {groupDescription(group).toLowerCase()}. These are
              configured starting points, not measured results, and the router normalises them before scoring.
            </p>

            {defaultsError ? (
              <ErrorState compact title="Defaults unavailable" message={defaultsError.message} hint={defaultsError.hint} />
            ) : null}

            {loadingDefaults || (!preferences && !defaultsError) ? (
              <div className="stack">
                <SkeletonBlock label="Loading routing priorities." lines={1} />
                <SkeletonBlock label="Loading routing priorities." lines={1} />
                <SkeletonBlock label="Loading routing priorities." lines={1} />
                <SkeletonBlock label="Loading routing priorities." lines={1} />
                <SkeletonBlock label="Loading routing priorities." lines={1} />
              </div>
            ) : preferences ? (
              <div className="stack">
                {OBJECTIVES.map((objective) => (
                  <Slider
                    key={objective.key}
                    label={objective.label}
                    value={preferences[objective.key]}
                    onChange={(value) =>
                      setPreferences((current) => (current ? { ...current, [objective.key]: value } : current))
                    }
                    description={objective.description}
                    formatValue={(value) => formatPercent(value, 0)}
                  />
                ))}
                <Notice tone="info" title="Relative weights, not a budget">
                  <span className="inline-note">
                    The router converts these into a normalised weight vector before scoring, so the absolute values
                    matter less than their relative order. You can change them at any time from{' '}
                    <Link to="/profile" className="text-link">
                      your profile
                    </Link>
                    .
                  </span>
                </Notice>
              </div>
            ) : null}

            <div className="row">
              <Button type="button" variant="ghost" size="lg" leadingIcon={<ArrowLeft />} onClick={() => setStep('group')}>
                Back
              </Button>
              <Button
                type="submit"
                variant="primary"
                size="lg"
                block
                loading={submitting}
                leadingIcon={<UserCog />}
              >
                {submitting ? 'Creating account' : 'Create account'}
              </Button>
            </div>
          </section>
        ) : null}
      </form>

      <Card tone="muted">
        <CardHeader title="What happens next" />
        <CardBody>
          <ol className="reason-list">
            <li>Your account is created with the group you chose.</li>
            <li>The router reads your group and priorities from your session on every query.</li>
            <li>Nothing is sent to a provider until you submit a query.</li>
          </ol>
        </CardBody>
      </Card>
    </AuthLayout>
  );
}
