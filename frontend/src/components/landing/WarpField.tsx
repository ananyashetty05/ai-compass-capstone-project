import { useEffect, useRef } from 'react';
import { storySignals } from './useStoryProgress';

/**
 * A depth field of light behind the story. Particles drift toward the
 * viewer; scrolling stretches them into streaks (you feel the speed of the
 * scroll), the pointer shifts near particles more than far ones, and each
 * change of scene sends a ring out from the core. Decorative only: it draws
 * no data. One canvas, no libraries, paused when off-screen or the tab is
 * hidden, and not mounted at all under reduced motion.
 */
interface Particle { x: number; y: number; z: number; s: number }

const rand = (a: number, b: number) => a + Math.random() * (b - a);

export function WarpField() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;

    let w = 0;
    let h = 0;
    let dpr = 1;
    let raf = 0;
    let visible = true;
    let particles: Particle[] = [];
    let lastY = window.scrollY;
    let vel = 0;
    let lastScene = storySignals.scene;
    let shock = -1; // 0..1 ring progress, -1 = idle
    let last = 0;

    const make = (): Particle => ({ x: rand(-1, 1), y: rand(-1, 1), z: rand(0.05, 1), s: rand(0.6, 1.8) });
    const resize = () => {
      const r = canvas.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      w = Math.max(1, Math.floor(r.width));
      h = Math.max(1, Math.floor(r.height));
      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const count = w < 700 ? 70 : 150;
      particles = Array.from({ length: count }, make);
    };

    const frame = (time: number) => {
      raf = 0;
      if (!visible || document.hidden) return;
      const dt = Math.min(48, time - (last || time));
      last = time;

      const dy = Math.abs(window.scrollY - lastY);
      lastY = window.scrollY;
      vel += (Math.min(1, dy / 70) - vel) * 0.12;

      if (storySignals.scene !== lastScene) { lastScene = storySignals.scene; shock = 0; }

      ctx.clearRect(0, 0, w, h);
      const cx = w / 2 + storySignals.mx * -24;
      const cy = h / 2 + storySignals.my * -16;
      const focal = Math.max(w, h) * 0.62;
      const hue = storySignals.hue;
      const light = document.documentElement.dataset.theme === 'light';
      const speed = (0.00007 + vel * 0.0011) * dt;

      ctx.lineCap = 'round';
      for (const p of particles) {
        const prevZ = p.z;
        p.z -= speed * (0.4 + p.z);
        if (p.z <= 0.02) { Object.assign(p, make(), { z: 1 }); continue; }
        const sx = cx + (p.x / p.z) * focal * 0.5 + storySignals.mx * -40 * (1 - p.z);
        const sy = cy + (p.y / p.z) * focal * 0.5 + storySignals.my * -28 * (1 - p.z);
        if (sx < -40 || sx > w + 40 || sy < -40 || sy > h + 40) { Object.assign(p, make(), { z: 1 }); continue; }
        const near = 1 - p.z;
        const alpha = Math.min(1, near * 1.4) * (0.35 + vel * 0.6);
        ctx.strokeStyle = `hsla(${hue + p.s * 18}, ${light ? 80 : 100}%, ${light ? 52 - near * 14 : 68 + near * 18}%, ${alpha})`;
        ctx.lineWidth = p.s * (0.6 + near * 1.6);
        const px = cx + (p.x / prevZ) * focal * 0.5 + storySignals.mx * -40 * (1 - prevZ);
        const py = cy + (p.y / prevZ) * focal * 0.5 + storySignals.my * -28 * (1 - prevZ);
        const trail = 1 + vel * 20;
        ctx.beginPath();
        ctx.moveTo(sx + (px - sx) * trail, sy + (py - sy) * trail);
        ctx.lineTo(sx, sy);
        ctx.stroke();
      }

      if (shock >= 0) {
        shock += dt / 1400;
        if (shock >= 1) shock = -1;
        else {
          const r = shock * Math.max(w, h) * 0.55;
          ctx.strokeStyle = `hsla(${hue}, 100%, ${light ? 50 : 70}%, ${(1 - shock) * 0.35})`;
          ctx.lineWidth = 2 + (1 - shock) * 3;
          ctx.beginPath();
          ctx.arc(cx, cy, r, 0, Math.PI * 2);
          ctx.stroke();
        }
      }
      raf = requestAnimationFrame(frame);
    };

    const start = () => { if (!raf && visible && !document.hidden) { last = 0; raf = requestAnimationFrame(frame); } };
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; if (visible) start(); }, { threshold: 0 });
    io.observe(canvas);
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    document.addEventListener('visibilitychange', start);
    resize();
    start();
    return () => {
      io.disconnect(); ro.disconnect();
      document.removeEventListener('visibilitychange', start);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);

  return <canvas ref={ref} className="story-warp" aria-hidden="true" />;
}
