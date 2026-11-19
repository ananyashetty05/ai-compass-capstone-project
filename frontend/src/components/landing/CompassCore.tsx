/**
 * The AI Compass intelligence core: one SVG object that evolves with the
 * story. Layers fade in and out through CSS custom properties written by
 * `useStoryProgress`, so this component never re-renders while scrolling.
 *
 * Everything drawn here is a conceptual illustration of the routing
 * workflow. The model names are placeholders, not live providers, and the
 * shapes carry no real metrics.
 */

const CX = 400;
const CY = 400;
const polar = (r: number, deg: number) => {
  const a = ((deg - 90) * Math.PI) / 180;
  return { x: +(CX + r * Math.cos(a)).toFixed(1), y: +(CY + r * Math.sin(a)).toFixed(1) };
};

const CANDIDATES = Array.from({ length: 8 }, (_, i) => ({
  id: String.fromCharCode(65 + i),
  ...polar(290, i * 45 + 22.5),
  // B, D, F and G are the ones the constraints remove.
  out: [1, 3, 5, 6].includes(i),
  selected: i === 2,
  fallback: i === 4,
}));

const SIGNALS = [
  { label: 'Task', ...polar(320, 308) },
  { label: 'Domain', ...polar(320, 334) },
  { label: 'Complexity', ...polar(320, 0) },
  { label: 'Context', ...polar(320, 26) },
  { label: 'Preferences', ...polar(320, 52) },
];

const DIMENSIONS = ['Quality', 'Cost', 'Latency', 'Reliability', 'Risk', 'Preference'].map((label, i) => ({
  label,
  ...polar(150, i * 60),
}));

const radarPoints = DIMENSIONS.map((_d, i) => {
  // Illustrative, deliberately uneven shape: no real scores.
  const r = [118, 92, 108, 124, 96, 112][i];
  const p = polar(r, i * 60);
  return `${p.x},${p.y}`;
}).join(' ');

// Illustrative reasons, one per removed candidate; not live results.
const REASONS = ['Over budget', 'Too slow', 'No vision', 'Context too small'];
// Illustrative score parts for the selected route (bar widths, px).
const LEDGER = [104, 82, 96, 70];

const sel = CANDIDATES.find((c) => c.selected)!;
const fb = CANDIDATES.find((c) => c.fallback)!;

export function CompassCore({ className, label }: { className?: string; label?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 800 800"
      role="img"
      aria-label={label ?? 'Illustration of the AI Compass routing workflow'}
      focusable="false"
    >
      <defs>
        <radialGradient id="cc-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#4cc2ff" stopOpacity="0.55" />
          <stop offset="45%" stopColor="#0a84ff" stopOpacity="0.18" />
          <stop offset="100%" stopColor="#0a84ff" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="cc-sphere" cx="38%" cy="32%" r="75%">
          <stop offset="0%" stopColor="#e6f6ff" />
          <stop offset="28%" stopColor="#6cc8ff" />
          <stop offset="65%" stopColor="#0a63d6" />
          <stop offset="100%" stopColor="#06285e" />
        </radialGradient>
        <marker id="cc-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0 0 L10 5 L0 10 z" fill="#4cc2ff" />
        </marker>
      </defs>

      {/* Atmosphere */}
      <circle className="cc-halo" cx={CX} cy={CY} r="330" fill="url(#cc-glow)" />

      {/* Orbital rings, always present, slowly rotating */}
      <g className="cc-rings" fill="none">
        <circle className="cc-ring cc-ring--a" cx={CX} cy={CY} r="120" />
        <circle className="cc-ring cc-ring--b" cx={CX} cy={CY} r="200" strokeDasharray="2 10" />
        <circle className="cc-ring cc-ring--c" cx={CX} cy={CY} r="290" strokeDasharray="1 14" />
      </g>

      {/* Scene 1 — query analysis: signals flow into the core */}
      <g className="cc-layer cc-l1">
        {SIGNALS.map((s) => (
          <g key={s.label}>
            <line className="cc-flow" x1={s.x} y1={s.y} x2={CX} y2={CY} />
            <circle className="cc-node" cx={s.x} cy={s.y} r="9" />
            <text className="cc-label" x={s.x} y={s.y - 18} textAnchor="middle">{s.label}</text>
          </g>
        ))}
      </g>

      {/* Scenes 2-5 — candidate models around the core */}
      <g className="cc-cands">
        {CANDIDATES.map((c) => (
          <g key={c.id} className={c.out ? 'cc-cand cc-cand--out' : 'cc-cand'}>
            <line className="cc-spoke" x1={c.x} y1={c.y} x2={CX} y2={CY} />
            <circle className="cc-model" cx={c.x} cy={c.y} r="20" />
            <text className="cc-model-text" x={c.x} y={c.y + 5} textAnchor="middle">{c.id}</text>
          </g>
        ))}
      </g>

      {/* Scene 3 — six objectives balanced around the core */}
      <g className="cc-layer cc-l3">
        <polygon className="cc-radar" points={radarPoints} />
        {DIMENSIONS.map((d) => (
          <g key={d.label}>
            <line className="cc-dim-line" x1={CX} y1={CY} x2={d.x} y2={d.y} />
            <circle className="cc-dim" cx={d.x} cy={d.y} r="7" />
            <text className="cc-label" x={d.x} y={d.y + (d.y > CY ? 26 : -14)} textAnchor="middle">{d.label}</text>
          </g>
        ))}
      </g>

      {/* Scene 4 — one route is selected, one kept as fallback */}
      <g className="cc-layer cc-l4">
        <line className="cc-route" x1={sel.x} y1={sel.y} x2={CX} y2={CY} />
        <circle className="cc-pick" cx={sel.x} cy={sel.y} r="30" />
        <text className="cc-label cc-label--strong" x={sel.x} y={sel.y - 40} textAnchor="middle">Selected</text>
        <line className="cc-fallback" x1={fb.x} y1={fb.y} x2={CX} y2={CY} />
        <text className="cc-label" x={fb.x} y={fb.y + 44} textAnchor="middle">Fallback</text>
      </g>

      {/* Scene 5 — transparent reasoning: every removed model keeps its reason,
          and the selected one shows the parts of its score (illustrative). */}
      <g className="cc-layer cc-lx">
        {CANDIDATES.filter((c) => c.out).map((c, k) => {
          const reason = REASONS[k];
          const below = c.y > CY;
          return (
            <g key={c.id} className="cc-why">
              <path className="cc-x" d={`M ${c.x - 9} ${c.y - 9} L ${c.x + 9} ${c.y + 9} M ${c.x + 9} ${c.y - 9} L ${c.x - 9} ${c.y + 9}`} />
              <text className="cc-label cc-why-text" x={c.x} y={c.y + (below ? 46 : -34)} textAnchor="middle">{reason}</text>
            </g>
          );
        })}
        <g className="cc-ledger" transform={`translate(${sel.x - 60} ${sel.y + 48})`}>
          {LEDGER.map((w, k) => (
            <g key={k} transform={`translate(0 ${k * 22})`}>
              <rect className="cc-bar-bg" width="120" height="8" rx="4" />
              <rect className="cc-bar" width={w} height="8" rx="4" style={{ ['--k' as string]: k }} />
            </g>
          ))}
        </g>
      </g>

      {/* Scene 6 — evaluation loop and escalation */}
      <g className="cc-layer cc-l5" fill="none">
        <path className="cc-loop" d="M 400 160 A 240 240 0 1 1 399 160" markerEnd="url(#cc-arrow)" />
        <path className="cc-escalate" d={`M ${sel.x} ${sel.y} Q 560 520 ${fb.x} ${fb.y}`} markerEnd="url(#cc-arrow)" />
        <text className="cc-label" x="400" y="140" textAnchor="middle">Quality check</text>
        <text className="cc-label" x="662" y="410" textAnchor="start">Risk check</text>
        <text className="cc-label cc-label--strong" x="400" y="728" textAnchor="middle">Accepted, or escalate</text>
      </g>

      {/* The core itself */}
      <g className="cc-core">
        <circle cx={CX} cy={CY} r="74" fill="url(#cc-sphere)" />
        <circle className="cc-core-ring" cx={CX} cy={CY} r="74" fill="none" />
        <path className="cc-needle" d="M400 350 L412 400 L400 450 L388 400 Z" />
      </g>
    </svg>
  );
}

