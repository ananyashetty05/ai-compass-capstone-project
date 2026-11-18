/**
 * Decorative orbital illustration for the authentication screens. Distinct
 * from the story's routing graph: a calm core with orbiting satellites, a
 * slow radar sweep and soft ripples. Purely illustrative.
 */
const CX = 300;
const CY = 300;
const at = (r: number, deg: number) => {
  const a = ((deg - 90) * Math.PI) / 180;
  return { x: +(CX + r * Math.cos(a)).toFixed(1), y: +(CY + r * Math.sin(a)).toFixed(1) };
};

const INNER = [0, 120, 240].map((d) => at(120, d));
const MIDDLE = [30, 120, 210, 300].map((d) => at(190, d));
const OUTER = [0, 60, 120, 180, 240, 300].map((d) => at(252, d));

export function AuthOrbit({ className }: { className?: string }) {
  return (
    <svg className={className ?? 'ao'} viewBox="0 0 600 600" aria-hidden="true" focusable="false">
      <defs>
        <radialGradient id="ao-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#4cc2ff" stopOpacity="0.5" />
          <stop offset="55%" stopColor="#0a84ff" stopOpacity="0.14" />
          <stop offset="100%" stopColor="#0a84ff" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="ao-sphere" cx="38%" cy="32%" r="75%">
          <stop offset="0%" stopColor="#e6f6ff" />
          <stop offset="30%" stopColor="#6cc8ff" />
          <stop offset="68%" stopColor="#0a63d6" />
          <stop offset="100%" stopColor="#06285e" />
        </radialGradient>
        <linearGradient id="ao-sweep" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#4cc2ff" stopOpacity="0" />
          <stop offset="100%" stopColor="#4cc2ff" stopOpacity="0.38" />
        </linearGradient>
      </defs>

      <circle className="ao-glow" cx={CX} cy={CY} r="290" fill="url(#ao-glow)" />

      {/* Ripples expanding from the core */}
      <circle className="ao-ripple" cx={CX} cy={CY} r="80" />
      <circle className="ao-ripple ao-ripple--b" cx={CX} cy={CY} r="80" />

      {/* Orbit paths */}
      <circle className="ao-path" cx={CX} cy={CY} r="120" />
      <circle className="ao-path ao-path--dash" cx={CX} cy={CY} r="190" />
      <circle className="ao-path" cx={CX} cy={CY} r="252" />

      {/* Radar sweep */}
      <g className="ao-sweep">
        <path d={`M ${CX} ${CY} L ${CX + 252} ${CY} A 252 252 0 0 0 ${at(252, 62).x} ${at(252, 62).y} Z`} fill="url(#ao-sweep)" />
      </g>

      {/* Satellites on three counter-rotating orbits */}
      <g className="ao-orbit ao-orbit--1">
        {INNER.map((p, i) => <circle key={i} className="ao-sat" cx={p.x} cy={p.y} r="8" />)}
      </g>
      <g className="ao-orbit ao-orbit--2">
        {MIDDLE.map((p, i) => <circle key={i} className="ao-sat ao-sat--soft" cx={p.x} cy={p.y} r="6" />)}
      </g>
      <g className="ao-orbit ao-orbit--3">
        {OUTER.map((p, i) => <circle key={i} className="ao-sat ao-sat--ring" cx={p.x} cy={p.y} r="9" />)}
      </g>

      {/* Core */}
      <g className="ao-core">
        <circle cx={CX} cy={CY} r="58" fill="url(#ao-sphere)" />
        <circle className="ao-core-ring" cx={CX} cy={CY} r="58" fill="none" />
        <path className="ao-needle" d={`M${CX} ${CY - 40} L${CX + 10} ${CY} L${CX} ${CY + 40} L${CX - 10} ${CY} Z`} />
      </g>
    </svg>
  );
}
