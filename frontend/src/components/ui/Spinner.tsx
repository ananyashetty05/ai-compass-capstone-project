/**
 * Indeterminate spinner.
 *
 * Always decorative: the surrounding element owns the accessible name
 * and the live region, so a spinner is never the only signal that
 * something is loading.
 */
import { cn } from '../../utils/cn';

export function Spinner({ size = 'md', className }: { size?: 'sm' | 'md' | 'lg'; className?: string }) {
  return <span className={cn('spinner', className)} data-size={size === 'md' ? undefined : size} aria-hidden="true" />;
}

/** Full-viewport loading surface used while the session bootstraps. */
export function AppLoading({ label = 'Loading your workspace…' }: { label?: string }) {
  return (
    <div className="route-gate" role="status" aria-live="polite">
      <Spinner size="lg" />
      <p>{label}</p>
    </div>
  );
}
