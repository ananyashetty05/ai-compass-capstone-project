import { useEffect, useRef, useState } from 'react';

/** Number of scenes in the story (opening + 5 workflow stages + finale). */
export const SCENE_COUNT = 7;

const clamp = (v: number, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v));
/** Cross-fade width, as a fraction of total story progress. */
const W = 0.04;

/** True when the user (OS or in-app setting) asks for reduced motion. */
export function useReducedMotion(): boolean {
  const read = () =>
    typeof window !== 'undefined' &&
    (window.matchMedia('(prefers-reduced-motion: reduce)').matches ||
      document.documentElement.dataset.reducedMotion === 'true');
  const [reduced, setReduced] = useState(read);
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduced(read());
    mq.addEventListener('change', update);
    const obs = new MutationObserver(update);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-reduced-motion'] });
    return () => { mq.removeEventListener('change', update); obs.disconnect(); };
  }, []);
  return reduced;
}

/**
 * Maps native page scroll to CSS custom properties on the stage element.
 * No React state changes while scrolling: the browser only re-composites
 * transforms and opacity. Scroll is never hijacked.
 *
 *  --p            overall progress 0..1
 *  --v0..--v6     per-scene visibility (cross-faded, sums to ~1)
 *  --l0..--l6     per-scene local progress 0..1 (stays 1 afterwards)
 *  --c            candidate-model layer presence (scenes 2-5)
 *  --side         0 at opening/finale, 1 while workflow scenes are shown
 */
export function useStoryProgress(enabled: boolean) {
  const trackRef = useRef<HTMLElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const track = trackRef.current;
    const stage = stageRef.current;
    if (!enabled || !track || !stage) return;

    let raf = 0;
    let active = -1;
    let target = 0;
    let current = -1; // -1 = not yet initialised (first frame snaps)
    let last = 0;

    const smooth = (t: number) => t * t * (3 - 2 * t);

    const apply = (p: number) => {
      const step = 1 / SCENE_COUNT;
      const v: number[] = [];
      for (let i = 0; i < SCENE_COUNT; i += 1) {
        const start = i * step;
        const end = (i + 1) * step;
        const rampIn = i === 0 ? 1 : smooth(clamp((p - (start - W / 2)) / W));
        const rampOut = i === SCENE_COUNT - 1 ? 1 : smooth(clamp((end + W / 2 - p) / W));
        v.push(Math.min(rampIn, rampOut));
        stage.style.setProperty(`--v${i}`, v[i].toFixed(4));
        stage.style.setProperty(`--l${i}`, smooth(clamp((p - start) / step)).toFixed(4));
      }
      stage.style.setProperty('--p', p.toFixed(5));
      stage.style.setProperty('--c', clamp(v[2] + v[3] + v[4] + v[5]).toFixed(4));
      stage.style.setProperty('--side', clamp(1 - v[0] - v[6]).toFixed(4));
      const now = Math.min(SCENE_COUNT - 1, Math.floor(p * SCENE_COUNT));
      if (now !== active) {
        active = now;
        stage.dataset.scene = String(now);
      }
    };

    const readTarget = () => {
      const rect = track.getBoundingClientRect();
      const total = rect.height - window.innerHeight;
      target = total > 0 ? clamp(-rect.top / total) : 0;
    };

    // Ease the displayed progress toward the scroll position each frame, so
    // wheel notches and touch flicks glide instead of stepping. Frame-rate
    // independent; stops as soon as it has converged.
    const frame = (time: number) => {
      raf = 0;
      const dt = last ? Math.min(64, time - last) : 16.7;
      last = time;
      if (current < 0) current = target;
      const k = 1 - Math.pow(1 - 0.1, dt / 16.7);
      current += (target - current) * k;
      if (Math.abs(target - current) < 0.00012) current = target;
      apply(current);
      if (current !== target) raf = requestAnimationFrame(frame);
      else last = 0;
    };
    const kick = () => {
      readTarget();
      if (!raf) raf = requestAnimationFrame(frame);
    };

    kick();
    window.addEventListener('scroll', kick, { passive: true });
    window.addEventListener('resize', kick);
    return () => {
      window.removeEventListener('scroll', kick);
      window.removeEventListener('resize', kick);
      if (raf) cancelAnimationFrame(raf);
    };
  }, [enabled]);

  return { trackRef, stageRef };
}
