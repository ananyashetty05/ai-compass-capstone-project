import { useState } from 'react';
import { Layers, Network } from 'lucide-react';
import { Reveal } from '../ui/Reveal';
import { EmptyState } from '../ui/EmptyState';
import { humanizeToken } from '../../utils/format';
import type { ModelSummary } from './insights';

const PROVIDER_NAMES: Record<string, string> = {
  openai: 'OpenAI', anthropic: 'Anthropic', google: 'Google', mistral: 'Mistral', meta: 'Meta', cohere: 'Cohere', together: 'Together AI', groq: 'Groq', openrouter: 'OpenRouter',
  deepseek: 'DeepSeek', huggingface: 'Hugging Face', hugging_face: 'Hugging Face', ai21: 'AI21', fireworks: 'Fireworks AI', fireworks_ai: 'Fireworks AI', together_ai: 'Together AI', amazon_bedrock: 'Amazon Bedrock', bedrock: 'Amazon Bedrock', xai: 'xAI', perplexity: 'Perplexity',
};
export const providerName = (p: string) => PROVIDER_NAMES[p.toLowerCase().trim().replace(/[\s-]+/g, '_')] ?? humanizeToken(p);

function Bar({ label, value, max, sub }: { label: string; value: number; max: number; sub?: string }) {
  return (
    <li className="cx-bar">
      <span className="cx-bar-label">{label}</span>
      <span className="cx-bar-track" aria-hidden="true"><span className="cx-bar-fill" style={{ ['--w' as string]: `${max > 0 ? (value / max) * 100 : 0}%` }} /></span>
      <span className="cx-bar-value">{value}{sub ? <span className="cx-bar-sub"> {sub}</span> : null}</span>
    </li>
  );
}

export function ProviderDistribution({ summary }: { summary: ModelSummary }) {
  const max = Math.max(1, ...summary.providers.map((p) => p.total));
  const [showAll, setShowAll] = useState(false);
  const LIMIT = 6;
  const shown = showAll ? summary.providers : summary.providers.slice(0, LIMIT);
  const hidden = summary.providers.length - LIMIT;
  return (
    <Reveal as="section" className="cx-card" delay={1} ariaLabelledBy="dist-provider">
      <header className="cx-card-head"><div><p className="cx-kicker">Model ecosystem</p><h2 id="dist-provider">Provider distribution</h2></div><Network aria-hidden="true" /></header>
      {summary.providers.length === 0 ? (
        <EmptyState title="No providers yet" description="No inference models are registered." align="start" />
      ) : (
        <ul className="cx-bars">
          {shown.map((p) => <Bar key={p.provider} label={providerName(p.provider)} value={p.total} max={max} sub={`· ${p.active} active`} />)}
        </ul>
      )}
      {hidden > 0 ? (
        <button type="button" className="cx-link cx-more" aria-expanded={showAll} onClick={() => setShowAll((v) => !v)}>
          {showAll ? 'Show fewer providers' : `Show ${hidden} more provider${hidden === 1 ? '' : 's'}`}
        </button>
      ) : null}
      <p className="cx-note">Counts are API inference models from the registry.</p>
    </Reveal>
  );
}

export function CapabilityOverview({ summary }: { summary: ModelSummary }) {
  const top = summary.capabilities.slice(0, 7);
  const max = Math.max(1, ...top.map((c) => c.count));
  return (
    <Reveal as="section" className="cx-card" delay={2} ariaLabelledBy="dist-cap">
      <header className="cx-card-head"><div><p className="cx-kicker">Model ecosystem</p><h2 id="dist-cap">Capability coverage</h2></div><Layers aria-hidden="true" /></header>
      {top.length === 0 ? (
        <EmptyState title="No capabilities listed" description="Registered models do not report capability tags." align="start" />
      ) : (
        <ul className="cx-bars">
          {top.map((c) => <Bar key={c.name} label={humanizeToken(c.name)} value={c.count} max={max} sub="models" />)}
        </ul>
      )}
      {summary.modalities.length > 0 ? (
        <p className="cx-chips" aria-label="Modalities">
          {summary.modalities.map((m) => <span key={m.name}>{humanizeToken(m.name)} · {m.count}</span>)}
        </p>
      ) : null}
    </Reveal>
  );
}
