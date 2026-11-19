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

/**
 * Full-viewport loading surface used while the session bootstraps. Brand loader: the AI Compass core with an
 * orbit and radar sweep. It is indeterminate by design: it shows activity, never progress.
 */
export function AppLoading({ label = 'Loading your workspace…' }: { label?: string }) {
  return (
    <div className="route-gate" role="status" aria-live="polite">
      <div className="rl-visual rl-visual--sm" aria-hidden="true">
        <span className="rl-ring rl-ring--1" /><span className="rl-ring rl-ring--2" />
        <span className="rl-sweep" />
        <span className="rl-orbit rl-orbit--a"><i /></span>
        <span className="rl-orbit rl-orbit--b"><i /></span>
        <div className="rl-core"><svg className="rl-needle" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" /></svg></div>
      </div>
      <p>{label}</p>
    </div>
  );
}
