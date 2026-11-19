import {
  AudioLines, BarChart3, Brain, Code2, FileText, GraduationCap, Image as ImageIcon, Layers, Palette, PenLine, Presentation, Search, Sigma, Video, Wand2,
} from 'lucide-react';
import type { ReactNode } from 'react';
import { SelectCard } from '../ui/ds';

const ICONS: Record<string, ReactNode> = {
  coding: <Code2 />, research: <Search />, creative: <PenLine />, analysis: <BarChart3 />, math: <Sigma />,
  'image-generation': <ImageIcon />, 'video-generation': <Video />, presentation: <Presentation />,
  'audio-generation': <AudioLines />, design: <Palette />, education: <GraduationCap />,
  summarization: <FileText />, reasoning: <Brain />,
};

interface Props {
  categories: readonly (readonly [string, string])[];
  value: string | null;
  onChange: (value: string | null) => void;
  disabled?: boolean;
}

/** Symmetrical selection cards: "Auto-detect" plus every task type. */
export function TaskTypeGrid({ categories, value, onChange, disabled }: Props) {
  return (
    <fieldset className="rq-tasktype" disabled={disabled}>
      <legend>Task type <span>Optional — leave on Auto-detect to let the router decide.</span></legend>
      <div className="rq-tasktype-grid">
        <SelectCard selected={value === null} onSelect={() => onChange(null)} icon={<Wand2 />} title="Auto-detect" />
        {categories.map(([id, label]) => (
          <SelectCard
            key={id} selected={value === id} onSelect={() => onChange(value === id ? null : id)}
            icon={ICONS[id] ?? <Layers />} title={label}
          />
        ))}
      </div>
    </fieldset>
  );
}
