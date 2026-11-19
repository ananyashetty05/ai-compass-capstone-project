/**
 * Stage timeline — how long each backend stage took, drawn in the order the backend reported them.
 * Durations are the server's own `duration_ms`; stages that did not run are listed without a bar. Bars are
 * laid end to end only to show proportion — the backend does not report start times, so this is not a
 * wall-clock trace.
 */
import { Reveal } from '../ui/Reveal';
import { formatDuration } from '../../utils/format';
import type { EngineResult } from '../../types';

export function StageTimeline({ engine }: { engine: EngineResult }) {
  const stages = engine.stages;
  const ran = stages.filter((s) => s.status === 'completed' || s.status === 'failed');
  const total = ran.reduce((a, s) => a + Math.max(0, s.duration_ms), 0);
  if (stages.length === 0) return null;
  let acc = 0;
  return (
    <Reveal as="section" className="stl" ariaLabelledBy="stl-title">
      <header className="stl-head">
        <div><p className="ds-kicker">Timing</p><h3 id="stl-title">Where the time went</h3></div>
        <p className="stl-note">{ran.length} of {stages.length} stages ran · {formatDuration(total)} in stages. Durations as reported by the backend, drawn in order.</p>
      </header>
      <ol className="stl-list">
        {stages.map((s) => {
          const ms = Math.max(0, s.duration_ms);
          const ranStage = s.status === 'completed' || s.status === 'failed';
          const left = total > 0 ? (acc / total) * 100 : 0;
          const width = total > 0 ? Math.max((ms / total) * 100, ranStage ? 0.8 : 0) : 0;
          if (ranStage) acc += ms;
          return (
            <li key={s.name} className="stl-row" data-status={s.status} title={s.detail}>
              <span className="stl-name">{s.label}</span>
              <span className="stl-track" aria-hidden="true">
                {ranStage ? <i className="stl-bar" style={{ left: `${left}%`, width: `${width}%` }} /> : null}
              </span>
              <span className="stl-ms">{ranStage ? formatDuration(ms) : s.status === 'skipped' ? 'Skipped' : 'Not run'}</span>
            </li>
          );
        })}
      </ol>
    </Reveal>
  );
}
