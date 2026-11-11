/**
 * Navigation — AI Compass 2.0
 * Recommendation-first. Research engine is the primary surface.
 */
import {
  BookOpen,
  Brain,
  Compass,
  Database,
  FlaskConical,
  LayoutDashboard,
  Settings,
  UserRound,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

export interface NavItem {
  to: string;
  label: string;
  shortLabel: string;
  icon: LucideIcon;
  description: string;
  end?: boolean;
  badge?: string;
}

export interface NavSection {
  id: string;
  title: string;
  items: NavItem[];
}

export const NAV_SECTIONS: NavSection[] = [
  {
    id: 'workspace',
    title: 'Workspace',
    items: [
      {
        to: '/',
        label: 'Recommend',
        shortLabel: 'Recommend',
        icon: Compass,
        description: 'Submit a task and receive an intelligent model recommendation.',
        end: true,
      },
      {
        to: '/dashboard',
        label: 'Dashboard',
        shortLabel: 'Dashboard',
        icon: LayoutDashboard,
        description: 'System overview, provider status, and routing pipeline.',
      },
      {
        to: '/explanation',
        label: 'Explanation',
        shortLabel: 'Explain',
        icon: BookOpen,
        description: 'Full explainability for the last routing decision.',
      },
    ],
  },
  {
    id: 'registry',
    title: 'Registry',
    items: [
      {
        to: '/models',
        label: 'Model Registry',
        shortLabel: 'Models',
        icon: Database,
        description: 'All configured models, tools, and capability metadata.',
      },
    ],
  },
  {
    id: 'research',
    title: 'Research',
    items: [
      {
        to: '/evaluation',
        label: 'Evaluation Lab',
        shortLabel: 'Evaluate',
        icon: FlaskConical,
        description: 'Compare AI Compass against routing baselines.',
      },
      {
        to: '/personalization',
        label: 'Personalization',
        shortLabel: 'Learn',
        icon: Brain,
        description: 'Learned model satisfaction and adaptive preferences.',
      },
    ],
  },
  {
    id: 'account',
    title: 'Account',
    items: [
      {
        to: '/profile',
        label: 'Profile',
        shortLabel: 'Profile',
        icon: UserRound,
        description: 'Your routing group and preference weights.',
      },
      {
        to: '/settings',
        label: 'Settings',
        shortLabel: 'Settings',
        icon: Settings,
        description: 'Appearance, accessibility, and account actions.',
      },
    ],
  },
];

export const NAV_ITEMS: NavItem[] = NAV_SECTIONS.flatMap((s) => s.items);

export const PAGE_TITLES: Record<string, string> = Object.fromEntries(
  NAV_ITEMS.map((item) => [item.to, item.label]),
);

export function resolveNavItem(pathname: string): NavItem | undefined {
  const exact = NAV_ITEMS.find((item) => (item.end ? item.to === pathname : item.to === pathname));
  if (exact) return exact;
  return [...NAV_ITEMS]
    .filter((item) => item.to !== '/' && pathname.startsWith(`${item.to}/`))
    .sort((a, b) => b.to.length - a.to.length)[0];
}
