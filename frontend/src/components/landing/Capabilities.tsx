import { useEffect, useRef, useState } from 'react';
import { BarChart3, Brain, Database, FileSearch, Wand2 } from 'lucide-react';
import type { ReactNode } from 'react';

interface Item { icon: ReactNode; title: string; text: string }

/** Only features that exist in the product today. */
const ITEMS: Item[] = [
  { icon: <FileSearch />, title: 'Explained decisions', text: 'Every recommendation shows the stages that ran, the candidates considered and why each was kept or removed.' },
  { icon: <Wand2 />, title: 'Prompt optimizer', text: 'Four optimization modes rewrite your prompt, then check that its intent, code and quoted text were preserved.' },
  { icon: <Database />, title: 'Live model registry', text: 'Models, lifecycle status and routing eligibility come from the registry, with the source of every figure labelled.' },
  { icon: <BarChart3 />, title: 'Evaluation lab', text: 'Compare AI Compass with strongest, cheapest and static baselines on the same candidate pool, offline.' },
  { icon: <Brain />, title: 'Personal priorities', text: 'Set how much quality, cost, latency, reliability and risk matter. Feedback adds a bounded nudge on top.' },
];

/** Scroll-revealed feature band between the story and the sign-in form. */
export function Capabilities() {
  const ref = useRef<HTMLElement>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === 'undefined') { setSeen(true); return; }
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setSeen(true); io.disconnect(); } }, { threshold: 0.15 });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <section className={seen ? 'lcap is-in' : 'lcap'} ref={ref} aria-labelledby="lcap-title">
      <p className="story-kicker">Inside AI Compass</p>
      <h2 className="story-title" id="lcap-title">Built so you can see why.</h2>
      <ul className="lcap-grid">
        {ITEMS.map((item, i) => (
          <li key={item.title} className="lcap-card" style={{ ['--i' as string]: i }}>
            <span className="lcap-icon" aria-hidden="true">{item.icon}</span>
            <strong>{item.title}</strong>
            <span>{item.text}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
