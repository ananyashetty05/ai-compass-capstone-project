/**
 * Provider ecosystem map. Every node is a provider present in the registry; its size is that provider's real model
 * count in the loaded pool. Clicking a node filters the table below (and clicking again clears it). Connections
 * show that all providers feed the one AI Compass router; they carry no per-provider data of their own.
 */
import { useMemo } from 'react';
import { formatNumber } from '../../utils/format';
import type { ModelInfo } from '../../types';

interface Node { id: string; label: string; count: number; x: number; y: number; r: number; other?: number }
const TOP = 11;

export function EcosystemMap({ models, selected, onSelect, labelOf, title = 'Providers feeding the router', unit = 'providers' }: {
  models: ModelInfo[]; selected: string; onSelect: (provider: string) => void; labelOf: (provider: string) => string; title?: string; unit?: string;
}) {
  const W = 760;
  const H = 360;
  const nodes = useMemo<Node[]>(() => {
    const counts = new Map<string, number>();
    models.forEach((m) => counts.set(m.provider, (counts.get(m.provider) ?? 0) + 1));
    const all = Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
    const head = all.slice(0, TOP);
    const rest = all.slice(TOP);
    const list: [string, number, number?][] = head.map(([id, n]) => [id, n]);
    if (rest.length) list.push(['__other', rest.reduce((t, [, n]) => t + n, 0), rest.length]);
    const max = Math.max(1, ...list.map(([, n]) => n));
    return list.map(([id, count, other], i) => {
      const a = -Math.PI / 2 + (i * 2 * Math.PI) / list.length;
      return { id, label: other ? `${other} other providers` : labelOf(id), count, other, x: W / 2 + Math.cos(a) * 270, y: H / 2 + Math.sin(a) * 120, r: 15 + 20 * Math.sqrt(count / max) };
    });
  }, [models, labelOf]);
  if (nodes.length === 0) return null;
  const total = models.length;
  return (
    <section className="eco" aria-labelledby="eco-title">
      <header className="eco-head">
        <div><p className="ds-kicker">Ecosystem</p><h2 id="eco-title">{title}</h2></div>
        <p className="eco-note">{new Set(models.map((m) => m.provider)).size} {unit} · {formatNumber(total, 0)} products. Node size = products in the pool. Select a node to filter the list.</p>
      </header>
      <svg className="eco-svg" viewBox={`0 0 ${W} ${H}`} role="group" aria-label="Provider map">
        {nodes.map((n, i) => (
          <line key={n.id} className="eco-edge" data-on={selected === 'all' || selected === n.id || undefined} data-all={selected === 'all' || undefined} x1={W / 2} y1={H / 2} x2={n.x} y2={n.y} style={{ animationDelay: `${i * 140}ms` }} />
        ))}
        <g className="eco-core">
          <circle cx={W / 2} cy={H / 2} r="36" className="eco-core-halo" />
          <circle cx={W / 2} cy={H / 2} r="27" className="eco-core-dot" />
          <g transform={`translate(${W / 2 - 11} ${H / 2 - 11})`} className="eco-core-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" /></svg>
          </g>
          <text x={W / 2} y={H / 2 + 52} textAnchor="middle" className="eco-core-label">AI Compass router</text>
        </g>
        {nodes.map((n, i) => {
          const on = selected === n.id;
          if (n.other) return (
            <g key={n.id} className="eco-node eco-node--other" style={{ animationDelay: `${i * 70}ms` }}>
              <title>{n.label}: {n.count} models in total. Use the Provider filter to pick one.</title>
              <circle cx={n.x} cy={n.y} r={n.r} className="eco-node-dot" strokeDasharray="3 3" />
              <text x={n.x} y={n.y} textAnchor="middle" dominantBaseline="central" className="eco-node-count">{n.count}</text>
              <text x={n.x} y={n.y + n.r + 15} textAnchor="middle" className="eco-node-label">{n.label}</text>
            </g>
          );
          return (
            <g key={n.id} className="eco-node" data-selected={on || undefined} data-dim={(selected !== 'all' && !on) || undefined} role="button" tabIndex={0}
              aria-pressed={on} aria-label={`${n.label}: ${n.count} ${n.count === 1 ? 'entry' : 'entries'}. ${on ? 'Clear filter' : 'Filter table'}`}
              onClick={() => onSelect(on ? 'all' : n.id)} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(on ? 'all' : n.id); } }}
              style={{ animationDelay: `${i * 70}ms` }}>
              <g className="eco-bubble">
                <circle cx={n.x} cy={n.y} r={n.r} className="eco-ripple" />
                <circle cx={n.x} cy={n.y} r={n.r} className="eco-node-dot" />
                <text x={n.x} y={n.y} textAnchor="middle" dominantBaseline="central" className="eco-node-count">{n.count}</text>
                <text x={n.x} y={n.y + n.r + 15} textAnchor="middle" className="eco-node-label">{n.label}</text>
              </g>
            </g>
          );
        })}
      </svg>
    </section>
  );
}
