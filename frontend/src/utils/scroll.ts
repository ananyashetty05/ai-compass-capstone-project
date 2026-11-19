/**
 * Smooth, interruptible scroll of the window so `el` sits just below the
 * sticky top navigation. Eased with a cubic in-out curve over a duration
 * that grows gently with distance, so short hops feel quick and long ones
 * glide. Any wheel, touch or key input from the user cancels it, so the page
 * never fights the person. Honours reduced motion (OS setting or the in-app
 * setting) by jumping instantly.
 */
let cancelActive: (() => void) | null = null;

/** Document-relative top from layout offsets, so an element that is mid entrance animation (transformed) is measured where it will rest. */
const layoutTop = (el: Element) => {
  let y = 0;
  let node = el as HTMLElement | null;
  while (node) { y += node.offsetTop; node = node.offsetParent as HTMLElement | null; }
  return y;
};

// The site sets `scroll-behavior: smooth` globally; each frame must jump exactly, or the browser's own smoothing fights this easing.
const jump = (top: number) => window.scrollTo({ top, behavior: 'instant' });

const reducedMotion = () =>
  window.matchMedia('(prefers-reduced-motion: reduce)').matches ||
  document.documentElement.dataset.reducedMotion === 'true';

const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

export function scrollToElement(el: Element, { gap = 16, onDone }: { gap?: number; onDone?: () => void } = {}) {
  cancelActive?.();
  const nav = document.querySelector('.app-topnav');
  const offset = (nav ? nav.getBoundingClientRect().height : 0) + gap;
  const start = window.scrollY;
  const max = document.documentElement.scrollHeight - window.innerHeight;
  const target = Math.max(0, Math.min(max, layoutTop(el) - offset));
  const distance = target - start;

  if (Math.abs(distance) < 4) { onDone?.(); return; }
  if (reducedMotion()) { jump(target); onDone?.(); return; }

  const duration = Math.min(1300, Math.max(600, Math.abs(distance) * 0.5));
  let raf = 0;
  let t0 = 0;
  const stop = () => {
    if (raf) cancelAnimationFrame(raf);
    raf = 0;
    window.removeEventListener('wheel', stop);
    window.removeEventListener('touchstart', stop);
    window.removeEventListener('keydown', stop);
    if (cancelActive === stop) cancelActive = null;
  };
  const frame = (now: number) => {
    if (!t0) t0 = now;
    const t = Math.min(1, (now - t0) / duration);
    jump(start + distance * ease(t));
    if (t < 1) raf = requestAnimationFrame(frame);
    else { stop(); onDone?.(); }
  };
  window.addEventListener('wheel', stop, { passive: true });
  window.addEventListener('touchstart', stop, { passive: true });
  window.addEventListener('keydown', stop);
  cancelActive = stop;
  raf = requestAnimationFrame(frame);
}
