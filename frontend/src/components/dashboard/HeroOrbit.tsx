import { Compass, MessageSquareText, Sparkles } from 'lucide-react';
import { AuthOrbit } from '../landing/AuthOrbit';

/**
 * Decorative hero illustration for the dashboard: the same orbit used on
 * the sign-in screens. The `landing` class supplies the shared --lv-*
 * colour variables.
 */
export function HeroOrbit() {
  return (
    <figure className="cx-orbit-fig" aria-hidden="true">
      <div className="landing cx-orbit"><AuthOrbit /></div>
    </figure>
  );
}

const STEPS = [
  { id: 'query', icon: MessageSquareText, title: 'Your query', text: 'Describe the task' },
  { id: 'compass', icon: Compass, title: 'AI Compass', text: 'Analyses, filters and scores' },
  { id: 'model', icon: Sparkles, title: 'Recommended model', text: 'Best fit, with the reasoning' },
];

/** The routing flow in three steps, shown across the foot of the welcome card. */
export function RouteFlow() {
  return (
    <ol className="dash-flow" aria-label="How routing works">
      {STEPS.map(({ id, icon: Icon, title, text }, i) => (
        <li key={id} className="dash-flow-step" data-step={id} style={{ ['--i' as string]: i }}>
          <span className="dash-flow-icon" aria-hidden="true"><Icon /></span>
          <span className="dash-flow-copy">
            <strong>{title}</strong>
            <small>{text}</small>
          </span>
          {i < STEPS.length - 1 ? <span className="dash-flow-link" aria-hidden="true"><i /></span> : null}
        </li>
      ))}
    </ol>
  );
}
