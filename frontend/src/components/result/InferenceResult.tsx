/**
 * InferenceResult — the routing decision.
 *
 * AI Compass is a routing layer, not a model. This component is
 * therefore built around the decision it produced, not around a
 * response it did not write:
 *
 *   1. Recommended model  (the primary artefact, with the provider)
 *   2. Why this model     (the objective scores behind the choice)
 *   3. Next step          (open the model, use the optimised prompt)
 *   4. Optimised prompt   (adapted for the selected model)
 *   5. Routing details    (analysis, filtering, scoring — collapsible)
 *   6. Model response     (OPTIONAL: only what the provider returned)
 *   7. Evaluation         (the deterministic evaluation of that response)
 *
 * The response section is optional by design. When the backend has not
 * called a provider, the routing decision is still complete and still
 * useful, so the panel does not pretend there is an answer.
 *
 * Every figure shown is a field the API returned for this run. Nothing
 * is derived from registry estimates, and a missing field reads
 * "Unavailable" rather than 0.
 */
import { Suspense, lazy, useCallback, useState } from 'react';
import {
  AlertTriangle,
  ArrowUpRight,
  BarChart3,
  BookOpen,
  Check,
  Clipboard,
  ExternalLink,
  Gauge,
  Info,
  Layers,
  SlidersHorizontal,
} from 'lucide-react';
import { Button, ButtonLink } from '../ui/Button';
import { Badge, ProvenanceTag, Status, Tag, TagList } from '../ui/Badge';
import { MetadataEntry, MetadataRow } from '../ui/Metadata';
import { Panel, PanelBody, PanelFooter, PanelHeader, PanelSection } from '../ui/Panel';
import { DimensionRow } from '../ui/ScoreBar';
import { Notice } from '../ui/EmptyState';
import { useToast } from '../../context/toastContext';
import { useModelProvider } from '../../hooks/useModelProvider';
import { ResponseHeader } from '../response/ResponseHeader';
import { OBJECTIVES, ROUTING_STAGES, groupLabel } from '../../utils/domain';
import { resolveModelLink } from '../../utils/modelLinks';
import {
  formatDuration,
  formatInteger,
  formatNumber,
  formatPercent,
  formatUsd,
  isPresentNumber,
  truncate,
} from '../../utils/format';
import { FeedbackPanel } from './FeedbackPanel';
import type { ModelScore, RouteResponse } from '../../types';

export interface InferenceResultProps {
  result: RouteResponse;
  /** Score row for `selected_model_id`, already looked up by the caller. */
  selectedScore?: ModelScore | null;
}

/**
 * The Markdown renderer pulls in a parser and a syntax highlighter,
 * which together are the heaviest dependency in the app. A response
 * only exists after a routing run, so the renderer is fetched at that
 * point rather than on first paint of /route.
 */
const ModelResponseRenderer = lazy(() =>
  import('../response/ModelResponseRenderer').then((m) => ({ default: m.ModelResponseRenderer })),
);

export function InferenceResult({ result, selectedScore }: InferenceResultProps) {
  const { push } = useToast();
  const [copied, setCopied] = useState<'prompt' | 'response' | 'metadata' | null>(null);

  const escalated = result.escalation_info.escalated;
  const evaluation = result.response_evaluation;
  const metrics = result.performance_metrics;
  const analysis = result.query_analysis;

  // The attempt that actually produced the delivered response, rather
  // than the first selection, when an escalation occurred.
  const usage = result.request_usage.find((entry) => entry.model_id === result.final_model_id);
  const generationLatency = usage?.latency_ms ?? null;
  const requestCost = usage?.estimated_cost ?? metrics.total_estimated_cost;

  // The provider that serves the recommended model. The routing payload
  // carries no provider field, and the model id's prefix is the author,
  // not the host — `openai/gpt-oss-20b` is served by Groq. The registry
  // reports the real provider, so it is the only source used here. An
  // unresolvable id yields `null`, which disables the link instead of
  // sending the user to the wrong company.
  const { provider } = useModelProvider(result.final_model_id);
  const model = {
    model_id: result.final_model_id,
    model_name: result.final_model_name,
    provider,
  };
  const prompt = result.optimized_prompt ?? null;
  const link = resolveModelLink(model, prompt);
  // A model id with no recognisable provider still needs a readable
  // label; `resolveModelLink` falls back to a generic one, which would
  // read as if the provider were unknown rather than unconfigured.
  const providerLabel = provider ? link.providerLabel : 'This provider';

  const hasResponse = typeof result.generated_response === 'string' && result.generated_response.trim().length > 0;

  const copy = useCallback(
    async (what: 'prompt' | 'response' | 'metadata', text: string, title: string) => {
      try {
        await navigator.clipboard.writeText(text);
        setCopied(what);
        window.setTimeout(() => setCopied(null), 1600);
        push({ tone: 'success', title });
      } catch {
        // Clipboard access can be denied by permissions policy. Say so
        // rather than silently doing nothing.
        push({
          tone: 'danger',
          title: 'Could not copy',
          description: 'Your browser blocked clipboard access for this page.',
        });
      }
    },
    [push],
  );

  /**
   * "Open the recommended model".
   *
   * When the provider takes the prompt in the URL, just navigate. When
   * it does not, copy the prompt first and tell the user to paste it —
   * never invent a prefill parameter.
   */
  const openModel = useCallback(async () => {
    if (!link.url) return;
    if (link.carriesPrompt) {
      window.open(link.url, '_blank', 'noopener,noreferrer');
      return;
    }
    if (prompt?.trim()) {
      try {
        await navigator.clipboard.writeText(prompt);
        setCopied('prompt');
        window.setTimeout(() => setCopied(null), 4000);
        push({ tone: 'info', title: 'Prompt copied', description: link.pasteHint });
      } catch {
        push({
          tone: 'warning',
          title: 'Clipboard blocked',
          description: `The provider page was not given your prompt. Copy it manually, then open ${providerLabel}.`,
        });
      }
    }
    window.open(link.url, '_blank', 'noopener,noreferrer');
  }, [link, prompt, providerLabel, push]);

  const metadataText = [
    `Recommended model: ${result.final_model_name} (${result.final_model_id})`,
    `Profile: ${groupLabel(result.profile)}`,
    `Status: ${escalated ? `escalated after ${result.escalation_info.attempts} attempts` : 'selected on first pass'}`,
    `Total latency: ${formatDuration(metrics.total_latency_ms)}`,
    `Routing latency: ${formatDuration(metrics.routing_latency_ms)}`,
    `Generation latency: ${generationLatency != null ? formatDuration(generationLatency) : 'Unavailable'}`,
    `Estimated cost: ${formatUsd(requestCost)}`,
    `Quality: ${formatPercent(evaluation.quality_score)}`,
    `Relevance: ${formatPercent(evaluation.relevance_score)}`,
    `Completeness: ${formatPercent(evaluation.completeness_score)}`,
    `Risk: ${formatPercent(evaluation.risk_score)}`,
  ].join('\n');

  return (
    <div className="result-stack">
      {escalated ? (
        <Notice tone="warning" title="Escalated before delivery" live="status">
          {result.escalation_info.escalation_reason ?? 'The first response did not meet the acceptance criteria.'} The
          router retried on <strong>{result.final_model_name}</strong> after{' '}
          {result.escalation_info.attempts} attempt{result.escalation_info.attempts === 1 ? '' : 's'}; the first
          selection was {result.selected_model_name}.
        </Notice>
      ) : null}

      {/* ── 1. The routing decision. The primary artefact of this app. ── */}
      <Panel tone="primary" className="decision-panel">
        <PanelHeader
          eyebrow="Routing decision"
          title="Recommended model"
          actions={
            <ProvenanceTag kind="measured" label="This run" />
          }
        />

        <PanelBody>
          <div className="decision-model">
            <div className="decision-model-identity">
              <p className="decision-model-name">{result.final_model_name}</p>
              <p className="decision-model-meta">
                <span className="mono">{result.final_model_id}</span>
                {model.provider ? <span> · {providerLabel}</span> : null}
                <span> · routed as {groupLabel(result.profile)}</span>
              </p>
            </div>

            <div className="decision-model-actions">
              {link.url ? (
                <Button
                  variant="primary"
                  onClick={() => void openModel()}
                  trailingIcon={<ArrowUpRight />}
                >
                  Open model
                </Button>
              ) : (
                <Button variant="secondary" disabled title="No provider page is configured for this model">
                  Open model
                </Button>
              )}
              <p className="decision-model-hint">
                {link.carriesPrompt
                  ? `Opens ${providerLabel} with this prompt.`
                  : `AI Compass routes; ${providerLabel} answers.`}
              </p>
            </div>
          </div>

          {/* The objective scores are the evidence for the choice. */}
          {selectedScore ? (
            <div className="decision-objectives">
              {OBJECTIVES.map((objective) => (
                <InferenceScore
                  key={objective.key}
                  label={objective.shortLabel}
                  value={selectedScore[objective.scoreField]}
                  invert={objective.key === 'risk'}
                />
              ))}
              <InferenceScore
                label="Preference"
                value={selectedScore.preference_alignment}
              />
            </div>
          ) : (
            <p className="text-xs text-secondary">
              <Gauge aria-hidden="true" /> The backend did not return a score row for{' '}
              {result.final_model_id}.
            </p>
          )}

          <MetadataRow label="Decision evidence">
            <MetadataEntry label="Overall score" value={formatPercent(selectedScore?.overall_score ?? null)} />
            <MetadataEntry label="Candidates scored" value={`${formatNumber(metrics.candidates_evaluated, 0)} scored`} />
            <MetadataEntry
              label="Excluded"
              value={`${formatNumber(metrics.models_filtered ?? result.filtered_models.length, 0)} filtered`}
            />
            <MetadataEntry label="Routing time" value={formatDuration(metrics.routing_latency_ms)} />
            <MetadataEntry
              label="Total time"
              value={formatDuration(metrics.total_latency_ms)}
              suffix={<Tag>incl. provider call</Tag>}
            />
          </MetadataRow>
        </PanelBody>

        <PanelFooter>
          <div className="row row-wrap">
            <Button
              size="sm"
              variant="secondary"
              onClick={() => void copy('metadata', metadataText, 'Decision copied')}
              leadingIcon={copied === 'metadata' ? <Check /> : <Clipboard />}
            >
              {copied === 'metadata' ? 'Copied' : 'Copy decision'}
            </Button>
            <ButtonLink to="/explanation" size="sm" variant="ghost" leadingIcon={<BookOpen />}>
              Full explanation
            </ButtonLink>
            <ButtonLink to="/evaluation" size="sm" variant="ghost" leadingIcon={<BarChart3 />}>
              Compare strategies
            </ButtonLink>
          </div>
          <p className="panel-footnote">
            <Info aria-hidden="true" />
            AI Compass selected and ranked this model. The response below, if present, was written by the provider.
          </p>
        </PanelFooter>
      </Panel>

      {/* ── 2. Why this model, in plain terms. ── */}
      <Panel>
        <PanelHeader eyebrow="Rationale" title="Why this model" />
        <PanelBody>
          <p className="decision-why">
            {result.routing_explanation.narrative ??
              'The router ranked this model highest on your saved priorities for this request.'}
          </p>

          <div className="decision-why-grid">
            <div>
              <h3 className="panel-section-title">Request</h3>
              <p className="text-xs text-secondary">
                {truncate(analysis.task_type, 60)} · {truncate(analysis.domain, 40)} ·{' '}
                {formatPercent(analysis.complexity, 0)} complexity
              </p>
            </div>
            <div>
              <h3 className="panel-section-title">Requirements</h3>
              <p className="text-xs text-secondary">
                {formatPercent(analysis.quality_requirement, 0)} quality ·{' '}
                {formatPercent(analysis.latency_requirement, 0)} speed
              </p>
            </div>
            <div>
              <h3 className="panel-section-title">Primary factors</h3>
              <TagList
                items={topFactors(selectedScore)}
              />
            </div>
          </div>
        </PanelBody>
      </Panel>

      {/* ── 3. The optimised prompt, adapted for the selected model. ── */}
      <Panel>
        <PanelHeader
          eyebrow="Next step"
          title="Optimised prompt"
          actions={
            prompt ? (
              <Button
                size="sm"
                variant="secondary"
                onClick={() => void copy('prompt', prompt, 'Prompt copied')}
                leadingIcon={copied === 'prompt' ? <Check /> : <Clipboard />}
              >
                {copied === 'prompt' ? 'Copied' : 'Copy prompt'}
              </Button>
            ) : null
          }
        />
        <PanelBody>
          {prompt ? (
            <>
              <p className="prompt-note">
                <Info aria-hidden="true" />
                Adapted for {result.final_model_name}. The wording of your request is preserved; this changes the
                framing, not the meaning.
              </p>
              <div className="prompt-text-container" tabIndex={0} role="region" aria-label="Optimised prompt">
                <div className="prompt-text">{prompt}</div>
              </div>
              <div className="row row-wrap">
                {link.url ? (
                  <Button variant="primary" size="sm" onClick={() => void openModel()} trailingIcon={<ExternalLink />}>
                    {link.carriesPrompt ? `Open ${providerLabel}` : 'Open model and paste'}
                  </Button>
                ) : null}
                {!link.carriesPrompt && link.url ? (
                  <p className="prompt-hint">{link.pasteHint}</p>
                ) : null}
              </div>
            </>
          ) : (
            /* Honest unavailable state: the backend does not return an
               adapted prompt yet, and inventing one would misrepresent
               what the system actually produced. */
            <Notice tone="neutral" icon={<SlidersHorizontal />} title="No adapted prompt yet">
              The routing endpoint does not return a model-specific prompt for this run, so there is nothing to hand to{' '}
              {result.final_model_name} yet. The decision above is complete — open the model and use your original
              query, or re-run the request once prompt adaptation is available.
            </Notice>
          )}
        </PanelBody>
      </Panel>

      {/* ── 4. Routing transparency, kept out of the way until asked. ── */}
      <details className="disclosure route-analysis">
        <summary>
          <Layers aria-hidden="true" />
          Routing details
        </summary>
        <div className="disclosure-body route-analysis-body">
          <ol className="pipeline-horizontal" aria-label="Routing stages completed for this request">
            {ROUTING_STAGES.map((stage) => (
              <li key={stage.id} className="pipeline-step" data-state="done">
                <span className="pipeline-marker" />
                <span className="pipeline-title">{stage.label}</span>
                <span className="pipeline-detail">{stage.detail}</span>
              </li>
            ))}
          </ol>

          <div className="split">
            <section>
              <h3 className="panel-section-title">Why this model</h3>
              {selectedScore ? (
                <>
                  <div className="dimension-list">
                    {OBJECTIVES.map((objective) => (
                      <DimensionRow
                        key={objective.key}
                        label={objective.label}
                        value={selectedScore[objective.scoreField]}
                        description={objective.description}
                      />
                    ))}
                  </div>
                  <div className="row between inference-score-total">
                    <strong>Overall routing score</strong>
                    <span className="text-numeric">{formatPercent(selectedScore.overall_score)}</span>
                  </div>
                </>
              ) : (
                <p className="text-xs text-secondary">
                  The API did not return a score row for {result.final_model_id}.
                </p>
              )}
            </section>
            <section>
              <h3 className="panel-section-title">Query analysis</h3>
              <div className="inference-chips">
                <Badge tone="primary" outline>
                  {truncate(analysis.task_type, 40)}
                </Badge>
                <Badge tone="neutral" outline>
                  {truncate(analysis.domain, 40)}
                </Badge>
                <Tag>Analysis: {analysis.analysis_method}</Tag>
                <Tag>~{formatNumber(analysis.estimated_tokens, 0)} tokens</Tag>
              </div>
              <div className="dimension-list">
                <DimensionRow label="Quality requirement" value={analysis.quality_requirement} />
                <DimensionRow label="Risk level" value={analysis.risk_level} />
                <DimensionRow label="Speed requirement" value={analysis.latency_requirement} />
                <DimensionRow label="Cost sensitivity" value={analysis.cost_sensitivity} />
                <DimensionRow label="Reliability requirement" value={analysis.reliability_requirement} />
              </div>
            </section>
          </div>

          <ConstraintSummary result={result} />

          <p className="panel-footnote">
            <Info aria-hidden="true" />
            Held for this session only — the backend exposes no routing-history endpoint.
          </p>
        </div>
      </details>

      {/* ── 5. The provider's response. Optional by design. ── */}
      {hasResponse ? (
        <Panel className="response-panel">
          <PanelHeader eyebrow="From the provider" title="Model response" />
          <PanelBody>
            {/* Attribution stays a single compact row so the response
                itself keeps the vertical space. */}
            <ResponseHeader
              modelName={result.final_model_name}
              provider={providerLabel}
              facts={[
                providerLabel,
                generationLatency != null ? formatDuration(generationLatency) : null,
                usage?.total_tokens != null ? `${formatInteger(usage.total_tokens)} tokens` : null,
                requestCost != null ? `${formatUsd(requestCost)} estimated` : null,
              ].filter((f): f is string => Boolean(f))}
              onCopy={() => void copy('response', result.generated_response, 'Response copied')}
            />

            <Suspense
              fallback={
                <div className="model-response-loading" role="status">
                  Rendering the provider&rsquo;s response&hellip;
                </div>
              }
            >
              <ModelResponseRenderer
                content={result.generated_response}
                label={`Response from ${result.final_model_name}`}
              />
            </Suspense>
          </PanelBody>

          <PanelFooter>
            <p className="panel-footnote">
              <AlertTriangle aria-hidden="true" />
              The text above was returned by {result.final_model_name} at {providerLabel}. AI Compass selected the
              model and evaluated the result; it did not write this response.
            </p>
          </PanelFooter>
        </Panel>
      ) : (
        <Panel tone="muted">
          <PanelHeader eyebrow="From the provider" title="Model response" />
          <PanelBody>
            <p className="text-xs text-secondary">
              No provider response was returned for this run. That does not affect the routing decision above — AI
              Compass can recommend a model without calling it.
            </p>
          </PanelBody>
        </Panel>
      )}

      {/* ── 6. Evaluation of the provider's response. ── */}
      {hasResponse ? (
        <Panel>
          <PanelHeader
            eyebrow="Evaluation"
            title="Response evaluation"
            actions={
              <>
                <Tag>{evaluation.evaluation_method}</Tag>
                <Status name={evaluation.accepted ? 'passed' : 'warning'}>
                  {evaluation.accepted ? 'Accepted' : 'Below threshold'}
                </Status>
              </>
            }
          />
          <PanelBody>
            <div className="inference-scores">
              <InferenceScore label="Quality" value={evaluation.quality_score} />
              <InferenceScore label="Relevance" value={evaluation.relevance_score} />
              <InferenceScore label="Completeness" value={evaluation.completeness_score} />
              <InferenceScore label="Risk" value={evaluation.risk_score} invert />
            </div>
            {evaluation.evaluation_reasons.length > 0 ? (
              <PanelSection title="Observations">
                <TagList items={evaluation.evaluation_reasons} />
              </PanelSection>
            ) : null}
          </PanelBody>
        </Panel>
      ) : null}

      {/* ── 7. Feedback — only shown when there is a real response to rate. ── */}
      {hasResponse ? <FeedbackPanel result={result} /> : null}
    </div>
  );
}

/**
 * The three objectives that contributed most to the winning score, read
 * from the score row. Falls back to the objectives themselves when the
 * backend returned no scores, so the section is never empty.
 */
function topFactors(selectedScore: ModelScore | null | undefined): string[] {
  if (!selectedScore) return OBJECTIVES.slice(0, 3).map((o) => o.label);
  return [...OBJECTIVES]
    .sort(
      (a, b) => Number(selectedScore[b.scoreField]) - Number(selectedScore[a.scoreField]),
    )
    .slice(0, 3)
    .map((objective) => objective.label);
}

/* ------------------------------------------------------------------ *
 * Helpers
 * ------------------------------------------------------------------ */

function InferenceScore({
  label,
  value,
  invert,
  hint,
}: {
  label: string;
  value: number | null | undefined;
  /** True when a lower raw value is the better outcome (risk). */
  invert?: boolean;
  hint?: string;
}) {
  const available = isPresentNumber(value);
  const shown = available ? (invert ? 1 - (value as number) : value) : null;
  return (
    <div className="inference-score">
      <div className="inference-score-head">
        <span className="inference-score-label">{label}</span>
        <span className="inference-score-value" data-unavailable={!available || undefined}>
          {shown === null ? 'Unavailable' : formatPercent(shown)}
        </span>
      </div>
      <div className="score-track" aria-hidden="true">
        <div
          className="score-fill"
          style={{
            width: `${(shown ?? 0) * 100}%`,
            ['--score-color' as string]: 'var(--color-primary)',
          }}
        />
      </div>
      {hint ? <span className="sr-only">{hint}</span> : null}
    </div>
  );
}

function ConstraintSummary({ result }: { result: RouteResponse }) {
  // The backend returns `{}` when no hard constraint was submitted, and
  // an empty object is truthy, so the entry count decides which of the
  // two states is shown.
  const chips = Object.entries(result.routing_explanation.applied_constraints ?? {}).map(
    ([key, value]) => `${key.replace(/_/g, ' ')}: ${String(value)}`,
  );

  return (
    <section>
      <h3 className="panel-section-title">Applied constraints</h3>
      {chips.length > 0 ? (
        <TagList items={chips} />
      ) : (
        <p className="text-xs text-secondary">
          <Gauge aria-hidden="true" /> No hard constraints were submitted — every active model was eligible for scoring.
        </p>
      )}
    </section>
  );
}
