import { Compass, LayoutDashboard, Route as RouteIcon } from 'lucide-react';
import { ButtonLink } from '../components/ui/Button';
import { Surface } from '../components/ui/ds';
import { BrandMark } from '../components/layout/BrandMark';
import { EmptyState } from '../components/ui/EmptyState';
import { PageHeader } from '../components/layout/PageHeader';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { useAuth } from '../context/authContext';

export function NotFound() {
  useDocumentTitle('Page not found · AI Compass');
  const { isAuthenticated } = useAuth();

  return (
    <div className="nf-page">
      <BrandMark className="nf-mark" />
      {/* Rendered outside `AppShell`, so this page owns its own `<h1>`. */}
      <PageHeader
        as="h1"
        eyebrow="Error 404"
        title="Page not found"
        description="The address you followed is not part of AI Compass. Nothing is broken, and no routing decision was lost."
      />
      <Surface variant="glass" className="nf-card">
          <EmptyState
            icon={<Compass />}
            title="There is nothing at this address"
            description="Check the link, or use one of the routes below to carry on. Your saved preferences and the current routing result are untouched."
            action={
              isAuthenticated ? (
                <ButtonLink to="/route" variant="primary" leadingIcon={<RouteIcon />}>
                  Route a request
                </ButtonLink>
              ) : (
                <ButtonLink to="/login" variant="primary">
                  Sign in
                </ButtonLink>
              )
            }
            secondaryAction={
              isAuthenticated ? (
                <ButtonLink to="/" variant="secondary" leadingIcon={<LayoutDashboard />}>
                  Go to the dashboard
                </ButtonLink>
              ) : (
                <ButtonLink to="/onboarding" variant="secondary">
                  Create an account
                </ButtonLink>
              )
            }
          />
      </Surface>
    </div>
  );
}
