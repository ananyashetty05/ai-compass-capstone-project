/**
 * Model Pool card.
 *
 * One fixed structure for every entry (header · chips · description · metrics · capabilities · footer), so a long name or
 * description can never change a card's shape: text is clamped or ellipsised, and the full value stays available through the
 * title attribute and the Inspect page. Everything shown is registry metadata; unknown values read "Not published" / "—".
 */
import { memo } from 'react';
import { ArrowUpRight, Check, GitCompareArrows } from 'lucide-react';
import { GenerationPill } from './Ecosystem';
import { formatModelCostPerThousand, formatPercent, formatSeconds, humanizeToken } from '../../utils/format';
import type { EcosystemCategory, ModelGroup, ModelInfo, PricingCategory, PrimaryCategory } from '../../types';

export const CATEGORY_LABEL: Record<PrimaryCategory, string> = {
  conversational: 'Conversational AI',
  developer: 'Developer & Project',
  application: 'AI application',
  unclassified: 'Unclassified',
};
export const GROUP_LABEL: Record<ModelGroup, string> = { conversational: 'Conversational AI', developer_api: 'Developer & API', unclassified: 'Unclassified' };
export const ECOSYSTEM_LABEL: Record<EcosystemCategory, string> = {
  conversational: 'Conversational AI', image: 'Image generation', video: 'Video generation', music_voice: 'Music & voice', document_design: 'Documents, slides & design', api_models: 'API models & inference', coding: 'Coding',
};
/** Metric tile text: a missing value is a dash with an explanation, never a word that truncates inside a four-column grid. */
const MISSING = '—';
export const ACCESS_LABEL: Record<string, string> = {
  consumer_chat: 'Consumer chat', provider_api: 'Provider API', hosted_inference: 'Hosted inference', aggregator_api: 'Aggregator API', self_hosted: 'Self-hosted', unknown: 'Access route not verified',
};
export const PRICING_LABEL: Record<PricingCategory, string> = {
  completely_free: 'Free', free_tier_limited: 'Free tier with limits', pay_as_you_go: 'Pay-as-you-go', paid_subscription: 'Paid subscription',
  self_hosted_open_weight: 'Self-hosted (open weights)', unknown: 'Pricing not verified',
};
export const KIND_LABEL: Record<string, string> = {
  chat: 'Chat', reasoning_chat: 'Reasoning chat', multimodal_chat: 'Multimodal chat', code_chat: 'Code chat', embedding: 'Embedding', reranker: 'Reranker',
  image_generation: 'Image generation', video_generation: 'Video generation', speech: 'Speech & audio', vision: 'Vision', vision_language: 'Vision-language',
  code: 'Code', base_model: 'Base model', consumer_app: 'Application', unclassified: 'Unclassified',
};
const WEIGHTS: Record<string, string> = { open_weights: 'Open weights', proprietary: 'Proprietary' };
const FREE: Record<string, string> = { free: 'Free', limited_free: 'Free tier', paid: 'Paid' };

export function formatContext(tokens: number | null | undefined): string {
  if (!tokens || tokens <= 0) return '—';
  if (tokens >= 1_000_000) return `${+(tokens / 1_000_000).toFixed(1)}M`;
  if (tokens >= 1_000) return `${Math.round(tokens / 1_000)}K`;
  return String(tokens);
}

function isEstimate(model: ModelInfo, metric: string): boolean {
  return model.metric_provenance?.[metric] === 'editorial_estimate';
}
function estimatedNote(model: ModelInfo, metric: string): string | undefined {
  return isEstimate(model, metric) ? 'Editorial estimate, not a measurement. It is shown for reference and does not decide the ranking.' : undefined;
}

export function cardKey(model: ModelInfo): string { return `${model.provider}::${model.model_id}`; }

interface Props {
  model: ModelInfo;
  providerLabel: string;
  compared: boolean;
  compareDisabled: boolean;
  onInspect: (model: ModelInfo) => void;
  onToggleCompare: (model: ModelInfo) => void;
}

function ModelCardBase({ model, providerLabel, compared, compareDisabled, onInspect, onToggleCompare }: Props) {
  const category = model.primary_category ?? 'unclassified';
  const kind = model.category_kind ?? 'unclassified';
  const isApp = model.entry_type !== 'inference_model' && model.entry_type !== 'model';
  const developer = model.developer && model.developer !== model.provider ? model.developer : null;
  const byline = developer ? `${developer} · via ${providerLabel}` : providerLabel;
  const caps = (model.capability_tags ?? []).filter((tag) => tag !== 'open_weights');
  const shownCaps = caps.slice(0, 3);
  const free = model.free_download ? 'Free download' : FREE[model.free_access ?? 'unknown'];
  const weights = WEIGHTS[model.weights_status ?? 'unknown'];
  const accessNote = [weights, free].filter(Boolean).join(' · ');
  const description = model.description?.trim() || model.classification_reason || 'No description published.';
  const showGeneration = model.catalog && !['retained', 'unmanaged'].includes(model.catalog.generation_status);
  const runnable = model.execution_available === true;

  return (
    <article className="mc" data-category={category} aria-label={model.model_name}>
      <header className="mc-head">
        <div className="mc-head-text">
          <p className="mc-byline" title={byline}>{byline}</p>
          <h3 className="mc-title">
            <button type="button" className="mc-title-btn" title={model.model_name} onClick={() => onInspect(model)}>{model.model_name}</button>
          </h3>
          <p className="mc-id" title={model.model_id}>{model.model_id}</p>
        </div>
        <span className="mc-status" data-active={model.active}><span aria-hidden="true" className="mc-dot" />{model.active ? 'Active' : 'Inactive'}</span>
      </header>

      <div className="mc-chips" aria-label="Classification">
        <span className="mc-chip mc-chip--category" data-category={category} title={model.category_basis ?? undefined}>{model.ecosystem_category ? ECOSYSTEM_LABEL[model.ecosystem_category] : GROUP_LABEL[model.model_category ?? 'unclassified']}</span>
        {kind !== 'unclassified' && kind !== 'consumer_app' ? <span className="mc-chip" title={model.classification_reason ?? undefined}>{KIND_LABEL[kind] ?? humanizeToken(kind)}</span> : null}
        {showGeneration && model.catalog ? <GenerationPill catalog={model.catalog} /> : null}
      </div>

      <p className="mc-desc" title={description}>{description}</p>

      {!isApp ? (
        <p className="mc-facts" aria-label="Access and pricing">
          <span title="How the model is reached">{ACCESS_LABEL[model.access_type ?? 'unknown']}</span>
          <span aria-hidden="true">·</span>
          <span title={model.free_access_note ?? 'Only documented pricing is shown; unknown is never presented as free.'} data-free={model.free_tier_available === true}>{PRICING_LABEL[model.pricing_category ?? 'unknown']}</span>
          {model.api_available === true ? <><span aria-hidden="true">·</span><span>API available</span></> : null}
        </p>
      ) : null}

      <dl className="mc-metrics">
        <div><dt>Context</dt><dd title={isApp ? 'Not applicable to an application' : undefined}>{isApp ? MISSING : formatContext(model.context_window)}</dd></div>
        <div><dt>Cost / 1K</dt><dd title={isApp ? 'Not applicable to an application' : undefined}>{isApp ? MISSING : formatModelCostPerThousand(model)}</dd></div>
        <div><dt>Quality</dt><dd title={estimatedNote(model, 'quality')}>{model.estimated_quality == null ? MISSING : formatPercent(model.estimated_quality, 0)}{isEstimate(model, 'quality') ? <span className="mc-est" aria-label="editorial estimate">est.</span> : null}</dd></div>
        <div><dt>Latency</dt><dd title={model.avg_latency_seconds == null ? 'Not published' : undefined}>{model.avg_latency_seconds == null ? MISSING : formatSeconds(model.avg_latency_seconds)}</dd></div>
      </dl>

      <div className="mc-caps" aria-label="Capabilities">
        {shownCaps.length > 0
          ? shownCaps.map((tag) => <span className="mc-tag" key={tag}>{humanizeToken(tag)}</span>)
          : <span className="mc-muted">No capabilities reported</span>}
        {caps.length > shownCaps.length ? <span className="mc-more" title={caps.slice(3).map(humanizeToken).join(', ')}>+{caps.length - shownCaps.length}</span> : null}
      </div>

      <footer className="mc-foot">
        <p className="mc-access" title={isApp ? 'Opened by the user; not routable' : `Comparison: eligible · Execution: ${runnable ? 'ready' : 'needs provider access'}${accessNote ? ` · ${accessNote}` : ''}`}>
          {isApp ? 'Application · not routable' : (
            <><span className="mc-dot" data-ok={runnable} aria-hidden="true" />{runnable ? 'Runnable now' : 'Needs provider access'}{accessNote ? ` · ${accessNote}` : ''}</>
          )}
        </p>
        <div className="mc-actions">
          <button type="button" className="mc-btn mc-btn--primary" onClick={() => onInspect(model)}>Inspect<span className="sr-only"> {model.model_name}</span></button>
          <button type="button" className="mc-btn" data-on={compared} aria-pressed={compared} disabled={!compared && compareDisabled} onClick={() => onToggleCompare(model)}>
            {compared ? <Check aria-hidden="true" /> : <GitCompareArrows aria-hidden="true" />}{compared ? 'Selected' : 'Compare'}
          </button>
          {model.external_url ? (
            <a className="mc-btn mc-btn--icon" href={model.external_url} target="_blank" rel="noreferrer noopener" aria-label={`Open ${model.model_name} destination (opens in a new tab)`} title="Open destination">
              <ArrowUpRight aria-hidden="true" />
            </a>
          ) : null}
        </div>
      </footer>
    </article>
  );
}

export const ModelCard = memo(ModelCardBase);
