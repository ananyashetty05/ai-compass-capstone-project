/**
 * Routing visual.
 *
 * The hero's focal point: the routing layer itself, drawn as a layered
 * sphere behind three orbital paths with nodes riding the rings.
 *
 * Two deliberate constraints:
 *
 *  1. Nothing here is focusable and nothing here is a control. These are
 *     explanatory annotations about a running system, not buttons, so the
 *     visual can never swallow or reorder focus on the sign-in form.
 *  2. The sphere, orbits and nodes are decorative geometry, so they are
 *     hidden from assistive technology. The six annotations are not —
 *     they are rendered as a real list so they are announced as one
 *     ordered set instead of six stray fragments.
 *
 * The annotations describe the pipeline the backend actually runs:
 * AI Compass scores and selects, and the selected provider model is what
 * performs inference. The visual never implies the router answers.
 */
import type { ReactNode } from 'react';
import {
  BadgeCheck,
  Filter,
  GaugeCircle,
  ListChecks,
  SlidersHorizontal,
  UserRound,
  type LucideIcon,
} from 'lucide-react';

interface StageAnnotation {
  name: string;
  note: string;
  icon: LucideIcon;
}

/**
 * Ordered to match the real request path, so the visual teaches the
 * architecture rather than decorating it.
 */
const ANNOTATIONS: StageAnnotation[] = [
  { name: 'Your Profile', note: 'Fixed group + preferences', icon: UserRound },
  { name: 'Query Analysis', note: 'Task, domain, complexity', icon: ListChecks },
  { name: 'Model Filtering', note: 'Constraint-based elimination', icon: Filter },
  { name: 'Multi-Objective', note: 'Quality · Cost · Latency · Reliability', icon: SlidersHorizontal },
  { name: 'Model Selection', note: 'Best overall score', icon: GaugeCircle },
  { name: 'Evaluation & Escalation', note: 'Quality checks + fallback', icon: BadgeCheck },
];

/** Nodes are pinned to a ring's edge; the ring's rotation moves them. */
const RINGS: { ring: 1 | 2 | 3; nodes: ('a' | 'b' | 'c')[] }[] = [
  { ring: 1, nodes: ['a', 'b'] },
  { ring: 2, nodes: ['c', 'a'] },
  { ring: 3, nodes: ['b', 'c'] },
];

function Core() {
  return (
    <div className="routing-core">
      {/* Sphere interior is pure CSS gradient layering — see auth.css. */}
    </div>
  );
}

function Orbits() {
  return (
    <div aria-hidden="true">
      {RINGS.map(({ ring, nodes }) => (
        <div key={ring} className="routing-orbit" data-ring={ring}>
          {nodes.map((bearing) => (
            <span
              key={bearing}
              className={ring === 2 ? 'routing-node routing-node--muted' : 'routing-node'}
              data-bearing={bearing}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

export interface RoutingVisualProps {
  /**
   * Accessible name for the group of annotations. Defaults describe the
   * pipeline so a screen reader user gets the same explanation the
   * sighted user reads off the labels.
   */
  label?: string;
  /** Rendered inside the stage, above the core — unused by the hero today. */
  children?: ReactNode;
}

export function RoutingVisual({ label = 'The stages AI Compass runs for every query', children }: RoutingVisualProps) {
  return (
    <div className="routing-visual" role="group" aria-label={label}>
      <div className="routing-stage">
        <Orbits />
        <Core />
        {children}

        <ul className="routing-labels">
          {ANNOTATIONS.map(({ name, note, icon: Icon }, index) => (
            <li key={name} className="routing-label" data-slot={index + 1}>
              <span className="routing-label-icon" aria-hidden="true">
                <Icon />
              </span>
              <span className="routing-label-text">
                <span className="routing-label-name">{name}</span>
                <span className="routing-label-note">{note}</span>
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
