import { useEffect, useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import { CheckCircle2, Info, TriangleAlert, X, XCircle } from 'lucide-react';
import { useDismissable } from '../../hooks/useDismissable';
import { IconButton } from './Button';
import type { ToastItem, ToastTone } from '../../context/toastContext';

const ICONS: Record<ToastTone, typeof Info> = {
  success: CheckCircle2,
  danger: XCircle,
  warning: TriangleAlert,
  info: Info,
};

const LABELS: Record<ToastTone, string> = {
  success: 'Success',
  danger: 'Error',
  warning: 'Warning',
  info: 'Information',
};

function ToastRow({ item, onDismiss }: { item: ToastItem; onDismiss: (id: number) => void }) {
  const Icon = ICONS[item.tone];
  return (
    <div className="toast" data-tone={item.tone}>
      <Icon aria-hidden="true" />
      <div className="grow">
        <p className="toast-title">
          <span className="sr-only">{LABELS[item.tone]}: </span>
          {item.title}
        </p>
        {item.description ? <p className="toast-description">{item.description}</p> : null}
      </div>
      <IconButton
        label={`Dismiss ${LABELS[item.tone].toLowerCase()} notification`}
        onClick={() => onDismiss(item.id)}
        size="sm"
        icon={<X />}
      />
    </div>
  );
}

/**
 * Polite live region for transient confirmations. Deliberately
 * non-blocking: nothing here interrupts a task in progress.
 */
export function Toast({ items, onDismiss }: { items: readonly ToastItem[]; onDismiss: (id: number) => void }) {
  const regionRef = useRef<HTMLDivElement>(null);
  const baseId = useId();
  useDismissable(items.length > 0, [regionRef], () => items.forEach((item) => onDismiss(item.id)), {
    escape: false,
    pointer: false,
  });

  useEffect(() => {
    if (items.length === 0) return;
    const last = items[items.length - 1];
    window.setTimeout(() => {
      const node = document.getElementById(`${baseId}-${last.id}`);
      node?.focus();
    }, 50);
  }, [baseId, items]);

  if (items.length === 0) return null;

  return createPortal(
    <div className="toast-viewport" role="region" aria-label="Notifications" ref={regionRef}>
      <div aria-live="polite" aria-atomic="false" style={{ display: 'contents' }}>
        {items.map((item) => (
          <div key={item.id} id={`${baseId}-${item.id}`} tabIndex={-1} style={{ display: 'contents' }}>
            <ToastRow item={item} onDismiss={onDismiss} />
          </div>
        ))}
      </div>
    </div>,
    document.body,
  );
}
