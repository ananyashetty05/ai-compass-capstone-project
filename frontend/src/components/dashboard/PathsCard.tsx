import { ArrowRight, Brain, Compass, Database, FlaskConical } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Reveal } from '../ui/Reveal';

const PATHS = [
  { to: '/route', icon: Compass, title: 'Route a query', text: 'Get a recommended model with the reasoning behind it.' },
  { to: '/models', icon: Database, title: 'Model pool', text: 'Browse, filter and inspect every registered model.' },
  { to: '/evaluation', icon: FlaskConical, title: 'Evaluation lab', text: 'Compare AI Compass with baseline routing strategies.' },
  { to: '/personalization', icon: Brain, title: 'Personalization', text: 'See how feedback and your priorities shape routing.' },
];

export function PathsCard() {
  return (
    <Reveal as="nav" className="cx-paths" aria-label="Where to go next">
      {PATHS.map(({ to, icon: Icon, title, text }) => (
        <Link key={to} to={to} className="cx-path">
          <span className="cx-path-icon" aria-hidden="true"><Icon /></span>
          <span className="cx-path-text"><strong>{title}</strong><span>{text}</span></span>
          <ArrowRight className="cx-path-arrow" aria-hidden="true" />
        </Link>
      ))}
    </Reveal>
  );
}
