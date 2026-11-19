import { Trophy } from 'lucide-react';
import { Chip, Meter, Surface } from '../ui/ds';
import { formatPercent } from '../../utils/format';
import type { ModelScore } from '../../types';

/**
 * Top-of-page verdict for the Explanation page. Every figure is read from
 * the routing payload: the selected model's overall score, the gap to the
 * next-ranked candidate, and the leading candidates' overall scores.
 */
export function DecisionHero({ ranked, selectedId, selectedName, finalName, escalated, profile }: {
  ranked: ModelScore[]; selectedId: string; selectedName: string; finalName: string; escalated: boolean; profile: string;
}) {
  const top = ranked.slice(0, 5);
  const winner = ranked.find((s) => s.model_id === selectedId) ?? null;
  const runnerUp = ranked.find((s) => s.model_id !== selectedId) ?? null;
  const margin = winner && runnerUp ? winner.overall_score - runnerUp.overall_score : null;

  return (
    <Surface className="xp-hero" variant="glass" aria-labelledby="xp-hero-title">
      <div className="xp-hero-main">
        <p className="ds-kicker"><Trophy aria-hidden="true" /> Decision</p>
        <h2 id="xp-hero-title" className="xp-hero-title">{selectedName}</h2>
        <p className="xp-hero-sub">
          Selected for the {profile} profile
          {winner ? <> with an overall score of <strong>{formatPercent(winner.overall_score, 1)}</strong></> : null}
          {margin !== null && runnerUp
            ? <>, {margin >= 0 ? 'ahead of' : 'behind'} the next scored candidate by <strong>{formatPercent(Math.abs(margin), 1)}</strong> points.</>
            : <>. The router reported only this one scored candidate for the run.</>}
        </p>
        {escalated ? <Chip tone="warning">Escalated — final model: {finalName}</Chip> : <Chip tone="primary">No escalation</Chip>}
      </div>
      {top.length > 0 ? (
        <div className="xp-hero-board" role="group" aria-label="Leading candidates by overall score">
          {top.map((s) => (
            <Meter
              key={s.model_id}
              label={s.model_id === selectedId ? `${s.model_id} · selected` : s.model_id}
              value={s.overall_score}
              display={formatPercent(s.overall_score, 1)}
              tone={s.model_id === selectedId ? 'primary' : 'neutral'}
            />
          ))}
        </div>
      ) : null}
    </Surface>
  );
}
