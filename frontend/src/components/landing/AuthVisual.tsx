import type { ReactNode } from 'react';
import { AuthOrbit } from './AuthOrbit';

/** Left-hand visual for authentication screens: orbit illustration plus copy. */
export function AuthVisual({ children }: { children?: ReactNode }) {
  return (
    <div className="la-visual">
      <div className="la-core"><AuthOrbit /></div>
      {children ? <div className="la-copy">{children}</div> : null}
    </div>
  );
}
