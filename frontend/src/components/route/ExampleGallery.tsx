import { useState } from 'react';
import {
  BarChart3, BookOpen, Braces, Brain, Bug, Code2, FileText, Image as ImageIcon, ListChecks, Network, PenLine, Search, Sigma, Sparkles,
} from 'lucide-react';
import type { ReactNode } from 'react';
import { EXAMPLE_CATEGORIES } from '../../utils/routeExamples';

const ICONS: Record<string, ReactNode> = {
  code: <Code2 />, bug: <Bug />, search: <Search />, sigma: <Sigma />, brain: <Brain />, pen: <PenLine />,
  file: <FileText />, chart: <BarChart3 />, sparkles: <Sparkles />, list: <ListChecks />, braces: <Braces />,
  book: <BookOpen />, network: <Network />, image: <ImageIcon />,
};

interface Props {
  onPick: (text: string) => void;
  disabled?: boolean;
}

/** Categorised, clickable example prompts. Picking one only fills the prompt box. */
export function ExampleGallery({ onPick, disabled }: Props) {
  const [active, setActive] = useState(EXAMPLE_CATEGORIES[0].id);
  const category = EXAMPLE_CATEGORIES.find((c) => c.id === active) ?? EXAMPLE_CATEGORIES[0];

  return (
    <section className="rq-gallery" aria-labelledby="rq-gallery-title">
      <div className="rq-gallery-head">
        <h3 id="rq-gallery-title">Try an example</h3>
        <span>Fills the prompt box — edit before routing.</span>
      </div>
      <div className="rq-gallery-tabs" role="tablist" aria-label="Example categories">
        {EXAMPLE_CATEGORIES.map((c) => (
          <button
            key={c.id} type="button" role="tab" id={`rq-ex-tab-${c.id}`} aria-selected={c.id === active}
            aria-controls="rq-ex-panel" tabIndex={c.id === active ? 0 : -1} className="rq-gallery-tab"
            onClick={() => setActive(c.id)}
          >
            <span aria-hidden="true">{ICONS[c.icon]}</span>{c.label}
          </button>
        ))}
      </div>
      <div className="rq-gallery-grid" id="rq-ex-panel" role="tabpanel" aria-labelledby={`rq-ex-tab-${category.id}`} key={category.id}>
        {category.examples.map((ex, i) => (
          <button
            key={ex.title} type="button" className="rq-gallery-card" style={{ ['--i' as string]: i }}
            onClick={() => onPick(ex.text)} disabled={disabled}
          >
            <strong>{ex.title}</strong>
            <span>{ex.text}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
