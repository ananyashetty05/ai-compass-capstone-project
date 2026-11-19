import { useSyncExternalStore } from 'react';

const QUERY = '(prefers-reduced-motion: reduce)';
const subscribe = (cb: () => void) => { const m = window.matchMedia(QUERY); m.addEventListener('change', cb); return () => m.removeEventListener('change', cb); };

/** Recharts animation props: staggered ease-out entrance, disabled for users who prefer reduced motion. */
export function useChartMotion() {
  const reduced = useSyncExternalStore(subscribe, () => window.matchMedia(QUERY).matches, () => false);
  return { isAnimationActive: !reduced, animationDuration: 800, animationEasing: 'ease-out' as const };
}
