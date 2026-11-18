import { ArrowRight } from 'lucide-react';
import { AuthOrbit } from '../landing/AuthOrbit';

/**
 * Decorative hero illustration for the dashboard — the same orbit used on
 * the sign-in screens — plus a one-line description of the routing flow.
 * The `landing` class supplies the shared --lv-* colour variables.
 */
export function HeroOrbit() {
  return (
    <figure className="cx-orbit-fig" aria-label="Illustration of AI Compass routing a query to a recommended model">
      <div className="landing cx-orbit"><AuthOrbit /></div>
      <figcaption className="cx-flow">
        <span>Your query</span><ArrowRight aria-hidden="true" />
        <span data-accent="true">AI Compass</span><ArrowRight aria-hidden="true" />
        <span>Recommended model</span>
      </figcaption>
    </figure>
  );
}
