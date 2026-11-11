/**
 * Route guard.
 *
 * Redirects to `/login` when there is no session and to `/onboarding`
 * when the profile is not usable yet. `initialising` renders a quiet
 * status instead of a redirect so a page refresh on a deep link does
 * not bounce the user out of the workspace.
 */
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from './authContext';
import { Spinner } from '../components/ui/Spinner';

export function RequireAuth() {
  const { status, isAuthenticated } = useAuth();
  const location = useLocation();

  if (status === 'initialising') {
    return (
      <div className="route-gate" role="status" aria-live="polite">
        <Spinner size="lg" />
        <p>Restoring your session…</p>
      </div>
    );
  }

  if (!isAuthenticated) {
    // Preserve the intended destination so login can return to it.
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }

  return <Outlet />;
}

/** Keeps signed-in users out of `/login` and `/onboarding`. */
export function RedirectIfAuthenticated({ children }: { children: React.ReactNode }) {
  const { status, isAuthenticated } = useAuth();

  if (status === 'initialising') {
    return (
      <div className="route-gate" role="status" aria-live="polite">
        <Spinner size="lg" />
        <p>Loading…</p>
      </div>
    );
  }

  if (isAuthenticated) return <Navigate to="/" replace />;
  return <>{children}</>;
}
