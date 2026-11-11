/**
 * ToastProvider.
 *
 * Toasts are a polite live region so they never interrupt the user
 * mid-task; the same information is also rendered inline by the form
 * that produced it.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { ToastContext } from './toastContext';
import type { ToastContextValue, ToastInput, ToastItem, ToastTone } from './toastContext';
import { Toast } from '../components/ui/Toast';

const DEFAULT_DURATION_MS = 6000;
const MAX_VISIBLE = 3;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(1);
  const timers = useRef(new Map<number, number>());

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
    const timer = timers.current.get(id);
    if (timer) {
      window.clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  const push = useCallback(
    (input: ToastInput) => {
      const id = nextId.current++;
      const tone: ToastTone = input.tone ?? 'info';
      const duration = input.durationMs ?? DEFAULT_DURATION_MS;
      setToasts((current) => [...current, { ...input, id, tone }].slice(-MAX_VISIBLE));
      if (duration > 0) {
        timers.current.set(
          id,
          window.setTimeout(() => dismiss(id), duration),
        );
      }
      return id;
    },
    [dismiss],
  );

  const clear = useCallback(() => {
    timers.current.forEach((timer) => window.clearTimeout(timer));
    timers.current.clear();
    setToasts([]);
  }, []);

  useEffect(() => {
    const pending = timers.current;
    return () => {
      pending.forEach((timer) => window.clearTimeout(timer));
      pending.clear();
    };
  }, []);

  const value = useMemo<ToastContextValue>(() => ({ toasts, push, dismiss, clear }), [toasts, push, dismiss, clear]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <Toast items={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}
