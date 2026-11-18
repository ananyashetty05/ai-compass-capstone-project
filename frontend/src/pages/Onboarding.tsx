/**
 * Sign up — three steps: account, user group, priorities.
 *
 * Design rules:
 *  - Group cards come from a built-in list, so step 2 renders instantly
 *    and can never be empty. The backend catalogue only supplies the
 *    default weights; if it is unreachable the user is told and can
 *    still finish (the server then applies the group defaults itself).
 *  - Nothing advances on its own: every step has an explicit Continue.
 *  - Priorities are only sent when the user actually changed them.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, ArrowRight, Check, Mail, User } from 'lucide-react';
import { AuthShell } from '../components/auth/AuthShell';
import { PasswordField } from '../components/auth/PasswordField';
import {
  MIN_PASSWORD_LENGTH,
  passwordStrength,
  validateConfirm,
  validateEmail,
  validateName,
  validateNewPassword,
} from '../components/auth/validation';
import { Button, Notice, Slider, TextInput } from '../components/ui';
import { useAuth } from '../context/authContext';
import { useAsync } from '../hooks/useAsync';
import { getGroupCatalog } from '../services/auth.service';
import { ApiError, describeError } from '../services/http';
import type { RoutingPreferences } from '../types';
import { OBJECTIVES, USER_GROUPS } from '../utils/domain';
import { cn } from '../utils/cn';

type StepId = 'account' | 'group' | 'priorities';
const STEPS: { id: StepId; label: string }[] = [
  { id: 'account', label: 'Account' },
  { id: 'group', label: 'User group' },
  { id: 'priorities', label: 'Priorities' },
];

type AccountErrors = Partial<Record<'name' | 'email' | 'password' | 'confirm', string | null>>;

function Stepper({ current }: { current: number }) {
  return (
    <nav aria-label="Sign-up progress">
      <ol className="auth-steps">
        {STEPS.map((step, i) => {
          const state = i < current ? 'done' : i === current ? 'current' : 'todo';
          return (
            <li key={step.id} className="auth-step" data-state={state} aria-current={state === 'current' ? 'step' : undefined}>
              <span className="auth-step-dot" aria-hidden="true">{state === 'done' ? <Check /> : i + 1}</span>
              <span className="auth-step-label">
                {step.label}
                <span className="sr-only">{state === 'done' ? ' (completed)' : state === 'current' ? ' (current step)' : ''}</span>
              </span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export function Onboarding() {
  const { signUp } = useAuth();
  const [stepIndex, setStepIndex] = useState(0);
  const step = STEPS[stepIndex].id;

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [accountErrors, setAccountErrors] = useState<AccountErrors>({});

  const [group, setGroup] = useState<string | null>(null);
  const [groupError, setGroupError] = useState<string | null>(null);

  const [custom, setCustom] = useState<RoutingPreferences | null>(null);
  const [submitError, setSubmitError] = useState<{ message: string; hint?: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const headingRef = useRef<HTMLHeadingElement>(null);
  const firstRender = useRef(true);
  const refs = {
    name: useRef<HTMLInputElement>(null),
    email: useRef<HTMLInputElement>(null),
    password: useRef<HTMLInputElement>(null),
    confirm: useRef<HTMLInputElement>(null),
  };

  // Default weights per group from the backend. Failure is non-fatal.
  const catalog = useAsync((signal) => getGroupCatalog(signal), []);
  const defaultsFor = useMemo(() => {
    const map = new Map<string, RoutingPreferences>();
    for (const entry of catalog.data ?? []) map.set(entry.group.toLowerCase(), entry.defaults);
    return map;
  }, [catalog.data]);
  const descriptionFor = (id: string, fallback: string) =>
    (catalog.data ?? []).find((e) => e.group.toLowerCase() === id)?.description || fallback;

  const defaults = group ? defaultsFor.get(group) ?? null : null;
  const prefs = custom ?? defaults;

  // Move focus to the step heading whenever the step changes.
  useEffect(() => {
    if (firstRender.current) { firstRender.current = false; return; }
    headingRef.current?.focus();
  }, [stepIndex]);

  const strength = passwordStrength(password);

  const validateAccount = (): boolean => {
    const next: AccountErrors = {
      name: validateName(name),
      email: validateEmail(email),
      password: validateNewPassword(password),
      confirm: validateConfirm(password, confirm),
    };
    setAccountErrors(next);
    const first = (['name', 'email', 'password', 'confirm'] as const).find((k) => next[k]);
    if (first) refs[first].current?.focus();
    return !first;
  };

  const touchAccount = (key: keyof AccountErrors, value: string) => {
    const check = { name: validateName, email: validateEmail, password: validateNewPassword } as const;
    if (key === 'confirm') setAccountErrors((s) => ({ ...s, confirm: validateConfirm(password, value) }));
    else setAccountErrors((s) => ({ ...s, [key]: check[key](value) }));
  };

  const next = () => {
    setSubmitError(null);
    if (step === 'account') {
      if (validateAccount()) setStepIndex(1);
    } else if (step === 'group') {
      if (!group) { setGroupError('Choose the group that best describes you.'); return; }
      setGroupError(null);
      setCustom(null);
      setStepIndex(2);
    }
  };

  const back = () => { setSubmitError(null); setStepIndex((i) => Math.max(0, i - 1)); };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (step !== 'priorities') { next(); return; }
    if (busy || !group) return;
    setBusy(true);
    setSubmitError(null);
    try {
      await signUp({
        name: name.trim(),
        email: email.trim(),
        password,
        user_group: group,
        // Only send weights the user changed; otherwise the server applies the group defaults.
        ...(custom ? { routing_preferences: custom } : {}),
      });
      // RedirectIfAuthenticated moves the user into the workspace.
    } catch (cause) {
      setBusy(false);
      if (cause instanceof ApiError && cause.status === 409) {
        setStepIndex(0);
        setAccountErrors({ email: 'An account with this email already exists.' });
        setTimeout(() => refs.email.current?.focus(), 0);
        return;
      }
      const d = describeError(cause, 'Could not create the account.');
      setSubmitError({
        message: d.message,
        hint: cause instanceof ApiError && cause.kind === 'network' ? 'Check that the backend is running and reachable, then try again.' : d.hint,
      });
    }
  };

  const titles: Record<StepId, { title: string; subtitle: string }> = {
    account: { title: 'Create your account', subtitle: 'Start with your details. You can change them later in Settings.' },
    group: { title: 'Choose your user group', subtitle: 'This sets your starting routing priorities. Your group stays fixed; the priorities can be tuned any time.' },
    priorities: { title: 'Set your priorities', subtitle: 'Adjust how much each objective matters, or keep the defaults for your group.' },
  };

  return (
    <AuthShell
      documentTitle="Create account"
      title={titles[step].title}
      subtitle={titles[step].subtitle}
      headingRef={headingRef}
      progress={<Stepper current={stepIndex} />}
      footer={<p>Already have an account? <Link to="/login" className="text-link">Sign in</Link></p>}
    >
      <form className="auth-form" onSubmit={submit} noValidate>
        <div key={step} className="al-step">
        {step === 'account' ? (
          <>
            <TextInput ref={refs.name} label="Full name" name="name" autoComplete="name" required leadingIcon={<User />}
              value={name} error={accountErrors.name}
              onChange={(e) => { setName(e.target.value); if (accountErrors.name) touchAccount('name', e.target.value); }}
              onBlur={(e) => touchAccount('name', e.target.value)} />
            <TextInput ref={refs.email} label="Email" name="email" type="email" inputMode="email" autoComplete="email"
              autoCapitalize="none" spellCheck={false} required leadingIcon={<Mail />}
              value={email} error={accountErrors.email}
              onChange={(e) => { setEmail(e.target.value); if (accountErrors.email) touchAccount('email', e.target.value); }}
              onBlur={(e) => touchAccount('email', e.target.value)} />
            <div>
              <PasswordField ref={refs.password} label="Password" name="new-password" autoComplete="new-password" required
                hint={`At least ${MIN_PASSWORD_LENGTH} characters.`}
                value={password} error={accountErrors.password}
                onChange={(e) => { setPassword(e.target.value); if (accountErrors.password) touchAccount('password', e.target.value); }}
                onBlur={(e) => touchAccount('password', e.target.value)} />
              {password ? (
                <div className="auth-strength" data-score={strength.score} role="status">
                  <span className="auth-strength-bar" aria-hidden="true"><span /><span /><span /><span /></span>
                  <span>Strength: {strength.label}</span>
                </div>
              ) : null}
            </div>
            <PasswordField ref={refs.confirm} label="Confirm password" name="confirm-password" autoComplete="new-password" required
              value={confirm} error={accountErrors.confirm}
              onChange={(e) => { setConfirm(e.target.value); if (accountErrors.confirm) touchAccount('confirm', e.target.value); }}
              onBlur={(e) => touchAccount('confirm', e.target.value)} />
          </>
        ) : null}

        {step === 'group' ? (
          <fieldset className="auth-fieldset">
            <legend className="sr-only">User group</legend>
            <div className="auth-groups">
              {USER_GROUPS.map((g) => {
                const selected = group === g.id;
                return (
                  <label key={g.id} className={cn('auth-group', selected && 'is-selected')}>
                    <input type="radio" name="user_group" value={g.id} checked={selected}
                      onChange={() => { setGroup(g.id); setGroupError(null); setCustom(null); }} />
                    <span className="auth-group-body">
                      <span className="auth-group-name">{g.label}</span>
                      <span className="auth-group-desc">{descriptionFor(g.id, g.description)}</span>
                    </span>
                    <span className="auth-group-check" aria-hidden="true"><Check /></span>
                  </label>
                );
              })}
            </div>
            {groupError ? <p className="field-error" role="alert">{groupError}</p> : null}
          </fieldset>
        ) : null}

        {step === 'priorities' ? (
          <>
            {catalog.isLoading ? (
              <p className="auth-muted" role="status">Loading defaults for your group…</p>
            ) : !prefs ? (
              <Notice tone="warning" live="status" title="Default priorities are unavailable"
                actions={<Button size="sm" variant="secondary" onClick={catalog.reload}>Retry</Button>}>
                {catalog.error?.message ?? 'The server did not return defaults.'} You can still create your account; the
                server will apply the standard priorities for your group, and you can adjust them afterwards.
              </Notice>
            ) : (
              <div className="auth-sliders">
                {OBJECTIVES.map((o) => (
                  <Slider key={o.key} label={o.label} description={o.description} value={prefs[o.key] ?? 0}
                    onChange={(v) => setCustom({ ...prefs, [o.key]: v })} />
                ))}
                {custom ? (
                  <Button size="sm" variant="ghost" onClick={() => setCustom(null)}>Reset to group defaults</Button>
                ) : null}
              </div>
            )}
          </>
        ) : null}

        </div>

        {submitError ? (
          <Notice tone="danger" live="alert" title={submitError.message}>{submitError.hint ?? ''}</Notice>
        ) : null}

        <div className="auth-actions">
          {stepIndex > 0 ? (
            <Button variant="secondary" size="lg" leadingIcon={<ArrowLeft />} onClick={back} disabled={busy}>Back</Button>
          ) : <span />}
          {step === 'priorities' ? (
            <Button type="submit" variant="primary" size="lg" loading={busy} disabled={catalog.isLoading}>
              {busy ? 'Creating account…' : 'Create account'}
            </Button>
          ) : (
            <Button type="submit" variant="primary" size="lg" trailingIcon={<ArrowRight />}>Continue</Button>
          )}
        </div>
      </form>
    </AuthShell>
  );
}
