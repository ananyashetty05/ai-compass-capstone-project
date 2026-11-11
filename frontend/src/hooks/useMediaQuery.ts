/**
 * Subscribes to a CSS media query.
 *
 * Built on `useSyncExternalStore` so the value is read from the browser
 * during render rather than copied into state by an effect. That keeps
 * the first paint correct and avoids a cascading render when the query
 * changes.
 */
import { useCallback, useMemo, useSyncExternalStore } from 'react';

export function useMediaQuery(query: string): boolean {
  const list = useMemo(
    () => (typeof window === 'undefined' ? null : window.matchMedia(query)),
    [query],
  );

  const subscribe = useCallback(
    (onChange: () => void) => {
      if (!list) return () => undefined;
      list.addEventListener('change', onChange);
      return () => list.removeEventListener('change', onChange);
    },
    [list],
  );

  const getSnapshot = useCallback(() => list?.matches ?? false, [list]);

  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}

/** Matches the CSS breakpoint where the sidebar becomes a drawer. */
export function useIsCompact(): boolean {
  return useMediaQuery('(max-width: 64rem)');
}
