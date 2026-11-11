/**
 * Sign in.
 *
 * The form posts to `POST /auth/login` only. On success the session is
 * adopted and the user returns to the route they originally requested.
 * Errors are rendered from the server's own `detail`; nothing is
 * invented here and no path bypasses the backend.
 *
 * Layout is the split-screen `LoginLayout`; all behaviour below is
 * unchanged from the previous implementation.
 */
import { useCallback, useId, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ArrowRight, Eye, EyeOff, LockKeyhole, Mail } from 'lucide-react';
import { LoginLayout } from '../components/layout/LoginLayout';
import { Button, IconButton } from '../components/ui/Button';
import { TextInput } from '../components/ui/Input';
import { ErrorState } from '../components/ui/EmptyState';
import { useAuth } from '../context/authContext';
import { ApiError, describeError } from '../services/http';

interface LocationState {
  from?: string;
}

export function Login() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<{ message: string; hint?: string } | null>(null);
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({});

  // Ties the visibility toggle to the field it controls, so the control's
  // state and its target are both announced rather than just its label.
  const passwordId = useId();

  const redirectTo = (location.state as LocationState | null)?.from ?? '/';

  const submit = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      if (submitting) return;

      const errors: { email?: string; password?: string } = {};
      if (!email.includes('@')) errors.email = 'Enter a valid email address.';
      if (password.length < 1) errors.password = 'Enter your password.';
      setFieldErrors(errors);
      if (Object.keys(errors).length > 0) return;

      setSubmitting(true);
      setError(null);
      try {
        await signIn(email.trim(), password);
        navigate(redirectTo, { replace: true });
      } catch (cause) {
        const described = describeError(cause, 'Unable to sign in. Check your email and password.');
        // A 401 here means the credentials were refused, not that an
        // existing session lapsed, so the status hint ("Sign in again to
        // continue") would be aimed at the wrong moment.
        setError(cause instanceof ApiError && cause.isUnauthorized ? { message: described.message } : described);
      } finally {
        setSubmitting(false);
      }
    },
    [email, navigate, password, redirectTo, signIn, submitting],
  );

  return (
    <LoginLayout eyebrow="Welcome back" title="Sign in" subtitle="Continue to your routing workspace.">
      <form className="login-form" onSubmit={submit} noValidate>
        {error ? (
          <div className="login-form-alerts">
            <ErrorState compact title="Could not sign in" message={error.message} hint={error.hint} />
          </div>
        ) : null}

        <TextInput
          label="Email address"
          type="email"
          autoComplete="email"
          inputMode="email"
          placeholder="you@company.com"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          error={fieldErrors.email}
          leadingIcon={<Mail />}
          required
          disabled={submitting}
        />

        <TextInput
          id={passwordId}
          label="Password"
          type={showPassword ? 'text' : 'password'}
          autoComplete="current-password"
          placeholder="Enter your password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          error={fieldErrors.password}
          leadingIcon={<LockKeyhole />}
          required
          disabled={submitting}
          trailing={
            <IconButton
              label={showPassword ? 'Hide password' : 'Show password'}
              onClick={() => setShowPassword((current) => !current)}
              size="sm"
              icon={showPassword ? <EyeOff /> : <Eye />}
              aria-pressed={showPassword}
              aria-controls={passwordId}
            />
          }
        />

        <Button
          type="submit"
          variant="primary"
          size="lg"
          block
          className="login-submit"
          loading={submitting}
          trailingIcon={<ArrowRight />}
        >
          {submitting ? 'Signing you in' : 'Continue'}
        </Button>

        <div className="login-divider" aria-hidden="true">
          or
        </div>
      </form>

      <p className="login-alt">
        New to AI Compass?{' '}
        <Link to="/onboarding" className="text-link">
          Create an account
        </Link>
      </p>
    </LoginLayout>
  );
}
