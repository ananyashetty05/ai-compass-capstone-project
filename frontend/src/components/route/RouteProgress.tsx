import { Check, PenLine, ScanSearch, Star, TriangleAlert } from 'lucide-react';

type StepState = 'pending' | 'active' | 'done' | 'error';

/**
 * Live progress for one routing request: the task is written, the router
 * analyses it, and a recommendation comes back. Driven entirely by real
 * page state, so it never claims progress that has not happened.
 */
export function RouteProgress({ hasTask, routing, hasResult, failed }: { hasTask: boolean; routing: boolean; hasResult: boolean; failed: boolean }) {
  const task: StepState = hasTask || routing || hasResult ? 'done' : 'active';
  const analysis: StepState = routing ? 'active' : failed ? 'error' : hasResult ? 'done' : 'pending';
  const rec: StepState = hasResult && !routing && !failed ? 'done' : 'pending';
  const steps = [
    { id: 'task', label: 'Task', icon: <PenLine />, state: task },
    { id: 'analysis', label: 'Analysis', icon: <ScanSearch />, state: analysis },
    { id: 'rec', label: 'Recommendation', icon: <Star />, state: rec },
  ];
  const current = steps.findIndex((s) => s.state === 'active' || s.state === 'error');
  const doneCount = steps.filter((s) => s.state === 'done').length;
  const fill = routing ? 0.75 : hasResult && !failed ? 1 : hasTask ? 0.25 : 0;

  return (
    <ol className="rq-progress" aria-label="Request progress" style={{ ['--fill' as string]: fill }}>
      {steps.map((s, i) => (
        <li key={s.id} className="rq-progress-step" data-state={s.state} aria-current={i === current ? 'step' : undefined}>
          <span className="rq-progress-dot" aria-hidden="true">
            {s.state === 'done' ? <Check /> : s.state === 'error' ? <TriangleAlert /> : s.icon}
          </span>
          <span className="rq-progress-label">{s.label}</span>
          <span className="sr-only">{s.state === 'done' ? ' (done)' : s.state === 'active' ? ' (in progress)' : s.state === 'error' ? ' (failed)' : ''}</span>
        </li>
      ))}
      <span className="sr-only" aria-live="polite">{doneCount === 3 ? 'Recommendation ready.' : routing ? 'Analysing your task.' : ''}</span>
    </ol>
  );
}
