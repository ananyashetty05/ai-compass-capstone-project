export interface SceneCopy {
  kicker: string;
  title: string;
  text: string;
  chips?: string[];
}

/** Copy for the seven scenes. Workflow scenes are conceptual, not live data. */
export const SCENES: SceneCopy[] = [
  {
    kicker: 'AI Compass',
    title: 'Every query.\nA smarter route.',
    text: 'Intelligent model routing that balances quality, cost, latency, reliability, risk and your preferences.',
  },
  {
    kicker: '01 — Query analysis',
    title: 'Every request begins with understanding what you actually need.',
    text: 'Task, domain, complexity, context and your preferences become signals the router can reason about.',
  },
  {
    kicker: '02 — Model filtering',
    title: 'Unsuitable models are eliminated before the decision is made.',
    text: 'Hard constraints remove candidates first, so the router never simply picks the first model available.',
    chips: ['Capabilities', 'Modalities', 'Task fit', 'Availability', 'Your constraints'],
  },
  {
    kicker: '03 — Multi-objective routing',
    title: 'The best model is not always the biggest or the cheapest.',
    text: 'Six objectives are weighed together, using the priorities you set.',
    chips: ['Quality', 'Cost', 'Latency', 'Reliability', 'Risk', 'Preference alignment'],
  },
  {
    kicker: '04 — Intelligent model selection',
    title: 'One request. The most suitable available model.',
    text: 'The choice follows your constraints and objective weights, not a fixed ranking. A fallback stays ready.',
  },
  {
    kicker: '05 — Evaluation & escalation',
    title: 'Intelligence does not end with selection.',
    text: 'The response is checked for quality and risk. If it falls short, the route escalates to a stronger candidate.',
  },
  {
    kicker: 'Get started',
    title: 'Intelligence, routed with purpose.',
    text: 'Your AI workspace starts here.',
  },
];
