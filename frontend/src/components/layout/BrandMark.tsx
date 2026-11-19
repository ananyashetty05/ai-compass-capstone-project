import { useId } from 'react';

/**
 * The AI Compass mark: a ring with three routing nodes and a compass
 * needle that points to the chosen path. Mirrors public/favicon.svg.
 */
export function BrandMark({ className }: { className?: string }) {
  const id = useId();
  return (
    <svg className={className} viewBox="0 0 64 64" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id={id} x1="8" y1="4" x2="56" y2="60" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#4f8cff" />
          <stop offset="1" stopColor="#1f4fd8" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="16" fill={`url(#${id})`} />
      <circle cx="32" cy="32" r="19" fill="none" stroke="#fff" strokeOpacity=".55" strokeWidth="3" />
      <circle cx="32" cy="13" r="3.4" fill="#fff" />
      <circle cx="48.5" cy="41.5" r="3.4" fill="#fff" fillOpacity=".8" />
      <circle cx="15.5" cy="41.5" r="3.4" fill="#fff" fillOpacity=".8" />
      <g transform="rotate(35 32 32)">
        <path d="M32 14 L38 32 L26 32 Z" fill="#fff" />
        <path d="M32 50 L38 32 L26 32 Z" fill="#fff" fillOpacity=".45" />
      </g>
      <circle cx="32" cy="32" r="2.6" fill="#1f4fd8" />
    </svg>
  );
}
