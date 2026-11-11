import { useId, useRef } from 'react';
import { createPortal } from 'react-dom';
import type { ReactNode } from 'react';
import { X } from 'lucide-react';
import { useFocusTrap } from '../../hooks/useFocusTrap';
import { IconButton } from './Button';

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  size?: 'sm' | 'md' | 'lg';
  /** Set false for destructive flows that require an explicit choice. */
  dismissible?: boolean;
}

/**
 * WCAG 2.2 dialog: labelled, focus-trapped, Escape-dismissible and
 * rendered in a portal so it is never clipped by page layout.
 */
export function Modal({ open, onClose, title, description, children, footer, size = 'sm', dismissible = true }: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descriptionId = useId();

  useFocusTrap(open, panelRef, dismissible ? onClose : undefined);

  if (!open) return null;

  return createPortal(
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && dismissible) onClose();
      }}
    >
      <div
        ref={panelRef}
        className="modal"
        data-size={size === 'sm' ? undefined : size}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
      >
        <div className="modal-header">
          <div>
            <h2 className="modal-title" id={titleId}>
              {title}
            </h2>
            {description ? (
              <p className="modal-description" id={descriptionId}>
                {description}
              </p>
            ) : null}
          </div>
          {dismissible ? (
            <IconButton label="Close dialog" onClick={onClose} icon={<X />} />
          ) : null}
        </div>
        <div className="modal-body">{children}</div>
        {footer ? <div className="modal-footer">{footer}</div> : null}
      </div>
    </div>,
    document.body,
  );
}
