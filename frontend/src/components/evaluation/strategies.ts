import { BarChart3, CircleDollarSign, ListOrdered, Trophy } from 'lucide-react';
import type { OfflineEvaluationStrategy } from '../../types';

/** The four selection policies, in display order. These are policies, not models. */
export const STRATEGIES: Array<{
  key: OfflineEvaluationStrategy;
  title: string;
  short: string;
  description: string;
  icon: typeof BarChart3;
}> = [
  { key: 'aicompass', title: 'AI Compass Routing', short: 'AI Compass', description: 'Multi-objective router using your routing weights.', icon: BarChart3 },
  { key: 'strongest', title: 'Strongest Model', short: 'Strongest', description: 'Highest registry quality score after filtering.', icon: Trophy },
  { key: 'cheapest', title: 'Cheapest Model', short: 'Cheapest', description: 'Lowest known input price; unknown prices excluded.', icon: CircleDollarSign },
  { key: 'static', title: 'Static Ranking', short: 'Static', description: 'Fixed fallback priority, ignores your weights.', icon: ListOrdered },
];

export const strategyTitle = (key: string) => STRATEGIES.find((s) => s.key === key)?.title ?? key;
export const strategyShort = (key: string) => STRATEGIES.find((s) => s.key === key)?.short ?? key;
