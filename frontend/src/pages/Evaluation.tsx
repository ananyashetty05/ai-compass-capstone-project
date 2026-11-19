import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowRight,
  ChevronDown,
  CornerDownLeft,
  FlaskConical,
  Info,
  Loader2,
  ShieldCheck,
  SlidersHorizontal,
  Tag,
  X,
} from 'lucide-react';
import { PageHeader } from '../components/layout/PageHeader';
import { EvaluationPipeline } from '../components/evaluation/EvaluationPipeline';
import { MetricGuide } from '../components/evaluation/EvaluationInsights';
import { BenchmarkResults } from '../components/evaluation/BenchmarkResults';
import { DecisionTrace } from '../components/evaluation/DecisionTrace';
import { STRATEGIES } from '../components/evaluation/strategies';
import { SegmentedControl } from '../components/ui/ds';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { useRouteResult } from '../context/routeResultContext';
import { evaluateOffline } from '../services/evaluation.service';
import { describeError } from '../services/http';
import { scrollToElement } from '../utils/scroll';
import type { OfflineEvaluationResponse } from '../types';

const MAX_QUERY = 8000;

const TASK_CATEGORIES = [
  ['coding', 'Coding'], ['research', 'Research'], ['creative', 'Writing'], ['analysis', 'Analysis'],
  ['math', 'Mathematics'], ['image-generation', 'Image generation'], ['video-generation', 'Video generation'],
  ['presentation', 'Presentations'], ['audio-generation', 'Audio / music'], ['reasoning', 'General reasoning'],
  ['education', 'Learning'], ['summarization', 'Summarization'], ['design', 'Design'],
] as const;

const CAPABILITIES = ['coding', 'reasoning', 'math', 'research', 'image-generation'];

export function Evaluation() {
  useDocumentTitle('Evaluation · AI Compass');
  const { result: lastRoute } = useRouteResult();
  const [query, setQuery] = useState(lastRoute?.query ?? '');
  const [taskTypeHint, setTaskTypeHint] = useState('');
  const [maxInputPrice, setMaxInputPrice] = useState('');
  const [maxLatency, setMaxLatency] = useState('');
  const [requiredCapabilities, setRequiredCapabilities] = useState<string[]>([]);
  const [constraintsOpen, setConstraintsOpen] = useState(false);
  const [evaluation, setEvaluation] = useState<OfflineEvaluationResponse | null>(null);
  const [tab, setTab] = useState<'trace' | 'benchmark'>('trace');
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<{ message: string; hint?: string } | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  const revealRef = useRef(false);
  const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const constraintCount = (maxInputPrice ? 1 : 0) + (maxLatency ? 1 : 0) + requiredCapabilities.length;

  const run = useCallback(async () => {
    const text = query.trim();
    if (text.length < 3 || running) return;
    if (maxInputPrice && (!Number.isFinite(Number(maxInputPrice)) || Number(maxInputPrice) <= 0)) {
      setError({ message: 'Maximum input price must be greater than zero.' });
      setConstraintsOpen(true);
      return;
    }
    if (maxLatency && (!Number.isFinite(Number(maxLatency)) || Number(maxLatency) <= 0)) {
      setError({ message: 'Maximum latency must be greater than zero.' });
      setConstraintsOpen(true);
      return;
    }
    const controller = new AbortController();
    controllerRef.current?.abort();
    controllerRef.current = controller;
    setRunning(true);
    setEvaluation(null);
    setError(null);
    revealRef.current = true;
    requestAnimationFrame(() => { if (resultsRef.current) scrollToElement(resultsRef.current); });
    try {
      const response = await evaluateOffline({
        query: text,
        ...(taskTypeHint ? { task_type_hint: taskTypeHint } : {}),
        ...(maxInputPrice ? { max_cost: Number(maxInputPrice) } : {}),
        ...(maxLatency ? { max_latency: Number(maxLatency) } : {}),
        ...(requiredCapabilities.length ? { require_capabilities: requiredCapabilities } : {}),
      }, controller.signal);
      setEvaluation(response);
    } catch (cause) {
      if (!controller.signal.aborted) setError(describeError(cause, 'Offline evaluation could not be completed.'));
    } finally {
      if (!controller.signal.aborted) setRunning(false);
    }
  }, [query, running, taskTypeHint, maxInputPrice, maxLatency, requiredCapabilities]);

  // Settle onto the results once they land.
  useEffect(() => {
    if (!revealRef.current || running || !evaluation) return;
    revealRef.current = false;
    const raf = requestAnimationFrame(() => { if (resultsRef.current) scrollToElement(resultsRef.current); });
    return () => cancelAnimationFrame(raf);
  }, [evaluation, running]);


  const toggleCapability = (c: string) =>
    setRequiredCapabilities((cur) => (cur.includes(c) ? cur.filter((v) => v !== c) : [...cur, c]));
  const clearConstraints = () => { setMaxInputPrice(''); setMaxLatency(''); setRequiredCapabilities([]); };
  const canUseLast = !!lastRoute?.query && lastRoute.query !== query;

  return (
    <>
      <PageHeader
        eyebrow="Research · routing policies"
        title="Evaluation Lab"
        description="Why a model was chosen, and how AI Compass compares with baseline strategies. Uses published metadata only."
      />

      <div className="page-body ev">
        <SegmentedControl<'trace' | 'benchmark'>
          label="Evaluation view"
          value={tab}
          onChange={setTab}
          options={[
            { value: 'trace', label: 'Decision explanation', hint: 'Explainable AI: why one model was chosen over the others' },
            { value: 'benchmark', label: 'Strategy benchmark', hint: 'Compare AI Compass with baseline strategies on a query' },
          ]}
        />
        {tab === 'trace' ? <DecisionTrace /> : null}
        {tab === 'benchmark' ? (<>
        {/* ── Test bench ─────────────────────────────────────────── */}
        <section className="ev-bench" aria-labelledby="ev-bench-title">
          <header className="ev-bench-head">
            <span className="ev-bench-icon" aria-hidden="true"><FlaskConical /></span>
            <div>
              <h2 id="ev-bench-title">Test a query</h2>
              <p>Describe a task. All four strategies pick a model for it from the same filtered pool.</p>
            </div>
            <span className="ev-offline-pill"><ShieldCheck aria-hidden="true" />Offline · no cost</span>
          </header>

          <div className="ev-input">
            <textarea
              id="offline-query"
              value={query}
              onChange={(e) => setQuery(e.target.value.slice(0, MAX_QUERY))}
              onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); void run(); } }}
              placeholder="e.g. Write a Python function that merges overlapping intervals and explain its complexity…"
              rows={3}
              aria-label="Test query"
              disabled={running}
            />
            <div className="ev-input-foot">
              <span className="ev-count">{query.length.toLocaleString()} / {MAX_QUERY.toLocaleString()}</span>
              {canUseLast ? (
                <button type="button" className="ev-link-btn" onClick={() => setQuery(lastRoute!.query)}>
                  <CornerDownLeft aria-hidden="true" />Use last routed query
                </button>
              ) : null}
              <span className="ev-input-actions">
                <kbd className="rq-kbd" aria-hidden="true">{isMac ? '⌘ ↵' : 'Ctrl ↵'}</kbd>
                <button type="button" className="ev-run" onClick={() => void run()} disabled={running || query.trim().length < 3} aria-keyshortcuts={isMac ? 'Meta+Enter' : 'Control+Enter'}>
                  {running ? <><Loader2 className="spin" aria-hidden="true" />Evaluating…</> : <>{evaluation ? 'Evaluate again' : 'Evaluate'}<ArrowRight aria-hidden="true" /></>}
                </button>
              </span>
            </div>
          </div>

          <div className="ev-options">
            <label className="ev-select">
              <Tag aria-hidden="true" />
              <span className="sr-only">Task category</span>
              <select value={taskTypeHint} onChange={(e) => setTaskTypeHint(e.target.value)} disabled={running}>
                <option value="">Category: detect from query</option>
                {TASK_CATEGORIES.map(([value, label]) => <option key={value} value={value}>Category: {label}</option>)}
              </select>
              <ChevronDown aria-hidden="true" className="ev-select-chev" />
            </label>
            <button type="button" className="ev-toggle" aria-expanded={constraintsOpen} aria-controls="ev-constraints" onClick={() => setConstraintsOpen((o) => !o)}>
              <SlidersHorizontal aria-hidden="true" />Hard constraints
              {constraintCount > 0 ? <span className="ev-badge">{constraintCount}</span> : null}
              <ChevronDown aria-hidden="true" className="ev-toggle-chev" />
            </button>
            {constraintCount > 0 ? (
              <button type="button" className="ev-link-btn" onClick={clearConstraints}><X aria-hidden="true" />Clear</button>
            ) : null}
          </div>

          <div id="ev-constraints" className="ev-constraints" data-open={constraintsOpen || undefined} inert={!constraintsOpen || undefined}>
            <div className="ev-constraints-inner">
              <label className="ev-field">
                <span>Max input price / 1K tokens</span>
                <span className="ev-field-input"><em>$</em><input type="number" min="0.0001" step="0.0001" value={maxInputPrice} onChange={(e) => setMaxInputPrice(e.target.value)} placeholder="No limit" /></span>
              </label>
              <label className="ev-field">
                <span>Max estimated latency</span>
                <span className="ev-field-input"><input type="number" min="0.1" step="0.5" value={maxLatency} onChange={(e) => setMaxLatency(e.target.value)} placeholder="No limit" /><em>sec</em></span>
              </label>
              <fieldset className="ev-caps">
                <legend>Required capabilities</legend>
                <div>
                  {CAPABILITIES.map((c) => (
                    <button key={c} type="button" className="ev-cap" aria-pressed={requiredCapabilities.includes(c)} onClick={() => toggleCapability(c)}>
                      {c.replaceAll('-', ' ')}
                    </button>
                  ))}
                </div>
              </fieldset>
            </div>
          </div>

          {error ? (
            <div className="ev-error" role="alert"><Info aria-hidden="true" /><span>{error.message}{error.hint ? ` ${error.hint}` : ''}</span></div>
          ) : null}
        </section>

        {/* ── Results ────────────────────────────────────────────── */}
        <div ref={resultsRef} className="ev-results-anchor">
          {running ? (
            <section className="ev-section" aria-busy="true" aria-label="Evaluating">
              <div className="ev-running" role="status"><Loader2 className="spin" aria-hidden="true" />Analysing the query and scoring registry candidates…</div>
              <div className="ev-grid">
                {STRATEGIES.map((s, i) => <div key={s.key} className="ev-card ev-card--skeleton" style={{ ['--i' as string]: i }} aria-hidden="true"><i /><i /><i /><i /></div>)}
              </div>
            </section>
          ) : null}

          {evaluation && !running ? (
            <BenchmarkResults evaluation={evaluation} />
          ) : null}
        </div>

        {/* ── Method ─────────────────────────────────────────────── */}
        <EvaluationPipeline evaluation={running ? null : evaluation} />
        <MetricGuide />
        </>) : null}
      </div>
    </>
  );
}
