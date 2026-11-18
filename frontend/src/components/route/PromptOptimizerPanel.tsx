/**
 * Prompt Optimizer — preview, edit, restore and choose which prompt is submitted.
 * The original is read-only and always one click away; quality figures are heuristic indicators and say so.
 */
import { AlertTriangle, Check, Clipboard, Loader2, RotateCcw, ShieldCheck, Wand2 } from 'lucide-react';
import { humanizeToken, formatPercent } from '../../utils/format';
import type { OptimizationMode, OptimizePromptResponse, SubmitPrompt } from '../../types';

export const OPTIMIZATION_MODES: { value: OptimizationMode; label: string; hint: string }[] = [
  { value: 'disabled', label: 'Off', hint: 'Use your prompt exactly as written.' },
  { value: 'conservative', label: 'Light', hint: 'Whitespace, capitalisation and punctuation only.' },
  { value: 'standard', label: 'Standard', hint: 'Adds your stated constraints and short task guidance.' },
  { value: 'advanced', label: 'Advanced', hint: 'Also isolates pasted code/quotes as data and suggests a structure.' },
];

interface Props {
  original: string;
  mode: OptimizationMode;
  onModeChange: (m: OptimizationMode) => void;
  result: OptimizePromptResponse | null;
  prompt: string;
  onPromptChange: (v: string) => void;
  submit: SubmitPrompt;
  onSubmitChange: (v: SubmitPrompt) => void;
  stale: boolean;
  busy: boolean;
  error: string | null;
  copied: boolean;
  onOptimize: () => void;
  onRestore: () => void;
  onCopy: () => void;
}

export function PromptOptimizerPanel(p: Props) {
  const r = p.result;
  const edited = !!r && p.prompt !== r.optimized_prompt;
  const tokens = p.prompt.trim() ? Math.ceil(p.prompt.trim().length / 4) : 0;
  return (
    <section className="rq-prompt-card" aria-labelledby="optimized-prompt-title">
      <div className="rq-prompt-header">
        <div>
          <div className="rq-rec-response-label" id="optimized-prompt-title"><Wand2 aria-hidden="true" /> Prompt Optimizer</div>
          <p className="rq-prompt-subtitle">Preview, edit or restore the prompt before it is used. Your original is never overwritten.</p>
        </div>
        <span className="rq-prompt-method">{r ? humanizeToken(r.method ?? 'optimizer') : 'Not run yet'}</span>
      </div>

      <div className="eng-seg" role="radiogroup" aria-label="Optimization mode">
        {OPTIMIZATION_MODES.map((m) => (
          <button key={m.value} type="button" role="radio" aria-checked={p.mode === m.value} className={p.mode === m.value ? 'is-on' : ''}
            title={m.hint} onClick={() => p.onModeChange(m.value)} disabled={p.busy}>{m.label}</button>
        ))}
      </div>
      <p className="cx-note">{OPTIMIZATION_MODES.find((m) => m.value === p.mode)?.hint}</p>

      {p.stale && <p className="rq-prompt-stale">The query or mode changed since this prompt was generated. Re-optimize to sync it.</p>}

      <div className="rq-prompt-columns">
        <div className="rq-prompt-original">
          <span className="rq-prompt-label">Original (read-only)</span>
          <p>{p.original || 'Enter a query above to begin.'}</p>
        </div>
        <div className="rq-prompt-editor">
          <label className="rq-prompt-label" htmlFor="rq-optimized-prompt">Optimized prompt {edited ? '(edited by you)' : ''}</label>
          <textarea id="rq-optimized-prompt" className="rq-textarea rq-prompt-textarea" value={p.prompt} rows={9}
            onChange={(e) => p.onPromptChange(e.target.value)} placeholder="Click Optimize to generate a task-aware prompt." aria-label="Editable optimized prompt" />
        </div>
      </div>

      {r && (
        <div className="eng-opt-meta">
          <p className="cx-chips">
            <span title="Checks that your numbers, quoted text and code blocks survived the rewrite"><ShieldCheck aria-hidden="true" /> Intent {r.intent_preserved ? 'preserved' : 'NOT verified'}</span>
            {r.applied === false && <span>No changes applied</span>}
            {!!r.isolated_untrusted_blocks && <span>{r.isolated_untrusted_blocks} block(s) isolated as data</span>}
            {(r.preserved_constraints ?? []).map((c) => <span key={c}>Kept · {c}</span>)}
          </p>
          {r.preservation_checks && (
            <ul className="eng-checks">
              {Object.entries(r.preservation_checks).map(([k, v]) => <li key={k} className={v ? 'eng-ok' : 'eng-bad'}>{v ? '✓' : '✗'} {humanizeToken(k)}</li>)}
            </ul>
          )}
          {(r.changes ?? []).length > 0 && <ul className="cx-notes">{(r.changes ?? []).map((c, i) => <li key={i}><strong>{humanizeToken(c.kind)}:</strong> {c.description}</li>)}</ul>}
          {(r.model_adaptation ?? []).length > 0 && <ul className="cx-notes">{(r.model_adaptation ?? []).map((c, i) => <li key={i}>{c}</li>)}</ul>}
          {(r.ambiguities ?? []).length > 0 && (
            <ul className="cx-notes">{(r.ambiguities ?? []).map((a, i) => <li key={i}><AlertTriangle aria-hidden="true" className="eng-warn" /> {a.message}{a.clarifying_question ? ` ${a.clarifying_question}` : ''}</li>)}</ul>
          )}
          {(r.warnings ?? []).length > 0 && <ul className="cx-notes">{(r.warnings ?? []).map((a, i) => <li key={i}>{a}</li>)}</ul>}
          {r.quality_before && r.quality_after && (
            <p className="cx-note">
              Prompt indicators (heuristic, not validated against answer quality): clarity {formatPercent(r.quality_before.clarity, 0)} → {formatPercent(r.quality_after.clarity, 0)},
              specificity {formatPercent(r.quality_before.specificity, 0)} → {formatPercent(r.quality_after.specificity, 0)},
              structure {formatPercent(r.quality_before.structure, 0)} → {formatPercent(r.quality_after.structure, 0)}.
            </p>
          )}
        </div>
      )}
      {p.error && <p className="rq-prompt-error" role="alert">{p.error}</p>}

      <fieldset className="eng-submit">
        <legend>Prompt to submit</legend>
        <label><input type="radio" name="submit-prompt" checked={p.submit === 'optimized'} onChange={() => p.onSubmitChange('optimized')} /> Optimized{edited ? ' (with my edits)' : ''}</label>
        <label><input type="radio" name="submit-prompt" checked={p.submit === 'original'} onChange={() => p.onSubmitChange('original')} /> Original</label>
      </fieldset>

      <div className="rq-prompt-footer">
        <span className="rq-prompt-token-count">≈ {tokens} tokens (estimate)</span>
        <div className="rq-prompt-actions">
          <button type="button" className="rq-clear-btn" onClick={p.onRestore} disabled={!p.original || p.busy}><RotateCcw aria-hidden="true" /> Restore original</button>
          <button type="button" className="rq-clear-btn" onClick={p.onOptimize} disabled={!p.original || p.busy || p.mode === 'disabled'}>
            {p.busy ? <Loader2 className="spin" aria-hidden="true" /> : <Wand2 aria-hidden="true" />}{p.busy ? 'Optimizing…' : r ? 'Re-optimize' : 'Optimize'}
          </button>
          <button type="button" className="rq-route-btn" onClick={p.onCopy} disabled={!p.prompt.trim()}>
            {p.copied ? <Check aria-hidden="true" /> : <Clipboard aria-hidden="true" />}{p.copied ? 'Copied' : 'Copy prompt'}
          </button>
        </div>
      </div>
    </section>
  );
}
