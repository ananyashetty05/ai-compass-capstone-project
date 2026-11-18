import type { CSSProperties, ElementType, ReactNode } from 'react';
import { useInView } from '../../hooks/useInView';
import { cn } from '../../utils/cn';

export interface RevealProps {
  children: ReactNode;
  as?: ElementType;
  className?: string;
  /** Stagger step (0–8); each step adds 60 ms. */
  delay?: number;
  id?: string;
  ariaLabelledBy?: string;
  'aria-label'?: string;
}

/**
 * Scroll-triggered entrance. Pure CSS transition driven by a one-shot
 * IntersectionObserver — no scroll listeners, no re-renders while
 * scrolling. Reduced-motion users see the content immediately.
 */
export function Reveal({ children, as: Element = 'div', className, delay = 0, id, ariaLabelledBy, 'aria-label': ariaLabel }: RevealProps) {
  const [ref, inView] = useInView<HTMLElement>();
  return (
    <Element
      ref={ref}
      id={id}
      aria-labelledby={ariaLabelledBy}
      aria-label={ariaLabel}
      className={cn('reveal', inView && 'is-in', className)}
      style={{ '--reveal-delay': `${delay * 60}ms` } as CSSProperties}
    >
      {children}
    </Element>
  );
}
