/**
 * Quiet live background shared by the sign-in and sign-up screens: drifting
 * aurora light, a very slow ring field, and a few twinkling points.
 * Pure CSS animation; disabled under reduced motion.
 */
const STARS = [
  [8, 14], [18, 72], [27, 38], [36, 86], [44, 22], [53, 64], [61, 12], [69, 48],
  [77, 80], [84, 28], [91, 58], [14, 52], [48, 92], [73, 6], [95, 88], [3, 90],
];

export function AuroraBackground() {
  return (
    <div className="la-bg" aria-hidden="true">
      <div className="story-bg" />
      <div className="la-aurora"><span /><span /><span /></div>
      <svg className="la-rings" viewBox="0 0 800 800" focusable="false">
        <g className="la-rings-spin">
          <circle cx="400" cy="400" r="180" />
          <circle cx="400" cy="400" r="290" strokeDasharray="2 12" />
          <circle cx="400" cy="400" r="390" />
        </g>
      </svg>
      <div className="la-stars">
        {STARS.map(([x, y], i) => (
          <i key={i} style={{ left: `${x}%`, top: `${y}%`, animationDelay: `${(i * 0.7) % 5}s` }} />
        ))}
      </div>
    </div>
  );
}
