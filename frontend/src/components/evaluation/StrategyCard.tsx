import { AlertCircle, ChevronDown, Equal } from 'lucide-react';
import type { OfflineStrategyResult } from '../../types';
import { formatDuration, formatPercent, formatUsd } from '../../utils/format';
import { STRATEGIES } from './strategies';

interface Props {
  row: OfflineStrategyResult;
  /** Model id AI Compass picked, to flag baselines that agree with it. */
  compassPick: string | null;
  index: number;
}

function Tile({ label, value, ratio }: { label: string; value: string | null; ratio?: number | null }) {
  const missing = value === null;
  return (
    <div className="ev-tile" data-missing={missing || undefined}>
      <span className="ev-tile-label">{label}</span>
      <strong className="ev-tile-value">{missing ? '—' : value}</strong>
      {ratio !== undefined ? (
        <span className="ev-tile-bar" aria-hidden="true">
          <i style={{ ['--w' as string]: ratio === null ? 0 : Math.max(0, Math.min(1, ratio)) }} />
        </span>
      ) : (
        <span className="ev-tile-note">{missing ? 'Not in registry' : ' '}</span>
      )}
    </div>
  );
}

/** One strategy's pick, shown with registry-derived figures only. Missing values stay missing. */
export function StrategyCard({ row, compassPick, index }: Props) {
  const meta = STRATEGIES.find((s) => s.key === row.strategy);
  const Icon = meta?.icon;
  const own = row.strategy === 'aicompass';
  const picked = row.status === 'selected';
  const agrees = !own && picked && compassPick !== null && row.selected_model_id === compassPick;

  const num = (v: number | null) => (v !== null && Number.isFinite(v) ? v : null);
  const quality = num(row.quality_score);
  const reliability = num(row.reliability_score);
  const latency = num(row.latency_seconds);
  const cost = num(row.estimated_cost_usd);

  return (
    <article className="ev-card" data-strategy={row.strategy} data-own={own || undefined} data-unavailable={!picked || undefined} style={{ ['--i' as string]: index }}>
      <header className="ev-card-head">
        <span className="ev-card-icon" aria-hidden="true">{Icon ? <Icon /> : null}</span>
        <div className="ev-card-title">
          <h3>{meta?.title ?? row.strategy}</h3>
          <p>{meta?.description}</p>
        </div>
      </header>

      {picked ? (
        <>
          <div className="ev-pick">
            <span className="ev-pick-label">Selected model</span>
            <strong className="ev-pick-name">{row.selected_model}</strong>
            {row.selected_model_id ? <code className="ev-pick-id" title={row.selected_model_id}>{row.provider ? `${row.provider} · ` : ''}{row.selected_model_id}</code> : null}
            <div className="ev-pick-tags">
              {own ? <span className="ev-tag ev-tag--accent">Uses your weights</span> : null}
              {agrees ? <span className="ev-tag"><Equal aria-hidden="true" />Same as AI Compass</span> : null}
              {!row.constraint_satisfied ? <span className="ev-tag ev-tag--warn">Constraints not met</span> : null}
            </div>
          </div>

          {row.routing_score !== null ? (
            <div className="ev-score">
              <div className="ev-score-top">
                <span>Routing score</span>
                <strong>{formatPercent(row.routing_score)}</strong>
              </div>
              <span className="ev-score-track" aria-hidden="true"><i style={{ ['--w' as string]: row.routing_score }} /></span>
            </div>
          ) : null}

          <div className="ev-tiles">
            <Tile label="Quality" value={quality === null ? null : formatPercent(quality)} ratio={quality} />
            <Tile label="Reliability" value={reliability === null ? null : formatPercent(reliability)} ratio={reliability} />
            <Tile label="Latency" value={latency === null ? null : formatDuration(latency * 1000)} />
            <Tile label="Input cost" value={cost === null ? null : formatUsd(cost, 6)} />
          </div>

          <details className="ev-more">
            <summary>Details <ChevronDown aria-hidden="true" /></summary>
            <div className="ev-more-body">
              <p className="ev-rationale">{row.selection_rationale}</p>
              <dl className="ev-facts">
                <div><dt>Risk indicator</dt><dd>{num(row.risk_score) === null ? '—' : formatPercent(row.risk_score as number)}</dd></div>
                <div><dt>Context window</dt><dd>{row.context_window ? `${row.context_window.toLocaleString()} tokens` : '—'}</dd></div>
                <div><dt>Constraints</dt><dd>{row.constraint_satisfied ? 'Satisfied' : 'Not satisfied'}</dd></div>
                {row.quality_source ? <div><dt>Quality source</dt><dd>{row.quality_source}</dd></div> : null}
                {row.cost_basis ? <div><dt>Cost basis</dt><dd>{row.cost_basis}</dd></div> : null}
              </dl>
              {row.missing_data.length > 0 ? (
                <div className="ev-missing">
                  <span>Missing from registry</span>
                  <ul>{row.missing_data.map((m) => <li key={m}>{m}</li>)}</ul>
                </div>
              ) : null}
            </div>
          </details>
        </>
      ) : (
        <div className="ev-empty-pick">
          <AlertCircle aria-hidden="true" />
          <strong>No model selected</strong>
          <p>{row.selection_rationale}</p>
        </div>
      )}
    </article>
  );
}
