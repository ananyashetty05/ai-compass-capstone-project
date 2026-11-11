/**
 * Toast contract — non-blocking, screen-reader announced.
 */
import { createContext, useContext } from 'react';

export type ToastTone = 'success' | 'danger' | 'warning' | 'info';

export interface ToastInput {
  title: string;
  description?: string;
  tone?: ToastTone;
  /** Milliseconds before auto-dismiss. 0 keeps it until dismissed. */
  durationMs?: number;
}

export interface ToastItem extends ToastInput {
  id: number;
  tone: ToastTone;
}

export interface ToastContextValue {
  toasts: ToastItem[];
  push: (toast: ToastInput) => number;
  dismiss: (id: number) => void;
  clear: () => void;
}

export const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) throw new Error('useToast must be used inside <ToastProvider>.');
  return context;
}
