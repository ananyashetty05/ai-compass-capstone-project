import { BarChart3 } from 'lucide-react';
import { Meter } from '../ui/ds';
import { Reveal } from '../ui/Reveal';
import { formatDuration, formatInteger, formatUsd } from '../../utils/format';
import type { RoutingHistoryEntry } from '../../types';

const DAYS = 14;
const dayKey = (d: Date) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
const median = (v: number[]) => {
  if (v.length === 0) return null;
  const s = [...v].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

/**
 * Trends computed only from the routing-history endpoint (your own runs,
 * newest 50). Nothing is estimated or filled in: a day with no runs is an
 * empty bar, and a figure the history does not carry is left out.
 */
export function HistoryInsights({ entries }: { entries: RoutingHistoryEntry[] }) {
  if (entries.length === 0) return null;

  const today = new Date();
  const days = Array.from({ length: DAYS }, (_, i) => {
    const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() - (DAYS - 1 - i));
    return { date: d, key: dayKey(d), count: 0 };
  });
  const byKey = new Map(days.map((d) => [d.key, d]));
  entries.forEach((e) => {
    const t = new Date(e.timestamp);
    if (!Number.isNaN(t.getTime())) {
      const slot = byKey.get(dayKey(t));
      if (slot) slot.count += 1;
    }
  });
  const peak = Math.max(1, ...days.map((d) => d.count));
  const inWindow = days.reduce((sum, d) => sum + d.count, 0);

  const usage = new Map<string, number>();
  entries.forEach((e) => {
    const name = e.final_model_name || e.selected_model_name;
    if (name) usage.set(name, (usage.get(name) ?? 0) + 1);
  });
  const topModels = [...usage.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 5);
  const topMax = Math.max(1, ...topModels.map(([, n]) => n));

  const escalated = entries.filter((e) => e.escalated).length;
  const executed = entries.filter((e) => e.mode === 'execute');
  const routingMedian = median(entries.map((e) => e.routing_latency_ms).filter((v): v is number => typeof v === 'number'));
  const totalMedian = median(executed.map((e) => e.total_latency_ms).filter((v): v is number => typeof v === 'number'));
  const costs = executed.map((e) => e.estimated_cost).filter((v): v is number => typeof v === 'number');
  const totalCost = costs.length ? costs.reduce((a, b) => a + b, 0) : null;

  return (
    <div className="cx-grid cx-grid--2 hi-grid">
      <Reveal as="section" className="cx-card" ariaLabelledBy="hi-activity-title">
        <header className="cx-card-head">
          <div><p className="cx-kicker">Your routing history</p><h2 id="hi-activity-title">Activity, last {DAYS} days</h2></div>
          <BarChart3 aria-hidden="true" />
        </header>
        <div className="hi-bars" role="img" aria-label={`Routing runs per day over the last ${DAYS} days: ${days.map((d) => `${d.date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} ${d.count}`).join(', ')}`}>
          {days.map((d, i) => (
            <div key={d.key} className="hi-col" title={`${d.date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}: ${d.count} run${d.count === 1 ? '' : 's'}`}>
              <span className="hi-bar" data-empty={d.count === 0 || undefined} style={{ ['--h' as string]: `${(d.count / peak) * 100}%`, ['--i' as string]: i }} />
              <span className="hi-label" aria-hidden="true">{d.date.getDate()}</span>
            </div>
          ))}
        </div>
        <p className="cx-note">{formatInteger(inWindow)} of your latest {formatInteger(entries.length)} runs fall in this window. The history returns your 50 most recent runs.</p>
        <dl className="hi-stats">
          <div><dt>Escalated</dt><dd>{formatInteger(escalated)} of {formatInteger(entries.length)}</dd></div>
          <div><dt>Median routing time</dt><dd>{formatDuration(routingMedian)}</dd></div>
          {executed.length > 0 ? <div><dt>Runs executed</dt><dd>{formatInteger(executed.length)}</dd></div> : null}
          {executed.length > 0 ? <div><dt>Median end-to-end</dt><dd>{formatDuration(totalMedian)}</dd></div> : null}
          {totalCost !== null ? <div><dt>Spend on executed runs</dt><dd>{formatUsd(totalCost, 4)}</dd></div> : null}
        </dl>
      </Reveal>

      <Reveal as="section" className="cx-card" delay={1} ariaLabelledBy="hi-usage-title">
        <header className="cx-card-head">
          <div><p className="cx-kicker">Your routing history</p><h2 id="hi-usage-title">Most-selected models</h2></div>
        </header>
        <div className="hi-usage">
          {topModels.map(([name, n]) => (
            <Meter key={name} label={name} value={n / topMax} display={`${n} run${n === 1 ? '' : 's'}`} />
          ))}
        </div>
        <p className="cx-note">Counts the final model of each run, including any escalation target.</p>
      </Reveal>
    </div>
  );
}
