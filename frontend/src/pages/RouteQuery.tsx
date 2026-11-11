/**
 * RouteQuery — Premium AI Model Recommendation Workspace.
 *
 * The recommendation is the visual centerpiece. Score visualizations,
 * ranked alternatives, tool recommendations, and full explainability
 * are all surfaced in a premium card-based layout.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowRight,
  BarChart3,
  BookOpen,
  Bot,
  Check,
  ChevronDown,
  ChevronUp,
  Clipboard,
  Code2,
  Compass,
  ExternalLink,
  Filter,
  FileText,
  Gauge,
  Image,
  Layers,
  Loader2,
  Music2,
  Presentation,
  Search,
  ShieldCheck,
  Sliders,
  Sparkles,
  Star,
  Wand2,
  Zap,
  Video,
} from 'lucide-react';
import { ButtonLink } from '../components/ui/Button';
import { useToast } from '../context/toastContext';
import { useAuth } from '../context/authContext';
import { useRouteResult } from '../context/routeResultContext';
import { routeAndGenerate } from '../services/routing.service';
import { listModels } from '../services/models.service';
import { optimizePrompt as requestPromptOptimization } from '../services/promptOptimization.service';
import { describeError } from '../services/http';
import { OBJECTIVES, EXAMPLE_QUERIES, groupLabel } from '../utils/domain';
import { formatPercent, formatDuration, formatUsd, toPercent } from '../utils/format';
import type { RouteRequest, RouteResponse, RankedAlternative, ModelInfo } from '../types';

const MAX_QUERY = 8000;

const TASK_CATEGORIES = [
  ['coding', 'Coding'], ['research', 'Research'], ['creative', 'Writing'],
  ['analysis', 'Analysis'], ['math', 'Mathematics'], ['image-generation', 'Image generation'],
  ['video-generation', 'Video generation'], ['presentation', 'Presentations'],
  ['audio-generation', 'Audio / music'], ['design', 'Design'],
  ['education', 'Learning'], ['summarization', 'Summarization'],
  ['reasoning', 'General reasoning'],
] as const;

const TOOL_TASK_ALIASES: Record<string, string[]> = {
  coding: ['coding', 'debugging', 'programming'],
  research: ['research', 'summarization', 'web search'],
  creative: ['writing', 'creative', 'summarization'],
  analysis: ['analysis', 'reasoning'],
  math: ['math', 'reasoning'],
  'image-generation': ['image-generation', 'image-editing'],
  'video-generation': ['video-generation', 'video-editing'],
  presentation: ['presentation', 'slides'],
  'audio-generation': ['audio-generation', 'music-generation', 'voice-synthesis'],
  design: ['image-generation', 'image-editing', 'design'],
  education: ['education', 'reasoning', 'qa'],
  summarization: ['summarization', 'research', 'writing'],
  reasoning: ['reasoning', 'analysis', 'qa'],
};

function inferToolTask(query: string): string | null {
  const text = query.toLowerCase();
  const intents: Array<[string, RegExp]> = [
    ['image-generation', /\b(image|illustration|draw|poster|logo|visual)\b/],
    ['video-generation', /\b(video|film|animation|clip)\b/],
    ['audio-generation', /\b(audio|music|song|soundtrack|voice)\b/],
    ['presentation', /\b(presentation|slides?|slide deck)\b/],
    ['coding', /\b(code|coding|function|program|debug|bug|api|script)\b/],
    ['research', /\b(research|sources?|citations?|literature|web search)\b/],
    ['summarization', /\b(summarize|summarise|summary|summarization|summarisation)\b/],
    ['education', /\b(learn|lesson|tutorial|teach|explain|beginner)\b/],
    ['analysis', /\b(analy[sz]e|analysis|compare|evaluate|assess)\b/],
    ['creative', /\b(write|writing|story|essay|article|blog)\b/],
  ];
  return intents.find(([, pattern]) => pattern.test(text))?.[0] ?? null;
}

function getRelevantTools(models: ModelInfo[], task: string | null, query: string): ModelInfo[] {
  if (!task) return [];
  const aliases = TOOL_TASK_ALIASES[task] ?? [task];
  return models
    .filter(model => model.entry_type !== 'inference_model' && model.external_url)
    .map(model => {
      const tags = [...model.supported_tasks, ...model.capabilities].map(tag => tag.toLowerCase());
      const score = aliases.reduce(
        (total, alias) => total + (tags.some(tag => tag === alias || tag.includes(alias)) ? 1 : 0),
        0,
      );
      const queryMatch = query.trim().length > 0
        && `${model.model_name} ${model.description ?? ''} ${model.capabilities.join(' ')}`
          .toLowerCase().includes(query.trim().toLowerCase());
      return { model, score: score + (queryMatch ? 1 : 0) };
    })
    .filter(item => item.score > 0)
    .sort((a, b) => b.score - a.score || a.model.model_name.localeCompare(b.model.model_name))
    .slice(0, 4)
    .map(item => item.model);
}

function providerColor(_provider: string): string {
  return 'var(--color-primary)';
}

export function RouteQuery() {
  const { user } = useAuth();
  const { push } = useToast();
  const { result, isRouting, setResult, setRouting, clearResult } = useRouteResult();

  const [query, setQuery] = useState('');
  const [taskTypeHint, setTaskTypeHint] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [error, setError] = useState<{ message: string; hint?: string } | null>(null);
  const [showConstraints, setShowConstraints] = useState(false);
  const [maxCost, setMaxCost] = useState('');
  const [maxLatency, setMaxLatency] = useState('');
  const [capabilities, setCapabilities] = useState<string[]>([]);
  const [selectedModelIds, setSelectedModelIds] = useState<string[]>([]);
  const [compareWith, setCompareWith] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [optimizerBusy, setOptimizerBusy] = useState(false);
  const [optimizerError, setOptimizerError] = useState<string | null>(null);
  const [optimizerMethod, setOptimizerMethod] = useState(result ? 'Task-aware local optimizer' : '');
  const [optimizedFor, setOptimizedFor] = useState(result?.query ?? '');
  const [registryModels, setRegistryModels] = useState<ModelInfo[]>([]);
  const [registryLoading, setRegistryLoading] = useState(true);
  const [registryError, setRegistryError] = useState<string | null>(null);
  const [optimizedPrompt, setOptimizedPrompt] = useState(
    result?.optimized_prompt || result?.query || '',
  );

  const controllerRef = useRef<AbortController | null>(null);
  const optimizerControllerRef = useRef<AbortController | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => () => {
    controllerRef.current?.abort();
    optimizerControllerRef.current?.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    listModels(controller.signal)
      .then(setRegistryModels)
      .catch(cause => {
        if (!controller.signal.aborted) {
          const failure = describeError(cause, 'Could not load the model registry.');
          setRegistryError(failure.hint ? `${failure.message} ${failure.hint}` : failure.message);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setRegistryLoading(false);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
  }, [query]);

  const run = useCallback(async () => {
    if (isRouting) return;
    const q = query.trim();
    if (q.length < 3) { setFieldError('Enter at least 3 characters.'); return; }
    setFieldError(null); setError(null);

    const payload: RouteRequest = { query: q };
    if (taskTypeHint) payload.task_type_hint = taskTypeHint;
    if (selectedModelIds.length) payload.model_ids = selectedModelIds;
    if (showConstraints) {
      if (capabilities.length) payload.require_capabilities = capabilities;
      if (maxCost.trim()) {
        const v = Number(maxCost);
        if (!Number.isFinite(v) || v <= 0) { setFieldError('Max cost must be a positive number.'); return; }
        payload.max_cost = v;
      }
      if (maxLatency.trim()) {
        const v = Number(maxLatency);
        if (!Number.isFinite(v) || v <= 0) { setFieldError('Max latency must be a positive number.'); return; }
        payload.max_latency = v;
      }
    }

    controllerRef.current?.abort();
    const ctrl = new AbortController();
    controllerRef.current = ctrl;
    setRouting(true);
    setCompareWith(null);

    try {
      const res = await routeAndGenerate(payload, ctrl.signal);
      setOptimizedPrompt(res.optimized_prompt || res.query);
      setOptimizedFor(res.query);
      setOptimizerMethod('Task-aware local optimizer');
      setOptimizerError(null);
      setResult(res);
      push({
        tone: res.escalation_info.escalated ? 'warning' : 'success',
        title: res.escalation_info.escalated
          ? `Escalated → ${res.final_model_name}`
          : `Recommended: ${res.final_model_name}`,
      });
    } catch (cause) {
      if (ctrl.signal.aborted) return;
      setError(describeError(cause, 'Routing failed.'));
    } finally {
      if (!ctrl.signal.aborted) setRouting(false);
    }
  }, [query, taskTypeHint, isRouting, showConstraints, maxCost, maxLatency, capabilities, selectedModelIds, push, setResult, setRouting]);

  const handleKey = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); void run(); }
  }, [run]);

  const copyResult = useCallback(async (value?: string) => {
    const text = value ?? optimizedPrompt ?? result?.optimized_prompt ?? result?.query ?? '';
    if (!text.trim()) {
      setOptimizerError('There is no prompt to copy yet.');
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      setOptimizerError(null);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setOptimizerError('Clipboard access was denied. Select and copy the prompt text manually.');
    }
  }, [result, optimizedPrompt]);

  const originalPrompt = query.trim() || result?.query || '';
  const selectedTaskForTools = taskTypeHint
    ?? (query.trim() && result?.query !== query.trim()
      ? inferToolTask(query)
      : result?.query_analysis.task_type ?? inferToolTask(query));
  const suggestedTools = useMemo(
    () => getRelevantTools(registryModels, selectedTaskForTools, query),
    [registryModels, selectedTaskForTools, query],
  );
  const selectableModels = useMemo(
    () => registryModels.filter(model => model.entry_type === 'inference_model' || model.entry_type === 'model'),
    [registryModels],
  );

  const optimizeCurrentPrompt = useCallback(async () => {
    if (!originalPrompt.trim()) {
      setOptimizerError('Enter a query before optimizing its prompt.');
      return;
    }
    optimizerControllerRef.current?.abort();
    const controller = new AbortController();
    optimizerControllerRef.current = controller;
    setOptimizerBusy(true);
    setOptimizerError(null);
    try {
      const response = await requestPromptOptimization(
        { query: originalPrompt, ...(taskTypeHint ? { task_type_hint: taskTypeHint } : {}) },
        controller.signal,
      );
      setOptimizedPrompt(response.optimized_prompt);
      setOptimizedFor(originalPrompt);
      setOptimizerMethod(response.method);
    } catch (cause) {
      if (!controller.signal.aborted) {
        const failure = describeError(cause, 'Prompt optimization failed.');
        setOptimizerError(failure.hint ? `${failure.message} ${failure.hint}` : failure.message);
      }
    } finally {
      if (!controller.signal.aborted) setOptimizerBusy(false);
    }
  }, [originalPrompt, taskTypeHint]);

  const resetOptimizedPrompt = useCallback(() => {
    setOptimizedPrompt(originalPrompt);
    setOptimizedFor(originalPrompt);
    setOptimizerMethod('Original query');
    setOptimizerError(null);
  }, [originalPrompt]);

  const selectedScore = useMemo(
    () => result?.model_scores.find(s => s.model_id === result.final_model_id) ?? null,
    [result],
  );

  const compareScore = useMemo(
    () => compareWith ? result?.model_scores.find(s => s.model_id === compareWith) ?? null : null,
    [result, compareWith],
  );

  return (
    <div className="rq-shell">
      <header className="rq-page-intro">
        <div>
          <p className="rq-page-eyebrow">AI Compass · Workspace</p>
          <h1>Route Query</h1>
          <p>Describe the task. AI Compass compares eligible models against your constraints and routing priorities.</p>
        </div>
        <span className="rq-workflow-label">Task <span aria-hidden="true">→</span> analysis <span aria-hidden="true">→</span> recommendation</span>
        <ButtonLink to="/models" variant="ghost" size="sm" trailingIcon={<ArrowRight />}>
          Browse model pool
        </ButtonLink>
      </header>

      <div className="rq-main-col">
        <div className="rq-input-col">
          <div className="rq-input-card">
            <div className="rq-input-header">
              <div className="rq-input-header-icon"><Compass aria-hidden="true" /></div>
              <div>
                <h2 className="rq-input-title">What are you working on?</h2>
                <p className="rq-input-sub">A little context helps the router find the right fit.</p>
              </div>
            </div>

            <div className="rq-textarea-wrap">
              <textarea
                ref={textareaRef}
                className="rq-textarea"
                placeholder="What would you like to accomplish? Be specific about your task, domain, and requirements…"
                value={query}
                onChange={e => setQuery(e.target.value.slice(0, MAX_QUERY))}
                onKeyDown={handleKey}
                rows={4}
                disabled={isRouting}
                aria-label="Query"
                aria-invalid={!!fieldError}
              />
              {fieldError && <p className="rq-field-error">{fieldError}</p>}
              <div className="rq-textarea-foot">
                <span className="rq-char-count">{query.length.toLocaleString()} / {MAX_QUERY.toLocaleString()}</span>
                <span className="rq-hint">⌘↵ to route</span>
              </div>
            </div>

            <div className="rq-examples">
              <span className="rq-examples-label">Try</span>
              {EXAMPLE_QUERIES.map(ex => (
                <button key={ex.label} type="button" className="rq-example-chip"
                  onClick={() => { setQuery(ex.text); setFieldError(null); }} disabled={isRouting}>
                  {ex.label}
                </button>
              ))}
            </div>

            <div className="rq-examples" aria-label="Task category">
              <span className="rq-examples-label">Task type</span>
              {TASK_CATEGORIES.map(([value, label]) => (
                <button key={value} type="button" className="rq-example-chip"
                  aria-pressed={taskTypeHint === value}
                  onClick={() => setTaskTypeHint(current => current === value ? null : value)}
                  disabled={isRouting}>
                  {label}
                </button>
              ))}
            </div>

            <details className="rq-model-pool">
              <summary>
                <span><Layers aria-hidden="true" /> Model pool</span>
                <small>
                  {selectedModelIds.length
                    ? `${selectedModelIds.length} selected`
                    : `All eligible models${selectableModels.length ? ` · ${selectableModels.length}` : ''}`}
                </small>
              </summary>
              <p className="rq-pool-description">
                Choose API models to compare, or leave the pool unfiltered to include every eligible model.
              </p>
              {registryLoading ? (
                <p className="rq-tools-message">Loading the model registry…</p>
              ) : registryError ? (
                <p className="rq-tools-error">{registryError}</p>
              ) : selectableModels.length ? (
                <div className="rq-model-pool-list">
                  {selectableModels.map(model => (
                    <label className="rq-model-pool-option" key={model.model_id}>
                      <input
                        type="checkbox"
                        checked={selectedModelIds.includes(model.model_id)}
                        onChange={event => setSelectedModelIds(current =>
                          event.target.checked
                            ? [...current, model.model_id]
                            : current.filter(id => id !== model.model_id),
                        )}
                        disabled={isRouting}
                      />
                      <span>
                        <strong>{model.model_name}</strong>
                        <small>{model.provider}</small>
                      </span>
                    </label>
                  ))}
                </div>
              ) : (
                <p className="rq-tools-message">No API inference models are available in the registry.</p>
              )}
              {selectedModelIds.length > 0 && (
                <button type="button" className="rq-pool-reset" onClick={() => setSelectedModelIds([])}>
                  Clear selection
                </button>
              )}
            </details>

            <button type="button" className="rq-constraints-toggle"
              onClick={() => setShowConstraints(v => !v)}>
              <Filter aria-hidden="true" />
              Hard constraints
              {showConstraints ? <ChevronUp aria-hidden="true" /> : <ChevronDown aria-hidden="true" />}
            </button>

            {showConstraints && (
              <div className="rq-constraints-body">
                <div className="rq-constraint-field">
                  <label className="rq-constraint-label" htmlFor="max-cost">Max cost (USD / request)</label>
                  <input id="max-cost" className="rq-constraint-input" type="number" min="0" step="0.001"
                    placeholder="0.05" value={maxCost} onChange={e => setMaxCost(e.target.value)} disabled={isRouting} />
                </div>
                <div className="rq-constraint-field">
                  <label className="rq-constraint-label" htmlFor="max-latency">Max latency (seconds)</label>
                  <input id="max-latency" className="rq-constraint-input" type="number" min="0" step="0.5"
                    placeholder="10" value={maxLatency} onChange={e => setMaxLatency(e.target.value)} disabled={isRouting} />
                </div>
                <div className="rq-constraint-field">
                  <span className="rq-constraint-label">Required capabilities</span>
                  <div className="rq-examples" aria-label="Required capabilities">
                    {['coding', 'reasoning', 'math', 'research', 'image-generation'].map(capability => (
                      <button key={capability} type="button" className="rq-example-chip"
                        aria-pressed={capabilities.includes(capability)}
                        onClick={() => setCapabilities(current => current.includes(capability) ? current.filter(item => item !== capability) : [...current, capability])}>
                        {capability.replace('-', ' ')}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            <div className="rq-actions">
              <div className="rq-profile-tag">
                <Gauge aria-hidden="true" />
                {groupLabel(user?.user_group)}
                {user?.preferences_customized ? ' · custom weights' : ' · group defaults'}
              </div>
              <div className="rq-action-btns">
                {result && !isRouting && (
                  <button type="button" className="rq-clear-btn" onClick={clearResult}>Clear</button>
                )}
                <button type="button" className="rq-route-btn" onClick={() => void run()} disabled={isRouting || !query.trim()}>
                  {isRouting ? <><Loader2 className="spin" aria-hidden="true" />Routing…</> : <><Wand2 aria-hidden="true" />Find Best Model</>}
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="rq-result-col">
          {isRouting && <RoutingLoader />}

          {!isRouting && error && (
            <div className="rq-error-card">
              <ShieldCheck aria-hidden="true" />
              <div>
                <p className="rq-error-title">Routing failed</p>
                <p className="rq-error-msg">{error.message}</p>
                {error.hint && <p className="rq-error-hint">{error.hint}</p>}
              </div>
              <button type="button" className="rq-retry-btn" onClick={() => void run()}>Retry</button>
            </div>
          )}

          {!isRouting && !error && !result && <RecommendationEmpty />}

          {!isRouting && !error && result && (
            <>
              <RecommendationCard
                key={result.routing_id}
                result={result}
                selectedScore={selectedScore}
                onCopy={() => void copyResult()}
                copied={copied}
              />

              {result.ranked_alternatives.length > 0 && (
                <AlternativesCard
                  alternatives={result.ranked_alternatives}
                  compareWith={compareWith}
                  onCompare={id => setCompareWith(prev => prev === id ? null : id)}
                />
              )}

            </>
          )}
        </div>

        <OptimizedPromptCard
          original={originalPrompt}
          prompt={optimizedPrompt}
          method={optimizerMethod}
          stale={!!optimizedFor && optimizedFor !== originalPrompt}
          busy={optimizerBusy}
          error={optimizerError}
          copied={copied}
          onChange={value => {
            setOptimizedPrompt(value);
            setOptimizerError(null);
          }}
          onOptimize={() => void optimizeCurrentPrompt()}
          onReset={resetOptimizedPrompt}
          onCopy={() => void copyResult(optimizedPrompt)}
        />
      </div>

      <aside className="rq-sidebar" aria-label="Recommendation context">
        <section className="rq-context-card rq-status-card">
          <div className="rq-context-heading">
            <Compass aria-hidden="true" />
            <h2>Recommendation status</h2>
          </div>
          <span className={`rq-status-badge${error ? ' rq-status-badge--error' : isRouting ? ' rq-status-badge--working' : ' rq-status-badge--ready'}`}>
            {error ? 'Needs attention' : isRouting ? 'In progress' : result ? 'Complete' : 'Ready'}
          </span>
          <p className="rq-context-copy">
            {error
              ? 'The last request could not be completed. Review the error and retry.'
              : isRouting
                ? 'Analyzing your task and comparing eligible models.'
                : result
                  ? result.escalation_info.escalated
                    ? 'Routing completed with an escalation.'
                    : 'Your recommendation and alternatives are ready.'
                  : 'Describe a task to get a model recommendation.'}
          </p>
        </section>

        <ToolRecommendationsCard
          tools={suggestedTools}
          task={selectedTaskForTools}
          loading={registryLoading}
          error={registryError}
        />

        {user?.routing_preferences && (
          <section className="rq-weights-card">
            <div className="rq-weights-header">
              <Sliders aria-hidden="true" />
              <span>Routing preferences</span>
              <ButtonLink to="/profile" variant="ghost" size="sm">
                Edit <ArrowRight aria-hidden="true" />
              </ButtonLink>
            </div>
            <div className="rq-weights-list">
              {OBJECTIVES.map(obj => {
                const weight = user.routing_preferences[obj.key] ?? 0;
                return (
                  <div key={obj.key} className="rq-weight-row">
                    <span className="rq-weight-label">{obj.shortLabel}</span>
                    <div className="rq-weight-track">
                      <div className="rq-weight-fill" style={{ width: `${toPercent(weight)}%` }} />
                    </div>
                    <span className="rq-weight-val">{formatPercent(weight, 0)}</span>
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {!isRouting && !error && selectedScore && (
          <ScoreBreakdownCard
            score={selectedScore}
            compareScore={compareScore}
            compareModelName={compareWith
              ? result?.ranked_alternatives.find(alternative => alternative.model_id === compareWith)?.model_name
              : undefined}
          />
        )}

        <section className="rq-context-card rq-learning-card">
          <div className="rq-context-heading">
            <Sparkles aria-hidden="true" />
            <h2>Personalization</h2>
          </div>
          <p className="rq-context-copy">
            {!isRouting && !error && result
              ? result.learning_active
                ? 'Learning is active for this recommendation.'
                : 'Learning is currently inactive for this recommendation.'
              : user?.preferences_customized
                ? 'Your custom routing weights personalize recommendations.'
                : 'Recommendations use your group defaults.'}
          </p>
          <ButtonLink to="/personalization" variant="ghost" size="sm" trailingIcon={<ArrowRight />}>
            View learning settings
          </ButtonLink>
        </section>

        <section className="rq-context-card rq-quick-actions">
          <h2>Quick actions</h2>
          <ButtonLink to="/explanation" variant="ghost" size="sm" leadingIcon={<BarChart3 />}>
            Full explanation
          </ButtonLink>
          <ButtonLink to="/evaluation" variant="ghost" size="sm" leadingIcon={<Layers />}>
            Compare strategies
          </ButtonLink>
        </section>
      </aside>
    </div>
  );
}

/* ------------------------------------------------------------------ */

function RoutingLoader() {
  return (
    <div className="rq-loading-card">
      <div className="rq-loading-orb">
        <Compass className="rq-loading-compass" aria-hidden="true" />
      </div>
      <p className="rq-loading-title">Routing your request…</p>
      <p className="rq-loading-sub">
        Analysing query · Filtering candidates · Scoring models · Selecting best match
      </p>
      <div className="rq-loading-stages">
        {['Query Analysis', 'Candidate Filter', 'Multi-Objective Score', 'Select & Generate'].map((s, i) => (
          <div key={s} className="rq-loading-stage" style={{ animationDelay: `${i * 0.18}s` }}>
            <div className="rq-loading-stage-dot" />
            <span>{s}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function RecommendationEmpty() {
  return (
    <div className="rq-empty-card">
      <div className="rq-empty-icon"><Compass /></div>
      <h2 className="rq-empty-title">No recommendation yet</h2>
      <p className="rq-empty-sub">
        Describe your task and AI Compass will recommend the optimal model from the registry,
        with full score transparency and ranked alternatives.
      </p>
      <div className="rq-empty-features">
        {[
          { icon: Star, text: 'Best model recommendation' },
          { icon: BarChart3, text: 'Score breakdown' },
          { icon: Layers, text: 'Ranked alternatives' },
          { icon: Zap, text: 'Personalized weights' },
        ].map(f => (
          <div key={f.text} className="rq-empty-feature">
            <f.icon aria-hidden="true" />
            <span>{f.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function RecommendationCard({
  result, selectedScore, onCopy, copied,
}: {
  result: RouteResponse;
  selectedScore: RouteResponse['model_scores'][0] | null;
  onCopy: (value?: string) => void;
  copied: boolean;
}) {
  const score = selectedScore?.overall_score ?? null;
  const pct = score !== null ? Math.round(score * 100) : null;
  const provider = result.recommended_destination.provider || result.final_model_id.split('/')[0];
  const color = providerColor(provider);

  return (
    <div className="rq-rec-card">
      <div className="rq-rec-header">
        <div className="rq-rec-badge">
          <Star aria-hidden="true" />
          Best Match
        </div>
        {result.escalation_info.escalated && (
          <div className="rq-rec-escalated-badge">Escalated</div>
        )}
        <div className="rq-rec-actions">
          <button type="button" className="rq-icon-btn" onClick={() => onCopy()} title="Copy optimized prompt">
            {copied ? <Check aria-hidden="true" /> : <Clipboard aria-hidden="true" />}
          </button>
        </div>
      </div>

      <div className="rq-rec-body">
        <div className="rq-rec-model-row">
          <div className="rq-rec-model-avatar" style={{ background: color }}>
            <Bot aria-hidden="true" />
          </div>
          <div className="rq-rec-model-info">
            <h2 className="rq-rec-model-name">{result.final_model_name}</h2>
            <p className="rq-rec-model-meta">
              <span className="rq-rec-provider">{provider}</span>
              <span className="rq-rec-sep">·</span>
              <span className="rq-rec-id">{result.final_model_id}</span>
            </p>
          </div>
          {pct !== null && (
            <div className="rq-rec-score-ring">
              <svg viewBox="0 0 44 44" className="rq-score-svg" aria-hidden="true">
                <circle cx="22" cy="22" r="18" className="rq-score-track" />
                <circle cx="22" cy="22" r="18" className="rq-score-fill"
                  style={{ strokeDashoffset: `${113 - (113 * pct) / 100}` }} />
              </svg>
              <span className="rq-score-label">{pct}</span>
            </div>
          )}
        </div>

        {result.routing_explanation.narrative && (
          <p className="rq-rec-narrative">{result.routing_explanation.narrative}</p>
        )}

        <div className="rq-rec-scores">
          {OBJECTIVES.map(obj => {
            const val = selectedScore ? selectedScore[obj.scoreField] as number : null;
            return (
              <div key={obj.key} className="rq-rec-score-item">
                <span className="rq-rec-score-label">{obj.shortLabel}</span>
                <div className="rq-rec-score-bar-wrap">
                  <div className="rq-rec-score-bar">
                    <div className="rq-rec-score-fill" style={{ width: `${toPercent(val)}%` }} />
                  </div>
                </div>
                <span className="rq-rec-score-val">{formatPercent(val, 0)}</span>
              </div>
            );
          })}
        </div>

        <div className="rq-rec-meta-row">
          <div className="rq-rec-meta-item">
            <span className="rq-rec-meta-label">Routing time</span>
            <span className="rq-rec-meta-val">{formatDuration(result.performance_metrics.routing_latency_ms)}</span>
          </div>
          <div className="rq-rec-meta-item">
            <span className="rq-rec-meta-label">Total latency</span>
            <span className="rq-rec-meta-val">{formatDuration(result.performance_metrics.total_latency_ms)}</span>
          </div>
          <div className="rq-rec-meta-item">
            <span className="rq-rec-meta-label">Est. cost</span>
            <span className="rq-rec-meta-val">{formatUsd(result.performance_metrics.total_estimated_cost)}</span>
          </div>
          <div className="rq-rec-meta-item">
            <span className="rq-rec-meta-label">Candidates</span>
            <span className="rq-rec-meta-val">{result.performance_metrics.candidates_evaluated}</span>
          </div>
        </div>

        <div className="rq-rec-actions" style={{ justifyContent: 'flex-start', marginTop: 'var(--space-4)' }}>
          {result.recommended_destination.official_url ? (
            <a className="rq-route-btn" href={result.recommended_destination.official_url} target="_blank" rel="noreferrer noopener">
              <ExternalLink aria-hidden="true" /> Open {result.final_model_name} + optimized prompt
            </a>
          ) : (
            <span className="rq-hint">Official consumer destination is not recorded for this API model.</span>
          )}
          <button type="button" className="rq-clear-btn" onClick={() => onCopy()}>
            <Clipboard aria-hidden="true" /> Copy optimized prompt
          </button>
        </div>
        <p className="rq-hint">Evidence: {result.recommended_destination.data_provenance.replaceAll('_', ' ')}{result.recommended_destination.last_verified_at ? ` · verified ${new Date(result.recommended_destination.last_verified_at).toLocaleDateString()}` : ''}</p>

        {result.generated_response && (
          <div className="rq-rec-response-preview">
            <div className="rq-rec-response-label">
              <Bot aria-hidden="true" />
              Response preview
            </div>
            <p className="rq-rec-response-text">
              {result.generated_response.slice(0, 320)}
              {result.generated_response.length > 320 ? '…' : ''}
            </p>
            <ButtonLink to="/explanation" variant="ghost" size="sm" trailingIcon={<ArrowRight />}>
              View routing explanation
            </ButtonLink>
          </div>
        )}
      </div>
    </div>
  );
}

function OptimizedPromptCard({
  original, prompt, method, stale, busy, error, copied,
  onChange, onOptimize, onReset, onCopy,
}: {
  original: string;
  prompt: string;
  method: string;
  stale: boolean;
  busy: boolean;
  error: string | null;
  copied: boolean;
  onChange: (value: string) => void;
  onOptimize: () => void;
  onReset: () => void;
  onCopy: () => void;
}) {
  const approximateTokens = prompt.trim() ? Math.ceil(prompt.trim().length / 4) : 0;

  return (
    <section className="rq-prompt-card" aria-labelledby="optimized-prompt-title">
      <div className="rq-prompt-header">
        <div>
          <div className="rq-rec-response-label" id="optimized-prompt-title">
            <Wand2 aria-hidden="true" /> Prompt Optimizer
          </div>
          <p className="rq-prompt-subtitle">Transform your query into a clearer, more effective prompt.</p>
        </div>
        <span className="rq-prompt-method">{method || 'Ready to optimize locally'}</span>
      </div>
      {stale && <p className="rq-prompt-stale">The query has changed since this prompt was generated. Re-optimize to sync it.</p>}
      <div className="rq-prompt-columns">
        <div className="rq-prompt-original">
          <span className="rq-prompt-label">Original query</span>
          <p>{original || 'Enter a query above to begin.'}</p>
        </div>
        <div className="rq-prompt-editor">
          <label className="rq-prompt-label" htmlFor="rq-optimized-prompt">Optimized prompt</label>
          <textarea
            id="rq-optimized-prompt"
            className="rq-textarea rq-prompt-textarea"
            value={prompt}
            onChange={event => onChange(event.target.value)}
            placeholder="Your task-aware prompt will appear here."
            rows={9}
            aria-label="Editable optimized prompt"
          />
        </div>
      </div>
      {error && <p className="rq-prompt-error" role="alert">{error}</p>}
      <div className="rq-prompt-footer">
        <span className="rq-prompt-token-count">Approx. tokens: {approximateTokens}</span>
        <div className="rq-prompt-actions">
          <button type="button" className="rq-clear-btn" onClick={onReset} disabled={!original || busy}>
            Reset
          </button>
          <button type="button" className="rq-clear-btn" onClick={onOptimize} disabled={!original || busy}>
            {busy ? <Loader2 className="spin" aria-hidden="true" /> : <Wand2 aria-hidden="true" />}
            {busy ? 'Optimizing…' : 'Re-optimize'}
          </button>
          <button type="button" className="rq-route-btn" onClick={onCopy} disabled={!prompt.trim()}>
            {copied ? <Check aria-hidden="true" /> : <Clipboard aria-hidden="true" />}
            {copied ? 'Copied' : 'Copy optimized prompt'}
          </button>
        </div>
      </div>
    </section>
  );
}

function ScoreBreakdownCard({
  score, compareScore, compareModelName,
}: {
  score: RouteResponse['model_scores'][0];
  compareScore: RouteResponse['model_scores'][0] | null;
  compareModelName?: string;
}) {
  const dims = [
    ...OBJECTIVES.map(o => ({ key: o.key, label: o.label, val: score[o.scoreField] as number })),
    { key: 'preference', label: 'Preference Alignment', val: score.preference_alignment },
  ];

  return (
    <div className="rq-breakdown-card">
      <div className="rq-breakdown-header">
        <BarChart3 aria-hidden="true" />
        <span>Score breakdown</span>
        {compareScore && compareModelName && (
          <span className="rq-breakdown-compare-label">vs {compareModelName}</span>
        )}
      </div>
      <div className="rq-breakdown-list">
        {dims.map(d => {
          const cval = compareScore
            ? (d.key === 'preference' ? compareScore.preference_alignment : compareScore[`${d.key}_score` as keyof typeof compareScore] as number)
            : null;
          return (
            <div key={d.key} className="rq-breakdown-row">
              <span className="rq-breakdown-label">{d.label}</span>
              <div className="rq-breakdown-bars">
                <div className="rq-breakdown-bar-wrap">
                  <div className="rq-breakdown-bar rq-breakdown-bar--primary"
                    style={{ width: `${toPercent(d.val)}%` }} />
                </div>
                {cval !== null && (
                  <div className="rq-breakdown-bar-wrap rq-breakdown-bar-wrap--compare">
                    <div className="rq-breakdown-bar rq-breakdown-bar--compare"
                      style={{ width: `${toPercent(cval)}%` }} />
                  </div>
                )}
              </div>
              <span className="rq-breakdown-val">{formatPercent(d.val, 0)}</span>
              {cval !== null && (
                <span className={`rq-breakdown-diff ${d.val >= cval ? 'pos' : 'neg'}`}>
                  {d.val >= cval ? '+' : ''}{formatPercent(d.val - cval, 0)}
                </span>
              )}
            </div>
          );
        })}
      </div>
      <div className="rq-breakdown-total">
        <span>Overall routing score</span>
        <span className="rq-breakdown-total-val">{formatPercent(score.overall_score)}</span>
      </div>
    </div>
  );
}

function AlternativesCard({
  alternatives, compareWith, onCompare,
}: {
  alternatives: RankedAlternative[];
  compareWith: string | null;
  onCompare: (id: string) => void;
}) {
  return (
    <div className="rq-alts-card">
      <div className="rq-alts-header">
        <Layers aria-hidden="true" />
        <span>Ranked alternatives</span>
        <span className="rq-alts-hint">Click to compare scores</span>
      </div>
      <div className="rq-alts-list">
        {alternatives.map((alt, i) => (
          <button
            key={alt.model_id}
            type="button"
            className={`rq-alt-row${compareWith === alt.model_id ? ' rq-alt-row--active' : ''}`}
            onClick={() => onCompare(alt.model_id)}
          >
            <span className="rq-alt-rank">#{i + 2}</span>
            <div className="rq-alt-avatar" style={{ background: providerColor(alt.provider) }}>
              <Bot aria-hidden="true" />
            </div>
            <div className="rq-alt-info">
              <span className="rq-alt-name">{alt.model_name}</span>
              <span className="rq-alt-provider">{alt.provider}</span>
            </div>
            <div className="rq-alt-scores">
              {OBJECTIVES.slice(0, 3).map(o => (
                <div key={o.key} className="rq-alt-score-mini">
                  <div className="rq-alt-score-bar">
                    <div className="rq-alt-score-fill"
                      style={{ width: `${toPercent(alt[`${o.key}_score` as keyof RankedAlternative] as number)}%` }} />
                  </div>
                </div>
              ))}
            </div>
            <span className="rq-alt-overall">{formatPercent(alt.overall_score, 0)}</span>
            {compareWith === alt.model_id && <Check className="rq-alt-check" aria-hidden="true" />}
          </button>
        ))}
      </div>
    </div>
  );
}

function ToolRecommendationsCard({
  tools, task, loading, error,
}: {
  tools: ModelInfo[];
  task: string | null;
  loading: boolean;
  error: string | null;
}) {
  return (
    <section className="rq-tools-card" aria-labelledby="suggested-tools-title">
      <div className="rq-tools-header">
        <Sparkles aria-hidden="true" />
        <span id="suggested-tools-title">Suggested tools</span>
      </div>
      <p className="rq-tools-intro">
        {task ? `Registry matches for ${task.replaceAll('-', ' ')}.` : 'Select a task or describe your query to see relevant tools.'}
      </p>
      <div className="rq-tools-list">
        {loading && <p className="rq-tools-message">Loading tools from the model registry…</p>}
        {!loading && error && <p className="rq-tools-error">{error}</p>}
        {!loading && !error && !tools.length && (
          <p className="rq-tools-message">
            {task ? 'No matching tools are listed for this task.' : 'Suggestions appear when a task is identified.'}
          </p>
        )}
        {!loading && !error && tools.map(tool => {
          const Icon = tool.modality === 'image' ? Image
            : tool.modality === 'audio' ? Music2
              : tool.modality === 'presentation' ? Presentation
                : tool.modality === 'video' ? Video
                  : task === 'research' ? Search
                    : task === 'education' ? BookOpen
                      : task === 'coding' ? Code2
                        : task === 'summarization' ? FileText
                          : Bot;
          const aliases = TOOL_TASK_ALIASES[task ?? ''] ?? [task ?? ''];
          const relevantCapabilities = [...tool.supported_tasks, ...tool.capabilities]
            .filter((capability, index, list) => list.indexOf(capability) === index)
            .filter(capability => aliases.some(alias => capability.toLowerCase().includes(alias)))
            .slice(0, 2)
            .map(capability => capability.replaceAll('-', ' '))
            .join(' · ');
          return (
            <article key={tool.model_id} className="rq-tool-item">
              <div className="rq-tool-icon"><Icon aria-hidden="true" /></div>
              <div className="rq-tool-info">
                <span className="rq-tool-name">{tool.model_name}</span>
                <span className="rq-tool-provider">{tool.provider}</span>
                <p className="rq-tool-desc">{tool.description || relevantCapabilities}</p>
                <span className="rq-tool-capability">{relevantCapabilities || tool.modality}</span>
                <span className="rq-tool-kind">
                  {tool.entry_type === 'specialized_ai_tool' ? 'Specialized tool' : 'Consumer application'}
                </span>
              </div>
              {tool.external_url && (
                <a href={tool.external_url} target="_blank" rel="noreferrer noopener"
                  className="rq-tool-link" aria-label={`Open ${tool.model_name}`}>
                  Open <ExternalLink aria-hidden="true" />
                </a>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
