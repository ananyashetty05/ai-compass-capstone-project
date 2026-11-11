import { useCallback, useEffect, useRef, useState } from 'react';
import { describeError } from '../services/http';

export interface UseAsyncState<T> {
  data: T | null;
  error: { message: string; hint?: string } | null;
  isLoading: boolean;
  /** True until the first attempt settles. */
  isInitialLoad: boolean;
}

/**
 * Runs an async loader and tracks its lifecycle.
 *
 * Aborts the in-flight request on unmount and on re-run, ignores stale
 * responses, and never leaves `isLoading` stuck after an error.
 */
export function useAsync<T>(
  loader: (signal: AbortSignal) => Promise<T>,
  deps: readonly unknown[] = [],
  options: { enabled?: boolean } = {},
): UseAsyncState<T> & { reload: () => void } {
  const { enabled = true } = options;
  const [state, setState] = useState<UseAsyncState<T>>({
    data: null,
    error: null,
    isLoading: enabled,
    isInitialLoad: enabled,
  });

  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  const [nonce, setNonce] = useState(0);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (!enabled) {
      setState({ data: null, error: null, isLoading: false, isInitialLoad: false });
      return;
    }

    const controller = new AbortController();
    setState((current) => ({ ...current, isLoading: true, error: null }));

    loaderRef
      .current(controller.signal)
      .then((data) => {
        if (controller.signal.aborted || !mounted.current) return;
        setState({ data, error: null, isLoading: false, isInitialLoad: false });
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted || !mounted.current) return;
        const described = describeError(cause);
        setState({ data: null, error: described, isLoading: false, isInitialLoad: false });
      });

    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, nonce, ...deps]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  return { ...state, reload };
}
