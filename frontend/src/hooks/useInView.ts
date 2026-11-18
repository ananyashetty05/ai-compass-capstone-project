import { useEffect, useRef, useState } from 'react';

/**
 * True once the element has entered the viewport (one-shot).
 * Falls back to "visible" if IntersectionObserver is missing or never
 * fires (background tab), so content is never left hidden.
 */
export function useInView<T extends Element>(rootMargin = '0px 0px -8% 0px') {
  const ref = useRef<T>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (typeof IntersectionObserver === 'undefined') {
      setInView(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setInView(true);
          observer.disconnect();
        }
      },
      { rootMargin, threshold: 0.05 },
    );
    observer.observe(node);
    const fallback = window.setTimeout(() => setInView(true), 1800);
    return () => {
      observer.disconnect();
      window.clearTimeout(fallback);
    };
  }, [rootMargin]);

  return [ref, inView] as const;
}
