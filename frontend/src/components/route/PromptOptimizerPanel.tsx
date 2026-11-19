/**
 * Prompt Optimizer — preview, edit, restore and choose which prompt is submitted.
 * The original is read-only and always one click away; quality figures are heuristic indicators and say so.
 */
import { AlertTriangle, Check, CheckCircle2, Clipboard, FileText, Lightbulb, ListChecks, Loader2, RotateCcw, ShieldCheck, Sparkles, Type, Wand2, XCircle } from 'lucide-react';
import type { ReactNode } from 'react';
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

const CHANGE_ICON: Record<string, ReactNode> = {
  punctuation: <Type />,
  requirements: <ListChecks />,
  guidance: <Lightbulb />,
};

function Indicator({ label, before, after }: { label: string; before: number; after: number }) {
  const up = after > before;
  return (
    <div className="po-indicator" data-trend={up ? 'up' : after < before ? 'down' : 'flat'}>
      <span className="po-indicator-label">{label}</span>
      <span className="po-indicator-values"><span>{formatPercent(before, 0)}</span><span aria-hidden="true">→</span><strong>{formatPercent(after, 0)}</strong></span>
      <span className="po-indicator-bar" aria-hidden="true"><i style={{ width: `${Math.max(0, Math.min(1, after)) * 100}%` }} /></span>
    </div>
  );
}

export function PromptOptimizerPanel(p: Props) {
  const r = p.result;
  const edited = !!r && p.prompt !== r.optimized_prompt;
  const tokens = p.prompt.trim() ? Math.ceil(p.prompt.trim().length / 4) : 0;
  const modeHint = OPTIMIZATION_MODES.find((m) => m.value === p.mode)?.hint;
  const changes = r?.changes ?? [];
  const adaptation = r?.model_adaptation ?? [];
  const ambiguities = r?.ambiguities ?? [];
  const warnings = r?.warnings ?? [];
  const hasReport = !!r && (changes.length > 0 || adaptation.length > 0 || ambiguities.length > 0 || warnings.length > 0);

  return (
    <section className="po-card" aria-labelledby="optimized-prompt-title">
      <header className="po-head">
        <span className="po-head-icon" aria-hidden="true"><Wand2 /></span>
        <div className="po-head-text">
          <h3 id="optimized-prompt-title">Prompt Optimizer</h3>
          <p>Preview, edit or restore the prompt before it is used. Your original is never overwritten.</p>
        </div>
        <span className="po-badge" data-ready={!!r}>{r ? humanizeToken(r.method ?? 'optimizer') : 'Not run yet'}</span>
      </header>

      <div className="po-section">
        <div className="po-modes" role="radiogroup" aria-label="Optimization mode">
          {OPTIMIZATION_MODES.map((m) => (
            <button key={m.value} type="button" role="radio" aria-checked={p.mode === m.value} data-on={p.mode === m.value}
              title={m.hint} onClick={() => p.onModeChange(m.value)} disabled={p.busy}>{m.label}</button>
          ))}
        </div>
        <p className="po-mode-hint" key={p.mode}>{modeHint}</p>
      </div>

      {p.stale && <p className="po-alert" data-tone="warn" role="status"><AlertTriangle aria-hidden="true" /> The query or mode changed since this prompt was generated. Re-optimize to sync it.</p>}

      <div className="po-panes">
        <div className="po-pane">
          <div className="po-pane-head"><span className="po-label">Original</span><span className="po-tag">Read-only</span></div>
          <div className="po-pane-body po-original">{p.original || <span className="po-placeholder">Enter a query above to begin.</span>}</div>
        </div>
        <div className="po-pane" data-edited={edited}>
          <div className="po-pane-head">
            <label className="po-label" htmlFor="rq-optimized-prompt">Optimized</label>
            {edited ? <span className="po-tag" data-tone="accent">Edited by you</span> : <span className="po-tag">Editable</span>}
          </div>
          <textarea id="rq-optimized-prompt" className="po-pane-body po-textarea" value={p.prompt} rows={9}
            onChange={(e) => p.onPromptChange(e.target.value)} placeholder="Click Optimize to generate a task-aware prompt." aria-label="Editable optimized prompt" />
        </div>
      </div>

      {r && (
        <div className="po-section po-report">
          <div className="po-section-head">
            <h4>Optimization report</h4>
            <div className="po-chips">
              <span data-tone={r.intent_preserved ? 'ok' : 'bad'} title="Checks that your numbers, quoted text and code blocks survived the rewrite"><ShieldCheck aria-hidden="true" /> Intent {r.intent_preserved ? 'preserved' : 'NOT verified'}</span>
              {r.applied === false && <span>No changes applied</span>}
              {!!r.isolated_untrusted_blocks && <span>{r.isolated_untrusted_blocks} block(s) isolated as data</span>}
              {(r.preserved_constraints ?? []).map((c) => <span key={c}>Kept · {c}</span>)}
            </div>
          </div>

          {r.preservation_checks && (
            <ul className="po-checks">
              {Object.entries(r.preservation_checks).map(([k, v]) => (
                <li key={k} data-ok={!!v}>{v ? <CheckCircle2 aria-hidden="true" /> : <XCircle aria-hidden="true" />}{humanizeToken(k)}</li>
              ))}
            </ul>
          )}

          {hasReport && (
            <div className="po-boxes">
              {changes.map((c, i) => (
                <article key={`c${i}`} className="po-box">
                  <h5><span className="po-box-icon" aria-hidden="true">{CHANGE_ICON[c.kind] ?? <Sparkles />}</span>{humanizeToken(c.kind)}</h5>
                  <p>{c.description}</p>
                </article>
              ))}
              {adaptation.map((a, i) => (
                <article key={`a${i}`} className="po-box">
                  <h5><span className="po-box-icon" aria-hidden="true"><Sparkles /></span>Model adaptation</h5>
                  <p>{a}</p>
                </article>
              ))}
              {ambiguities.map((a, i) => (
                <article key={`m${i}`} className="po-box" data-tone="warn">
                  <h5><span className="po-box-icon" aria-hidden="true"><AlertTriangle /></span>Needs clarity</h5>
                  <p>{a.message}{a.clarifying_question ? ` ${a.clarifying_question}` : ''}</p>
                </article>
              ))}
              {warnings.map((a, i) => (
                <article key={`w${i}`} className="po-box" data-tone="warn">
                  <h5><span className="po-box-icon" aria-hidden="true"><AlertTriangle /></span>Warning</h5>
                  <p>{a}</p>
                </article>
              ))}
            </div>
          )}

          {r.quality_before && r.quality_after && (
            <div className="po-indicators">
              <Indicator label="Clarity" before={r.quality_before.clarity} after={r.quality_after.clarity} />
              <Indicator label="Specificity" before={r.quality_before.specificity} after={r.quality_after.specificity} />
              <Indicator label="Structure" before={r.quality_before.structure} after={r.quality_after.structure} />
              <p className="po-footnote">Heuristic prompt indicators, not validated against answer quality.</p>
            </div>
          )}
        </div>
      )}
      {p.error && <p className="po-alert" data-tone="bad" role="alert"><XCircle aria-hidden="true" /> {p.error}</p>}

      <fieldset className="ps-choice">
        <legend>Prompt to submit</legend>
        <div className="ps-options">
          <label className="ps-option" data-on={p.submit === 'optimized'}>
            <input type="radio" name="submit-prompt" checked={p.submit === 'optimized'} onChange={() => p.onSubmitChange('optimized')} />
            <span className="ps-icon" aria-hidden="true"><Sparkles /></span>
            <span className="ps-text">
              <span className="ps-title">Optimized{edited ? ' · your edits' : ''}</span>
              <span className="ps-hint">{r ? 'Sends the improved prompt shown above' : 'Sends the optimized version once it is ready'}</span>
            </span>
            <span className="ps-check" aria-hidden="true"><Check /></span>
          </label>
          <label className="ps-option" data-on={p.submit === 'original'}>
            <input type="radio" name="submit-prompt" checked={p.submit === 'original'} onChange={() => p.onSubmitChange('original')} />
            <span className="ps-icon" aria-hidden="true"><FileText /></span>
            <span className="ps-text">
              <span className="ps-title">Original</span>
              <span className="ps-hint">Sends exactly what you wrote</span>
            </span>
            <span className="ps-check" aria-hidden="true"><Check /></span>
          </label>
        </div>
      </fieldset>

      <footer className="po-footer">
        <span className="po-tokens">≈ {tokens} tokens (estimate)</span>
        <div className="po-actions">
          <button type="button" className="po-btn" onClick={p.onRestore} disabled={!p.original || p.busy}><RotateCcw aria-hidden="true" /> Restore original</button>
          <button type="button" className="po-btn" onClick={p.onOptimize} disabled={!p.original || p.busy || p.mode === 'disabled'}>
            {p.busy ? <Loader2 className="spin" aria-hidden="true" /> : <Wand2 aria-hidden="true" />}{p.busy ? 'Optimizing…' : r ? 'Re-optimize' : 'Optimize'}
          </button>
          <button type="button" className="po-btn po-btn--primary" data-copied={p.copied} onClick={p.onCopy} disabled={!p.prompt.trim()} aria-live="polite">
            <span className="po-btn-swap" aria-hidden="true"><Clipboard /><Check /></span>{p.copied ? 'Copied!' : 'Copy prompt'}
          </button>
        </div>
      </footer>
    </section>
  );
}
