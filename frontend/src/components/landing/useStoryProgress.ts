import { useEffect, useRef, useState } from 'react';
import type { RefObject } from 'react';
import { SCENES, SCENE_HUES } from './scenes';

/** Number of scenes in the story (opening + 6 workflow stages + finale). */
export const SCENE_COUNT = SCENES.length;

/**
 * Plain mutable values shared with the canvas layer. The canvas reads these
 * on its own animation frame, so nothing here triggers a React render.
 */
export const storySignals = { p: 0, hue: SCENE_HUES[0], scene: 0, mx: 0, my: 0 };

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
 *  --v0..--v7     per-scene visibility (cross-faded, sums to ~1)
 *  --l0..--l7     per-scene local progress 0..1 (stays 1 afterwards)
 *  --c            candidate-model layer presence (scenes 2-6)
 *  --sel          selected-route layer presence (scenes 4-5)
 *  --hue          background hue, interpolated between scene hues
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
      const last = SCENE_COUNT - 1;
      stage.style.setProperty('--c', clamp(v[2] + v[3] + v[4] + v[5] + v[6]).toFixed(4));
      stage.style.setProperty('--sel', clamp(v[4] + v[5]).toFixed(4));
      stage.style.setProperty('--side', clamp(1 - v[0] - v[last]).toFixed(4));
      const f = clamp(p * SCENE_COUNT - 0.5, 0, last);
      const i0 = Math.floor(f);
      const i1 = Math.min(last, i0 + 1);
      const hue = SCENE_HUES[i0] + (SCENE_HUES[i1] - SCENE_HUES[i0]) * smooth(f - i0);
      stage.style.setProperty('--hue', hue.toFixed(1));
      storySignals.p = p;
      storySignals.hue = hue;
      const now = Math.min(SCENE_COUNT - 1, Math.floor(p * SCENE_COUNT));
      if (now !== active) {
        active = now;
        storySignals.scene = now;
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

/**
 * Eased pointer position (-1..1) written to the stage as --mx / --my, for a
 * little depth: the core tilts and layers slide by different amounts. Only on
 * devices with a real pointer; stops its frame loop once it has settled.
 */
export function usePointerParallax(stageRef: RefObject<HTMLDivElement | null>, enabled: boolean) {
  useEffect(() => {
    const stage = stageRef.current;
    if (!enabled || !stage || !window.matchMedia('(hover: hover) and (pointer: fine)').matches) return;
    let raf = 0;
    let tx = 0;
    let ty = 0;
    let x = 0;
    let y = 0;
    const frame = () => {
      raf = 0;
      x += (tx - x) * 0.07;
      y += (ty - y) * 0.07;
      if (Math.abs(tx - x) < 0.001 && Math.abs(ty - y) < 0.001) { x = tx; y = ty; }
      stage.style.setProperty('--mx', x.toFixed(3));
      stage.style.setProperty('--my', y.toFixed(3));
      storySignals.mx = x;
      storySignals.my = y;
      if (x !== tx || y !== ty) raf = requestAnimationFrame(frame);
    };
    const onMove = (e: PointerEvent) => {
      tx = (e.clientX / window.innerWidth) * 2 - 1;
      ty = (e.clientY / window.innerHeight) * 2 - 1;
      if (!raf) raf = requestAnimationFrame(frame);
    };
    window.addEventListener('pointermove', onMove, { passive: true });
    return () => { window.removeEventListener('pointermove', onMove); if (raf) cancelAnimationFrame(raf); };
  }, [enabled, stageRef]);
}
