import { useEffect, useRef } from 'react';

export interface CountUpProps {
  value: number;
  /** Formats the displayed number (defaults to locale integer). */
  format?: (value: number) => string;
  duration?: number;
}

/**
 * Animates a number from its previous value. Writes to the DOM node
 * directly so a 600 ms tween causes no React re-renders.
 */
export function CountUp({ value, format = (n) => Math.round(n).toLocaleString('en-US'), duration = 700 }: CountUpProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const from = useRef(0);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const reduce =
      window.matchMedia('(prefers-reduced-motion: reduce)').matches ||
      document.documentElement.dataset.reducedMotion === 'true';
    const start = from.current;
    if (reduce || start === value) {
      node.textContent = format(value);
      from.current = value;
      return;
    }
    let raf = 0;
    const t0 = performance.now();
    const tick = (now: number) => {
      const t = Math.min(1, (now - t0) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      node.textContent = format(start + (value - start) * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
      else from.current = value;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // format is intentionally excluded: it is a pure presentation function.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, duration]);

  return <span ref={ref}>{format(value)}</span>;
}
