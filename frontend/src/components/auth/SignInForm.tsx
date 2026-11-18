/**
 * Sign-in form (email + password). Extracted from the old Login page so the
 * cinematic landing and any future entry point share one implementation.
 * On success the route guard moves the user to the page they came from.
 */
import { useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { ArrowRight, Mail } from 'lucide-react';
import { PasswordField } from './PasswordField';
import { validateEmail } from './validation';
import { Button, Notice, TextInput } from '../ui';
import { useAuth } from '../../context/authContext';
import { ApiError, describeError } from '../../services/http';

interface Errors { email?: string | null; password?: string | null }

export function SignInForm() {
  const { signIn } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState<{ message: string; hint?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    const next: Errors = {
      email: validateEmail(email),
      password: password ? null : 'Enter your password.',
    };
    setErrors(next);
    setFormError(null);
    if (next.email) return emailRef.current?.focus();
    if (next.password) return passwordRef.current?.focus();

    setBusy(true);
    try {
      await signIn(email.trim(), password);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        setFormError({ message: 'That email and password do not match an account.', hint: 'Check both and try again, or create an account.' });
        setPassword('');
        passwordRef.current?.focus();
      } else {
        const d = describeError(cause, 'Could not sign in.');
        setFormError({
          message: d.message,
          hint: cause instanceof ApiError && cause.kind === 'network' ? 'Check that the backend is running and reachable.' : d.hint,
        });
      }
      setBusy(false);
    }
  };

  return (
    <form className="auth-form" onSubmit={onSubmit} noValidate>
      {formError ? (
        <Notice tone="danger" live="alert" title={formError.message}>
          {formError.hint ?? ''}
        </Notice>
      ) : null}
      <TextInput
        ref={emailRef}
        label="Email"
        name="email"
        type="email"
        inputMode="email"
        autoComplete="username"
        autoCapitalize="none"
        spellCheck={false}
        required
        leadingIcon={<Mail />}
        value={email}
        error={errors.email}
        onChange={(e) => { setEmail(e.target.value); if (errors.email) setErrors((s) => ({ ...s, email: null })); }}
      />
      <PasswordField
        ref={passwordRef}
        label="Password"
        name="password"
        autoComplete="current-password"
        required
        value={password}
        error={errors.password}
        onChange={(e) => { setPassword(e.target.value); if (errors.password) setErrors((s) => ({ ...s, password: null })); }}
      />
      <Button type="submit" variant="primary" size="lg" block loading={busy} trailingIcon={<ArrowRight />}>
        {busy ? 'Signing in…' : 'Sign in'}
      </Button>
    </form>
  );
}
