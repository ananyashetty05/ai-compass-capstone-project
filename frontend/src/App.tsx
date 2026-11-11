/**
 * Route table — AI Compass 2.0
 * Recommendation-first: /route is the primary surface.
 */
import { Suspense, lazy } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import { AppLoading } from './components/ui/Spinner';
import { RedirectIfAuthenticated, RequireAuth } from './context/RouteGuards';
import { RouteResultProvider } from './context/RouteResultProvider';
import { Login } from './pages/Login';
import { Onboarding } from './pages/Onboarding';
import { NotFound } from './pages/NotFound';

const Dashboard     = lazy(() => import('./pages/Dashboard').then((m) => ({ default: m.Dashboard })));
const RouteQuery    = lazy(() => import('./pages/RouteQuery').then((m) => ({ default: m.RouteQuery })));
const ModelPool     = lazy(() => import('./pages/ModelPool').then((m) => ({ default: m.ModelPool })));
const Explanation   = lazy(() => import('./pages/Explanation').then((m) => ({ default: m.Explanation })));
const Evaluation    = lazy(() => import('./pages/Evaluation').then((m) => ({ default: m.Evaluation })));
const Personalization = lazy(() => import('./pages/Personalization').then((m) => ({ default: m.Personalization })));
const Profile       = lazy(() => import('./pages/Profile').then((m) => ({ default: m.Profile })));
const SettingsPage  = lazy(() => import('./pages/SettingsPage').then((m) => ({ default: m.SettingsPage })));

export default function App() {
  return (
    <Suspense fallback={<AppLoading />}>
      <Routes>
        {/* Public */}
        <Route path="/login" element={<RedirectIfAuthenticated><Login /></RedirectIfAuthenticated>} />
        <Route path="/onboarding" element={<RedirectIfAuthenticated><Onboarding /></RedirectIfAuthenticated>} />

        {/* Authenticated shell */}
        <Route element={<RequireAuth />}>
          <Route element={<RouteResultProvider><AppShell /></RouteResultProvider>}>
            <Route index element={<RouteQuery />} />
            <Route path="/route" element={<RouteQuery />} />
            <Route path="/models" element={<ModelPool />} />
            <Route path="/explanation" element={<Explanation />} />
            <Route path="/evaluation" element={<Evaluation />} />
            <Route path="/personalization" element={<Personalization />} />
            <Route path="/profile" element={<Profile />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/dashboard" element={<Dashboard />} />
          </Route>
        </Route>

        {/* Remaining legacy redirects */}
        <Route path="/images" element={<Navigate to="/models" replace />} />
        <Route path="/history" element={<Navigate to="/route" replace />} />

        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  );
}
