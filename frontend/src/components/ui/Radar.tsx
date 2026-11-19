/**
 * Radar chart (SVG, no dependency). Axes with a null value are drawn as a dashed "n/a" marker at the centre and are
 * never given a made-up number. Values are 0..1. The polygon grows in on mount; reduced-motion users get it static.
 */
import { useId } from 'react';

export interface RadarAxis { label: string; value: number | null; display: string }

export interface RadarCompare { name: string; values: (number | null)[] }

export function Radar({ axes, label, size = 280, name, compare }: { axes: RadarAxis[]; label: string; size?: number; name?: string; compare?: RadarCompare }) {
  const uid = useId();
  const c = size / 2;
  const r = size / 2 - 46;
  const n = axes.length;
  const ang = (i: number) => -Math.PI / 2 + (i * 2 * Math.PI) / n;
  const pt = (i: number, v: number) => [c + Math.cos(ang(i)) * r * v, c + Math.sin(ang(i)) * r * v] as const;
  const poly = axes.map((a, i) => pt(i, a.value === null ? 0 : Math.max(0, Math.min(1, a.value))).join(',')).join(' ');
  const rings = [0.25, 0.5, 0.75, 1];
  const poly2 = compare ? compare.values.map((v, i) => pt(i, v === null ? 0 : Math.max(0, Math.min(1, v))).join(',')).join(' ') : null;
  return (
    <figure className="radar">
      <svg viewBox={`-34 0 ${size + 68} ${size}`} role="img" aria-labelledby={`${uid}-t`}>
        <title id={`${uid}-t`}>{label}: {axes.map((a) => `${a.label} ${a.display}`).join(', ')}</title>
        <defs>
          <linearGradient id={`${uid}-g`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="var(--color-primary)" stopOpacity=".55" /><stop offset="100%" stopColor="#8b5cf6" stopOpacity=".35" />
          </linearGradient>
        </defs>
        {rings.map((k) => <polygon key={k} className="radar-ring" points={axes.map((_, i) => pt(i, k).join(',')).join(' ')} />)}
        {axes.map((_, i) => <line key={i} className="radar-axis" x1={c} y1={c} x2={pt(i, 1)[0]} y2={pt(i, 1)[1]} />)}
        <polygon className="radar-shape" points={poly} fill={`url(#${uid}-g)`} style={{ transformOrigin: `${c}px ${c}px` }} />
        {poly2 && <polygon className="radar-shape radar-shape--b" points={poly2} style={{ transformOrigin: `${c}px ${c}px` }} />}
        {axes.map((a, i) => {
          const [x, y] = pt(i, a.value === null ? 0 : Math.max(0, Math.min(1, a.value)));
          const [lx, ly] = pt(i, 1.2);
          const anchor = Math.abs(lx - c) < 6 ? 'middle' : lx > c ? 'start' : 'end';
          return (
            <g key={a.label} className="radar-pt" data-missing={a.value === null || undefined}>
              <circle cx={x} cy={y} r={a.value === null ? 3 : 4.5} />
              <text x={lx} y={ly} textAnchor={anchor} dominantBaseline="middle" className="radar-label">{a.label}</text>
              <text x={lx} y={ly + 14} textAnchor={anchor} dominantBaseline="middle" className="radar-value">{a.display}</text>
              <title>{a.label}: {a.display}</title>
            </g>
          );
        })}
      </svg>
      {compare ? (
        <figcaption className="radar-legend"><span><i className="radar-key radar-key--a" />{name ?? 'Selected'}</span><span><i className="radar-key radar-key--b" />{compare.name}</span></figcaption>
      ) : null}
    </figure>
  );
}
