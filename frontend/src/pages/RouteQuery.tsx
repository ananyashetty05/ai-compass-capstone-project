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
  Clipboard,
  Code2,
  Compass,
  ExternalLink,
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
import { Radar } from '../components/ui/Radar';
import { RoutingInsights } from '../components/result/RoutingInsights';
import { EngineInsights } from '../components/route/EngineInsights';
import { PromptOptimizerPanel } from '../components/route/PromptOptimizerPanel';
import { ConstraintsPanel } from '../components/route/ConstraintsPanel';
import type { PrivacyLevel } from '../components/route/ConstraintsPanel';
import { useToast } from '../context/toastContext';
import { copyText } from '../utils/clipboard';
import { useAuth } from '../context/authContext';
import { useRouteResult } from '../context/routeResultContext';
import { routeAndGenerate } from '../services/routing.service';
import { listModels } from '../services/models.service';
import { optimizePrompt as requestPromptOptimization } from '../services/promptOptimization.service';
import { describeError } from '../services/http';
import { scrollToElement } from '../utils/scroll';
import { ExampleGallery } from '../components/route/ExampleGallery';
import { TaskTypeGrid } from '../components/route/TaskTypeGrid';
import { RouteProgress } from '../components/route/RouteProgress';
import { OBJECTIVES, groupLabel } from '../utils/domain';
import { formatPercent, formatDuration, formatUsd, toPercent } from '../utils/format';
import type { RouteRequest, EngineRankingRow, RouteResponse, RankedAlternative, ModelInfo, OptimizationMode, OptimizePromptResponse, RouteMode, SubmitPrompt } from '../types';

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
  const [maxCost, setMaxCost] = useState('');
  const [maxLatency, setMaxLatency] = useState('');
  const [capabilities, setCapabilities] = useState<string[]>([]);
  const [privacy, setPrivacy] = useState<PrivacyLevel>('standard');
  const [excludedProviders, setExcludedProviders] = useState<string[]>([]);
  const [selectedModelIds, setSelectedModelIds] = useState<string[]>([]);
  const [compareWith, setCompareWith] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [optimizerBusy, setOptimizerBusy] = useState(false);
  const [optimizerError, setOptimizerError] = useState<string | null>(null);
  const [optMode, setOptMode] = useState<OptimizationMode>('standard');
  const [optResult, setOptResult] = useState<OptimizePromptResponse | null>(result?.engine?.optimization ?? null);
  const [submitChoice, setSubmitChoice] = useState<SubmitPrompt>('optimized');
  const [promptEdited, setPromptEdited] = useState(false);
  const runMode: RouteMode = 'recommend'; // AI Compass recommends; it never runs a model
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
  const resultColRef = useRef<HTMLDivElement>(null);
  /** Set when a route is started from the form; the result scrolls into view once it lands. */
  const revealPendingRef = useRef(false);
  const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);

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

    const payload: RouteRequest = { query: q, mode: runMode, optimization_mode: optMode, submit_prompt: submitChoice };
    const fresh = !!optResult && optimizedFor === q && optResult.mode === optMode;
    if (fresh && optimizedPrompt.trim()) payload.optimized_prompt = optimizedPrompt;
    if (taskTypeHint) payload.task_type_hint = taskTypeHint;
    if (selectedModelIds.length) payload.model_ids = selectedModelIds;
    if (capabilities.length) payload.require_capabilities = capabilities;
    if (privacy === 'strict') payload.privacy_requirement = 'strict';
    if (excludedProviders.length) payload.excluded_providers = excludedProviders;
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

    controllerRef.current?.abort();
    const ctrl = new AbortController();
    controllerRef.current = ctrl;
    setRouting(true);
    setCompareWith(null);
    revealPendingRef.current = true;
    // Glide down to the result area straight away so the progress is visible.
    requestAnimationFrame(() => { if (resultColRef.current) scrollToElement(resultColRef.current); });

    try {
      const res = await routeAndGenerate(payload, ctrl.signal);
      if (res.engine) {
        setOptResult(res.engine.optimization);
        if (!promptEdited) setOptimizedPrompt(res.engine.optimization.optimized_prompt);
      } else {
        setOptimizedPrompt(res.optimized_prompt || res.query);
      }
      setOptimizedFor(res.query);
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
  }, [query, taskTypeHint, isRouting, maxCost, maxLatency, capabilities, privacy, excludedProviders, selectedModelIds, runMode, optMode, submitChoice, optResult, optimizedFor, optimizedPrompt, promptEdited, push, setResult, setRouting]);

  // When the result (or an error) lands, settle onto it and give the Best Match card a brief glow.
  useEffect(() => {
    if (!revealPendingRef.current || isRouting) return;
    if (!result && !error) return;
    revealPendingRef.current = false;
    const raf = requestAnimationFrame(() => {
      const col = resultColRef.current;
      const target = col?.querySelector('.rq-rec-card, .rq-error-card') ?? col;
      if (!target) return;
      scrollToElement(target, {
        onDone: () => {
          if (!target.classList.contains('rq-rec-card')) return;
          target.classList.remove('rq-rec-card--arrive');
          void (target as HTMLElement).offsetWidth;
          target.classList.add('rq-rec-card--arrive');
        },
      });
    });
    return () => cancelAnimationFrame(raf);
  }, [result, error, isRouting]);

  const handleKey = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); void run(); }
  }, [run]);

  const copyTimer = useRef<number | undefined>(undefined);
  const copyResult = useCallback(async (value?: string) => {
    const text = value ?? optimizedPrompt ?? result?.optimized_prompt ?? result?.query ?? '';
    if (!text.trim()) {
      setOptimizerError('There is no prompt to copy yet.');
      return;
    }
    if (await copyText(text)) {
      setOptimizerError(null);
      setCopied(true);
      push({ tone: 'success', title: 'Prompt copied', description: 'The prompt is on your clipboard, ready to paste.', durationMs: 2600 });
      window.clearTimeout(copyTimer.current);
      copyTimer.current = window.setTimeout(() => setCopied(false), 2200);
    } else {
      setOptimizerError('Clipboard access was denied. Select and copy the prompt text manually.');
      push({ tone: 'danger', title: 'Could not copy', description: 'Your browser blocked clipboard access. Select the text and copy it manually.' });
    }
  }, [result, optimizedPrompt, push]);

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
        { query: originalPrompt, mode: optMode, ...(taskTypeHint ? { task_type_hint: taskTypeHint } : {}) },
        controller.signal,
      );
      setOptimizedPrompt(response.optimized_prompt);
      setOptResult(response);
      setPromptEdited(false);
      setOptimizedFor(originalPrompt);
    } catch (cause) {
      if (!controller.signal.aborted) {
        const failure = describeError(cause, 'Prompt optimization failed.');
        setOptimizerError(failure.hint ? `${failure.message} ${failure.hint}` : failure.message);
      }
    } finally {
      if (!controller.signal.aborted) setOptimizerBusy(false);
    }
  }, [originalPrompt, taskTypeHint, optMode]);

  const resetOptimizedPrompt = useCallback(() => {
    setOptimizedPrompt(originalPrompt);
    setPromptEdited(false);
    setSubmitChoice('original');
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

  const optimizerPanel = (
    <PromptOptimizerPanel
      original={originalPrompt}
      mode={optMode}
      onModeChange={setOptMode}
      result={optResult}
      prompt={optimizedPrompt}
      onPromptChange={value => { setOptimizedPrompt(value); setPromptEdited(true); setSubmitChoice('optimized'); setOptimizerError(null); }}
      submit={submitChoice}
      onSubmitChange={setSubmitChoice}
      stale={!!optResult && (optimizedFor !== originalPrompt || optResult.mode !== optMode)}
      busy={optimizerBusy}
      error={optimizerError}
      copied={copied}
      onOptimize={() => void optimizeCurrentPrompt()}
      onRestore={resetOptimizedPrompt}
      onCopy={() => void copyResult(submitChoice === 'original' ? originalPrompt : optimizedPrompt)}
    />
  );

  return (
    <div className="rq-shell">
      <header className="rq-page-intro">
        <div>
          <p className="rq-page-eyebrow">AI Compass · Workspace</p>
          <h1>Route Query</h1>
          <p>Describe the task. AI Compass compares eligible models against your constraints and routing priorities.</p>
        </div>
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
              <RouteProgress hasTask={query.trim().length >= 3} routing={isRouting} hasResult={!!result} failed={!!error && !isRouting} />
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
                <span className="rq-char-count" title="Rough estimate: about 4 characters per token">{query.length.toLocaleString()} / {MAX_QUERY.toLocaleString()} · ≈{Math.ceil(query.length / 4).toLocaleString()} tokens</span>
                <div className="rq-inline-run">
                  <kbd className="rq-kbd" aria-hidden="true">{isMac ? '⌘ ↵' : 'Ctrl ↵'}</kbd>
                  <button
                    type="button"
                    className="rq-inline-run-btn"
                    onClick={() => void run()}
                    disabled={isRouting || !query.trim()}
                    aria-keyshortcuts={isMac ? 'Meta+Enter' : 'Control+Enter'}
                  >
                    {isRouting
                      ? <><Loader2 className="spin" aria-hidden="true" />Routing…</>
                      : <>Find best model<ArrowRight aria-hidden="true" /></>}
                  </button>
                </div>
              </div>
            </div>

            <ExampleGallery onPick={(text) => { setQuery(text); setFieldError(null); }} disabled={isRouting} />

            <TaskTypeGrid categories={TASK_CATEGORIES} value={taskTypeHint} onChange={setTaskTypeHint} disabled={isRouting} />

            <ConstraintsPanel
              models={selectableModels}
              loading={registryLoading}
              error={registryError}
              disabled={isRouting}
              maxCost={maxCost} onMaxCost={setMaxCost}
              maxLatency={maxLatency} onMaxLatency={setMaxLatency}
              capabilities={capabilities} onCapabilities={setCapabilities}
              privacy={privacy} onPrivacy={setPrivacy}
              excludedProviders={excludedProviders} onExcludedProviders={setExcludedProviders}
              selectedModelIds={selectedModelIds} onSelectedModelIds={setSelectedModelIds}
            />

            <p className="rq-reco-only"><Compass aria-hidden="true" />Recommendation only: AI Compass picks the best fit and sends you to it. No model is run and nothing is spent. Provider keys, if you add one, are used only to optimise your prompt.</p>

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

        <div className="rq-result-col" ref={resultColRef}>
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

              {optimizerPanel}

              {result.engine?.ranking?.length ? (
                <EcosystemCandidates ranking={result.engine.ranking} bestId={result.engine.best_match_id ?? result.final_model_id} suggestedIds={result.engine.suggested_ids ?? []} />
              ) : result.ranked_alternatives.length > 0 && (
                <AlternativesCard
                  selectedName={result.final_model_name}
                  selectedScore={selectedScore}
                  alternatives={result.ranked_alternatives}
                  compareWith={compareWith}
                  onCompare={id => setCompareWith(prev => prev === id ? null : id)}
                />
              )}

              {result.engine ? <EngineInsights engine={result.engine} /> : <RoutingInsights result={result} />}

            </>
          )}
        </div>

        {!result || isRouting || error ? optimizerPanel : null}
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

        {result?.engine?.ranking?.length && !isRouting && !error ? (
          <SuggestedFromRanking ranking={result.engine.ranking} suggestedIds={result.engine.suggested_ids ?? []} />
        ) : <ToolRecommendationsCard
          tools={suggestedTools}
          task={selectedTaskForTools}
          loading={registryLoading}
          error={registryError}
        />}

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

const LOADER_STEPS = [
  'Query understanding', 'Intent & task', 'Requirements', 'Preference analysis', 'Candidate filtering',
  'Multi-objective scoring', 'Model selection', 'Model execution', 'Response evaluation', 'Accept or escalate',
] as const;

/**
 * The routing service answers in a single response and does not stream stage events, so this state never
 * marks a stage as done. It shows the stages the router will report, animated only to signal that the
 * request is in flight. Real per-stage status and timings appear in the result.
 */
function RoutingLoader() {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const clock = window.setInterval(() => setElapsed((n) => n + 1), 1000);
    return () => window.clearInterval(clock);
  }, []);
  return (
    <div className="rl-card" role="status" aria-live="polite" aria-busy="true">
      <span className="rl-aurora" aria-hidden="true" />
      <div className="rl-visual" aria-hidden="true">
        <span className="rl-ring rl-ring--1" /><span className="rl-ring rl-ring--2" /><span className="rl-ring rl-ring--3" />
        <span className="rl-sweep" />
        <span className="rl-orbit rl-orbit--a"><i /></span>
        <span className="rl-orbit rl-orbit--b"><i /></span>
        <span className="rl-orbit rl-orbit--c"><i /></span>
        <div className="rl-core"><Compass className="rl-needle" /></div>
      </div>
      <h3 className="rl-title">Routing your request<span className="rl-dots" aria-hidden="true"><i>.</i><i>.</i><i>.</i></span></h3>
      <p className="rl-sub">
        Waiting for the routing service. Stage results and timings appear only when the backend reports them, so nothing below is marked complete yet.
      </p>
      <div className="rl-bar" aria-hidden="true"><i /></div>
      <ol className="rl-wait" aria-label="Stages the router will report">
        {LOADER_STEPS.map((label, i) => (
          <li key={label} style={{ ['--i' as string]: i }}><span className="rl-wait-dot" aria-hidden="true" />{label}</li>
        ))}
      </ol>
      <p className="rl-elapsed">{elapsed}s elapsed</p>
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

        <div className="rq-rec-profile">
          {selectedScore ? (
            <Radar label={`${result.final_model_name} objective scores`} size={250}
              axes={OBJECTIVES.map(obj => { const v = selectedScore[obj.scoreField] as number | null; return { label: obj.shortLabel, value: typeof v === 'number' ? v : null, display: typeof v === 'number' ? formatPercent(v, 0) : 'n/a' }; })} />
          ) : null}
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
          {result.engine?.recommendation_only ? <p className="rq-est-note">Quality, speed, reliability and risk are editorial estimates, relative judgements and not measurements. Cost shows the documented access class when known.</p> : null}
        </div>

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
            <span className="rq-rec-meta-val">{result.performance_metrics.total_estimated_cost == null ? 'Not run' : formatUsd(result.performance_metrics.total_estimated_cost)}</span>
          </div>
          <div className="rq-rec-meta-item">
            <span className="rq-rec-meta-label">Candidates</span>
            <span className="rq-rec-meta-val" title="Candidates with real quality, cost, latency, reliability or risk data. The rest are in the pool but have no metadata, so they cannot be compared.">
              {result.performance_metrics.candidates_scored ?? result.performance_metrics.candidates_evaluated}
              {result.performance_metrics.candidates_scored != null && result.performance_metrics.candidates_evaluated != null && result.performance_metrics.candidates_evaluated > result.performance_metrics.candidates_scored
                ? <small> scored · {result.performance_metrics.candidates_evaluated} in pool</small> : null}
            </span>
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
  alternatives, compareWith, onCompare, selectedName, selectedScore,
}: {
  selectedName: string;
  selectedScore: RouteResponse['model_scores'][0] | null | undefined;
  alternatives: RankedAlternative[];
  compareWith: string | null;
  onCompare: (id: string) => void;
}) {
  return (
    <div className="rq-alts-card">
      <div className="rq-alts-header">
        <Layers aria-hidden="true" />
        <span>Ranked alternatives</span>
        <span className="rq-alts-hint">Bars: {OBJECTIVES.slice(0, 3).map(o => o.shortLabel).join(' · ')}. Click a row for the full comparison.</span>
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
                <div key={o.key} className="rq-alt-score-mini" title={`${o.shortLabel}: ${formatPercent(alt[`${o.key}_score` as keyof RankedAlternative] as number, 0)}`}>
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
      {(() => {
        const alt = alternatives.find(a => a.model_id === compareWith);
        if (!alt || !selectedScore) return null;
        const altVal = (k: string) => { const v = alt[`${k}_score` as keyof RankedAlternative]; return typeof v === 'number' ? v : null; };
        const selVal = (f: (typeof OBJECTIVES)[number]['scoreField']) => { const v = selectedScore[f] as number | null; return typeof v === 'number' ? v : null; };
        return (
          <div className="rq-alt-compare" aria-live="polite">
            <Radar label={`${selectedName} compared with ${alt.model_name}`} size={250} name={selectedName}
              compare={{ name: alt.model_name, values: OBJECTIVES.map(o => altVal(o.key)) }}
              axes={OBJECTIVES.map(o => { const v = selVal(o.scoreField); return { label: o.shortLabel, value: v, display: v === null ? 'n/a' : formatPercent(v, 0) }; })} />
            <table className="rq-alt-delta">
              <caption>{alt.model_name} vs {selectedName} (percentage points)</caption>
              <thead><tr><th scope="col">Objective</th><th scope="col">Selected</th><th scope="col">Alternative</th><th scope="col">Δ</th></tr></thead>
              <tbody>
                {OBJECTIVES.map(o => {
                  const a = selVal(o.scoreField); const b = altVal(o.key);
                  const d = a !== null && b !== null ? Math.round((b - a) * 100) : null;
                  return (
                    <tr key={o.key}><th scope="row">{o.shortLabel}</th><td>{a === null ? 'n/a' : formatPercent(a, 0)}</td><td>{b === null ? 'n/a' : formatPercent(b, 0)}</td>
                      <td data-sign={d === null ? undefined : d > 0 ? 'up' : d < 0 ? 'down' : 'flat'}>{d === null ? 'n/a' : d > 0 ? `+${d}` : d}</td></tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        );
      })()}
    </div>
  );
}

/** Candidates: the single ranking that also decides Best Match and Suggested. Nothing here is recomputed. */
function EcosystemCandidates({ ranking, bestId, suggestedIds }: { ranking: EngineRankingRow[]; bestId: string; suggestedIds: string[] }) {
  const top = ranking[0]?.score ?? 0;
  return (
    <section className="rq-cand-card" aria-labelledby="rq-cand-title">
      <div className="rq-alts-header">
        <Layers aria-hidden="true" />
        <span id="rq-cand-title">Candidates in this category</span>
        <span className="rq-alts-hint">One ranking drives Best Match, Suggested and this list.</span>
      </div>
      <ol className="rq-cand-list">
        {ranking.map((r) => {
          const tag = r.model_id === bestId ? 'Best match' : suggestedIds.includes(r.model_id) ? 'Suggested' : null;
          const width = top > 0 ? Math.max(4, Math.round((r.score / top) * 100)) : 0;
          return (
            <li key={r.model_id} className="rq-cand-row" data-tag={tag ? tag.toLowerCase().replace(' ', '-') : undefined}>
              <span className="rq-cand-rank">#{r.rank}</span>
              <div className="rq-cand-main">
                <span className="rq-cand-name">{r.model_name}{tag ? <em>{tag}</em> : null}</span>
                <span className="rq-cand-sub">{r.provider}{r.role === 'secondary' ? ' · also serves this category' : ''}{r.matched_features.length ? ` · ${r.matched_features.slice(0, 3).join(', ').replaceAll('_', ' ')}` : ''}</span>
                <span className="rq-cand-bar" aria-hidden="true"><i style={{ width: `${width}%` }} /></span>
              </div>
              <span className="rq-cand-score" title="Fit score from the routing algorithm">{Math.round(r.score * 100)}%</span>
              {r.external_url ? <a className="rq-tool-link" href={r.external_url} target="_blank" rel="noreferrer noopener" aria-label={`Open ${r.model_name}`}>Open <ExternalLink aria-hidden="true" /></a> : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function SuggestedFromRanking({ ranking, suggestedIds }: { ranking: EngineRankingRow[]; suggestedIds: string[] }) {
  const rows = suggestedIds.map((id) => ranking.find((r) => r.model_id === id)).filter((r): r is EngineRankingRow => !!r);
  return (
    <section className="rq-tools-card" aria-labelledby="suggested-tools-title">
      <div className="rq-tools-header"><Sparkles aria-hidden="true" /><span id="suggested-tools-title">Suggested alongside</span></div>
      <p className="rq-tools-intro">The next best fits from the same ranking as Best Match.</p>
      <div className="rq-tools-list">
        {rows.length === 0 ? <p className="rq-tools-message">No other tool serves this category for your request.</p> : rows.map((r) => (
          <article key={r.model_id} className="rq-tool-item">
            <div className="rq-tool-icon"><Bot aria-hidden="true" /></div>
            <div className="rq-tool-info">
              <span className="rq-tool-name">#{r.rank} {r.model_name}</span>
              <span className="rq-tool-provider">{r.provider}</span>
              {r.description ? <p className="rq-tool-desc">{r.description}</p> : null}
            </div>
            {r.external_url ? <a href={r.external_url} target="_blank" rel="noreferrer noopener" className="rq-tool-link" aria-label={`Open ${r.model_name}`}>Open <ExternalLink aria-hidden="true" /></a> : null}
          </article>
        ))}
      </div>
    </section>
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
