import { cloneElement, useId, useRef, useState } from 'react';
import type { ReactElement, ReactNode } from 'react';

export type TooltipPlacement = 'top' | 'bottom' | 'left' | 'right';

export interface TooltipProps {
  content: ReactNode;
  children: ReactElement<{ 'aria-describedby'?: string; 'aria-label'?: string }>;
  placement?: TooltipPlacement;
}

/**
 * Tooltip for unfamiliar controls.
 *
 * The trigger is described with `aria-describedby` when it has no
 * visible label, so the tooltip text is also available to assistive
 * technology. Tooltips never contain the only copy of essential
 * information.
 */
export function Tooltip({ content, children, placement = 'top' }: TooltipProps) {
  const [open, setOpen] = useState(false);
  const timeout = useRef<number | undefined>(undefined);
  const tooltipId = useId();

  const show = () => {
    window.clearTimeout(timeout.current);
    setOpen(true);
  };
  const hide = () => {
    window.clearTimeout(timeout.current);
    setOpen(false);
  };
  const scheduleHide = () => {
    window.clearTimeout(timeout.current);
    timeout.current = window.setTimeout(() => setOpen(false), 120);
  };

  // `children` is a single element, and the props below are event
  // handlers, not ref accessors: the rule cannot tell the difference
  // and this is the documented way to describe a caller-owned trigger.
  // oxlint-disable-next-line react/refs
  const trigger = cloneElement(children, {
    'aria-describedby': open ? tooltipId : undefined,
    onMouseEnter: show,
    onMouseLeave: scheduleHide,
    onFocus: show,
    onBlur: hide,
    onPointerDown: hide,
  } as Record<string, unknown>);

  return (
    <span className="tooltip-anchor">
      {trigger}
      {open ? (
        <span role="tooltip" id={tooltipId} className="tooltip" data-placement={placement}>
          {content}
        </span>
      ) : null}
    </span>
  );
}

/** Info affordance with an accessible explanation. */
export function InfoHint({ content, label = 'More information' }: { content: ReactNode; label?: string }) {
  return (
    <Tooltip content={content}>
      <button type="button" className="icon-btn info-hint-button" aria-label={label}>
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6">
          <circle cx="8" cy="8" r="6.5" />
          <path d="M8 7.2v4M8 4.9h.01" strokeLinecap="round" />
        </svg>
      </button>
    </Tooltip>
  );
}
