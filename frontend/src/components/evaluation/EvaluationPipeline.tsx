import { Check, Filter, Search, Table2, Trophy } from 'lucide-react';
import type { ReactNode } from 'react';
import { Reveal } from '../ui/Reveal';
import type { OfflineEvaluationResponse } from '../../types';
import { humanizeToken } from '../../utils/format';
import { STRATEGIES } from './strategies';

interface Step { id: string; icon: ReactNode; title: string; text: string; live?: string }

/**
 * "How evaluation works", mirroring the real offline evaluation endpoint:
 * analyse -> candidate catalog -> hard-constraint filter -> four strategies
 * on the same pool -> comparison. Drawn as a connected flow; after a run each
 * step lights up and shows the actual figures from that run.
 */
export function EvaluationPipeline({ evaluation }: { evaluation: OfflineEvaluationResponse | null }) {
  const filtered = evaluation?.filtered_models.length ?? 0;
  const picks = evaluation?.strategy_results.filter((r) => r.status === 'selected').length ?? 0;
  const steps: Step[] = [
    { id: 'analyse', icon: <Search />, title: 'Analyse the query', text: 'Detects task, domain and complexity. A chosen category overrides the guess.',
      live: evaluation ? `${humanizeToken(evaluation.query_analysis.task_type)} · ${humanizeToken(evaluation.query_analysis.domain)}` : undefined },
    { id: 'catalog', icon: <Table2 />, title: 'Load the catalog', text: 'Takes registry models that fit the task and the required modality.',
      live: evaluation ? `${evaluation.candidate_count + filtered} considered` : undefined },
    { id: 'filter', icon: <Filter />, title: 'Apply hard constraints', text: 'Drops models over your price or latency limit, or missing a capability.',
      live: evaluation ? `${evaluation.candidate_count} kept · ${filtered} excluded` : undefined },
    { id: 'strategies', icon: <span className="evf-quad" aria-hidden="true"><i /><i /><i /><i /></span>, title: 'Four strategies pick', text: 'Each policy chooses from the same remaining pool, so any difference comes from the policy.',
      live: evaluation ? `${picks} of ${evaluation.strategy_results.length} selected a model` : undefined },
    { id: 'compare', icon: <Trophy />, title: 'Compare the picks', text: 'Side by side with registry quality, price, latency and reliability.',
      live: evaluation ? 'Results below' : undefined },
  ];
  const done = !!evaluation;

  return (
    <Reveal as="section" className={done ? 'evf is-done' : 'evf'} ariaLabelledBy="evf-title">
      <header className="evf-head">
        <div>
          <p className="ev-kicker">Method</p>
          <h2 id="evf-title">How evaluation works</h2>
        </div>
        <p className="evf-note">Offline. Uses registry metadata only. No provider is called and no model is run.</p>
      </header>

      <ol className="evf-flow">
        {steps.map((s, i) => (
          <li key={s.id} className="evf-step" data-step={s.id} style={{ ['--i' as string]: i }}>
            <div className="evf-rail" aria-hidden="true">
              <span className="evf-node">
                {s.icon}
                <span className="evf-num">{done ? <Check /> : i + 1}</span>
              </span>
            </div>
            <div className="evf-body">
              <strong className="evf-title">{s.title}</strong>
              <p className="evf-text">{s.text}</p>
              {s.id === 'strategies' ? (
                <ul className="evf-fan" aria-label="Strategies compared">
                  {STRATEGIES.map(({ key, short, icon: Icon }) => (
                    <li key={key} data-strategy={key}><Icon aria-hidden="true" />{short}</li>
                  ))}
                </ul>
              ) : null}
              {s.live ? <span className="evf-live">{s.live}</span> : null}
            </div>
          </li>
        ))}
      </ol>
    </Reveal>
  );
}
