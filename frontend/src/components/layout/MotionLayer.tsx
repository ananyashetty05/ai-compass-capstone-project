/**
 * Motion layer for the signed-in application (never mounted on the landing or auth pages).
 *
 *  - ScrollProgress: a thin reading-progress bar under the top navigation (one rAF-throttled scroll listener).
 *  - BackToTop: appears after a screenful of scrolling and glides back up.
 *  - useAutoReveal: staggered, one-shot entrance for the main blocks of every page without editing each page. It only ever
 *    animates opacity/transform, skips anything already handled by <Reveal>, skips big virtualised grids, never leaves content
 *    hidden (timer fallback), and does nothing for reduced-motion users.
 */
import { useEffect, useRef, useState } from 'react';
import { ArrowUp } from 'lucide-react';
import { scrollToTop } from '../../utils/scroll';

const reduced = () =>
  window.matchMedia('(prefers-reduced-motion: reduce)').matches || document.documentElement.dataset.reducedMotion === 'true';

const SKIP = '.reveal, .mp-grid, .mc, .modal, [role="dialog"], [data-no-motion], .skeleton, .app-loading, table, tbody, thead, tr, svg, canvas, input, select, textarea, button, a, label, p, h1, h2, h3, h4, li, span';
const ALWAYS = '.page-header, section, article';
const MAX_DEPTH = 5;
const MAX_VISITED = 500;

/** Outer-most "visual blocks" (a surface with a border, fill or shadow, or a section/article/page header). Walks a bounded depth and prunes at the first block it finds, so each card animates once and cheaply. */
function visualBlocks(root: Element): HTMLElement[] {
  const found: HTMLElement[] = [];
  let visited = 0;
  const vh = window.innerHeight;
  const walk = (el: Element, depth: number) => {
    for (const child of Array.from(el.children)) {
      if (++visited > MAX_VISITED) return;
      const node = child as HTMLElement;
      if (node.matches(SKIP)) continue;
      const rect = node.getBoundingClientRect();
      if (rect.height < 24 || rect.width < 80) continue;
      let block = node.matches(ALWAYS);
      if (!block) {
        const cs = getComputedStyle(node);
        block = parseFloat(cs.borderTopWidth) > 0 || cs.boxShadow !== 'none' || (cs.backgroundColor !== 'rgba(0, 0, 0, 0)' && cs.backgroundColor !== 'transparent');
      }
      if (block && rect.height <= vh * 2.2) { found.push(node); continue; }
      if (depth < MAX_DEPTH) walk(node, depth + 1);
    }
  };
  walk(root, 0);
  return found;
}

export function useAutoReveal(pathname: string): void {
  useEffect(() => {
    if (reduced()) return;
    const root = document.querySelector('.app-page-transition');
    if (!root) return;
    let batch = 0;
    let batchTimer = 0;
    const seen = new WeakSet<Element>();
    const io = new IntersectionObserver((entries) => {
      const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
      visible.forEach((entry, i) => {
        const el = entry.target as HTMLElement;
        el.style.setProperty('--mo-delay', `${Math.min(i, 7) * 55}ms`);
        el.classList.add('mo-in');
        io.unobserve(el);
        // Drop the hidden-state class once the transition has finished so it can never affect later layout/stacking.
        window.setTimeout(() => { el.classList.remove('mo', 'mo-in'); el.style.removeProperty('--mo-delay'); }, 900);
      });
    }, { rootMargin: '0px 0px -6% 0px', threshold: 0.04 });

    const tag = (scope: ParentNode) => {
      visualBlocks(scope as Element).forEach((el) => {
        if (seen.has(el) || el.classList.contains('mo-in')) return;
        seen.add(el);
        el.classList.add('mo');
        io.observe(el);
      });
    };
    tag(root);
    // Content that arrives after data loads is tagged too (debounced so a burst of renders is one pass).
    const mo = new MutationObserver(() => {
      window.clearTimeout(batchTimer);
      batchTimer = window.setTimeout(() => { batch += 1; tag(root); }, 60);
    });
    mo.observe(root, { childList: true, subtree: true });
    // Safety net: a hidden tab or a missed intersection must never leave content invisible.
    const safety = window.setTimeout(() => {
      // Only what should already be on screen: blocks further down keep waiting for their scroll-in.
      document.querySelectorAll('.mo:not(.mo-in)').forEach((el) => {
        if (el.getBoundingClientRect().top > window.innerHeight * 1.1) return;
        el.classList.add('mo-in'); window.setTimeout(() => el.classList.remove('mo', 'mo-in'), 900);
      });
    }, 2600);
    return () => {
      io.disconnect(); mo.disconnect(); window.clearTimeout(batchTimer); window.clearTimeout(safety);
      document.querySelectorAll('.mo').forEach((el) => el.classList.remove('mo', 'mo-in'));
      void batch;
    };
  }, [pathname]);
}

export function ScrollProgress() {
  const bar = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let raf = 0;
    const update = () => {
      raf = 0;
      const max = document.documentElement.scrollHeight - window.innerHeight;
      const p = max > 0 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0;
      if (bar.current) { bar.current.style.transform = `scaleX(${p})`; bar.current.dataset.on = p > 0.002 ? 'true' : 'false'; }
    };
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(update); };
    update();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll, { passive: true });
    return () => { window.removeEventListener('scroll', onScroll); window.removeEventListener('resize', onScroll); if (raf) cancelAnimationFrame(raf); };
  }, []);
  return <div className="mo-progress" ref={bar} aria-hidden="true" data-on="false" />;
}

export function BackToTop() {
  const [show, setShow] = useState(false);
  useEffect(() => {
    let raf = 0;
    const check = () => { raf = 0; setShow(window.scrollY > window.innerHeight * 0.8); };
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(check); };
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => { window.removeEventListener('scroll', onScroll); if (raf) cancelAnimationFrame(raf); };
  }, []);
  const goTop = () => {
    if (reduced()) { scrollToTop(); return; }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };
  return (
    <button type="button" className="mo-top" data-show={show} onClick={goTop} aria-label="Back to top" tabIndex={show ? 0 : -1}>
      <ArrowUp aria-hidden="true" />
    </button>
  );
}

/**
 * Cursor-lit cards: while the pointer is over a card, two CSS variables carry its position inside the card so the
 * stylesheet can paint a soft highlight that follows it. One passive listener, rAF-throttled, no React state, and
 * nothing runs for touch/coarse pointers or reduced-motion users. Cards that already have a background image keep it.
 */
const SPOT = ':is([class*="card"], .cx-path, .cx-kpi, .po-box, .rj-node, .registry-card, .settings-block > *):not(button, input, select, textarea, label)';
export function useCardSpotlight(): void {
  useEffect(() => {
    if (reduced() || !window.matchMedia('(hover: hover) and (pointer: fine)').matches) return;
    let raf = 0;
    let active: HTMLElement | null = null;
    let ev: PointerEvent | null = null;
    const clear = () => { if (active) { active.removeAttribute('data-spot'); active = null; } };
    const frame = () => {
      raf = 0;
      if (!ev) return;
      const card = (ev.target as Element | null)?.closest?.(SPOT) as HTMLElement | null;
      if (card !== active) {
        clear();
        if (card && getComputedStyle(card).backgroundImage === 'none') { active = card; card.setAttribute('data-spot', ''); }
      }
      if (active) {
        const r = active.getBoundingClientRect();
        active.style.setProperty('--mx', `${ev.clientX - r.left}px`);
        active.style.setProperty('--my', `${ev.clientY - r.top}px`);
      }
    };
    const move = (e: PointerEvent) => { ev = e; if (!raf) raf = requestAnimationFrame(frame); };
    document.addEventListener('pointermove', move, { passive: true });
    document.addEventListener('pointerleave', clear);
    return () => { document.removeEventListener('pointermove', move); document.removeEventListener('pointerleave', clear); if (raf) cancelAnimationFrame(raf); clear(); };
  }, []);
}
